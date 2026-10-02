"""Stratégie de classement ML — Phase 2
(Dixon, Halperin & Bilokon, chap. 4, 8).

Boucle walk-forward stricte :
1. Tous les `rebalance_every` jours, le modèle (ridge ou feedforward)
   est RÉ-ENTRAÎNÉ sur la fenêtre passée glissante :
   - features construites aux dates passées (uniquement le passé),
   - cible = rendement forward sur `horizon` jours, demeané par date
     (classement relatif).
2. À la date t, les features actuelles sont construites et le modèle
   prédit un score par actif.
3. Les `n_positions` meilleurs scores -> long, les pires -> short,
   pondérés proportionnellement au score, exposition normalisée.

Anti-look-ahead :
- l'entraînement n'utilise QUE des dates <= t - horizon (la cible
  forward d'une date d'entraînement doit être COMPLÈTEMENT observée),
- embargo implicite de `horizon` jours entre train et décision,
- les features sont causales par construction (Phase 1/2).
"""
from __future__ import annotations

import numpy as np

from .features import FeatureBuilder
from .linear import RidgeModel
from .feedforward import FeedForwardNet


def ml_ranking_strategy(
    *,
    model: str = "ridge",
    horizon: int = 21,
    train_window: int = 500,
    rebalance_every: int = 5,
    n_positions: int = 5,
    max_leverage: float = 1.0,
    hidden: int = 16,
    lam: float = 10.0,
    seed: int = 42,
):
    """Classement cross-sectional par modèle ML, rebalancement périodique.

    model : "ridge" (baseline ML) ou "feedforward" (non-linéaire).
    """
    state: dict = {
        "model": None,
        "builder": None,
        "last_train": -10**9,
        "last_rebalance": -10**9,
        "weights": {},
    }

    def _make_model():
        if model == "feedforward":
            return FeedForwardNet(hidden=hidden, seed=seed, max_epochs=150)
        return RidgeModel(lam=lam)

    def _train(prices: dict[str, np.ndarray], t: int):
        """Ré-entraîne sur les dates passées dont la cible est observée."""
        builder = FeatureBuilder(seed=seed)
        train_end = t - horizon  # dernier indice dont la cible est complète
        train_start = max(130, train_end - train_window)
        if train_end - train_start < 60:
            return
        window = {tk: np.asarray(v, dtype=float) for tk, v in prices.items()}
        builder.fit({tk: v[:train_end] for tk, v in window.items()})
        Xs: list[np.ndarray] = []
        ys: list[float] = []
        dates = range(train_start, train_end, rebalance_every)
        for d in dates:
            feats = builder.build(window, d)
            target = builder.target(window, d, horizon)
            if target is None:
                continue
            tickers = sorted(feats)
            # cible demeanée cross-sectionelle : classement relatif
            vals = np.array([target[tk] for tk in tickers])
            vals = vals - vals.mean()
            for i, tk in enumerate(tickers):
                Xs.append(feats[tk])
                ys.append(float(vals[i]))
        if len(Xs) < 100:
            return
        m = _make_model()
        m.fit(np.vstack(Xs), np.array(ys))
        state["model"] = m
        state["builder"] = builder
        state["last_train"] = t

    def weight_fn(t, prices_by_ticker):
        prices = {tk: np.asarray(v, dtype=float) for tk, v in prices_by_ticker.items()}
        if t - state["last_train"] >= max(train_window // 4, 60):
            try:
                _train(prices, t)
            except Exception:
                pass
            state["last_train"] = t
        if state["model"] is None or t - state["last_rebalance"] < rebalance_every:
            return state["weights"]
        try:
            feats = state["builder"].build(prices, t)
        except Exception:
            return state["weights"]
        tickers = sorted(feats)
        X = np.vstack([feats[tk] for tk in tickers])
        scores = state["model"].predict(X)
        # demean des scores puis classement
        scores = scores - scores.mean()
        order = np.argsort(scores)
        n = len(tickers)
        k = min(n_positions, n // 4) if n >= 8 else max(1, n // 4)
        longs = [(tickers[i], scores[i]) for i in order[-k:] if scores[i] > 0]
        shorts = [(tickers[i], scores[i]) for i in order[:k] if scores[i] < 0]
        weights: dict[str, float] = {}
        half = max_leverage / 2.0
        long_sum = sum(s for _, s in longs)
        short_sum = sum(abs(s) for _, s in shorts)
        if longs and long_sum > 0:
            for tk, s in longs:
                weights[tk] = half * s / long_sum
        if shorts and short_sum > 0:
            for tk, s in shorts:
                weights[tk] = -half * abs(s) / short_sum
        state["weights"] = weights
        state["last_rebalance"] = t
        return weights

    return weight_fn
