"""Tableau de bord du risque du portefeuille ACTUEL (paper v2).

- risque ex-ante : covariance EWMA (demi-vie 60 j) -> vol annualisée,
  contribution au risque par ligne et par classe d'actifs
- VaR / CVaR 1 jour à 95 % et 99 % : simulation historique (500 dernières
  séances rejouées avec les poids d'aujourd'hui) + VaR paramétrique
- corrélations entre classes d'actifs (1 an)
- scénarios de crise : les poids d'aujourd'hui appliqués aux mouvements réels
  de chaque épisode (cryptos absentes avant 2017 : signalé)
- limites de risque et alertes de dépassement
"""

from __future__ import annotations

import numpy as np

from .data.yahoo import CRYPTO_UNIVERSE, ETF_UNIVERSE, YahooConnector, asset_class_of

SCENARIOS = [
    ("Faillite de Lehman (2008)", "2008-09-01", "2008-11-20"),
    ("Crise de la dette euro (2011)", "2011-07-22", "2011-10-03"),
    ("Taper tantrum (2013)", "2013-05-21", "2013-06-24"),
    ("Dévaluation chinoise (2015)", "2015-08-10", "2015-08-25"),
    ("Volmageddon (fév. 2018)", "2018-01-26", "2018-02-08"),
    ("Krach de fin 2018", "2018-10-01", "2018-12-24"),
    ("COVID (fév.-mars 2020)", "2020-02-19", "2020-03-23"),
    ("Inflation et hausse des taux (2022)", "2022-01-03", "2022-10-12"),
    ("Faillite de SVB (2023)", "2023-03-08", "2023-03-15"),
]

LIMITS = {
    "vol_ex_ante": (0.12, "Volatilité prévue du portefeuille"),
    "var99": (0.025, "VaR 99 % à 1 jour (historique)"),
    "gross": (2.0, "Exposition brute"),
    "net": (1.0, "Exposition nette"),
    "max_position": (0.35, "Plus grosse ligne"),
    "crypto": (0.25, "Poids total crypto"),
    "drawdown": (0.15, "Drawdown du portefeuille"),
}


