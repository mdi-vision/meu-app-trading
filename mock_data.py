"""
mock_data.py
------------
Gera dados fake (mock) para que o Dashboard funcione visualmente
antes de conectar as APIs reais de estatísticas e da bolsa (exchange).

Quando for integrar de verdade:
- Troque `get_player_history()` / `get_team_history()` por chamadas
  à sua fonte de estatísticas (API de dados esportivos).
- Troque `get_order_book()` / `get_tape()` pela API da exchange
  (ex: Betfair Exchange API-NG).
"""

import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


MARKETS = ["Gols", "Cantos", "Cartões", "Match Odds"]
PLAYER_PROP_TYPES = ["Chutes a Gol", "Finalizações", "Faltas Cometidas", "Cartões"]


def get_team_history(team: str, market: str, n_games: int = 10) -> pd.DataFrame:
    """Histórico simulado do time em um mercado (últimos N jogos)."""
    base = {"Gols": 1.4, "Cantos": 5.2, "Cartões": 2.1, "Match Odds": 1.0}.get(market, 1.5)
    values = np.clip(np.random.normal(base, base * 0.4, n_games), 0, None)
    games = [f"J{n_games - i}" for i in range(n_games)]
    return pd.DataFrame({"jogo": games, "valor": np.round(values, 1)})


def get_player_history(player: str, prop_type: str, n_games: int = 10) -> pd.DataFrame:
    """Histórico simulado de um jogador em um player prop."""
    base = {
        "Chutes a Gol": 1.8,
        "Finalizações": 3.2,
        "Faltas Cometidas": 1.5,
        "Cartões": 0.3,
    }.get(prop_type, 1.5)
    values = np.clip(np.random.normal(base, base * 0.5, n_games), 0, None)
    games = [f"J{n_games - i}" for i in range(n_games)]
    return pd.DataFrame({"jogo": games, "valor": np.round(values, 1)})


def calc_ev(media_historica: float, linha_mercado: float, odd_mercado: float) -> dict:
    """
    Calcula uma probabilidade estatística simples (aproximada) de Over
    e compara com a odd oferecida para gerar o indicador EV+.
    """
    # Probabilidade aproximada via distribuição de Poisson para o "Over"
    from math import exp, factorial

    lam = max(media_historica, 0.05)
    linha_int = int(linha_mercado)
    p_under_or_equal = sum((lam ** k) * exp(-lam) / factorial(k) for k in range(0, linha_int + 1))
    p_over = max(0.0, 1 - p_under_or_equal)

    prob_implicita = 1 / odd_mercado if odd_mercado > 0 else 0
    ev_percent = (p_over - prob_implicita) * 100

    return {
        "prob_estatistica": round(p_over * 100, 1),
        "prob_implicita": round(prob_implicita * 100, 1),
        "ev_percent": round(ev_percent, 1),
        "is_value": ev_percent > 0,
    }


def get_odds_series(n_points: int = 60, start_odd: float = 2.0) -> pd.DataFrame:
    """Série temporal simulada da odd (para o gráfico central de linha/candle)."""
    now = datetime.now()
    times = [now - timedelta(seconds=(n_points - i) * 5) for i in range(n_points)]
    walk = np.cumsum(np.random.normal(0, 0.015, n_points))
    odds = np.clip(start_odd + walk, 1.05, 20)
    return pd.DataFrame({"tempo": times, "odd": np.round(odds, 2)})


def get_order_book(mid_odd: float = 2.0) -> dict:
    """Livro de ofertas simulado (Back vs Lay) para um mercado."""
    back = sorted(
        [round(mid_odd - i * 0.02, 2) for i in range(1, 6)], reverse=True
    )
    lay = sorted([round(mid_odd + i * 0.02, 2) for i in range(1, 6)])

    back_vol = [random.randint(50, 2000) for _ in back]
    lay_vol = [random.randint(50, 2000) for _ in lay]

    total_back = sum(back_vol)
    total_lay = sum(lay_vol)
    total = total_back + total_lay if (total_back + total_lay) > 0 else 1

    wom_back_pct = round((total_back / total) * 100, 1)
    wom_lay_pct = round(100 - wom_back_pct, 1)

    return {
        "back_odds": back,
        "back_vol": back_vol,
        "lay_odds": lay,
        "lay_vol": lay_vol,
        "wom_back_pct": wom_back_pct,
        "wom_lay_pct": wom_lay_pct,
        "total_liquidity": total_back + total_lay,
    }


def get_tape(n: int = 8) -> pd.DataFrame:
    """Simula o Time & Trades (negócios agressivos executados)."""
    now = datetime.now()
    rows = []
    for i in range(n):
        rows.append({
            "hora": (now - timedelta(seconds=i * 3)).strftime("%H:%M:%S"),
            "lado": random.choice(["BACK", "LAY"]),
            "odd": round(random.uniform(1.8, 2.2), 2),
            "volume": random.randint(20, 800),
        })
    return pd.DataFrame(rows)
