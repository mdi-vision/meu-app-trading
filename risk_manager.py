"""
risk_manager.py
---------------
Módulo B: "Gerenciador 3:1" (Swing Trade / Tendência).

Regras implementadas (independentes de UI):
1. Entrada só é aceita dentro da janela de odds configurável (padrão 1.50–2.20).
2. Stop Loss dinâmico: calculado como uma distância da odd de entrada
   (proporcional à volatilidade/suporte informado — aqui simplificado como
   um percentual configurável da odd de entrada, mas a função é isolada e
   pode ser trocada por um cálculo mais sofisticado depois).
3. Take Profit = 3x a distância do Stop Loss (Take Profit e Stop sempre em
   lados opostos da entrada).
4. Ao atingir a marca de 1.5:1 (1.5x a distância do risco), realiza 50% da
   posição automaticamente (parcial).
5. Depois da parcial, o Stop é movido para o preço de entrada (breakeven) —
   trailing/breakeven automático, protegendo o restante da posição.

Convenção usada aqui: pode operar tanto para uma odd que se espera SUBIR
(direção "LAY"/odd subindo = favorável) quanto DESCER ("BACK"/odd caindo
= favorável). Isso é definido pelo parâmetro `direction`.
"""

from dataclasses import dataclass, field
from enum import Enum


class PositionStatus(Enum):
    AGUARDANDO_ENTRADA = "aguardando_entrada"
    ABERTA = "aberta"
    PARCIAL_REALIZADA = "parcial_realizada"
    FINALIZADA_STOP = "finalizada_stop"
    FINALIZADA_TARGET = "finalizada_target"
    REJEITADA_FORA_JANELA = "rejeitada_fora_janela"


@dataclass
class PositionManager:
    odd_min_janela: float = 1.50
    odd_max_janela: float = 2.20
    stop_loss_pct: float = 0.15   # distância do stop em % da odd de entrada
    parcial_fracao: float = 0.5   # 50% da posição na parcial
    razao_parcial: float = 1.5    # dispara parcial em 1.5:1
    razao_alvo: float = 3.0       # take profit final em 3:1

    # estado interno (preenchido em open_position)
    direction: str = field(default="BACK", init=False)   # "BACK" (odd cai) ou "LAY" (odd sobe)
    entrada: float = field(default=0.0, init=False)
    stop_loss: float = field(default=0.0, init=False)
    parcial_preco: float = field(default=0.0, init=False)
    take_profit: float = field(default=0.0, init=False)
    risco: float = field(default=0.0, init=False)
    status: PositionStatus = field(default=PositionStatus.AGUARDANDO_ENTRADA, init=False)
    parcial_executada: bool = field(default=False, init=False)
    fracao_aberta: float = field(default=1.0, init=False)

    def open_position(self, odd_entrada: float, direction: str = "BACK") -> dict:
        """Tenta abrir uma posição. Recusa se a odd estiver fora da janela configurada."""
        self.direction = direction

        if not (self.odd_min_janela <= odd_entrada <= self.odd_max_janela):
            self.status = PositionStatus.REJEITADA_FORA_JANELA
            return self.state()

        self.entrada = odd_entrada
        self.risco = round(odd_entrada * self.stop_loss_pct, 3)

        sinal = -1 if direction == "BACK" else 1  # BACK: lucro = odd caindo; LAY: lucro = odd subindo
        self.stop_loss = round(odd_entrada - sinal * self.risco, 3)
        self.take_profit = round(odd_entrada + sinal * self.risco * self.razao_alvo, 3)
        self.parcial_preco = round(odd_entrada + sinal * self.risco * self.razao_parcial, 3)

        self.status = PositionStatus.ABERTA
        self.parcial_executada = False
        self.fracao_aberta = 1.0
        return self.state()

    def update(self, odd_atual: float) -> dict:
        """Alimenta o gerenciador com a odd corrente e atualiza o estado
        (dispara parcial, breakeven, stop ou take profit conforme o caso)."""
        if self.status not in (PositionStatus.ABERTA, PositionStatus.PARCIAL_REALIZADA):
            return self.state()

        atingiu_stop = (odd_atual >= self.stop_loss) if self.direction == "BACK" else (odd_atual <= self.stop_loss)
        atingiu_parcial = (odd_atual <= self.parcial_preco) if self.direction == "BACK" else (odd_atual >= self.parcial_preco)
        atingiu_alvo = (odd_atual <= self.take_profit) if self.direction == "BACK" else (odd_atual >= self.take_profit)

        # 1) Stop Loss atingido primeiro (antes de qualquer parcial) encerra tudo
        if atingiu_stop and not self.parcial_executada:
            self.status = PositionStatus.FINALIZADA_STOP
            self.fracao_aberta = 0.0
            return self.state()

        # 2) Parcial ainda não feita e preço bateu a marca de 1.5:1
        if atingiu_parcial and not self.parcial_executada:
            self.parcial_executada = True
            self.fracao_aberta = round(1.0 - self.parcial_fracao, 3)
            self.status = PositionStatus.PARCIAL_REALIZADA
            # Breakeven automático: stop vai para o preço de entrada
            self.stop_loss = self.entrada

        # 3) Depois da parcial, se voltar e bater o novo stop (breakeven) -> encerra o restante no zero a zero
        if self.parcial_executada:
            bateu_breakeven = (odd_atual >= self.stop_loss) if self.direction == "BACK" else (odd_atual <= self.stop_loss)
            if bateu_breakeven and self.status == PositionStatus.PARCIAL_REALIZADA:
                self.status = PositionStatus.FINALIZADA_STOP  # encerra no breakeven (sem perda no restante)
                self.fracao_aberta = 0.0
                return self.state()

        # 4) Take profit final atingido
        if atingiu_alvo:
            self.status = PositionStatus.FINALIZADA_TARGET
            self.fracao_aberta = 0.0
            return self.state()

        return self.state()

    def state(self) -> dict:
        return {
            "status": self.status.value,
            "direction": self.direction,
            "entrada": self.entrada,
            "stop_loss": self.stop_loss,
            "parcial_preco": self.parcial_preco,
            "take_profit": self.take_profit,
            "risco": self.risco,
            "parcial_executada": self.parcial_executada,
            "fracao_aberta": self.fracao_aberta,
        }
