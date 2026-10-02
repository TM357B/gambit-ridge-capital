"""Santé de la stratégie : la performance réelle est-elle dans la zone normale ?

Référence : le backtest quotidien du FONDS COMPLET tel qu'il tourne en
production (90 % poche ETF retenue + 10 % poche crypto retenue, coûts inclus),
calculé par `build_reference()` et mis en cache dans data/fund_backtest.json.

Pour chaque horizon h (5, 20, 60, 120 séances), on compare le rendement et
le pire drawdown réels sur les h dernières séances à la distribution de
toutes les fenêtres de h séances du backtest. Verdict :
- « dans la norme »   : entre les centiles 5 et 95
- « à surveiller »    : entre 1-5 ou 95-99
- « hors norme »      : au-delà du centile 1 ou 99 -> alerte
Une stratégie en « hors norme » durable ne se comporte plus comme testé :
c'est le signal pour la réexaminer — pas une mauvaise semaine isolée.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
REF_PATH = ROOT / "data" / "fund_backtest.json"
HORIZONS = (5, 20, 60, 120)
MIN_DAYS = 5


def build_reference() -> dict:
    """Backtest quotidien du fonds 90/10 (sur les séances ETF), coûts inclus."""
    from ..data.yahoo import load_crypto_universe, load_etf_universe
    from ..research.backtest import simulate
    from ..research.evaluate import CRYPTO_COST_BPS, ETF_COST_BPS, WARMUP, crypto_candidates, etf_candidates
    from ..research.production import CRYPTO_SHARE, ETF_SHARE

    ed, ep = load_etf_universe()
    cd, cp = load_crypto_universe()
    E = etf_candidates(ed, ep, include_ml=False)["60/40 + couche tendance"]["W"]
    C = crypto_candidates(cd, cp)["Tendance crypto long-only"]["W"]
    re = simulate(np.column_stack([ep[t] for t in ep]), E, ETF_COST_BPS).returns
    rc = simulate(np.column_stack([cp[t] for t in cp]), C, CRYPTO_COST_BPS).returns
    ceq = np.cumprod(1 + rc)
    cdates, edates = np.array(cd), np.array(ed)
    idx = np.searchsorted(cdates, edates, side="right") - 1
    eqc = np.where(idx >= 0, ceq[np.clip(idx, 0, None)], np.nan)
    r_c = np.zeros(len(edates))
    r_c[1:] = eqc[1:] / eqc[:-1] - 1
    r_c = np.nan_to_num(r_c)
    start = max(WARMUP, int(np.argmax(idx >= WARMUP)))  # les deux poches actives
    r = ETF_SHARE * re + CRYPTO_SHARE * r_c
    ref = {"generated": date.today().isoformat(), "allocation": {"etf": ETF_SHARE, "crypto": CRYPTO_SHARE},
           "dates": [str(x) for x in edates[start:]], "returns": [round(float(x), 7) for x in r[start:]]}
    REF_PATH.write_text(json.dumps(ref))
    return ref


def _reference() -> dict:
    if not REF_PATH.exists():
        return build_reference()
    return json.loads(REF_PATH.read_text())


def _windows(r: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Rendement cumulé et pire drawdown de toutes les fenêtres de h séances."""
    eq = np.concatenate([[1.0], np.cumprod(1 + r)])
    rets, dds = [], []
    for i in range(0, len(r) - h + 1):
        w = eq[i:i + h + 1] / eq[i]
        rets.append(w[-1] - 1)
        dds.append((w / np.maximum.accumulate(w) - 1).min())
    return np.array(rets), np.array(dds)


def _verdict(pct: float) -> str:
    if pct < 1 or pct > 99:
        return "hors norme"
    if pct < 5 or pct > 95:
        return "à surveiller"
    return "dans la norme"


def health() -> dict:
    from ..paper import _load_journal

    j = _load_journal()
    hist = j.get("equity_history", [])
    live = np.array([e["day_pnl"] / (e["equity"] - e["day_pnl"]) for e in hist if e["equity"] - e["day_pnl"] > 0])
    ref = _reference()
    r = np.array(ref["returns"])
    ann_vol_ref = float(np.std(r, ddof=1) * np.sqrt(252))
    out = {"n_days": int(len(live)), "reference": {"start": ref["dates"][0], "end": ref["dates"][-1], "vol": ann_vol_ref,
           "sharpe": float(np.mean(r) / np.std(r) * np.sqrt(252))}, "horizons": [], "status": "trop tôt"}
    if len(live) < MIN_DAYS:
        out["message"] = f"Il faut au moins {MIN_DAYS} séances réelles pour juger ({len(live)} pour l'instant)."
        return out
    worst = "dans la norme"
    order = ["dans la norme", "à surveiller", "hors norme"]
    for h in HORIZONS:
        if len(live) < h:
            continue
        R, D = _windows(r, h)
        w = np.concatenate([[1.0], np.cumprod(1 + live[-h:])])
        lr, ld = float(w[-1] - 1), float((w / np.maximum.accumulate(w) - 1).min())
        pr = float((R < lr).mean() * 100)
        pd = float((D < ld).mean() * 100)
        v = max(_verdict(pr), "dans la norme" if pd >= 5 else ("à surveiller" if pd >= 1 else "hors norme"), key=order.index)
        worst = max(worst, v, key=order.index)
        out["horizons"].append({"h": h, "return": lr, "return_pct": pr, "return_band": [float(np.percentile(R, 5)), float(np.percentile(R, 95))],
                                "drawdown": ld, "drawdown_pct": pd, "drawdown_p5": float(np.percentile(D, 5)), "verdict": v})
    live_vol = float(np.std(live[-60:], ddof=1) * np.sqrt(252)) if len(live) >= 10 else None
    out["live_vol"] = live_vol
    out["status"] = worst
    return out
