"""
app.py
------
Estrutura base do Dashboard — Inteligência e Execução Esportiva.

Como rodar:
    pip install -r requirements.txt
    streamlit run app.py

Estrutura:
    - Painel Superior: filtros (Jogo, Time, Jogador, Mercado)
    - Painel Esquerdo: Módulo Estatístico (histórico/props estilo PropsBR)
    - Painel Central: Odd ao vivo + régua do Gerenciador 3:1
    - Painel Direito: Barômetro WOM + Livro de Ofertas + Time&Trades + Execução

Este arquivo é a "casca" (estrutura visual). A lógica de sinal do
Scanner WOM (Módulo A) e a automação de execução do Gerenciador 3:1
(Módulo B) entram como próximo passo, plugadas nos módulos já
preparados em modules/wom_panel.py e modules/odds_panel.py.
"""

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

from modules.mock_data import MARKETS
from modules.stats_panel import render_stats_panel
from modules.odds_panel import render_odds_panel
from modules.wom_panel import render_wom_panel


st.set_page_config(
    page_title="Sports Intelligence & Execution",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- Dark mode / estilo customizado ----------
st.markdown(
    """
    <style>
        .stApp { background-color: #0E1117; color: #E5E7EB; }
        section[data-testid="stSidebar"] { background-color: #12151C; }
        div[data-testid="stMetric"] {
            background-color: #161A23;
            border: 1px solid #262B36;
            border-radius: 10px;
            padding: 10px;
        }
        .block-container { padding-top: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Painel Superior: Filtros ----------
st.title("⚽ Sports Intelligence & Execution Dashboard")

if HAS_AUTOREFRESH:
    st_autorefresh(interval=1000, key="live_tick")
else:
    st.button("🔄 Atualizar (tick manual — instale streamlit-autorefresh para tempo real)")

f1, f2, f3, f4 = st.columns(4)
with f1:
    jogo = st.selectbox("Jogo", ["Flamengo x Palmeiras", "Real Madrid x Barcelona", "Man City x Arsenal"])
with f2:
    team, opponent = [x.strip() for x in jogo.split("x")]
    time_selecionado = st.selectbox("Time", [team, opponent])
with f3:
    jogador = st.selectbox("Jogador", ["Jogador A", "Jogador B", "Jogador C"])
with f4:
    mercado = st.selectbox("Mercado", MARKETS)

st.divider()

# ---------- Painéis principais ----------
col_left, col_center, col_right = st.columns([1.1, 1.4, 1.1])

with col_left:
    render_stats_panel(team=time_selecionado, player=jogador, market=mercado)

odd_atual = 1.95  # placeholder — viria da API da exchange em tempo real

with col_right:
    wom_signal = render_wom_panel(odd_atual=odd_atual, market=mercado, wom_threshold=65)

with col_center:
    render_odds_panel(odd_atual=odd_atual, auto_signal=wom_signal)
