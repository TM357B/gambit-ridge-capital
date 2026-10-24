"""Équipe Forex : un agent par paire majeure + manager."""

from __future__ import annotations

from ..core.agent import QuantAgent
from ..core.manager import Manager

FOREX_MAJORS = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD"]
# paires ajoutées le 24/10/2026 (la campagne 2 reste calculée sur les 6 majeures : etendue=False)
FOREX_AJOUTS = ["NZDUSD", "EURGBP", "EURJPY", "USDMXN", "USDSEK"]


def build_forex_team(etendue: bool = True) -> Manager:
    paires = FOREX_MAJORS + (FOREX_AJOUTS if etendue else [])
    agents = [
        QuantAgent(
            f"fx-{pair.lower()}",
            f"paire {'majeure' if pair in FOREX_MAJORS else 'secondaire'} {pair[:3]}/{pair[3:]}",
            [pair],
            mom_lookback=20,
            mr_lookback=40,
            mom_weight=0.35,
            mr_weight=0.65,
        )
        for pair in paires
    ]
    return Manager("Forex", agents, max_signals=3)
