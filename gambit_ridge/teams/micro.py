"""Équipe Micro : analyse fondamentale/technique par zone."""

from __future__ import annotations

from ..core.agent import QuantAgent
from ..core.manager import Manager

MICRO_DM_TICKERS = ["AAPL", "MSFT", "NVDA", "ASML", "SAP", "MC.PA", "7203.T"]
MICRO_EM_TICKERS = ["TSM", "BABA", "TCEHY", "INFY", "VALE"]


def build_micro_team() -> Manager:
    dm = QuantAgent(
        "micro-dm",
        "micro économie / actions développés",
        MICRO_DM_TICKERS,
    )
    em = QuantAgent(
        "micro-em",
        "micro économie / actions émergents",
        MICRO_EM_TICKERS,
    )
    return Manager("Micro", [dm, em])
