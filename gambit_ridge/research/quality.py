"""Contrôles qualité des données avant toute décision de trading.

Une poche dont les données échouent n'est PAS rebalancée ce jour-là (les
positions sont conservées) et ses prix suspects ne servent pas à la
valorisation. Mieux vaut un jour sans trade qu'un trade sur un prix faux.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

LIMITS = {
    # âge max de la dernière clôture (jours calendaires), saut quotidien max, jours figés max
    "etf": {"max_age": 5, "max_jump": 0.25, "max_flat": 4},
    "crypto": {"max_age": 3, "max_jump": 0.45, "max_flat": 3},
}


def check_sleeve(kind: str, dates: list[str], prices: dict[str, np.ndarray], today: date | None = None) -> tuple[list[str], set[str]]:
    """Retourne (problèmes lisibles, tickers suspects)."""
    lim = LIMITS[kind]
    issues: list[str] = []
    bad: set[str] = set()
    if not dates:
        return [f"{kind} : aucune donnée"], set(prices)
    age = ((today or date.today()) - date.fromisoformat(dates[-1])).days
    if age > lim["max_age"]:
        issues.append(f"{kind} : dernière clôture du {dates[-1]} ({age} jours) — source figée ?")
        bad |= set(prices)
    for tk, px in prices.items():
        px = np.asarray(px, dtype=float)
        if len(px) < 300 or not np.all(np.isfinite(px[-300:])) or np.any(px[-300:] <= 0):
            issues.append(f"{tk} : série incomplète ou prix invalides")
            bad.add(tk)
            continue
        jump = abs(px[-1] / px[-2] - 1.0)
        if jump > lim["max_jump"]:
            issues.append(f"{tk} : variation de {jump:.0%} sur la dernière séance — à vérifier")
            bad.add(tk)
        flat = int(np.sum(px[-lim["max_flat"] - 1:] == px[-1]))
        if flat > lim["max_flat"]:
            issues.append(f"{tk} : prix inchangé depuis {flat} séances")
            bad.add(tk)
    return issues, bad
