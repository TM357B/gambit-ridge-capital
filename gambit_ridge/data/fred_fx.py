"""Données forex FRED : 6 paires majeures quotidiennes + taux courts mensuels.

Paires (cotations FRED, tout en USD) :
  EURUSD = DEXUSEU, GBPUSD = DEXUSUK, AUDUSD = DEXUSAL
  USDJPY = DEXJPUS, USDCHF = DEXSFUS, USDCAD = DEXCAUS

Taux 3 mois interbancaires (OECD, mensuels, forward-fill) :
  US, DE (proxy EUR avant 1999 via FR), JP, GB, AU, CH, CA
"""

from __future__ import annotations

import io
import time
import urllib.request
from pathlib import Path

import numpy as np

BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data_cache"

FX_SERIES = {
    "EURUSD": "DEXUSEU",
    "GBPUSD": "DEXUSUK",
    "AUDUSD": "DEXUSAL",
    "USDJPY": "DEXJPUS",
    "USDCHF": "DEXSFUS",
    "USDCAD": "DEXCAUS",
}

RATE_SERIES = {
    "USD": "IR3TIB01USM156N",
    "EUR": "IR3TIB01FRM156N",  # France comme proxy zone EUR (série la plus longue)
    "JPY": "IR3TIB01JPM156N",
    "GBP": "IR3TIB01GBM156N",
    "AUD": "IR3TIB01AUM156N",
    "CHF": "IR3TIB01CHM156N",
    "CAD": "IR3TIB01CAM156N",
}

# Paire -> (devise longue, devise courte) quand on est long la paire
PAIR_LEGDS = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"),
    "USDJPY": ("USD", "JPY"),
    "USDCHF": ("USD", "CHF"),
    "USDCAD": ("USD", "CAD"),
}


def _fetch_csv(series_id: str) -> str:
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / f"fred_{series_id}.csv"
    if cache.exists() and cache.stat().st_size > 100:
        return cache.read_text()
    for attempt in range(3):
        try:
            data = urllib.request.urlopen(
                BASE_URL.format(sid=series_id), timeout=8
            ).read()
            cache.write_text(data.decode())
            time.sleep(0.4)
            return data.decode()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5)
    raise RuntimeError(series_id)


def _parse_daily(csv_text: str) -> list[tuple[str, float]]:
    out = []
    for line in csv_text.strip().splitlines()[1:]:
        date, _, val = line.partition(",")
        val = val.strip().strip('"')
        if val in ("", ".", "NA"):
            continue
        try:
            out.append((date, float(val)))
        except ValueError:
            continue
    return out


def _parse_monthly(csv_text: str) -> dict[str, float]:
    out = {}
    for line in io.StringIO(csv_text).read().strip().splitlines()[1:]:
        date, _, val = line.partition(",")
        val = val.strip().strip('"')
        if val in ("", ".", "NA"):
            continue
        try:
            out[date[:7]] = float(val)  # "YYYY-MM"
        except ValueError:
            continue
    return out


def load_fx_universe(start: str = "1999-01-04") -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Retourne (prices, rates) alignés sur les dates FX communes.

    prices : paire -> série quotidienne
    rates  : devise -> taux 3M forward-fillé aligné sur les mêmes dates (en %)
    """
    pairs = {}
    for pair, sid in FX_SERIES.items():
        rows = _parse_daily(_fetch_csv(sid))
        pairs[pair] = {d: v for d, v in rows if d >= start}

    rates_monthly = {
        ccy: _parse_monthly(_fetch_csv(sid)) for ccy, sid in RATE_SERIES.items()
    }

    dates = sorted(
        set.intersection(*(set(pairs[p]) for p in pairs))
    )

    # Trim des dates où un taux est encore inconnu (CHF démarre mi-1999)
    first_valid = 0
    for i, d in enumerate(dates):
        if all(rates_monthly[c].get(d[:7]) is not None for c in rates_monthly):
            first_valid = i
            break
    dates = dates[first_valid:]

    prices: dict[str, np.ndarray] = {}
    for pair in FX_SERIES:
        prices[pair] = np.array([pairs[pair][d] for d in dates])

    rates: dict[str, np.ndarray] = {}
    for ccy, monthly in rates_monthly.items():
        vals, last = [], np.nan
        for d in dates:
            m = monthly.get(d[:7])
            if m is not None:
                last = m
            vals.append(last)
        rates[ccy] = np.array(vals)

    return prices, rates
