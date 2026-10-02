"""Réplication du portefeuille papier sur le compte de SIMULATION Saxo.

Le paper trading décide à la clôture de New York ; la réplication passe les
ordres le lendemain pendant les heures de la bourse de Londres (instruments
UCITS cotés en USD) : c'est le délai réaliste d'un vrai gérant, et on mesure
ce qu'il coûte (écart entre le prix de décision et le prix d'exécution).

- longs : ETF / ETC UCITS ; courts : CFD sur ces ETF (vente à découvert d'ETF
  impossible pour un particulier) ; devises (FXE, FXY, UUP) : change au comptant
- poche crypto exclue (pas d'équivalent simple chez Saxo)
- filtre : on ne passe un ordre que si l'écart dépasse 0,5 % de la valeur du compte

Usage :
  python3 -m gambit_ridge.brokers.mirror setup     # recherche les instruments -> data/saxo_instruments.json
  python3 -m gambit_ridge.brokers.mirror plan      # ordres prévus, rien n'est envoyé (défaut)
  python3 -m gambit_ridge.brokers.mirror execute   # envoie les ordres (compte de simulation)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from .saxo import SaxoClient, SaxoError

ROOT = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = ROOT / "data" / "saxo_instruments.json"
LOG_PATH = ROOT / "data_cache" / "saxo_mirror.json"
MIN_TRADE = 0.005  # fraction de la valeur du compte

# ticker de la stratégie -> mots-clés UCITS à chercher chez Saxo (par ordre de préférence)
UCITS_CANDIDATES = {
    "SPY": ["CSPX", "SXR8"], "QQQ": ["CNDX", "SXRV"], "IWM": ["R2US", "ZPRR"],
    "EFA": ["EXUS", "XMWX"], "EEM": ["EIMI", "IS3N"], "EWJ": ["SJPA", "IJPN"], "VNQ": ["IUSP", "IQQ7"],
    "TLT": ["IDTL", "DTLA"], "IEF": ["IBTM", "CBU0"], "TIP": ["ITPS", "IUST"], "LQD": ["LQDE", "IBCD"],
    "HYG": ["IHYU", "IHYA"], "GLD": ["IGLN", "SGLN"], "SLV": ["PHAG", "ISLN"], "DBC": ["CMOD", "ICOM"],
    "USO": ["CRUD", "OILW"], "DBA": ["AIGA", "AGAP"],
}
# devises : (paire Saxo, signe) — long FXE = long EURUSD ; long FXY = short USDJPY ;
# long UUP (dollar contre panier, ~58 % euro) approximé par short EURUSD
FX_PROXIES = {"FXE": ("EURUSD", +1), "FXY": ("USDJPY", -1), "UUP": ("EURUSD", -1)}
EXCHANGE_PREF = ["xlon", "xams", "xetr", "xpar", "xmil", "xswx"]


def _pick(results: list[dict], asset_types: tuple[str, ...]) -> dict | None:
    cands = [r for r in results if r.get("AssetType") in asset_types]
    if not cands:
        return None

    def rank(r):
        sym = (r.get("Symbol") or "").lower()
        ex = sym.split(":")[-1] if ":" in sym else ""
        return (0 if r.get("CurrencyCode") == "USD" else 1, EXCHANGE_PREF.index(ex) if ex in EXCHANGE_PREF else 99)

    return sorted(cands, key=rank)[0]


def setup(client: SaxoClient | None = None) -> dict:
    """Recherche les instruments chez Saxo et écrit la correspondance (à relire)."""
    c = client or SaxoClient()
    mapping: dict[str, dict] = {}
    for tk, keywords in UCITS_CANDIDATES.items():
        entry: dict = {"long": None, "short": None, "keywords": keywords}
        for kw in keywords:
            res = c.search(kw)
            lng = _pick(res, ("Etf", "Etc", "Etn"))
            sht = _pick(res, ("CfdOnEtf", "CfdOnEtc", "CfdOnEtn"))
            if lng and not entry["long"]:
                entry["long"] = {k: lng.get(k) for k in ("Identifier", "AssetType", "Symbol", "Description", "CurrencyCode", "ExchangeId")}
            if sht and not entry["short"]:
                entry["short"] = {k: sht.get(k) for k in ("Identifier", "AssetType", "Symbol", "Description", "CurrencyCode", "ExchangeId")}
            if entry["long"] and entry["short"]:
                break
        mapping[tk] = entry
    for tk, (pair, sign) in FX_PROXIES.items():
        res = c.search(pair, asset_types="FxSpot")
        fx = next((r for r in res if (r.get("Symbol") or "").upper() == pair), res[0] if res else None)
        inst = {k: fx.get(k) for k in ("Identifier", "AssetType", "Symbol", "Description", "CurrencyCode")} if fx else None
        mapping[tk] = {"fx": inst, "sign": sign, "pair": pair}
    MAPPING_PATH.write_text(json.dumps({"generated": datetime.now().isoformat(timespec="seconds"), "instruments": mapping}, ensure_ascii=False, indent=1))
    return mapping


def _usd_rate(ccy: str) -> float:
    """Valeur en USD d'une unité de `ccy` (cache Yahoo)."""
    if ccy == "USD":
        return 1.0
    from ..market_functions import FX
    from ..data.yahoo import YahooConnector

    sym, usd_per = FX.get(ccy, (None, True))
    if not sym:
        raise SaxoError(f"devise non gérée : {ccy}")
    d = YahooConnector().fetch(sym, refresh=False)
    v = d[sorted(d)[-1]]
    return v if usd_per else 1.0 / v


