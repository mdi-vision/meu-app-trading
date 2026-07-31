"""
stats_panel.py
--------------
Painel Esquerdo do Dashboard: Módulo Estatístico (estilo PropsBR).
Histórico de últimos 5/10/20 jogos + linha de mercado + indicador EV+.

Fonte de dados real: Sportmonks (via modules/sportmonks_client.py).
O token é lido automaticamente de .streamlit/secrets.toml quando presente.
"""

import streamlit as st
import plotly.graph_objects as go

from modules.mock_data import (
    get_team_history,
    get_player_history,
    calc_ev,
    PLAYER_PROP_TYPES,
)
from modules.sportmonks_client import (
    cached_team_history,
    cached_player_history,
    TEAM_MARKET_TYPE_ID,
    SportmonksError,
)


def _get_saved_token() -> str:
    try:
        # Busca tanto por SPORTMONKS_API_KEY quanto por SPORTMONKS_API_TOKEN
        token = st.secrets.get("SPORTMONKS_API_KEY", "") or st.secrets.get("SPORTMONKS_API_TOKEN", "")
        return token
    except Exception:
        return ""


def _bar_chart(df, linha_mercado: float, titulo: str):
    media = df["valor"].mean() if not df.empty else 0.0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["jogo"], y=df["valor"],
        marker_color="#3B82F6",
        name="Histórico",
    ))
    fig.add_hline(
        y=linha_mercado, line_dash="dash", line_color="#F59E0B",
        annotation_text=f"Linha mercado: {linha_mercado}",
        annotation_position="top left",
    )
    fig.add_hline(
        y=media, line_dash="dot", line_color="#22C55E",
        annotation_text=f"Média real: {media:.2f}",
        annotation_position="bottom left",
    )
    fig.update_layout(
        title=titulo,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=260,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig, media


def render_stats_panel(team: str, player: str, market: str):
    st.subheader("📊 Módulo Estatístico")

    token_salvo = _get_saved_token()
    fonte_default = "Sportmonks (real)" if token_salvo else "Mock (teste)"
    fonte = st.radio(
        "Fonte de dados", ["Mock (teste)", "Sportmonks (real)"],
        index=0 if fonte_default == "Mock (teste)" else 1,
        horizontal=True,
    )
    usar_real = fonte.startswith("Sportmonks")

    sportmonks_token = token_salvo
    team_id = 53
    player_id = 275

    if usar_real:
        with st.expander("🔑 Configuração Sportmonks", expanded=not bool(token_salvo)):
            sportmonks_token = st.text_input(
                "API Token Sportmonks", value=token_salvo, type="password",
                help="Carregado automaticamente de .streamlit/secrets.toml quando presente.",
            )
            c1, c2 = st.columns(2)
            team_id = c1.number_input("ID do Time (Sportmonks)", min_value=0, value=53, step=1)
            player_id = c2.number_input("ID do Jogador (Sportmonks)", min_value=0, value=275, step=1)
            st.caption("IDs de exemplo pré-preenchidos (Celtic / Joe Hart). Troque pelos seus.")

    n_games = st.select_slider("Janela de jogos", options=[5, 10, 20], value=10)

    tab_time, tab_jogador = st.tabs(["Time Props", "Player Props"])

    with tab_time:
        if usar_real and market not in TEAM_MARKET_TYPE_ID:
            st.info(
                f"O mercado '{market}' ainda não tem histórico real mapeado "
                f"(Match Odds depende do resultado, não de uma contagem por jogo). "
                f"Usando dados mockados neste mercado."
            )

        linha_time = st.number_input(
            f"Linha de mercado ({market})", min_value=0.0, value=1.5, step=0.5, key="linha_time"
        )
        odd_time = st.number_input("Odd oferecida (Over)", min_value=1.01, value=1.90, step=0.01, key="odd_time")

        df_time = _load_team_df(usar_real, sportmonks_token, team_id, team, market, n_games)
        fig, media = _bar_chart(df_time, linha_time, f"{team} — {market} (últimos {n_games} jogos)")
        st.plotly_chart(fig, use_container_width=True)

        ev = calc_ev(media, linha_time, odd_time)
        _render_ev_badge(ev)

    with tab_jogador:
        prop_type = st.selectbox("Tipo de Player Prop", PLAYER_PROP_TYPES, key="prop_type")
        linha_jog = st.number_input(
            f"Linha de mercado ({prop_type})", min_value=0.0, value=1.5, step=0.5, key="linha_jogador"
        )
        odd_jog = st.number_input("Odd oferecida (Over)", min_value=1.01, value=1.90, step=0.01, key="odd_jogador")

        df_jog = _load_player_df(usar_real, sportmonks_token, player_id, team_id, player, prop_type, n_games)
        fig2, media2 = _bar_chart(df_jog, linha_jog, f"{player} — {prop_type} (últimos {n_games} jogos)")
        st.plotly_chart(fig2, use_container_width=True)

        ev2 = calc_ev(media2, linha_jog, odd_jog)
        _render_ev_badge(ev2)


def _load_team_df(usar_real, token, team_id, team_name, market, n_games):
    if usar_real and market in TEAM_MARKET_TYPE_ID and token and team_id:
        try:
            return cached_team_history(token, int(team_id), market, n_games)
        except SportmonksError as e:
            st.error(f"Erro Sportmonks: {e} — usando dados mockados como fallback.")
    return get_team_history(team_name, market, n_games)


def _load_player_df(usar_real, token, player_id, team_id, player_name, prop_type, n_games):
    if usar_real and token and player_id and team_id:
        try:
            return cached_player_history(token, int(player_id), int(team_id), prop_type, n_games)
        except SportmonksError as e:
            st.error(f"Erro Sportmonks: {e} — usando dados mockados como fallback.")
    return get_player_history(player_name, prop_type, n_games)


def _render_ev_badge(ev: dict):
    if ev["is_value"]:
        st.success(
            f"✅ EV+ Detectado: {ev['ev_percent']}% "
            f"(Prob. estatística {ev['prob_estatistica']}% vs Prob. implícita {ev['prob_implicita']}%)"
        )
    else:
        st.info(
            f"Sem valor estatístico no momento "
            f"(Prob. estatística {ev['prob_estatistica']}% vs Prob. implícita {ev['prob_implicita']}%)"
        )
