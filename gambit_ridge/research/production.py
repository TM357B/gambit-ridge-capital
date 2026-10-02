"""Stratégie de production du fonds — portefeuille cible du jour.

Retenue par le banc d'évaluation (gambit_ridge/research/evaluate.py,
sélection sur la période de développement 2008-2019 uniquement) :

- Poche ETF (90 % du capital) : socle 60/40 (30 % SPY, 20 % IEF) + couche
  d'ensemble tendance (TSMOM 12 mois + EWMA multi-vitesses + Kalman) sur
  20 ETF, positions à risque égal (vol GARCH), vol cible 10 %.
- Poche crypto (10 % du capital) : ensemble tendance long-only sur 7
  cryptos, vol cible 25 %, exposition brute <= 100 % (le reste en cash).

Les poids de la couche tendance sont des cibles ; le filtre anti
micro-trades est appliqué par le paper trading au moment d'exécuter.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from . import signals as sg
from .portfolio import build_weights, ewma_covariance

# Répartition par budget de risque (décision du 2026-10-02) : à 80/20 la crypto
# portait ~55 % du risque du fonds ; à 90/10, ~23 %, pour un Sharpe identique
# (1,29 sur 2018-2026).
ETF_SHARE = 0.90
CRYPTO_SHARE = 0.10
CORE_WEIGHTS = {"SPY": 0.60, "IEF": 0.40}
CORE_SHARE = 0.50

COST_BPS = {"etf": 5.0, "crypto": 20.0}


def _complete_bars(dates: list[str], prices: dict[str, np.ndarray]):
    """Retire les barres dont la séance n'est pas close (règle la plus stricte
    parmi les symboles de la poche)."""
    from ..data.yahoo import complete_cutoff

    cut = min(complete_cutoff(s) for s in prices)
    n = len(dates)
    while n > 0 and dates[n - 1] > cut:
        n -= 1
    return dates[:n], {k: v[:n] for k, v in prices.items()}


def _trend_signal(P: np.ndarray) -> dict[str, np.ndarray]:
    parts = {
        "tsmom": sg.tsmom(P, 252),
        "ewma": sg.ewma_trend(P),
        "kalman": sg.kalman_trend(P),
    }
    parts["ensemble"] = (parts["tsmom"] + parts["ewma"] + parts["kalman"]) / 3.0
    return parts


def etf_sleeve(dates: list[str], prices: dict[str, np.ndarray]) -> dict:
    tickers = list(prices)
    P = np.column_stack([prices[t] for t in tickers])
    vol = sg.garch_vol(P)
    cov = ewma_covariance(P)
    sig = _trend_signal(P)
    W_trend = build_weights(sig["ensemble"], vol, cov)
    w = (1.0 - CORE_SHARE) * W_trend[-1]
    for tk, cw in CORE_WEIGHTS.items():
        w[tickers.index(tk)] += CORE_SHARE * cw
    return {
        "date": dates[-1],
        "weights": {tk: float(x) for tk, x in zip(tickers, w)},
        "detail": {
            tk: {
                "signal": round(float(sig["ensemble"][-1, j]), 3),
                "tsmom": round(float(sig["tsmom"][-1, j]), 3),
                "ewma": round(float(sig["ewma"][-1, j]), 3),
                "kalman": round(float(sig["kalman"][-1, j]), 3),
                "vol": round(float(vol[-1, j]), 4),
                "poids_tendance": round(float((1.0 - CORE_SHARE) * W_trend[-1, j]), 4),
                "poids_socle": round(CORE_SHARE * CORE_WEIGHTS.get(tk, 0.0), 4),
            }
            for j, tk in enumerate(tickers)
        },
        "prices": {tk: float(prices[tk][-1]) for tk in tickers},
    }


def crypto_sleeve(dates: list[str], prices: dict[str, np.ndarray]) -> dict:
    tickers = list(prices)
    P = np.column_stack([prices[t] for t in tickers])
    vol = sg.garch_vol(P)
    cov = ewma_covariance(P)
    sig = _trend_signal(P)
    long_only = np.clip(sig["ensemble"], 0.0, None)
    W = build_weights(long_only, vol, cov, port_vol=0.25, max_gross=1.0, max_position=0.5)
    return {
        "date": dates[-1],
        "weights": {tk: float(x) for tk, x in zip(tickers, W[-1])},
        "detail": {
            tk: {
                "signal": round(float(sig["ensemble"][-1, j]), 3),
                "vol": round(float(vol[-1, j]), 4),
            }
            for j, tk in enumerate(tickers)
        },
        "prices": {tk: float(prices[tk][-1]) for tk in tickers},
    }


def target_portfolio(refresh: bool = True) -> dict:
    """Portefeuille cible complet (poids en fraction du capital total).

    Chaque poche passe les contrôles qualité (research/quality.py) ; une poche
    en échec est marquée « blocked » : le paper trading conserve ses positions.
    """
    from ..data.yahoo import load_crypto_universe, load_etf_universe
    from .quality import check_sleeve

    out = {"weights": {}, "kind": {}, "prices": {}, "detail": {}, "dates": {},
           "quality": {}, "blocked": [], "suspect": []}
    sleeves = (("etf", load_etf_universe, etf_sleeve, ETF_SHARE),
               ("crypto", load_crypto_universe, crypto_sleeve, CRYPTO_SHARE))
    for kind, loader, builder, share in sleeves:
        try:
            d, p = _complete_bars(*loader(refresh=refresh))
            issues, bad = check_sleeve(kind, d, p)
            out["quality"][kind] = issues
            res = builder(d, p)
            for tk, w in res["weights"].items():
                out["weights"][tk] = share * w
                out["kind"][tk] = kind
            out["prices"].update(res["prices"])
            out["detail"].update(res["detail"])
            out["dates"][kind] = res["date"]
            if issues:
                out["blocked"] += list(res["weights"])
                out["suspect"] += sorted(bad)
            else:  # second avis indépendant : seules les lignes en désaccord sont gelées
                from ..data.crosscheck import cross_check

                x_issues, x_bad = cross_check(kind, d, p)
                out.setdefault("crosscheck", {})[kind] = x_issues
                out["blocked"] += sorted(x_bad)
                out["suspect"] += sorted(x_bad)
        except Exception as exc:
            out[f"{kind}_error"] = str(exc)
            out["quality"][kind] = [f"{kind} : {exc}"]
    return out
