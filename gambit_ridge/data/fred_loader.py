"""Univers de backtest décennal via FRED (gratuit).

Construit des séries de prix alignées par date à partir des séries
officielles FRED. Les taux (DGS10...) sont des niveaux, pas des prix :
ils servent de facteurs macro, pas d'actifs négociables directement.

Deux univers :
- large  (~20 ans, 2006+) : 6 actifs (S&P via DTWEXBGS+..., Nasdaq, Brent,
  dollar, EUR/USD, JPY/USD)
- long   (1971+)          : 2 actifs (Nasdaq, JPY/USD) pour le backtest
  très longue durée (inclusion de 1987, dot-com, 2008)
"""

from __future__ import annotations

import numpy as np

from .fred import FredConnector, FRED_SERIES

# Séries utilisées comme ACTIFS négociables (niveaux de prix d'actifs)
PRICE_SERIES = {
    "SP500": "S&P 500",
    "NASDAQCOM": "Nasdaq Composite",
    "DCOILBRENTEU": "Brent",
    "DCOILWTICO": "WTI",
    "DHHNGSP": "Gaz Henry Hub",
    "DTWEXBGS": "Dollar index",
    "DEXUSEU": "EUR/USD (inversé)",
    "DEXJPUS": "JPY/USD (inversé)",
}

LONG_PRICE_SERIES = {
    "NASDAQCOM": "Nasdaq Composite",
    "DEXJPUS": "JPY/USD (inversé)",
    "DCOILWTICO": "WTI",
}

# Séries facteurs macro (entrées des agents macro, pas négociables)
FACTOR_SERIES = {
    "DGS10": "Taux 10 ans",
    "T10Y2Y": "Pente",
    "VIXCLS": "VIX",
    "DGS2": "Taux 2 ans",
}


def _align(raw: dict[str, tuple[list[str], np.ndarray]]) -> dict[str, np.ndarray]:
    common = set(next(iter(raw.values()))[0])
    for dates, _ in raw.values():
        common &= set(dates)
    aligned: dict[str, np.ndarray] = {}
    for series_id, (dates, values) in raw.items():
        date_index = {d: i for i, d in enumerate(dates)}
        idx = sorted(date_index[d] for d in common)
        vals = np.array(values[idx], dtype=float)
        # Prix non strictement positifs (ex : WTI -36.98 le 2020-04-20) :
        # remplacés par le dernier prix positif connu (flat), sinon les
        # rendements divergent (log/P négatifs) et corrompent le backtest.
        bad = vals <= 0
        if bad.any():
            last = np.nan
            fixed = vals.copy()
            for i in range(len(fixed)):
                if fixed[i] <= 0:
                    fixed[i] = last
                else:
                    last = fixed[i]
            vals = np.where(np.isfinite(fixed), fixed, np.nan)
        aligned[series_id] = vals
    return aligned


def load_fred_universe(min_common: int = 1200) -> dict[str, np.ndarray]:
    """Univers large : toutes les séries de prix, alignées (~20 ans)."""
    connector = FredConnector()
    raw = {}
    for series_id in PRICE_SERIES:
        dates, values = connector.fetch_series(series_id)
        if len(values) > 0:
            raw[series_id] = (dates, values)
    if not raw:
        raise RuntimeError("aucune série FRED chargée")
    aligned = _align(raw)
    n = len(next(iter(aligned.values())))
    if n < min_common:
        raise RuntimeError(f"intersection trop courte: {n} points")
    return aligned


def load_fred_long_universe(min_common: int = 8000) -> dict[str, np.ndarray]:
    """Univers long terme : Nasdaq + JPY depuis 1971 (~55 ans, crises incluses)."""
    connector = FredConnector()
    raw = {}
    for series_id in LONG_PRICE_SERIES:
        dates, values = connector.fetch_series(series_id)
        if len(values) > 0:
            raw[series_id] = (dates, values)
    aligned = _align(raw)
    n = len(next(iter(aligned.values())))
    if n < min_common:
        raise RuntimeError(f"intersection trop courte: {n} points")
    return aligned


def load_fred_universe_with_dates(min_common: int = 1200):
    """Univers large + liste des dates ISO alignées (pour résoudre les crises datées)."""
    connector = FredConnector()
    raw = {}
    for series_id in PRICE_SERIES:
        dates, values = connector.fetch_series(series_id)
        if len(values) > 0:
            raw[series_id] = (dates, values)
    if not raw:
        raise RuntimeError("aucune série FRED chargée")
    common = set(next(iter(raw.values()))[0])
    for dates, _ in raw.values():
        common &= set(dates)
    common_dates = sorted(common)
    aligned = _align(raw)
    n = len(next(iter(aligned.values())))
    if n < min_common or n != len(common_dates):
        raise RuntimeError(f"intersection trop courte: {n} points")
    return aligned, common_dates


def load_fred_factors() -> dict[str, tuple[list[str], np.ndarray]]:
    """Charge les facteurs macro (dates brutes + valeurs)."""
    connector = FredConnector()
    return {sid: connector.fetch_series(sid) for sid in FACTOR_SERIES}
