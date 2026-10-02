"""Équipe IA/Tech : cœur du fonds, plusieurs agents par sous-thème."""

from __future__ import annotations

from ..core.agent import QuantAgent
from ..core.manager import Manager

IA_THEMES = {
    "Semi-conducteurs": ["NVDA", "AMD", "TSM", "ASML", "AVGO", "MU"],
    "Datacenters & infra": ["EQIX", "DLR", "PLTR", "ANET", "CRWV"],
    "Cloud & hyperscalers": ["MSFT", "GOOGL", "AMZN", "ORCL"],
    "Modèles & applications": ["META", "PLTR", "AI.PA", "MSTR"],
}

IA_TICKERS = {t for tickers in IA_THEMES.values() for t in tickers}


def build_ia_tech_team() -> Manager:
    agents: list[QuantAgent] = []
    for theme, tickers in IA_THEMES.items():
        agents.append(
            QuantAgent(
                f"ia-{'-'.join(theme.lower().split())}",
                f"thème IA : {theme}",
                tickers,
                mom_lookback=30,
                mr_lookback=25,
            )
        )
    return Manager("IA & Tech", agents, max_signals=8)
