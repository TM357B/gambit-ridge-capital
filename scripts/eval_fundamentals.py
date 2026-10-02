"""Évaluation ridge prix + fondamentaux (Phase 2 étendue, chap. 4-8 Dixon).

Walk-forward purgé avec embargo, coûts 7 bps, comparaison systématique :
  1. momentum 126j (baseline)
  2. ridge prix seul (features techniques causales)
  3. ridge prix + fondamentaux visibles à date (règle lag 45j, anti-look-ahead n°1)
  4. test de permutation : cibles aléatoires -> l'edge doit disparaître.

Fenêtre honnête : à partir de la première date où des fondamentaux sont
visibles (FY2021 + 45j ~ février 2022) jusqu'à la fin des prix.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gambit_ridge.data.fundamentals import fundamentals_visible_at, load_fundamentals

ROOT = Path(__file__).resolve().parent.parent
HORIZON = 21
REBAL = 5
TRAIN = 504
TEST = 126
STEP = 126
EMBARGO = 10
COST_BPS = 7.0
LAM = 10.0
SEED = 42
PPY = 252


def load_prices() -> tuple[list[str], np.ndarray, dict[str, np.ndarray]]:
    path = ROOT / "data" / "equity_prices.csv"
    with open(path) as f:
        rows = list(csv.DictReader(f))
    dates = np.array([r["date"] for r in rows])
    tickers = [t for t in rows[0] if t != "date"]
    px = {tk: np.array([float(r[tk]) if r[tk] else np.nan for r in rows]) for tk in tickers}
    keep = ~np.isnan(sum(np.isnan(v) for v in px.values()).astype(bool))
    n_min = int(np.nanmin([np.isnan(v).sum() for v in px.values()]))
    first = int(np.argmax(~np.isnan(px[tickers[0]])))
    return tickers, dates, px, first


def price_features(arr: np.ndarray, t: int) -> list[float]:
    x = arr[: t + 1]
    out = []
    for lb in (21, 63, 126):
        out.append(float(x[-1] / x[-1 - lb] - 1.0) if len(x) > lb else 0.0)
    for lb in (20, 60):
        r = np.diff(x[-lb - 1:]) / x[-lb - 1:-1]
        out.append(float(np.std(r, ddof=1)) if len(r) > 2 else 0.0)
    return out


def funda_features(row, price: float) -> list[float]:
    if row is None or price is None or not np.isfinite(price):
        return [np.nan] * 6
    v = {k: (vv if vv is not None else np.nan) for k, vv in row.values.items()}
    fcf_yield = np.nan
    sh = v.get("shares_outstanding_total")
    fcf = v.get("free_cash_flow")
    if np.isfinite(sh) and np.isfinite(fcf) and price > 0:
        fcf_yield = fcf / (sh * price)
    return [
        v.get("croissance_revenue_yoy_pct", np.nan),
        v.get("marge_brute_pct", np.nan),
        v.get("marge_operationnelle_pct", np.nan),
        v.get("marge_nette_pct", np.nan),
        v.get("marge_fcf_pct", np.nan),
        fcf_yield,
    ]


def zscore(mat: np.ndarray) -> np.ndarray:
    out = np.empty_like(mat)
    for j in range(mat.shape[1]):
        col = mat[:, j]
        ok = np.isfinite(col)
        if ok.sum() < 2:
            out[:, j] = 0.0
            continue
        mu, sd = col[ok].mean(), col[ok].std(ddof=1)
        out[ok, j] = np.clip((col[ok] - mu) / (sd if sd > 1e-12 else 1.0), -3, 3)
        out[~ok, j] = 0.0
    return out


def build_features(tickers, dates, px, t, funda_rows, use_funda: bool):
    vis = fundamentals_visible_at(funda_rows, str(dates[t])) if use_funda else {}
    vis = {k.replace("-", "."): v for k, v in vis.items()}
    rows = []
    for tk in tickers:
        f = price_features(px[tk], t)
        if use_funda:
            f += funda_features(vis.get(tk), px[tk][t])
        rows.append(f)
    return zscore(np.array(rows))


def forward_target(tickers, px, t):
    out = []
    for tk in tickers:
        a, b = px[tk][t], px[tk][t + HORIZON]
        out.append(b / a - 1.0 if np.isfinite(a) and np.isfinite(b) else np.nan)
    return np.array(out)


def weights_from_scores(scores: np.ndarray, tickers, k: int) -> dict[str, float]:
    s = scores - scores.mean()
    order = np.argsort(s)
    longs = [(i, s[i]) for i in order[-k:] if s[i] > 0]
    shorts = [(i, s[i]) for i in order[:k] if s[i] < 0]
    w = {}
    ls = sum(v for _, v in longs)
    ss = sum(abs(v) for _, v in shorts)
    if ls > 0:
        for i, v in longs:
            w[tickers[i]] = 0.5 * v / ls
    if ss > 0:
        for i, v in shorts:
            w[tickers[i]] = 0.5 * v / ss
    return w


def ridge_fit(X, y, lam=LAM):
    d = X.shape[1]
    return np.linalg.solve(X.T @ X + lam * np.eye(d), X.T @ y)


def run_strategy(name, tickers, dates, px, funda_rows, mode, permute=False,
                 start_vis=None):
    rng = np.random.default_rng(SEED)
    n = len(dates)
    k = max(1, len(tickers) // 4)
    oos_rets = []
    folds = []
    prev_w: dict[str, float] = {}
    s = 0
    while s + TRAIN + TEST <= n:
        test0, test1 = s + TRAIN, s + TRAIN + TEST
        Xs, ys = [], []
        for d in range(s, test0 - HORIZON - EMBARGO, REBAL):
            if mode == "momentum":
                continue
            F = build_features(tickers, dates, px, d, funda_rows, mode == "ridge_funda")
            y = forward_target(tickers, px, d)
            if not np.isfinite(y).all():
                continue
            y = y - y.mean()
            for i in range(len(tickers)):
                Xs.append(F[i])
                ys.append(y[i])
        beta = None
        if mode != "momentum" and len(Xs) >= 100:
            X, y = np.array(Xs), np.array(ys)
            if permute:
                y = rng.permutation(y)
            beta = ridge_fit(X, y)
        fold_rets = []
        w: dict[str, float] = {}
        for t in range(test0, test1):
            if (t - test0) % REBAL == 0:
                if mode == "momentum":
                    scores = np.array([price_features(px[tk], t)[2] for tk in tickers])
                    w = weights_from_scores(scores, tickers, k)
                else:
                    if beta is None:
                        scores = np.array([price_features(px[tk], t)[2] for tk in tickers])
                    else:
                        F = build_features(tickers, dates, px, t, funda_rows,
                                           mode == "ridge_funda")
                        scores = F @ beta
                    w = weights_from_scores(scores, tickers, k)
                turn = sum(abs(w.get(tk, 0.0) - prev_w.get(tk, 0.0)) for tk in tickers)
                cost = turn * COST_BPS / 1e4
                prev_w = w
            r = 0.0
            for i, tk in enumerate(tickers):
                a, b = px[tk][t], px[tk][t + 1] if t + 1 < n else px[tk][t]
                if np.isfinite(a) and np.isfinite(b) and a > 0:
                    r += w.get(tk, 0.0) * (b / a - 1.0)
            if (t - test0) % REBAL == 0:
                r -= cost
            fold_rets.append(r)
        oos_rets.extend(fold_rets)
        sh = float(np.mean(fold_rets) / (np.std(fold_rets, ddof=1) + 1e-12) * np.sqrt(PPY))
        folds.append({"test": [str(dates[test0]), str(dates[test1 - 1])], "sharpe": sh})
        s += STEP
    r = np.array(oos_rets)
    sharpe = float(np.mean(r) / (np.std(r, ddof=1) + 1e-12) * np.sqrt(PPY))
    total = float(np.prod(1 + r) - 1)
    dd = float(np.max(1 - np.cumprod(1 + r) / np.maximum.accumulate(np.cumprod(1 + r))))
    return {"name": name, "sharpe": sharpe, "total_return": total, "max_dd": dd,
            "folds": folds}


def main():
    tickers, dates, px, first = load_prices()
    funda_path = ROOT / "data" / "fundamentals.csv"
    funda_rows = load_fundamentals(funda_path)
    tickers = [t for t in tickers if not np.all(np.isnan(px[t]))]
    vis_dates = [r.visible_from.isoformat() for r in funda_rows]
    start_vis = min(vis_dates)
    idx0 = int(np.searchsorted(dates, start_vis))
    dates = dates[idx0:]
    px = {tk: v[idx0:] for tk, v in px.items()}
    tickers = [tk for tk in tickers if np.isfinite(px[tk][:126]).all()]
    n = len(dates)
    print(f"Univers: {tickers} ({len(tickers)} actifs)")
    print(f"Fenêtre: {dates[0]} -> {dates[-1]} ({n} bars)")
    print(f"Folds: train {TRAIN}, test {TEST}, step {STEP}, embargo {EMBARGO}, "
          f"coûts {COST_BPS} bps\n")
    results = []
    for mode, label in (("momentum", "Momentum 126j (baseline)"),
                        ("ridge_price", "Ridge prix seul"),
                        ("ridge_funda", "Ridge prix + fondamentaux")):
        res = run_strategy(mode, tickers, dates, px, funda_rows, mode)
        results.append(res)
        print(f"{label:32s} Sharpe OOS {res['sharpe']:+.2f}  "
              f"rendement {res['total_return']*100:+.1f}%  maxDD {res['max_dd']*100:.1f}%")
        for f in res["folds"]:
            print(f"    fold {f['test'][0]} -> {f['test'][1]}: {f['sharpe']:+.2f}")
    print()
    perm = run_strategy("perm", tickers, dates, px, funda_rows, "ridge_funda", permute=True)
    print(f"{'Permutation cibles (anti-fuite)':32s} Sharpe OOS {perm['sharpe']:+.2f}  "
          f"(doit être ~0/négatif)")
    out = {"window": [str(dates[0]), str(dates[-1])], "tickers": tickers,
           "results": results, "permutation": perm["sharpe"]}
    import json
    (ROOT / "data" / "eval_fundamentals.json").write_text(json.dumps(out, indent=2))
    print("\nRésultats sauvés dans data/eval_fundamentals.json")


if __name__ == "__main__":
    main()
