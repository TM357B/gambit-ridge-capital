"""Équipe Commodities : un agent par sous-jacent (métaux, énergie...)."""

from __future__ import annotations

from ..core.agent import QuantAgent
from ..core.manager import Manager

COMMODITY_DESKS = {
    "Or": "GLD",
    "Argent": "SLV",
    "Pétrole WTI": "USO",
    "Pétrole Brent": "BNO",
    "Gaz naturel": "UNG",
    "Cuivre": "CPER",
}


def build_commodities_team() -> Manager:
    agents = [
        QuantAgent(
            f"commodity-{ticker.lower()}",
            f"desk {label} ({ticker})",
            [ticker],
            mom_lookback=40,
            mr_lookback=30,
        )
        for label, ticker in COMMODITY_DESKS.items()
    ]
    return Manager("Commodities", agents, max_signals=3)
