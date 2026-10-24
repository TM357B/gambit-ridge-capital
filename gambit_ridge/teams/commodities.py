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

# Desks ajoutés le 24/10/2026 (la campagne 2 reste calculée sur les 6 d'origine : etendue=False)
COMMODITY_DESKS_AJOUTS = {
    "Platine": "PPLT",
    "Palladium": "PALL",
    "Essence": "UGA",
    "Métaux de base": "DBB",
}


def build_commodities_team(etendue: bool = True) -> Manager:
    desks = {**COMMODITY_DESKS, **(COMMODITY_DESKS_AJOUTS if etendue else {})}
    agents = [
        QuantAgent(
            f"commodity-{ticker.lower()}",
            f"desk {label} ({ticker})",
            [ticker],
            mom_lookback=40,
            mr_lookback=30,
        )
        for label, ticker in desks.items()
    ]
    return Manager("Commodities", agents, max_signals=3)
