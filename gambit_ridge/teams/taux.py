"""Équipe Taux : courbe américaine, crédit et obligations internationales, un agent par marché."""

from __future__ import annotations

from ..core.agent import QuantAgent
from ..core.manager import Manager

TAUX_DESKS = {
    "Trésor 1-3 ans": "SHY",
    "Trésor 7-10 ans": "IEF",
    "Trésor 20 ans et plus": "TLT",
    "Indexées inflation": "TIP",
    "Crédit investment grade": "LQD",
    "Haut rendement": "HYG",
    "Souverains internationaux": "BWX",
    "Dette émergente": "EMB",
}


def build_taux_team() -> Manager:
    # les taux tendent plus qu'ils ne reviennent : poids momentum dominant
    agents = [
        QuantAgent(
            f"taux-{ticker.lower()}",
            f"desk {label} ({ticker})",
            [ticker],
            mom_lookback=60,
            mr_lookback=40,
            mom_weight=0.65,
            mr_weight=0.35,
        )
        for label, ticker in TAUX_DESKS.items()
    ]
    return Manager("Taux", agents, max_signals=3)