def plan(client: SaxoClient | None = None) -> dict:
    """Calcule les ordres pour aligner le compte Saxo sur le portefeuille papier."""
    from ..paper import _load_journal

    c = client or SaxoClient()
    if not MAPPING_PATH.exists():
        raise SaxoError("Correspondance absente — lance d'abord : python3 -m gambit_ridge.brokers.mirror setup")
    mapping = json.loads(MAPPING_PATH.read_text())["instruments"]
    j = _load_journal()
    weights = {tk: p["weight"] for tk, p in j.get("positions", {}).items() if not tk.endswith("-USD")}
    bal = c.balance()
    nav_ccy = bal.get("Currency") or c.account().get("Currency") or "EUR"
    nav_usd = float(bal.get("TotalValue", 0.0)) * _usd_rate(nav_ccy)
    held: dict[tuple, float] = {}
    for p in c.net_positions():
        b = p.get("NetPositionBase", {})
        held[(b.get("Uic"), b.get("AssetType"))] = held.get((b.get("Uic"), b.get("AssetType")), 0.0) + float(b.get("Amount", 0.0))

    targets: dict[tuple, dict] = {}
    unmapped = []
    for tk, w in weights.items():
        m = mapping.get(tk)
        if not m:
            unmapped.append(tk)
            continue
        if "fx" in m:
            if not m["fx"]:
                unmapped.append(tk)
                continue
            inst, amount_sign = m["fx"], m["sign"] * (1 if w > 0 else -1)
            pair = m["pair"]
            base = pair[:3]
            # montant en devise de base : notionnel USD / valeur USD d'une unité de base
            units = abs(w) * nav_usd / _usd_rate(base)
            key = (inst["Identifier"], inst["AssetType"])
            t = targets.setdefault(key, {"tickers": [], "units": 0.0, "symbol": inst["Symbol"], "ccy": inst.get("CurrencyCode")})
            t["tickers"].append(tk)
            t["units"] += amount_sign * units
            continue
        inst = m["long"] if w > 0 else m["short"]
        if not inst:
            unmapped.append(tk)
            continue
        q = c.quote(inst["Identifier"], inst["AssetType"])
        px = q.get("Mid") or q.get("Ask") or q.get("Bid")
        if not px:
            unmapped.append(tk)
            continue
        px_usd = float(px) * _usd_rate(inst.get("CurrencyCode") or "USD")
        units = round(abs(w) * nav_usd / px_usd)
        key = (inst["Identifier"], inst["AssetType"])
        targets[key] = {"tickers": [tk], "units": units if w > 0 else -units, "symbol": inst["Symbol"], "price": float(px),
                        "ccy": inst.get("CurrencyCode"), "price_usd": px_usd}

    orders = []
    for key in set(targets) | set(held):
        tgt = targets.get(key, {}).get("units", 0.0)
        cur = held.get(key, 0.0)
        diff = tgt - cur
        info = targets.get(key, {"tickers": ["(hors stratégie)"], "symbol": str(key[0])})
        notional = abs(diff) * info.get("price_usd", 0.0) if key[1] != "FxSpot" else abs(diff) * _usd_rate(info.get("symbol", "USD")[:3] if info.get("symbol") else "USD")
        if abs(diff) < 1 or (nav_usd and notional / nav_usd < MIN_TRADE and tgt != 0):
            continue
        orders.append({"uic": key[0], "asset_type": key[1], "symbol": info.get("symbol"), "tickers": info["tickers"],
                       "buy_sell": "Buy" if diff > 0 else "Sell", "amount": abs(round(diff, 2 if key[1] == "FxSpot" else 0)),
                       "current": cur, "target": tgt, "notional_usd": round(notional, 2)})
    return {"nav_usd": round(nav_usd, 2), "account_ccy": nav_ccy, "orders": sorted(orders, key=lambda o: -o["notional_usd"]),
            "unmapped": unmapped, "excluded": sorted(tk for tk in j.get("positions", {}) if tk.endswith("-USD"))}


