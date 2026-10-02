"""Historique synthétique multi-décennies avec crises intégrées.

Simule ~40 ans de données quotidiennes pour ~10 actifs, avec :
- Régimes normaux (drift + vol modérée)
- Crises calquées sur 1987, 2000, 2008, 2020, 2022 (chocs de vol et drawdown)
- Corrélation croissante pendant les crises (propriété clé à tester)

Sert à valider le moteur. Les vraies données (Polygon, phase 3)
remplaceront cette source.
"""

from __future__ import annotations

import numpy as np

N_YEARS = 40
PERIODS_PER_YEAR = 252

SYNTHETIC_TICKERS = ["US_EQUITY", "EU_EQUITY", "JP_EQUITY", "EM_EQUITY", "BOND", "GOLD", "OIL", "USD_INDEX", "TECH", "CRYPTO"]

_BASE_PARAMS = {
    "US_EQUITY": (0.08, 0.16), "EU_EQUITY": (0.06, 0.18), "JP_EQUITY": (0.05, 0.20),
    "EM_EQUITY": (0.07, 0.24), "BOND": (0.04, 0.06), "GOLD": (0.05, 0.15),
    "OIL": (0.03, 0.30), "USD_INDEX": (0.01, 0.07), "TECH": (0.11, 0.25),
    "CRYPTO": (0.25, 0.60),
}

# (début en années, durée en jours, intensité du choc)
_CRISIS_SCHEDULE = [
    (1987 + 10 / 12, 10, 2.5),   # lundi noir
    (2000 + 2 / 12, 400, 1.8),   # dot-com
    (2008 + 8 / 12, 250, 2.2),   # GFC
    (2020 + 2 / 12, 25, 3.0),    # COVID
    (2022 + 0 / 12, 200, 1.3),   # taux
]


def generate_synthetic_history(
    n_years: int = N_YEARS,
    seed: int = 7,
    start_year: int = 1985,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = n_years * PERIODS_PER_YEAR
    tickers = list(_BASE_PARAMS)
    prices = {tk: np.zeros(n + 1) for tk in tickers}
    for tk in tickers:
        prices[tk][0] = 100.0

    crisis_spans = [
        (
            int((cy - start_year) * PERIODS_PER_YEAR),
            int((cy - start_year) * PERIODS_PER_YEAR + dur),
            intensity,
        )
        for cy, dur, intensity in _CRISIS_SCHEDULE
        if start_year <= cy <= start_year + n_years
    ]

    for t in range(n):
        year_frac = t / PERIODS_PER_YEAR
        in_crisis = any(s <= t < e for s, e, _ in crisis_spans)
        intensity = next((i for s, e, i in crisis_spans if s <= t < e), 1.0)

        shocks = {tk: rng.standard_normal() for tk in tickers}
        market_shock = rng.standard_normal()

        for tk in tickers:
            drift, vol = _BASE_PARAMS[tk]
            beta = 0.5 if tk not in ("BOND", "USD_INDEX", "GOLD") else -0.1
            if tk == "CRYPTO":
                beta = 0.3
            crisis_mult = intensity if in_crisis and tk != "BOND" else (0.6 if in_crisis and tk == "BOND" else 1.0)
            idio = shocks[tk] * np.sqrt(max(1 - beta * beta, 0.1))
            ret = drift / PERIODS_PER_YEAR + vol / np.sqrt(PERIODS_PER_YEAR) * crisis_mult * (beta * market_shock + idio)
            ret = np.clip(ret, -0.25, 0.25)
            prices[tk][t + 1] = prices[tk][t] * (1 + ret)

    return prices


def crisis_year_windows() -> list[tuple[str, int, int]]:
    """Fenêtres en périodes pour le stress testing de l'historique synthétique."""
    ppy = PERIODS_PER_YEAR
    spans = [
        ("Krach 1987", 1987, 2),
        ("Dot-com 2000-2002", 2000, 2),
        ("GFC 2008", 2008, 1),
        ("COVID 2020", 2020, 1),
        ("Taux 2022", 2022, 1),
    ]
    return [
        (name, int((year - 1985) * ppy), int((year - 1985) * ppy) + duration * ppy)
        for name, year, duration in spans
    ]
