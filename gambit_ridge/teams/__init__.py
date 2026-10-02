"""Équipes d'agents spécialisés, chacune dirigée par un manager."""

from .crypto import build_crypto_team
from .forex import build_forex_team
from .commodities import build_commodities_team
from .ia_tech import build_ia_tech_team, IA_TICKERS
from .macro import build_macro_team
from .micro import build_micro_team

__all__ = [
    "build_crypto_team",
    "build_forex_team",
    "build_commodities_team",
    "build_ia_tech_team",
    "build_macro_team",
    "build_micro_team",
    "IA_TICKERS",
]