def risk_report() -> dict:
    from .paper import _load_journal, summary

    s = summary()
    j = _load_journal()
    w = {p["ticker"]: p["weight"] for p in s["positions"]}
    if not w:
        return {"error": "portefeuille vide — le paper trading n'a pas encore tourné"}
    tickers = sorted(w)
    conn = YahooConnector()
    raw = {t: conn.fetch(t, refresh=False) for t in set(tickers) | {"SPY"}}
    # calendrier des séances ETF ; les cryptos (7 j/7) sont échantillonnées sur ces dates
    etf = [t for t in tickers if not t.endswith("-USD")]
    dates = sorted(set.intersection(*(set(raw[t]) for t in etf))) if etf else sorted(set.intersection(*(set(raw[t]) for t in tickers)))
    cutoff = max(s.get("last_price_dates", {}).values() or [dates[-1]])
    dates = [d for d in dates if d <= cutoff]

    def series(t):
        r = raw[t]
        last, out = np.nan, []
        for d in dates:  # dernier prix connu à chaque date (NaN avant le début de la série)
            last = r.get(d, last)
            out.append(last)
        return np.array(out, dtype=float)

    P = np.column_stack([series(t) for t in tickers])
    R = np.full_like(P, np.nan)
    R[1:] = np.log(P[1:] / P[:-1])
    wv = np.array([w[t] for t in tickers])
    cls = [asset_class_of(t) for t in tickers]

    # --- risque ex-ante : covariance EWMA sur 2 ans
    recent = np.nan_to_num(R[-504:])
    lam = 0.5 ** (1 / 60)
    C = np.cov(recent[:60].T)
    for r in recent[60:]:
        C = lam * C + (1 - lam) * np.outer(r, r)
    C *= 252
    port_var = float(wv @ C @ wv)
    vol = float(np.sqrt(port_var))
    mrc = C @ wv
    contrib = wv * mrc / port_var if port_var > 0 else np.zeros_like(wv)
    by_class: dict[str, dict] = {}
    for t, c, x, wt in zip(tickers, cls, contrib, wv):
        d = by_class.setdefault(c, {"weight": 0.0, "risk": 0.0})
        d["weight"] += float(wt)
        d["risk"] += float(x)

    # --- VaR / CVaR : rejoue 500 séances avec les poids actuels
    hist = np.nan_to_num(R[-500:]) @ wv
    hist_simple = np.expm1(hist)
    var95, var99 = -float(np.percentile(hist_simple, 5)), -float(np.percentile(hist_simple, 1))
    cvar95 = -float(hist_simple[hist_simple <= -var95].mean())
    cvar99 = -float(hist_simple[hist_simple <= -var99].mean())
    sd_d = vol / np.sqrt(252)

    # --- corrélations entre classes (1 an)
    classes = sorted(set(cls), key=lambda c: ["Actions", "Obligations", "Matières premières", "Devises", "Crypto"].index(c) if c in ["Actions", "Obligations", "Matières premières", "Devises", "Crypto"] else 9)
    cls_ret = {c: np.nan_to_num(R[-252:])[:, [i for i, k in enumerate(cls) if k == c]] @ wv[[i for i, k in enumerate(cls) if k == c]] for c in classes}
    corr = {a: {b: float(np.corrcoef(cls_ret[a], cls_ret[b])[0, 1]) if np.std(cls_ret[a]) > 0 and np.std(cls_ret[b]) > 0 else None for b in classes} for a in classes}

    # --- scénarios de crise
    scen = []
    for name, a, b in SCENARIOS:
        idx = [i for i, d in enumerate(dates) if a <= d <= b]
        if len(idx) < 3:
            continue
        i0, i1 = idx[0], idx[-1]
        rets = P[i1] / P[i0] - 1.0
        avail = np.isfinite(rets)
        pnl = float(np.nansum(np.where(avail, rets, 0.0) * wv))
        by_c: dict[str, float] = {}
        for t, c, rr, wt, ok in zip(tickers, cls, rets, wv, avail):
            if ok:
                by_c[c] = by_c.get(c, 0.0) + float(rr * wt)
        missing = [t for t, ok in zip(tickers, avail) if not ok]
        sp = series("SPY")
        spy = float(sp[i1] / sp[i0] - 1)
        scen.append({"name": name, "start": dates[i0], "end": dates[i1], "pnl": pnl, "by_class": by_c,
                     "missing": missing, "spy": spy, "missing_weight": float(sum(abs(w[t]) for t in missing))})

    # --- limites
    crypto_w = sum(v for t, v in w.items() if t.endswith("-USD"))
    values = {
        "vol_ex_ante": vol, "var99": var99, "gross": s["gross"], "net": abs(s["net"]),
        "max_position": max(abs(v) for v in w.values()), "crypto": crypto_w, "drawdown": s["current_drawdown"],
    }
    limits = [{"key": k, "label": lab, "value": values[k], "limit": lim, "usage": values[k] / lim,
               "status": "DÉPASSEMENT" if values[k] > lim else ("VIGILANCE" if values[k] > 0.8 * lim else "OK")}
              for k, (lim, lab) in LIMITS.items()]

    names = {x: n for m in ETF_UNIVERSE.values() for x, n in m.items()} | CRYPTO_UNIVERSE
    return {
        "as_of": dates[-1],
        "equity": s["equity"],
        "vol_ex_ante": vol,
        "var": {"var95": var95, "var99": var99, "cvar95": cvar95, "cvar99": cvar99,
                "param95": 1.645 * sd_d, "param99": 2.326 * sd_d, "n_obs": int(len(hist))},
        "positions": sorted([{"ticker": t, "name": names.get(t, t), "asset_class": c, "weight": float(x),
                              "risk_contrib": float(rc), "vol": float(np.sqrt(C[i, i]))}
                             for i, (t, c, x, rc) in enumerate(zip(tickers, cls, wv, contrib))], key=lambda p: -abs(p["risk_contrib"])),
        "by_class": by_class,
        "corr": {"classes": classes, "matrix": corr},
        "scenarios": scen,
        "limits": limits,
        "breaches": [l for l in limits if l["status"] != "OK"],
    }
