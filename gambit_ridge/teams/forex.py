"""Équipe Forex : un agent par paire majeure + manager."""

from __future__ import annotations

from ..core.agent import QuantAgent
from ..core.manager import Manager

FOREX_MAJORS = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD"]


def build_forex_team() -> Manager:
    agents = [
        QuantAgent(
            f"fx-{pair.lower()}",
            f"paire majeure {pair[:3]}/{pair[3:]}",
            [pair],
            mom_lookback=20,
            mr_lookback=40,
            mom_weight=0.35,
            mr_weight=0.65,
        )
        for pair in FOREX_MAJORS
    ]
    return Manager("Forex", agents, max_signals=3)
