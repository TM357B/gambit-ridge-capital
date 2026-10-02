"""Analyse des coûts d'exécution (TCA) sur les ordres réels du compte Alpaca.

Pour chaque ordre exécuté : écart de mise en œuvre (implementation shortfall)
= (prix d'exécution - prix de décision) / prix de décision, signé pour qu'un
nombre POSITIF soit un COÛT (acheter plus cher / vendre moins cher que la
clôture qui a servi à décider). Il mélange deux choses : le mouvement de
marché entre la clôture et l'ouverture (aléatoire, de moyenne ~0 sur beaucoup
d'ordres) et le vrai coût d'exécution. On compare la moyenne pondérée à
l'hypothèse du backtest (5 bps ETF, 20 bps crypto) ; les frais crypto
d'Alpaca (activités CFEE) sont ajoutés.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LOG = ROOT / "data_cache" / "alpaca_mirror.json"
MODEL_BPS = {"etf": 5.0, "crypto": 20.0}


def _decision_prices() -> dict[str, dict]:
    """order_id -> {prix de décision, session} depuis le journal de réplication."""
    out: dict[str, dict] = {}
    try:
        runs = json.loads(LOG.read_text()).get("runs", [])
    except Exception:
        return out
    for r in runs:
        for o in r.get("results", []):
            if o.get("order_id"):
                out[o["order_id"]] = {"decision_price": o.get("decision_price"), "session": r.get("session"), "symbol": o["symbol"]}
    return out


def _fallback_price(symbol: str, session: str | None) -> float | None:
    """Ordres antérieurs à l'enregistrement du prix de décision : clôture Yahoo de la séance."""
    if not session:
        return None
    from ..data.yahoo import YahooConnector

    tk = symbol.replace("/USD", "-USD")
    try:
        d = YahooConnector().fetch(tk, refresh=False)
    except Exception:
        return None
    return d.get(session)


def tca() -> dict:
    from ..brokers.alpaca import AlpacaClient

    c = AlpacaClient()
    known = _decision_prices()
    orders = c._req("GET", "/v2/orders", {"status": "closed", "limit": 500, "direction": "desc"})
    fills = []
    for o in orders:
        if o.get("status") not in ("filled", "partially_filled") or not o.get("filled_avg_price"):
            continue
        if not (o.get("client_order_id") or "").startswith("grc-"):
            continue
        info = known.get(o["id"], {})
        session = info.get("session") or (o["client_order_id"][4:14] if len(o["client_order_id"]) > 14 else None)
        dp = info.get("decision_price") or _fallback_price(o["symbol"], session)
        if not dp:
            continue
        fill = float(o["filled_avg_price"])
        qty = float(o["filled_qty"])
        sign = 1 if o["side"] == "buy" else -1
        bps = sign * (fill / dp - 1) * 1e4
        crypto = "/" in o["symbol"]
        fills.append({"symbol": o["symbol"], "side": o["side"], "qty": qty, "decision_price": dp, "fill_price": fill,
                      "notional": qty * fill, "bps": bps, "cost_usd": bps / 1e4 * qty * fill, "kind": "crypto" if crypto else "etf",
                      "filled_at": o.get("filled_at"), "tif": o.get("time_in_force"), "session": session})
    fees = 0.0
    try:
        for a in c._req("GET", "/v2/account/activities/CFEE", {"page_size": 100}):
            px = float(a.get("price") or 0)
            fees += abs(float(a.get("qty") or 0)) * px
    except Exception:
        pass
    summary = {}
    for kind in ("etf", "crypto"):
        f = [x for x in fills if x["kind"] == kind]
        notional = sum(x["notional"] for x in f)
        cost = sum(x["cost_usd"] for x in f) + (fees if kind == "crypto" else 0.0)
        summary[kind] = {"n": len(f), "notional": notional, "cost_usd": cost,
                         "bps": cost / notional * 1e4 if notional else None, "model_bps": MODEL_BPS[kind],
                         "fees_usd": fees if kind == "crypto" else 0.0}
    return {"fills": sorted(fills, key=lambda x: x["filled_at"] or "", reverse=True), "summary": summary,
            "note": "Positif = coût. Mélange coût d'exécution et mouvement de marché clôture -> ouverture : ne devient fiable qu'après quelques dizaines d'ordres."}
