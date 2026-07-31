"""
odds_panel.py
-------------
Painel Central do Dashboard: gráfico de linha da odd ao vivo +
régua visual do Gerenciador 3:1 (Stop Loss, Entrada, Parcial, Take Profit).

Agora integrado com o motor real de risco (modules/risk_manager.py):
- Abre a posição respeitando a janela de odds configurável
- Acompanha a odd e dispara parcial (50% em 1.5:1) e breakeven automático
- Mostra o status real da posição (aberta / parcial / stop / alvo)
"""

import streamlit as st
import plotly.graph_objects as go

from modules.mock_data import get_odds_series
from modules.risk_manager import PositionManager


def _get_manager(odd_min, odd_max, stop_loss_pct) -> PositionManager:
    """Mantém UMA instância do gerenciador viva no session_state, para que
    o estado da posição (parcial já feita, stop já em breakeven, etc.)
    persista entre reruns do Streamlit."""
    key = "risk_manager"
    if key not in st.session_state:
        st.session_state[key] = PositionManager(
            odd_min_janela=odd_min, odd_max_janela=odd_max, stop_loss_pct=stop_loss_pct
        )
    return st.session_state[key]


def render_odds_panel(odd_atual: float, auto_signal: dict | None = None):
    st.subheader("📈 Odd ao Vivo & Régua 3:1")

    with st.expander("⚙️ Configurar Gerenciador 3:1", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            direction = st.radio("Direção (entrada manual)", ["BACK (odd caindo)", "LAY (odd subindo)"], horizontal=True)
            direction = "BACK" if direction.startswith("BACK") else "LAY"
            odd_min = st.number_input("Janela mínima aceita", min_value=1.01, value=1.50, step=0.01)
        with col2:
            odd_max = st.number_input("Janela máxima aceita", min_value=1.01, value=2.20, step=0.01)
            stop_loss_pct = st.slider("Stop Loss (% da odd de entrada)", 5, 30, 15) / 100

        c1, c2 = st.columns(2)
        abrir = c1.button("🔓 Abrir posição na odd atual", use_container_width=True)
        resetar = c2.button("♻️ Resetar posição", use_container_width=True)

        auto_trade = st.checkbox(
            "🤖 Permitir entrada automática pelo sinal confirmado do Scanner WOM (Módulo A)",
            value=False,
            help="Só dispara quando não há posição aberta e o Scanner WOM confirmar sinal "
                 "(dominância sustentada + liquidez OK + Tape confirmado).",
        )

    manager = _get_manager(odd_min, odd_max, stop_loss_pct)

    if resetar:
        del st.session_state["risk_manager"]
        manager = _get_manager(odd_min, odd_max, stop_loss_pct)

    if abrir:
        manager.open_position(odd_entrada=odd_atual, direction=direction)

    # Gatilho automático: só dispara se não houver posição em andamento e o
    # Scanner WOM tiver confirmado sinal (dominância + liquidez + tape OK).
    posicao_livre = manager.status.value in (
        "aguardando_entrada", "rejeitada_fora_janela", "finalizada_stop", "finalizada_target",
    )
    if auto_trade and auto_signal and auto_signal.get("signal_final") and posicao_livre:
        auto_direction = auto_signal["dominant_side"]  # "BACK" ou "LAY", mesma convenção do gerenciador
        resultado = manager.open_position(odd_entrada=odd_atual, direction=auto_direction)
        if resultado["status"] == "aberta":
            st.toast(f"🤖 Entrada automática disparada pelo Scanner WOM: {auto_direction} @ {odd_atual}")

    # Atualiza a posição com a odd corrente (se já estiver aberta)
    state = manager.update(odd_atual)

    df = get_odds_series(start_odd=odd_atual)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["tempo"], y=df["odd"], mode="lines",
        line=dict(color="#3B82F6", width=2), name="Odd",
    ))

    if state["status"] != "aguardando_entrada" and state["entrada"] > 0:
        for y, label, color in [
            (state["entrada"], "Entrada", "#E5E7EB"),
            (state["stop_loss"], "Stop Loss" if not state["parcial_executada"] else "Stop (Breakeven)", "#EF4444"),
            (state["parcial_preco"], "Parcial (1.5:1)", "#F59E0B"),
            (state["take_profit"], "Take Profit (3:1)", "#22C55E"),
        ]:
            fig.add_hline(y=y, line_dash="dash", line_color=color,
                          annotation_text=f"{label}: {y}", annotation_position="right")

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=380,
        margin=dict(l=10, r=10, t=20, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---------- Status da posição ----------
    status_map = {
        "aguardando_entrada": ("⏳ Aguardando abertura de posição", "info"),
        "rejeitada_fora_janela": ("❌ Entrada rejeitada — odd fora da janela configurada", "error"),
        "aberta": ("🟢 Posição aberta", "success"),
        "parcial_realizada": ("🟡 Parcial de 50% realizada — stop em breakeven", "warning"),
        "finalizada_stop": ("🔴 Posição encerrada no Stop / Breakeven", "error"),
        "finalizada_target": ("🏁 Take Profit (3:1) atingido — posição encerrada", "success"),
    }
    msg, kind = status_map[state["status"]]
    getattr(st, kind)(msg)

    if state["entrada"] > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Entrada", state["entrada"])
        c2.metric("Stop Loss", state["stop_loss"])
        c3.metric("Parcial (50% @ 1.5:1)", state["parcial_preco"])
        c4.metric("Take Profit (3:1)", state["take_profit"])
        st.caption(f"Fração da posição ainda aberta: {int(state['fracao_aberta']*100)}%")
