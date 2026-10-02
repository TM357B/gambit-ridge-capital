"""Stratégie améliorée : regime-momentum v2 avec crisis guard dégressif.

Différences vs v1 (mom=42, vol_thr=0.20, n=2 — validée par grille) :
- crisis guard dégressif : au-delà de 35% de vol, l'exposition de l'actif
  est réduite progressivement (crisis_vol/vol) au lieu d'une coupe sèche
  à 2× le seuil. Testé sur 40 ans : maxDD -29% → -24.8%, OOS +0.48 → +0.51.
- L'anti-cliff et le momentum multi-échelles ont été testés et REJETÉS :
  ils diluent le signal (OOS +0.48 → +0.32). La v2 ne garde que ce qui
  gagne le duel contre la baseline.
"""

from __future__ import annotations

import numpy as np

from .strategies import realized_vol


def adaptive_regime_momentum(
    *,
    mom_lookback: int = 42,
    n_positions: int = 2,
    vol_lookback: int = 40,
    vol_threshold: float = 0.20,
    crisis_vol: float = 0.35,
    max_leverage: float = 1.0,
):
    """Regime-momentum avec garde-fou de crise dégressif."""

    def weight_fn(t, prices_by_ticker):
        scores: dict[str, float] = {}
        for tk, series in prices_by_ticker.items():
            arr = np.asarray(series, dtype=float)
            if len(arr) < mom_lookback + 1:
                continue
            ret = arr[-1] / arr[-1 - mom_lookback] - 1.0
            daily = np.diff(arr[-mom_lookback - 1 :]) / arr[-mom_lookback - 1 : -1]
            vol = daily.std(ddof=1)
            if vol > 1e-12:
                scores[tk] = ret / vol

        if not scores:
            return {}

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        winners = [(tk, s) for tk, s in ranked[:n_positions] if s > 0]
        losers = [(tk, s) for tk, s in ranked[-n_positions:] if s < 0]

        def scaled_weight(tk) -> float | None:
            arr = np.asarray(prices_by_ticker[tk], dtype=float)
            v = realized_vol(arr, vol_lookback)
            if v < 1e-12:
                return None
            scale = min(1.0, vol_threshold / v)
            if v > crisis_vol:
                scale *= crisis_vol / v
            return scale

        weights: dict[str, float] = {}
        half = max_leverage / 2.0
        for tk, _ in winners:
            scale = scaled_weight(tk)
            if scale is not None:
                weights[tk] = half * scale / max(len(winners), 1)
        for tk, _ in losers:
            scale = scaled_weight(tk)
            if scale is not None:
                weights[tk] = -half * scale / max(len(losers), 1)
        return weights

    return weight_fn
