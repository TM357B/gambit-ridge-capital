"""Projection du portefeuille à un an (onglet Risque) — rééchantillonnage du backtest du fonds.

Méthode : bootstrap par blocs de 21 séances sur les rendements quotidiens du backtest du fonds
dans sa répartition de production (data/fund_backtest.json, coûts inclus). Les blocs conservent les séquences de mauvaises
journées (les krachs ne sont pas des tirages indépendants). 4 000 trajectoires, graine fixe.

Ce n'est PAS une prévision : la projection suppose que l'avenir ressemble à 2018-2026. Elle
sert à dimensionner les attentes (fourchette de résultats, probabilité de perte, baisse à
laquelle il faut s'attendre) et à juger si le réel sort de cette fourchette.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FUND = ROOT / "data" / "fund_backtest.json"
HORIZON = 252
BLOCK = 21
PATHS = 4000
QUANTILES = (5, 25, 50, 75, 95)
_CACHE: dict = {}


def simulate(returns: np.ndarray, horizon: int = HORIZON, paths: int = PATHS, block: int = BLOCK, seed: int = 7) -> np.ndarray:
    """Trajectoires de capital (paths, horizon + 1), base 1. Fonction pure (testée)."""
    rng = np.random.default_rng(seed)
    n_blocks = -(-horizon // block)
    starts = rng.integers(0, len(returns) - block + 1, size=(paths, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(paths, -1)[:, :horizon]
    eq = np.cumprod(1.0 + returns[idx], axis=1)
    return np.concatenate([np.ones((paths, 1)), eq], axis=1)


def projection(equity: float | None = None) -> dict:
    key = (date.today().isoformat(), round(equity or 0))
    if key in _CACHE:
        return _CACHE[key]
    f = json.loads(FUND.read_text())
    r = np.array(f["returns"], dtype=float)

    def stats(rets: np.ndarray) -> dict:
        eq = simulate(rets)
        final = eq[:, -1] - 1.0
        max_dd = (1.0 - eq / np.maximum.accumulate(eq, axis=1)).max(axis=1)
        return {
            "quantiles": {str(q): [round(float(x), 4) for x in np.percentile(eq[:, grid], q, axis=0)] for q in QUANTILES},
            "rendement": {str(q): round(float(np.percentile(final, q)), 4) for q in QUANTILES},
            "moyenne": round(float(final.mean()), 4),
            "prob_perte": round(float((final < 0).mean()), 4),
            "prob_perte_5": round(float((final < -0.05).mean()), 4),
            "prob_gain_10": round(float((final > 0.10).mean()), 4),
            "baisse_max": {str(q): round(float(np.percentile(max_dd, q)), 4) for q in (50, 75, 95)},
            "prob_baisse_10": round(float((max_dd > 0.10).mean()), 4),
        }

    grid = list(range(0, HORIZON + 1, 5))
    out = {
        "source": {"debut": f["dates"][0], "fin": f["dates"][-1], "n": len(r), "allocation": f.get("allocation")},
        "methode": f"bootstrap par blocs de {BLOCK} séances, {PATHS} trajectoires, horizon {HORIZON} séances",
        "equity": equity,
        "jours": grid,
        **stats(r),
        # scénario prudent : même risque, rendement moyen divisé par deux (un backtest surestime
        # presque toujours le rendement futur ; la période 2018-2026 a été favorable à la stratégie)
        "prudent": stats(r - 0.5 * r.mean()),
    }
    _CACHE.clear()
    _CACHE[key] = out
    return out
