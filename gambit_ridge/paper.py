"""Paper trading v2 : portefeuille virtuel piloté par la stratégie retenue.

Stratégie : gambit_ridge/research/production.py (socle 60/40 + couche
tendance sur 20 ETF, poche crypto tendance long-only), sélectionnée par le
banc d'évaluation sur la période de développement uniquement.

À chaque exécution (au plus une fois par jour) :
1. Prix de clôture réels (Yahoo : ETF + crypto), barre du jour exclue
2. P&L de chaque position depuis le DERNIER prix enregistré (corrige la v1
   qui ne comptait qu'un jour de rendement même après un week-end)
3. Dérive des poids avec les prix, puis rebalancement vers la cible avec
   filtre anti micro-trades ; coûts déduits (5 bps ETF, 20 bps crypto)
4. Journal persistant (data_cache/paper_journal_v2.json)

Aucune connexion courtier : tout est simulé localement à partir de prix réels.
Le journal v1 (FRED/Binance, désalignements de dates) est archivé tel quel.
"""
from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

import numpy as np

_RUN_LOCK = threading.Lock()

CACHE = Path(__file__).resolve().parent.parent / "data_cache"
JOURNAL_PATH = CACHE / "paper_journal_v2.json"
LEGACY_PATH = CACHE / "paper_journal.json"
INITIAL_CAPITAL = 1_000_000.0
STRATEGY_LABEL = "60/40 + couche tendance (90 %) · crypto tendance long-only (10 %)"

# Filtre anti micro-trades (identique au backtest de sélection)
BUFFER_REL = 0.25
BUFFER_ABS = 0.005
COST_BPS = {"etf": 5.0, "crypto": 20.0}


def _load_journal() -> dict:
    if JOURNAL_PATH.exists():
        try:
            j = json.loads(JOURNAL_PATH.read_text())
            # migration : les premières entrées étaient datées au jour calendaire
            # de l'exécution ; on les date à la séance de prix utilisée
            for e in j.get("equity_history", []):
                pd = e.get("price_dates") or {}
                if pd and "attrib" not in e and e["date"] != max(pd.values()):
                    e["date"] = max(pd.values())
            return j
        except Exception:
            JOURNAL_PATH.replace(JOURNAL_PATH.with_suffix(".corrupt"))
    return {
        "version": 2,
        "strategy": STRATEGY_LABEL,
        "initial_capital": INITIAL_CAPITAL,
        "started": None,
        "equity_history": [],
        "positions": {},
        "trades": [],
        "last_run": None,
        "costs_paid": 0.0,
    }


def _save_journal(j: dict) -> None:
    JOURNAL_PATH.parent.mkdir(exist_ok=True)
    tmp = JOURNAL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(j, indent=2, ensure_ascii=False))
    tmp.replace(JOURNAL_PATH)


def _mark_to_market(j: dict, prices: dict[str, float], skip: set[str] = frozenset()) -> tuple[float, float, dict[str, float]]:
    """P&L depuis le dernier prix enregistré, par position ; met à jour les
    poids dérivés. Les tickers de `skip` (prix suspects) ne sont pas revalorisés."""
    equity_before = j["equity_history"][-1]["equity"] if j["equity_history"] else INITIAL_CAPITAL
    attrib: dict[str, float] = {}
    growth: dict[str, float] = {}
    for tk, pos in j["positions"].items():
        p_now = prices.get(tk)
        p_last = pos.get("last_price")
        ret = 0.0
        if p_now and p_last and tk not in skip:
            ret = p_now / p_last - 1.0
            pos["last_return"] = round(ret, 6)
            pos["last_price"] = p_now
        attrib[tk] = pos["weight"] * equity_before * ret
        growth[tk] = pos["weight"] * (1.0 + ret)
    equity = equity_before + sum(attrib.values())
    # dérive : nouveau poids = valeur de la position / nouvelle équity
    for tk, pos in j["positions"].items():
        pos["weight"] = growth[tk] * equity_before / equity if equity > 0 else 0.0
    return equity_before, equity, attrib


def _session_dates() -> dict[str, str]:
    """Dernière séance close par poche (sans réseau)."""
    from .data.yahoo import complete_cutoff

    return {"etf": complete_cutoff("SPY"), "crypto": complete_cutoff("BTC-USD")}


