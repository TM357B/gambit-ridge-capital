"""Contrôle croisé des prix : Yahoo (source principale) contre Alpaca Market Data.

Alpaca est une source indépendante (bourse IEX pour les actions, plateformes
crypto réelles). On compare le DERNIER RENDEMENT quotidien de chaque actif
plutôt que le niveau (Yahoo est ajusté des dividendes, Alpaca non). Écart
> 1 % (ETF) ou > 2,5 % (crypto, heures de clôture légèrement différentes) :
la ligne est marquée suspecte — ni revalorisée, ni tradée ce jour-là.
Sans clés Alpaca, le contrôle est simplement sauté (signalé).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

DATA = "https://data.alpaca.markets"
TOLERANCE = {"etf": 0.01, "crypto": 0.025}


def _get(path: str, params: dict) -> dict:
    from ..brokers.alpaca import _secret

    req = urllib.request.Request(DATA + path + "?" + urllib.parse.urlencode(params), headers={
        "APCA-API-KEY-ID": _secret("ALPACA_KEY_ID"), "APCA-API-SECRET-KEY": _secret("ALPACA_SECRET")})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def alpaca_closes(kind: str, tickers: list[str], start: str) -> dict[str, dict[str, float]]:
    """ticker -> {date ISO: clôture brute}."""
    if kind == "crypto":
        syms = {t.replace("-USD", "/USD"): t for t in tickers}
        d = _get("/v1beta3/crypto/us/bars", {"symbols": ",".join(syms), "timeframe": "1Day", "start": start, "limit": 10000})
    else:
        syms = {t: t for t in tickers}
        d = _get("/v2/stocks/bars", {"symbols": ",".join(syms), "timeframe": "1Day", "start": start, "feed": "iex", "adjustment": "raw", "limit": 10000})
    out: dict[str, dict[str, float]] = {}
    for sym, bars in (d.get("bars") or {}).items():
        out[syms.get(sym, sym)] = {b["t"][:10]: float(b["c"]) for b in bars}
    return out


def cross_check(kind: str, dates: list[str], prices: dict) -> tuple[list[str], set[str]]:
    from ..brokers.alpaca import has_credentials

    if not has_credentials():
        return ["contrôle croisé sauté (clés Alpaca absentes)"], set()
    if len(dates) < 2:
        return [], set()
    d0, d1 = dates[-2], dates[-1]
    try:
        ref = alpaca_closes(kind, list(prices), d0)
    except Exception as exc:
        return [f"contrôle croisé indisponible ({str(exc)[:60]})"], set()
    issues, bad = [], set()
    tol = TOLERANCE[kind]
    for tk, px in prices.items():
        a = ref.get(tk, {})
        if d0 not in a or d1 not in a:
            continue  # absent chez Alpaca (ex. BNB) : pas de second avis, pas de blocage
        r_y = float(px[-1] / px[-2] - 1)
        r_a = a[d1] / a[d0] - 1
        if abs(r_y - r_a) > tol:
            issues.append(f"{tk} : rendement du {d1} {r_y:+.2%} (Yahoo) contre {r_a:+.2%} (Alpaca) — ligne gelée")
            bad.add(tk)
    return issues, bad
