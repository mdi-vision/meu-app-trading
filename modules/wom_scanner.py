"""
wom_scanner.py
--------------
Módulo A: "Scanner Peso do Dinheiro" (Scalping In-Play).

Regras implementadas:
1. Sinal bruto: um lado (BACK ou LAY) deve concentrar >= wom_threshold% do
   volume por >= min_duration_seconds SEGUNDOS CONTÍNUOS (não apenas em um
   instante isolado). Isso é o filtro anti-spoofing: ordens que aparecem e
   somem rápido (spoofing) não sustentam a dominância pelo tempo mínimo e
   não geram sinal.
2. Confirmação obrigatória via Tape (Time & Trades): o sinal bruto só vira
   sinal CONFIRMADO se o volume agressivo executado recentemente também
   estiver majoritariamente no mesmo lado.
3. Filtro de liquidez adaptativo: cada categoria de mercado tem um piso de
   liquidez mínima diferente (ex: Gols/Match Odds exigem mais volume total
   que Cantos/Cartões, que naturalmente têm livros mais finos).

Este módulo é independente de UI — pode ser plugado tanto no Streamlit
mockado quanto, depois, em um stream real da API da exchange.
"""

from collections import deque
from datetime import timedelta


DEFAULT_LIQUIDITY_MIN = {
    "Gols": 500,
    "Match Odds": 500,
    "Cantos": 150,
    "Cartões": 150,
}


class WOMScanner:
    def __init__(
        self,
        wom_threshold: float = 65.0,
        min_duration_seconds: float = 3.0,
        liquidity_thresholds: dict | None = None,
        rolling_window_seconds: float = 30.0,
    ):
        self.wom_threshold = wom_threshold
        self.min_duration_seconds = min_duration_seconds
        self.liquidity_thresholds = liquidity_thresholds or DEFAULT_LIQUIDITY_MIN
        self.rolling_window_seconds = rolling_window_seconds
        self._history = deque()  # cada item: {"t": datetime, "side": str, "pct": float}

    def _liquidity_floor(self, market: str) -> float:
        return self.liquidity_thresholds.get(market, 200)

    def _dominant_streak_duration(self, timestamp, dominant_side: str) -> float:
        """Quanto tempo (em segundos) o lado dominante atual vem se mantendo
        continuamente acima do limiar, olhando a amostra mais recente para trás."""
        streak_start = None
        for entry in reversed(self._history):
            if entry["side"] == dominant_side and entry["pct"] >= self.wom_threshold:
                streak_start = entry["t"]
            else:
                break
        if streak_start is None:
            return 0.0
        return (timestamp - streak_start).total_seconds()

    def update(self, timestamp, wom_back_pct: float, wom_lay_pct: float,
               total_liquidity: float, market: str) -> dict:
        """Alimenta o scanner com uma nova leitura do livro de ofertas e
        retorna o status atual (sem ainda considerar a confirmação do Tape)."""
        dominant_side = "BACK" if wom_back_pct >= wom_lay_pct else "LAY"
        dominant_pct = max(wom_back_pct, wom_lay_pct)

        self._history.append({"t": timestamp, "side": dominant_side, "pct": dominant_pct})

        cutoff = timestamp - timedelta(seconds=self.rolling_window_seconds)
        while self._history and self._history[0]["t"] < cutoff:
            self._history.popleft()

        duration = self._dominant_streak_duration(timestamp, dominant_side)
        liquidity_ok = total_liquidity >= self._liquidity_floor(market)
        raw_signal = dominant_pct >= self.wom_threshold and duration >= self.min_duration_seconds

        return {
            "dominant_side": dominant_side,
            "dominant_pct": dominant_pct,
            "duration_seconds": round(duration, 1),
            "duration_target": self.min_duration_seconds,
            "liquidity_ok": liquidity_ok,
            "liquidity_floor": self._liquidity_floor(market),
            "raw_signal": raw_signal,
        }

    @staticmethod
    def confirm_with_tape(tape_df, dominant_side: str, min_majority: float = 0.55) -> dict:
        """Confirma o sinal bruto checando se o volume agressivo (Time & Trades)
        recente também está majoritariamente no mesmo lado do WOM."""
        if tape_df is None or tape_df.empty:
            return {"confirmed": False, "tape_side_pct": 0.0}

        vol_back = tape_df.loc[tape_df["lado"] == "BACK", "volume"].sum()
        vol_lay = tape_df.loc[tape_df["lado"] == "LAY", "volume"].sum()
        total = vol_back + vol_lay
        if total == 0:
            return {"confirmed": False, "tape_side_pct": 0.0}

        pct_no_lado = (vol_back if dominant_side == "BACK" else vol_lay) / total
        return {"confirmed": pct_no_lado >= min_majority, "tape_side_pct": round(pct_no_lado * 100, 1)}

    def full_signal(self, timestamp, wom_back_pct, wom_lay_pct, total_liquidity, market, tape_df) -> dict:
        """Roda a leitura completa: sinal bruto + liquidez + confirmação do Tape."""
        status = self.update(timestamp, wom_back_pct, wom_lay_pct, total_liquidity, market)
        tape_check = self.confirm_with_tape(tape_df, status["dominant_side"])

        status["tape_confirmed"] = tape_check["confirmed"]
        status["tape_side_pct"] = tape_check["tape_side_pct"]
        status["signal_final"] = (
            status["raw_signal"] and status["liquidity_ok"] and tape_check["confirmed"]
        )
        return status
