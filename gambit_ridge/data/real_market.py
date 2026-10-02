"""Données RÉELLES pour les agents du conseil (remplace le marché simulé).

Chaque ticker des équipes est associé à un symbole Yahoo (actions, ETF,
indices, devises, cryptos). Les clôtures complètes uniquement (barre du jour
exclue). Un ticker introuvable reste absent : l'agent ne produit alors pas de
signal dessus — on ne fabrique jamais de prix.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from ..core.agent import MarketData
from .simulation import all_configured_tickers
from .yahoo import YahooConnector, complete_cutoff

# ticker interne -> symbole Yahoo (identique si absent)
YAHOO_MAP = {
    "DAX": "^GDAXI", "N225": "^N225", "US10Y": "^TNX", "DXY": "DX-Y.NYB",
    "BRL": "BRL=X",
    "USDCNH": "CNY=X",  # Yahoo n'a pas l'historique du CNH offshore : CNY onshore (écart minime)
    "EURUSD": "EURUSD=X", "USDJPY": "JPY=X", "GBPUSD": "GBPUSD=X", "AUDUSD": "AUDUSD=X",
    "USDCHF": "CHF=X", "USDCAD": "CAD=X",
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "BNB": "BNB-USD",
    "XRP": "XRP-USD", "ADA": "ADA-USD", "AVAX": "AVAX-USD", "DOGE": "DOGE-USD",
}

_CACHE: dict = {}


def load_agent_market_data(periods: int = 260, refresh: bool = True) -> tuple[dict[str, MarketData], dict[str, str]]:
    """Retourne (données par ticker interne, source par ticker)."""
    key = (date.today().isoformat(), periods)
    if key in _CACHE:
        return _CACHE[key]
    conn = YahooConnector()
    tickers = all_configured_tickers()

    def fetch(tk: str):
        sym = YAHOO_MAP.get(tk, tk)
        try:
            raw = conn.fetch(sym, refresh=refresh)
        except Exception:
            return tk, None
        cut = complete_cutoff(sym)
        ds = sorted(d for d in raw if d <= cut)[-(periods + 1):]
        if len(ds) < 60:
            return tk, None
        return tk, MarketData(ticker=tk, prices=[raw[d] for d in ds], volumes=[])

    data: dict[str, MarketData] = {}
    sources: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for tk, md in pool.map(fetch, tickers):
            if md is not None:
                data[tk] = md
                sources[tk] = "yahoo"
            else:
                sources[tk] = "indisponible"
    _CACHE.clear()
    _CACHE[key] = (data, sources)
    return data, sources
