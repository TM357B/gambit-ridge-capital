"""Réunion quotidienne automatisée : journalise le briefing sans dashboard.

Usage : python3 -m gambit_ridge.daily
Conçu pour le cron : exécute la réunion, enregistre l'allocation du jour,
recalcule le P&L cumulé et imprime un résumé d'une ligne.
"""

from __future__ import annotations

import sys

from . import journal
from .demo import build_fund


def main() -> int:
    from .data.real_market import load_agent_market_data
    from .app.server import _fred_factors

    council = build_fund(_fred_factors())
    merged, _sources = load_agent_market_data()

    briefing = council.meeting(merged)

    today_prices = {}
    for tk in briefing.proposed_allocation:
        md = merged.get(tk)
        if md and md.prices:
            today_prices[tk] = float(md.prices[-1])

    journal.record_briefing(briefing.proposed_allocation, today_prices)
    pnl = journal.compute_pnl(today_prices)

    equity = pnl[-1]["equity"] if pnl else 100.0
    n = len(briefing.proposed_allocation)
    risk = "OK" if not briefing.risk_reasons else "⚠ " + "; ".join(briefing.risk_reasons)
    print(
        f"{briefing.day} | {n} positions | track record {equity:.2f}/100 | risque {risk}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
