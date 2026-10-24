"""Équipe Agricoles : céréales, oléagineux et denrées tropicales, un agent par marché."""

from __future__ import annotations

from ..core.agent import QuantAgent
from ..core.manager import Manager

AGRI_DESKS = {
    "Maïs": "CORN",
    "Blé": "WEAT",
    "Soja": "SOYB",
    "Sucre": "CANE",
    "Panier agricole": "DBA",
}


def build_agricoles_team() -> Manager:
    # marchés saisonniers et lents : tendance longue, retour à la moyenne court
    agents = [
        QuantAgent(
            f"agri-{ticker.lower()}",
            f"desk {label} ({ticker})",
            [ticker],
            mom_lookback=60,
            mr_lookback=20,
        )
        for label, ticker in AGRI_DESKS.items()
    ]
    return Manager("Agricoles", agents, max_signals=2)