def needs_run(j: dict | None = None) -> bool:
    """Vrai si une nouvelle séance est close depuis la dernière exécution.
    Si la source n'a pas encore publié la séance attendue, on ne retente
    qu'au bout de 2 h (évite de recalculer à chaque ouverture)."""
    import time as _t

    j = j or _load_journal()
    done = j.get("last_price_dates") or {}
    pending = any(done.get(k, "") < v for k, v in _session_dates().items())
    if not pending:
        return False
    return _t.time() - j.get("last_attempt", 0) > 2 * 3600 or not j.get("last_attempt_pending")


def run_paper_day(force: bool = False, full_rebalance: bool = False) -> dict:
    """Applique la stratégie au portefeuille papier dès qu'une nouvelle séance
    est close (ETF après 16 h 30 New York, crypto après minuit UTC).
    Ne bloque jamais : si un calcul est déjà en cours, renvoie l'état courant."""
    today = date.today().isoformat()
    j = _load_journal()
    if not force and not needs_run(j):
        return summary(j)
    if not _RUN_LOCK.acquire(blocking=False):
        s = summary(j)
        s["loading"] = True
        return s
    import fcntl

    JOURNAL_PATH.parent.mkdir(exist_ok=True)
    lock_file = open(JOURNAL_PATH.with_suffix(".lock"), "w")
    try:  # verrou inter-processus : serveur de l'app et tâche planifiée
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        _RUN_LOCK.release()
        s = summary(j)
        s["loading"] = True
        return s
    try:
        j = _load_journal()
        if not force and not needs_run(j):
            return summary(j)
        from .research.production import target_portfolio

        target = target_portfolio(refresh=True)
        prices = target["prices"]
        if not target["weights"]:
            s = summary(j)
            s["warning"] = "Prix indisponibles (Yahoo injoignable) — vérifie ta connexion puis relance."
            return s
        if j.get("started") is None:
            j["started"] = today
        blocked, suspect = set(target.get("blocked", [])), set(target.get("suspect", []))

        weights_before = {tk: round(p["weight"], 5) for tk, p in j["positions"].items()}
        equity_before, equity, attrib = _mark_to_market(j, prices, skip=suspect)
        day_pnl = equity - equity_before

        # rebalancement avec filtre anti micro-trades + coûts ; poche bloquée = on garde
        costs = 0.0
        held = {tk: p["weight"] for tk, p in j["positions"].items()}
        for tk in sorted(set(held) | set(target["weights"])):
            if tk in blocked:
                continue
            old_w = held.get(tk, 0.0)
            tgt = target["weights"].get(tk, 0.0)
            # full_rebalance : changement d'allocation décidé -> on aligne tout, sans filtre
            small_move = abs(tgt - old_w) <= (1e-4 if full_rebalance else max(BUFFER_REL * abs(tgt), BUFFER_ABS))
            closing = tgt == 0.0 and old_w != 0.0  # toujours solder une position sortie
            if small_move and not closing:
                continue
            kind = target["kind"].get(tk, "etf")
            cost = abs(tgt - old_w) * equity * COST_BPS[kind] / 1e4
            costs += cost
            attrib[tk] = attrib.get(tk, 0.0) - cost
            j["trades"].append({
                "date": today, "ticker": tk, "kind": kind,
                "old_weight": round(old_w, 4), "new_weight": round(tgt, 4),
            })
            if abs(tgt) < 1e-6:
                j["positions"].pop(tk, None)
            else:
                pos = j["positions"].setdefault(tk, {"entry_date": today})
                if np.sign(tgt) != np.sign(old_w):
                    pos["entry_date"] = today
                pos.update({"weight": tgt, "kind": kind, "last_price": prices.get(tk), "last_return": pos.get("last_return", 0.0)})
        equity -= costs
        day_pnl -= costs
        j["costs_paid"] = round(j.get("costs_paid", 0.0) + costs, 2)
        j["trades"] = j["trades"][-500:]

        price_dates = target.get("dates", {})
        entry_date = max(price_dates.values()) if price_dates else today
        peak = max([e["equity"] for e in j["equity_history"]] + [INITIAL_CAPITAL])
        entry = {
            "date": entry_date,
            "equity": round(equity, 2),
            "day_pnl": round(day_pnl, 2),
            "costs": round(costs, 2),
            "gross": round(sum(abs(p["weight"]) for p in j["positions"].values()), 4),
            "net": round(sum(p["weight"] for p in j["positions"].values()), 4),
            "n_positions": len(j["positions"]),
            "drawdown": round(max(0.0, 1.0 - equity / peak), 6),
            "price_dates": price_dates,
            "attrib": {tk: round(v, 2) for tk, v in attrib.items() if abs(v) >= 0.01},
            "weights": weights_before,  # poids détenus pendant la séance (attribution)
        }
        hist = j["equity_history"]
        if hist and hist[-1]["date"] == entry_date:  # deux exécutions sur la même séance : on fusionne
            prev = hist.pop()
            entry["day_pnl"] = round(prev["day_pnl"] + day_pnl, 2)
            entry["costs"] = round(prev.get("costs", 0.0) + costs, 2)
            merged = dict(prev.get("attrib", {}))
            for tk, v in entry["attrib"].items():
                merged[tk] = round(merged.get(tk, 0.0) + v, 2)
            entry["attrib"] = merged
        hist.append(entry)
        j["equity_history"] = hist[-2000:]
        if j.get("strategy") != STRATEGY_LABEL:  # changement d'allocation : tracé dans le journal
            j.setdefault("allocation_changes", []).append({"date": today, "from": j.get("strategy"), "to": STRATEGY_LABEL})
            j["strategy"] = STRATEGY_LABEL
        j["last_run"] = today
        import time as _t

        done = j.get("last_price_dates") or {}
        j["last_price_dates"] = {k: max(price_dates.get(k, ""), done.get(k, "")) for k in ("etf", "crypto")}
        j["last_attempt"] = _t.time()
        # séance attendue pas encore publiée par la source -> nouvelle tentative plus tard
        j["last_attempt_pending"] = any(j["last_price_dates"][k] < v for k, v in _session_dates().items())
        j["last_detail"] = target.get("detail", {})
        j["errors"] = {k: v for k, v in target.items() if k.endswith("_error")}
        j["quality"] = target.get("quality", {})
        j["crosscheck"] = target.get("crosscheck", {})
        j["blocked"] = sorted(blocked)
        _save_journal(j)
        return summary(j)
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
        _RUN_LOCK.release()


