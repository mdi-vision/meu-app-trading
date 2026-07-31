"""
wom_panel.py
------------
Painel Direito do Dashboard: Barômetro do Peso do Dinheiro (WOM),
Livro de Ofertas simplificado, Time & Trades e botões de execução rápida.

Agora integrado com o motor real do Scanner WOM (modules/wom_scanner.py):
- Sinal bruto (dominância >= limiar por N segundos contínuos)
- Filtro de liquidez adaptativo por mercado
- Confirmação obrigatória via Tape (Time & Trades)

IMPORTANTE:
Os botões de execução aqui estão desativados por padrão (modo demonstração).
Para operar de verdade, é necessário plugar a API real da exchange e manter
todas as travas de confirmação ativas antes de liberar qualquer envio de
ordem real.
"""

from datetime import datetime

import streamlit as st
import plotly.graph_objects as go

from modules.mock_data import get_order_book, get_tape
from modules.wom_scanner import WOMScanner


def _get_scanner(wom_threshold: int, min_duration: float) -> WOMScanner:
    """Mantém UMA instância do scanner viva no session_state, para que o
    histórico de dominância (usado no filtro anti-spoofing) não se perca
    a cada rerun do Streamlit."""
    key = "wom_scanner"
    if key not in st.session_state:
        st.session_state[key] = WOMScanner(
            wom_threshold=wom_threshold, min_duration_seconds=min_duration
        )
    scanner = st.session_state[key]
    scanner.wom_threshold = wom_threshold
    scanner.min_duration_seconds = min_duration
    return scanner


def render_wom_panel(odd_atual: float, market: str, wom_threshold: int = 65,
                      min_duration_seconds: float = 3.0):
    st.subheader("💰 Peso do Dinheiro (WOM) — Scanner Ativo")

    c_cfg1, c_cfg2 = st.columns(2)
    with c_cfg1:
        wom_threshold = st.slider("Limiar WOM (%)", 50, 90, wom_threshold)
    with c_cfg2:
        min_duration_seconds = st.slider("Duração mínima (anti-spoofing, s)", 1, 10, int(min_duration_seconds))

    scanner = _get_scanner(wom_threshold, min_duration_seconds)

    book = get_order_book(mid_odd=odd_atual)
    tape = get_tape()

    signal = scanner.full_signal(
        timestamp=datetime.now(),
        wom_back_pct=book["wom_back_pct"],
        wom_lay_pct=book["wom_lay_pct"],
        total_liquidity=book["total_liquidity"],
        market=market,
        tape_df=tape,
    )

    fig = go.Figure(go.Bar(
        x=[book["wom_back_pct"]], y=["WOM"], orientation="h",
        marker_color="#22C55E", name="Back",
    ))
    fig.add_trace(go.Bar(
        x=[book["wom_lay_pct"]], y=["WOM"], orientation="h",
        marker_color="#EF4444", name="Lay",
    ))
    fig.update_layout(
        barmode="stack", template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=100, margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False, xaxis=dict(range=[0, 100], showticklabels=False),
    )
    st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns(2)
    col_a.metric("Back", f"{book['wom_back_pct']}%")
    col_b.metric("Lay", f"{book['wom_lay_pct']}%")

    st.markdown("**🔎 Status do Scanner**")

    progresso = min(signal["duration_seconds"] / signal["duration_target"], 1.0) if signal["duration_target"] else 0
    st.progress(progresso, text=(
        f"Dominância {signal['dominant_side']} em {signal['dominant_pct']}% "
        f"há {signal['duration_seconds']}s / {signal['duration_target']}s necessários"
    ))

    liq_icon = "✅" if signal["liquidity_ok"] else "❌"
    tape_icon = "✅" if signal["tape_confirmed"] else "❌"
    st.write(f"{liq_icon} Liquidez: {book['total_liquidity']} (mínimo p/ {market}: {signal['liquidity_floor']})")
    st.write(f"{tape_icon} Confirmação Tape: {signal['tape_side_pct']}% do volume agressivo no mesmo lado")

    if signal["signal_final"]:
        st.error(
            f"🚨 SINAL CONFIRMADO: {signal['dominant_side']} "
            f"({signal['dominant_pct']}%, {signal['duration_seconds']}s, "
            f"liquidez e tape OK) — entrada de scalping 1-3 ticks"
        )
    elif signal["raw_signal"] and not signal["liquidity_ok"]:
        st.warning("⚠️ Dominância sustentada, mas liquidez insuficiente para este mercado — sinal descartado.")
    elif signal["raw_signal"] and not signal["tape_confirmed"]:
        st.warning("⚠️ Dominância sustentada, mas Tape não confirma o lado — possível spoofing, sinal descartado.")
    else:
        st.caption("Sem sinal no momento. Aguardando dominância sustentada.")

    st.divider()
    st.markdown("**📖 Livro de Ofertas**")
    col_back, col_lay = st.columns(2)
    with col_back:
        st.markdown("🟢 Back")
        for odd, vol in zip(book["back_odds"], book["back_vol"]):
            st.write(f"{odd} — {vol}")
    with col_lay:
        st.markdown("🔴 Lay")
        for odd, vol in zip(book["lay_odds"], book["lay_vol"]):
            st.write(f"{odd} — {vol}")

    st.divider()
    st.markdown("**⏱️ Time & Trades**")
    st.dataframe(tape, use_container_width=True, hide_index=True, height=180)

    st.divider()
    st.markdown("**🚀 Execução Rápida** _(modo demonstração — desativado)_")
    e1, e2 = st.columns(2)
    e1.button(
        "BACK Rápido",
        disabled=not (signal["signal_final"] and signal["dominant_side"] == "BACK"),
        use_container_width=True,
    )
    e2.button(
        "LAY Rápido",
        disabled=not (signal["signal_final"] and signal["dominant_side"] == "LAY"),
        use_container_width=True,
    )
    st.caption(
        "Os botões só ficam habilitados quando há sinal confirmado nesse lado. "
        "Mesmo assim, execução real exige a API da exchange conectada — hoje é apenas demonstração visual."
    )

    return signal
