"""Équipe Crypto : surveillance 24/7, un sous-agent par crypto suivie."""

from __future__ import annotations

from ..core.agent import QuantAgent
from ..core.manager import Manager

CRYPTO_WATCHLIST = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE"]


def build_crypto_team() -> Manager:
    """Un agent par crypto (surveillance continue), un manager au-dessus."""
    agents = [
        QuantAgent(
            f"crypto-{symbol.lower()}",
            f"surveillance 24/7 de {symbol}",
            [symbol],
            mom_lookback=7,
            mr_lookback=14,
            mom_weight=0.6,
            mr_weight=0.4,
        )
        for symbol in CRYPTO_WATCHLIST
    ]
    return Manager("Crypto 24/7", agents, max_signals=4)