def summary(j: dict | None = None) -> dict:
    from .data.yahoo import CRYPTO_UNIVERSE, ETF_UNIVERSE, asset_class_of
    from .research.production import ETF_SHARE

    names = {s: n for m in ETF_UNIVERSE.values() for s, n in m.items()} | CRYPTO_UNIVERSE
    if j is None:
        j = _load_journal()
    hist = j.get("equity_history", [])
    init = j.get("initial_capital", INITIAL_CAPITAL)
    equity = hist[-1]["equity"] if hist else init
    peak = max([e["equity"] for e in hist] + [init])
    rets = [h["day_pnl"] / (h["equity"] - h["day_pnl"]) for h in hist if h["equity"] - h["day_pnl"] > 0]
    sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(252)) if len(rets) >= 20 and np.std(rets) > 0 else None
    detail = j.get("last_detail", {})
    positions = []
    for tk, p in j.get("positions", {}).items():
        positions.append({
            **p,
            "ticker": tk,
            "name": names.get(tk, tk),
            "asset_class": asset_class_of(tk),
            "value": round(p["weight"] * equity, 2),
            "signal": detail.get(tk, {}).get("signal"),
            "core": round(ETF_SHARE * detail.get(tk, {}).get("poids_socle", 0.0), 4),
            "vol": detail.get(tk, {}).get("vol"),
        })
    positions.sort(key=lambda p: -abs(p["weight"]))
    by_class: dict[str, float] = {}
    for p in positions:
        by_class[p["asset_class"]] = by_class.get(p["asset_class"], 0.0) + p["weight"]
    return {
        "strategy": STRATEGY_LABEL,
        "initial_capital": init,
        "equity": round(equity, 2),
        "total_return": round(equity / init - 1.0, 6),
        "current_drawdown": round(max(0.0, 1.0 - equity / peak), 6),
        "n_days": len(hist),
        "sharpe_annualized": round(sharpe, 3) if sharpe is not None else None,
        "costs_paid": j.get("costs_paid", 0.0),
        "gross": round(sum(abs(p["weight"]) for p in positions), 4),
        "net": round(sum(p["weight"] for p in positions), 4),
        "exposure_by_class": {k: round(v, 4) for k, v in by_class.items()},
        "positions": positions,
        "recent_trades": j.get("trades", [])[-40:],
        "equity_history": hist[-500:],
        "started": j.get("started"),
        "last_run": j.get("last_run"),
        "errors": j.get("errors", {}),
        "quality": j.get("quality", {}),
        "crosscheck": j.get("crosscheck", {}),
        "blocked": j.get("blocked", []),
        "last_price_dates": j.get("last_price_dates", {}),
        "legacy_journal": LEGACY_PATH.exists(),
    }
