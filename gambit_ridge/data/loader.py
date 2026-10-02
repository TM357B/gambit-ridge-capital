"""Chargement d'historiques réels alignés par date pour le backtest.

Le plan gratuit Polygon limite l'historique à ~2 ans et 5 req/min :
le loader respecte le débit et aligne les séries sur les dates communes.
"""

from __future__ import annotations

import numpy as np

from .connectors import PolygonConnector

# Tickers Polygon : préfixes C: pour forex, X: pour crypto.
BACKTEST_UNIVERSE = {
    "SPY": "Actions US",
    "QQQ": "Nasdaq / Tech",
    "NVDA": "Semi-conducteurs",
    "MSFT": "Cloud/IA",
    "GOOGL": "Cloud/IA",
    "AMZN": "Cloud/IA",
    "META": "IA appl.",
    "TSM": "Semi-conducteurs",
    "GLD": "Or",
    "SLV": "Argent",
    "USO": "Pétrole WTI",
    "C:EURUSD": "Forex EUR/USD",
    "C:USDJPY": "Forex USD/JPY",
    "X:BTCUSD": "Bitcoin",
}


def load_backtest_universe_with_dates(
    from_date: str = "2024-09-01",
    to_date: str = "2026-09-01",
    min_history: int = 200,
    rate_limit_sleep: float = 13.0,
):
    """Charge l'univers via Polygon + les dates ISO alignées (pour les crises datées)."""
    connector = PolygonConnector(rate_limit_sleep=rate_limit_sleep)
    raw: dict[str, list] = {}
    for ticker in BACKTEST_UNIVERSE:
        try:
            dates, prices = connector.fetch_daily_bars(ticker, from_date, to_date)
            if len(prices) >= min_history:
                raw[ticker] = (dates, prices)
        except Exception:
            continue
    if not raw:
        raise RuntimeError("aucun ticker chargé")

    def _day(ts_ms: int) -> int:
        return ts_ms // 86_400_000

    day_sets = [{_day(d) for d in dates} for dates, _ in raw.values()]
    common = sorted(set.intersection(*day_sets))
    aligned: dict[str, np.ndarray] = {}
    for ticker, (dates, prices) in raw.items():
        date_index = {_day(d): i for i, d in enumerate(dates)}
        idx = sorted(date_index[d] for d in common)
        aligned[ticker] = prices[idx]
    common_dates = [_day_iso(d) for d in common]
    return aligned, common_dates


def _day_iso(ts_ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def load_backtest_universe(
    from_date: str = "2024-09-01",
    to_date: str = "2026-09-01",
    min_history: int = 200,
    rate_limit_sleep: float = 13.0,
) -> dict[str, np.ndarray]:
    """Charge l'univers via Polygon, aligné sur les dates communes.

    Les tickers non autorisés par le plan ou trop courts sont écartés.
    """
    connector = PolygonConnector(rate_limit_sleep=rate_limit_sleep)
    raw: dict[str, list] = {}

    for ticker in BACKTEST_UNIVERSE:
        try:
            dates, prices = connector.fetch_daily_bars(ticker, from_date, to_date)
            if len(prices) >= min_history:
                raw[ticker] = (dates, prices)
            else:
                print(f"  ! {ticker} trop court ({len(prices)} bars)")
        except Exception as exc:
            print(f"  ! {ticker} ignoré ({str(exc)[:80]})")

    if not raw:
        raise RuntimeError("aucun ticker chargé")

    # Intersection des dates communes, normalisées au jour près :
    # les timestamps diffèrent selon l'actif (00:00 UTC crypto/forex vs actions).
    def _day(ts_ms: int) -> int:
        return ts_ms // 86_400_000

    day_sets = [ {_day(d) for d in dates} for dates, _ in raw.values() ]
    common = set.intersection(*day_sets)

    aligned: dict[str, np.ndarray] = {}
    for ticker, (dates, prices) in raw.items():
        date_index = {_day(d): i for i, d in enumerate(dates)}
        idx = sorted(date_index[d] for d in common)
        aligned[ticker] = prices[idx]
    return aligned


def align_series(series: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Tronque toutes les séries à la longueur de la plus courte."""
    n = min(len(s) for s in series.values())
    return {tk: s[:n] for tk, s in series.items()}
