"""Réplication du portefeuille papier sur le compte PAPER Alpaca.

Mêmes instruments que la stratégie (SPY, TLT… et BTC/USD…), donc on mesure
uniquement ce que la simulation ignore : exécution réelle (prix d'ouverture,
glissement), arrondis à l'action entière, titres non empruntables.

Exécution :
- actions/ETF : ordres « à l'ouverture » (opg) envoyés entre 19 h et 9 h 25
  (heure de New York), ordres « jour » si le marché est ouvert ; sinon on attend
  le passage suivant (8 h 30 heure de Paris)
- crypto : ordres immédiats (gtc), positions longues uniquement
- une position ne peut pas passer de long à court en un ordre : on la solde,
  le côté opposé est ouvert au passage suivant
- filtre : pas d'ordre si l'écart est inférieur à 0,5 % du compte

Mode : « essai » par défaut (rien n'est envoyé). Activer : `... alpaca_mirror enable`.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .alpaca import AlpacaClient, AlpacaError, has_credentials

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "data_cache" / "broker.json"
LOG = ROOT / "data_cache" / "alpaca_mirror.json"
MIN_TRADE = 0.005


def _config() -> dict:
    try:
        return json.loads(CONFIG.read_text()).get("alpaca", {})
    except Exception:
        return {}


def set_live(on: bool) -> None:
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    cfg.setdefault("alpaca", {})["live_orders"] = on
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1))


def _log() -> dict:
    try:
        return json.loads(LOG.read_text())
    except Exception:
        return {"runs": [], "snapshots": []}


def _symbol(tk: str) -> str:
    return tk.replace("-USD", "/USD") if tk.endswith("-USD") else tk


def _equity_tif(clock: dict) -> str | None:
    if clock.get("is_open"):
        return "day"
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() < 5 and (now.hour >= 19 or (now.hour, now.minute) < (9, 25)):
        return "opg"
    if now.weekday() >= 5:  # week-end : les opg du lundi sont acceptés
        return "opg"
    return None


def plan(c: AlpacaClient | None = None) -> dict:
    from ..paper import _load_journal

    c = c or AlpacaClient()
    j = _load_journal()
    acct = c.account()
    equity = float(acct["equity"])
    held = {p["symbol"].replace("/", ""): float(p["qty"]) for p in c.positions()}
    clock = c.clock()
    tif_eq = _equity_tif(clock)
    orders, skipped = [], []
    targets = {}
    for tk, pos in j.get("positions", {}).items():
        price = pos.get("last_price")
        if not price:
            skipped.append(f"{tk} : prix inconnu")
            continue
        sym = _symbol(tk)
        crypto = tk.endswith("-USD")
        w = pos["weight"]
        try:
            a = c.asset(sym)
        except AlpacaError:
            skipped.append(f"{tk} : instrument absent chez Alpaca")
            continue
        if not a.get("tradable"):
            skipped.append(f"{tk} : non négociable chez Alpaca")
            continue
        if crypto and w < 0:
            skipped.append(f"{tk} : vente à découvert crypto impossible")
            continue
        if w < 0 and not (a.get("shortable") and a.get("easy_to_borrow")):
            skipped.append(f"{tk} : pas empruntable pour une vente à découvert")
            continue
        qty = round(w * equity / price, 6) if crypto else int(round(w * equity / price))
        targets[sym.replace("/", "")] = {"symbol": sym, "qty": qty, "price": price, "crypto": crypto, "ticker": tk}
    for key in set(targets) | set(held):
        t = targets.get(key)
        cur = held.get(key, 0.0)
        tgt = t["qty"] if t else 0.0
        sym = t["symbol"] if t else (key[:-3] + "/USD" if key.endswith("USD") and len(key) > 5 else key)
        crypto = t["crypto"] if t else sym.endswith("/USD")
        price = t["price"] if t else None
        note = ""
        if cur and tgt and (cur > 0) != (tgt > 0):  # changement de sens : on solde d'abord
            tgt, note = 0.0, "changement de sens : solde maintenant, ouverture au prochain passage"
        diff = tgt - cur
        if abs(diff) < (1e-6 if crypto else 1):
            continue
        if price and tgt != 0 and abs(diff) * price < MIN_TRADE * equity:
            continue
        orders.append({"symbol": sym, "side": "buy" if diff > 0 else "sell", "qty": abs(round(diff, 6)), "current": cur, "target": tgt,
                       "decision_price": price,
                       "notional": round(abs(diff) * price, 2) if price else None, "tif": "gtc" if crypto else tif_eq, "note": note})
    return {"equity": equity, "clock": {"is_open": clock.get("is_open"), "next_open": clock.get("next_open")},
            "orders": sorted(orders, key=lambda o: -(o["notional"] or 0)), "skipped": skipped,
            "session": (j.get("last_price_dates") or {}).get("etf")}


def run(live: bool | None = None) -> dict:
    from ..paper import summary

    c = AlpacaClient()
    live = _config().get("live_orders", False) if live is None else live
    p = plan(c)
    results = []
    if live:
        for o in c.open_orders():  # ordres « grc » restés en attente d'une décision précédente
            if (o.get("client_order_id") or "").startswith("grc-"):
                try:
                    c.cancel(o["id"])
                except AlpacaError:
                    pass
    for o in p["orders"]:
        if not o["tif"]:
            results.append({**o, "status": "reporté (hors fenêtre d'envoi)"})
            continue
        if not live:
            results.append({**o, "status": "essai"})
            continue
        cid = f"grc-{p['session']}-{o['symbol'].replace('/', '')}-{o['side']}-{datetime.now():%H%M}"[:48]
        try:
            r = c.submit(o["symbol"], o["qty"], o["side"], o["tif"], cid)
            results.append({**o, "status": "envoyé", "order_id": r.get("id")})
        except AlpacaError as exc:
            results.append({**o, "status": "refusé", "error": str(exc)})
    log = _log()
    log["runs"].append({"at": datetime.now().isoformat(timespec="seconds"), "live": live, **p, "results": results})
    log["runs"] = log["runs"][-200:]
    today = datetime.now().date().isoformat()
    snap = {"date": today, "alpaca_equity": p["equity"], "paper_equity": summary()["equity"]}
    log["snapshots"] = [s for s in log.get("snapshots", []) if s["date"] != today] + [snap]
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1, default=str))
    return {"live": live, **p, "results": results}


def status() -> dict:
    log = _log()
    return {"configured": has_credentials(), "live_orders": _config().get("live_orders", False),
            "last_run": log["runs"][-1] if log["runs"] else None, "snapshots": log.get("snapshots", [])}


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "plan"
    if cmd == "enable":
        set_live(True)
        print("✓ Envoi des ordres activé (compte paper Alpaca).")
        return 0
    if cmd == "disable":
        set_live(False)
        print("✓ Envoi des ordres désactivé (mode essai).")
        return 0
    try:
        r = run(live=True if cmd == "execute" else (False if cmd == "plan" else None))
    except AlpacaError as exc:
        print("✗", exc)
        return 1
    print(f"Compte paper Alpaca : {r['equity']:,.0f} $ · marché {'ouvert' if r['clock']['is_open'] else 'fermé'} · {'ORDRES ENVOYÉS' if r['live'] else 'ESSAI (rien envoyé)'}")
    for o in r["results"]:
        print(f"  {o['side']:<4} {o['qty']:>12,.4f} {o['symbol']:<9} ~{(o['notional'] or 0):>10,.0f} $ {str(o['tif']):<4} {o['status']} {o.get('error', '')[:100]} {o['note']}")
    for s in r["skipped"]:
        print("  ·", s)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
