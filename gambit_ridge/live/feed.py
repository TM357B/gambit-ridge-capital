"""Flux de prix en direct : Alpaca Market Data (IEX pour les ETF, crypto 24/7).

Instantanés interrogés en boucle par le moteur live (une requête par poche) : ils servent
à valoriser le compte, contrôler la fraîcheur des prix et dimensionner les ordres.
Les signaux, eux, sont calculés sur les clôtures quotidiennes Yahoo (voir engine.daily_targets).
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..data.crosscheck import _get

MAX_SPREAD = 0.02  # cotation plus large : on ne s'y fie pas


def _alpaca_symbol(tk: str) -> str:
    return tk.replace("-USD", "/USD") if tk.endswith("-USD") else tk


def snapshots(kind: str, tickers: list[str]) -> dict[str, dict]:
    """ticker -> {price, at, bars: {date ISO: clôture brute}}.

    `price` = dernier échange ; `bars` contient la séance précédente et la
    séance en cours (pour retrouver la clôture de référence).
    """
    syms = {_alpaca_symbol(t): t for t in tickers}
    if kind == "crypto":
        raw = _get("/v1beta3/crypto/us/snapshots", {"symbols": ",".join(syms)}).get("snapshots") or {}
    else:
        raw = _get("/v2/stocks/snapshots", {"symbols": ",".join(syms), "feed": "iex"})
    out: dict[str, dict] = {}
    for sym, s in raw.items():
        if not s:
            continue
        trade = s.get("latestTrade") or {}
        quote = s.get("latestQuote") or {}
        price, at, src = trade.get("p"), trade.get("t"), "échange"
        bp, ap = float(quote.get("bp") or 0), float(quote.get("ap") or 0)
        # milieu de cotation s'il est plus récent que le dernier échange (actifs peu échangés)
        if 0 < bp <= ap < bp * (1 + MAX_SPREAD) and (not at or (quote.get("t") or "") > at):
            price, at, src = (bp + ap) / 2, quote.get("t"), "cotation"
        bars = {}
        for key in ("prevDailyBar", "dailyBar"):
            b = s.get(key) or {}
            if b.get("t") and b.get("c"):
                bars[b["t"][:10]] = float(b["c"])
        if price:
            out[syms.get(sym, sym)] = {"price": float(price), "at": at, "src": src, "bars": bars}
    return out


def age_seconds(at: str | None, now: datetime | None = None) -> float | None:
    if not at:
        return None
    import re

    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?", at)
    if not m:
        return None
    t = datetime.fromisoformat(m.group(1) + (m.group(2) or "")[:7]).replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - t).total_seconds()
