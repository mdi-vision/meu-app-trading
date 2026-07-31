"""
sportmonks_client.py
---------------------
Cliente para a API real da Sportmonks (v3, football), usado para alimentar
o Módulo Estatístico com histórico real de time/jogador no lugar dos dados
mockados em modules/mock_data.py.

IMPORTANTE — escopo desta integração:
A Sportmonks fornece dados de partidas, estatísticas e odds de casas de
apostas. Ela NÃO fornece livro de ofertas de bolsa (Back/Lay) — então o
Módulo A (Scanner WOM) continua precisando de uma exchange separada
(ex: Betfair) para o order flow em tempo real.

Endpoints usados (confirmados na documentação oficial em
docs.sportmonks.com/v3, lida em 31/07/2026):
- GET /fixtures/between/{inicio}/{fim}/{team_id}   -> jogos do time no período
- GET /fixtures/{id}?include=statistics.type        -> estatísticas do time na partida
- GET /fixtures/{id}?include=lineups.details.type   -> estatísticas por jogador na partida

IDs de tipo de estatística usados (catálogo oficial "Statistics Types"):
    52  = Gols
    34  = Cantos
    193 = Cartões (total)
    86  = Chutes a Gol (Shots On Target)
    42  = Finalizações (Shots Total)
    56  = Faltas Cometidas
"""

from datetime import datetime, timedelta

import requests
import pandas as pd
import streamlit as st

BASE_URL = "https://api.sportmonks.com/v3/football"

TEAM_MARKET_TYPE_ID = {
    "Gols": 52,
    "Cantos": 34,
    "Cartões": 193,
}

PLAYER_PROP_TYPE_ID = {
    "Chutes a Gol": 86,
    "Finalizações": 42,
    "Faltas Cometidas": 56,
    "Cartões": 193,
}


class SportmonksError(Exception):
    pass


class SportmonksClient:
    def __init__(self, api_token: str):
        if not api_token:
            raise SportmonksError("Token da Sportmonks não informado.")
        self.api_token = api_token

    def _get(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params["api_token"] = self.api_token
        try:
            resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
        except requests.RequestException as exc:
            raise SportmonksError(f"Falha de conexão com a Sportmonks: {exc}") from exc

        if resp.status_code == 401:
            raise SportmonksError("Token inválido ou sem permissão (401).")
        if resp.status_code == 404:
            raise SportmonksError("Recurso não encontrado (404) — confira o ID.")
        if resp.status_code == 429:
            raise SportmonksError("Limite de requisições da Sportmonks atingido (429).")
        if not resp.ok:
            raise SportmonksError(f"Erro da Sportmonks: HTTP {resp.status_code}")

        return resp.json()

    def get_team_recent_fixtures(self, team_id: int, n_games: int = 10, lookback_days: int = 240) -> list[dict]:
        """Busca as últimas N partidas JÁ ENCERRADAS do time num período retroativo."""
        end = datetime.utcnow().date()
        start = end - timedelta(days=lookback_days)
        data = self._get(f"/fixtures/between/{start}/{end}/{team_id}")
        fixtures = data.get("data", [])
        encerradas = [f for f in fixtures if f.get("result_info")]
        encerradas.sort(key=lambda f: f.get("starting_at", ""), reverse=True)
        return encerradas[:n_games]

    def get_fixture_team_stat_value(self, fixture_id: int, team_id: int, type_id: int) -> float | None:
        """Valor de uma estatística de TIME numa partida específica."""
        data = self._get(
            f"/fixtures/{fixture_id}",
            params={"include": "statistics.type", "filters": f"fixtureStatisticTypes:{type_id}"},
        )
        stats = data.get("data", {}).get("statistics", []) or []
        for s in stats:
            if s.get("participant_id") == team_id and s.get("type_id") == type_id:
                return s.get("data", {}).get("value")
        return None

    def get_fixture_player_stat_value(self, fixture_id: int, player_id: int, type_id: int) -> float | None:
        """Valor de uma estatística de JOGADOR numa partida específica."""
        data = self._get(
            f"/fixtures/{fixture_id}",
            params={"include": "lineups.details.type", "filters": f"lineupDetailTypes:{type_id}"},
        )
        lineups = data.get("data", {}).get("lineups", []) or []
        for player in lineups:
            if player.get("player_id") != player_id:
                continue
            for detail in player.get("details", []) or []:
                if detail.get("type_id") == type_id:
                    return detail.get("data", {}).get("value")
        return None

    def get_team_history(self, team_id: int, market: str, n_games: int = 10) -> pd.DataFrame:
        """Equivalente real de mock_data.get_team_history: histórico dos
        últimos N jogos do time para um mercado (Gols/Cantos/Cartões)."""
        type_id = TEAM_MARKET_TYPE_ID.get(market)
        if type_id is None:
            raise SportmonksError(
                f"Mercado '{market}' não tem histórico real mapeado ainda "
                f"(Match Odds depende de resultado, não de contagem por jogo)."
            )
        fixtures = self.get_team_recent_fixtures(team_id, n_games)
        rows = []
        for fx in reversed(fixtures):  # mais antigo -> mais recente, como no mock
            valor = self.get_fixture_team_stat_value(fx["id"], team_id, type_id)
            rows.append({"jogo": fx.get("name", str(fx["id"])), "valor": valor if valor is not None else 0})
        return pd.DataFrame(rows)

    def get_player_history(self, player_id: int, team_id: int, prop_type: str, n_games: int = 10) -> pd.DataFrame:
        """Equivalente real de mock_data.get_player_history."""
        type_id = PLAYER_PROP_TYPE_ID.get(prop_type)
        if type_id is None:
            raise SportmonksError(f"Player prop '{prop_type}' não mapeado.")
        fixtures = self.get_team_recent_fixtures(team_id, n_games)
        rows = []
        for fx in reversed(fixtures):
            valor = self.get_fixture_player_stat_value(fx["id"], player_id, type_id)
            rows.append({"jogo": fx.get("name", str(fx["id"])), "valor": valor if valor is not None else 0})
        return pd.DataFrame(rows)


@st.cache_data(ttl=300, show_spinner=False)
def cached_team_history(api_token: str, team_id: int, market: str, n_games: int) -> pd.DataFrame:
    client = SportmonksClient(api_token)
    return client.get_team_history(team_id, market, n_games)


@st.cache_data(ttl=300, show_spinner=False)
def cached_player_history(api_token: str, player_id: int, team_id: int, prop_type: str, n_games: int) -> pd.DataFrame:
    client = SportmonksClient(api_token)
    return client.get_player_history(player_id, team_id, prop_type, n_games)
