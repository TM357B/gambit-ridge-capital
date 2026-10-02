"""Générateur de marché simulé, déterministe (seed) et reproductible.

Sert à valider l'architecture avant de brancher les vraies données
(phase 3 : Polygon.io / Alpha Vantage / Binance).
"""

from __future__ import annotations

import math
import random

from ..core.agent import MarketData

_START_PRICES = {
    "SPY": 520.0, "EZU": 58.0, "DAX": 18000.0, "N225": 38000.0,
    "US10Y": 4.2, "DXY": 104.0,
    "MCHI": 25.0, "EEM": 42.0, "INDA": 48.0, "BRL": 5.1, "USDCNH": 7.20,
    "AAPL": 210.0, "MSFT": 420.0, "NVDA": 120.0, "ASML": 800.0,
    "SAP": 180.0, "MC.PA": 580.0, "7203.T": 2400.0,
    "TSM": 150.0, "BABA": 80.0, "TCEHY": 45.0, "INFY": 18.0, "VALE": 10.0,
    "BTC": 65000.0, "ETH": 3200.0, "SOL": 140.0, "BNB": 580.0,
    "XRP": 0.55, "ADA": 0.45, "AVAX": 30.0, "DOGE": 0.12,
    "EURUSD": 1.085, "USDJPY": 152.0, "GBPUSD": 1.27, "AUDUSD": 0.665,
    "USDCHF": 0.88, "USDCAD": 1.36,
    "GLD": 230.0, "SLV": 27.0, "USO": 75.0, "BNO": 80.0, "UNG": 15.0, "CPER": 28.0,
    "AMD": 160.0, "AVGO": 900.0, "MU": 110.0, "EQIX": 780.0, "DLR": 180.0,
    "PLTR": 40.0, "ANET": 350.0, "CRWV": 60.0, "GOOGL": 170.0, "AMZN": 185.0,
    "ORCL": 160.0, "META": 520.0, "AI.PA": 140.0, "MSTR": 150.0,
}


def simulate_market_data(
    tickers: list[str],
    periods: int = 90,
    seed: int = 42,
) -> dict[str, MarketData]:
    """Génère un jeu de données reproductible pour chaque ticker.

    Drift + volatilité spécifique à l'asset (crypto/forex/actions).
    """
    rng = random.Random(seed)
    data: dict[str, MarketData] = {}

    for ticker in tickers:
        start = _START_PRICES.get(ticker, 100.0)
        is_crypto = ticker in {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE"}
        is_fx = ticker in {"EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD", "USDCNH", "BRL"}

        if is_crypto:
            drift, vol = 0.0008, 0.035
        elif is_fx:
            drift, vol = 0.0000, 0.004
        else:
            drift, vol = 0.0003, 0.012

        prices: list[float] = [start]
        volumes: list[float] = []
        for _ in range(periods):
            shock = rng.gauss(0.0, 1.0) * vol
            prices.append(max(prices[-1] * (1 + drift + shock), start * 0.05))
            volumes.append(abs(rng.gauss(1e6, 2e5)))

        data[ticker] = MarketData(
            ticker=ticker,
            prices=prices,
            volumes=volumes,
        )
    return data


def all_configured_tickers() -> list[str]:
    return sorted(_START_PRICES)
