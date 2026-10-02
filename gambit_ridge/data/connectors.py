"""Interface connecteurs : simulation + APIs réelles (Polygon)."""

from __future__ import annotations

import json
import time
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.agent import MarketData
from .simulation import simulate_market_data

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data_cache"


class DataConnector(ABC):
    """Source de données normalisée vers MarketData."""

    @abstractmethod
    def fetch(self, ticker: str, periods: int = 90) -> MarketData:
        ...


class SimulatedConnector(DataConnector):
    """Connecteur simulation : reproductible, zéro réseau."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self._cache: Optional[dict[str, MarketData]] = None

    def fetch(self, ticker: str, periods: int = 90) -> MarketData:
        if self._cache is None:
            self._cache = simulate_market_data([ticker], periods, self.seed)
            return self._cache[ticker]
        return self._cache.get(ticker) or simulate_market_data([ticker], periods, self.seed)[ticker]


class PolygonConnector(DataConnector):
    """Connecteur Polygon.io : barres journalières ajustées, avec cache disque.

    Plan gratuit : 5 req/min → pause configurable entre requêtes ;
    historique limité (2 ans sur le plan gratuit).
    Le cache persiste dates + prix pour permettre l'alignement des séries.
    """

    BASE_URL = "https://api.polygon.io"

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Path | None = None,
        rate_limit_sleep: float = 13.0,
    ) -> None:
        from ..config import get_polygon_key

        self.api_key = api_key or get_polygon_key()
        if not self.api_key:
            raise RuntimeError(
                "POLYGON_API_KEY manquante : la définir dans l'environnement ou .env"
            )
        self.cache_dir = cache_dir or CACHE_DIR
        self.rate_limit_sleep = rate_limit_sleep

    def _cache_path(self, ticker: str, from_date: str, to_date: str) -> Path:
        return self.cache_dir / f"polygon_{ticker}_{from_date}_{to_date}.json"

    def _request(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": "gambit-ridge/0.1"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())

    def fetch_daily_bars(
        self,
        ticker: str,
        from_date: str = "2024-01-01",
        to_date: str = "2026-01-01",
    ) -> tuple[list[int], np.ndarray]:
        """Télécharge (ou relit le cache) dates(ms) + prix de clôture.

        Retourne (timestamps_ms, prix) pour alignement inter-actifs.
        """
        path = self._cache_path(ticker, from_date, to_date)
        if path.exists():
            payload = json.loads(path.read_text())
            return payload["dates"], np.array(payload["prices"], dtype=float)

        url = (
            f"{self.BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/"
            f"{from_date}/{to_date}?adjusted=true&sort=asc&limit=50000"
            f"&apiKey={self.api_key}"
        )
        payload = self._request(url)
        if payload.get("status") != "OK":
            raise RuntimeError(f"Polygon: statut {payload.get('status')} pour {ticker}")
        results = payload.get("results") or []
        if not results:
            raise RuntimeError(f"Polygon: aucune donnée pour {ticker}")

        dates = [int(bar["t"]) for bar in results]
        prices = np.array([bar["c"] for bar in results], dtype=float)
        self.cache_dir.mkdir(exist_ok=True)
        path.write_text(json.dumps({"dates": dates, "prices": prices.tolist()}))
        time.sleep(self.rate_limit_sleep)
        return dates, prices

    def fetch(self, ticker: str, periods: int = 90) -> MarketData:
        end = np.datetime64("today", "D")
        start = end - np.timedelta64(max(periods, 720), "D")
        _, prices = self.fetch_daily_bars(ticker, str(start), str(end))
        return MarketData(ticker=ticker, prices=prices.tolist())


class BinanceConnector(DataConnector):
    """Stub pour Binance (crypto 24/7) — phase 3."""

    def fetch(self, ticker: str, periods: int = 90) -> MarketData:
        raise NotImplementedError("BinanceConnector: phase 3 (surveillance 24/7)")