def execute(dry_run: bool = True) -> dict:
    c = SaxoClient()
    p = plan(c)
    results = []
    for o in p["orders"]:
        body = c.order_body(o["uic"], o["asset_type"], o["buy_sell"], o["amount"])
        try:
            r = c.precheck(body) if dry_run else c.place(body)
            results.append({**o, "status": "vérifié" if dry_run else "envoyé", "response": r})
        except SaxoError as exc:
            results.append({**o, "status": "refusé", "error": str(exc)})
    run = {"at": datetime.now().isoformat(timespec="seconds"), "dry_run": dry_run, **p, "results": results}
    LOG_PATH.parent.mkdir(exist_ok=True)
    hist = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else []
    hist.append(run)
    LOG_PATH.write_text(json.dumps(hist[-200:], ensure_ascii=False, indent=1, default=str))
    return run


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "plan"
    try:
        if cmd == "setup":
            m = setup()
            for tk, e in m.items():
                if "fx" in e:
                    print(f"{tk:<5} change  {e['fx']['Symbol'] if e['fx'] else 'INTROUVABLE'} (signe {e['sign']:+d})")
                else:
                    lo, sh = e["long"], e["short"]
                    print(f"{tk:<5} long {lo['Symbol'] + ' ' + lo['AssetType'] if lo else 'INTROUVABLE':<28} court {sh['Symbol'] + ' ' + sh['AssetType'] if sh else 'INTROUVABLE'}")
            print(f"\nCorrespondance écrite dans {MAPPING_PATH} — relis-la avant d'exécuter.")
        elif cmd in ("plan", "execute"):
            r = execute(dry_run=cmd == "plan")
            print(f"Compte : {r['nav_usd']:,.0f} USD ({r['account_ccy']}) · {'ESSAI (rien envoyé)' if r['dry_run'] else 'ORDRES ENVOYÉS'}")
            for o in r["results"]:
                print(f"  {o['buy_sell']:<4} {o['amount']:>12,.2f} {o['symbol']:<14} {o['asset_type']:<9} {'/'.join(o['tickers']):<10} ~{o['notional_usd']:>10,.0f} $  {o['status']} {o.get('error', '')[:120]}")
            if r["unmapped"]:
                print("  Non répliqués :", ", ".join(r["unmapped"]))
            print("  Exclus (crypto) :", ", ".join(r["excluded"]) or "—")
        else:
            print(__doc__)
        return 0
    except SaxoError as exc:
        print("✗", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
