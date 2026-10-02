"""Stratégie régime-conditionnée (Phase 1, Dixon chap. 7).

Principe : un HMM gaussien 3 états (haussier / baissier / haute vol)
est entraîné sur les rendements AGRÉGÉS du portefeuille momentum en
fenêtre train (jamais sur le test). En backtest, les probabilités
a posteriori FILTRÉES (causales) conditionnent l'exposition :

    - régime haussier   -> exposition pleine de la stratégie de base
    - régime baissier   -> exposition réduite à bear_scale
    - haute volatilité   -> exposition réduite à vol_scale

La stratégie de base reste regime-momentum v2 (adaptive) : on ne
change QUE l'exposition, jamais les signaux -> si le régime n'apporte
rien, le backtest le montrera immédiatement (règle n°5 du cahier des
charges : comparaison stricte contre la baseline).
"""
from __future__ import annotations

import numpy as np

from ...backtest.adaptive import adaptive_regime_momentum
from .hmm import GaussianHMM


def regime_conditioned_momentum(
    *,
    mom_lookback: int = 42,
    n_positions: int = 2,
    vol_lookback: int = 40,
    vol_threshold: float = 0.20,
    crisis_vol: float = 0.35,
    min_scale: float = 0.3,
    hmm_window: int = 750,
    n_states: int = 3,
    seed: int = 42,
):
    """Momentum adaptatif dont l'exposition est conditionnée par un HMM.

    L'HMM est ré-entraîné tous les hmm_window jours sur la fenêtre
    glissante précédente (fit walk-forward implicite, jamais de futur).

    Le conditionnement est fondé sur le SHARPE ESPÉRÉ de l'état,
    s_k = mu_k / sd_k, et non sur des étiquettes arbitraires :
    l'exposition est réduite (jusqu'à min_scale) si le Sharpe espéré
    pondéré par les probabilités a posteriori est négatif, inchangée
    sinon. Ainsi un état de haute volatilité à rendement positif
    n'est PAS pénalisé (leçon du diagnostic FRED).
    """
    base_fn = adaptive_regime_momentum(
        mom_lookback=mom_lookback,
        n_positions=n_positions,
        vol_lookback=vol_lookback,
        vol_threshold=vol_threshold,
        crisis_vol=crisis_vol,
    )
    hmm = GaussianHMM(n_states=n_states, seed=seed, max_iter=50)
    state: dict = {"last_fit": -10**9, "labels": {}, "post": None}

    def _aggregate_returns(prices_by_ticker: dict, lookback: int) -> np.ndarray:
        """Rendement moyen de l'univers sur les derniers lookback jours."""
        arrs = [np.asarray(v, dtype=float) for v in prices_by_ticker.values() if len(v) > 1]
        if not arrs:
            return np.array([])
        n = min(len(a) for a in arrs)
        rets = [np.diff(a[-lookback - 1 :]) / a[-lookback - 1 : -1] for a in arrs]
        return np.mean(np.vstack([r[-n + 1 :] if len(r) >= n else r for r in rets]), axis=0)

    def weight_fn(t, prices_by_ticker):
        # Ré-entraînement périodique de l'HMM sur la fenêtre passée
        if t - state["last_fit"] >= hmm_window:
            rets = _aggregate_returns(prices_by_ticker, hmm_window)
            if len(rets) >= 250:
                try:
                    hmm.fit(rets)
                    state["labels"] = hmm.state_labels()
                    state["last_fit"] = t
                except Exception:
                    state["last_fit"] = t

        # Probabilités filtrées CAUSALES au temps t
        scale = 1.0
        if hmm.fitted:
            rets = _aggregate_returns(prices_by_ticker, min(60, t + 1))
            if len(rets) >= 30:
                post = hmm.filtered_posteriors(rets)
                p_now = post[-1]  # P(state | y_1..t) — que du passé
                # Sharpe espéré de chaque état (estimé au fit, données passées)
                sds = np.sqrt(np.maximum(hmm.variances, 1e-12))
                state_sharpe = hmm.means / sds
                expected_sharpe = float(np.dot(p_now, state_sharpe))
                if expected_sharpe < 0:
                    # Réduction linéaire : -0.05 -> scale ~0.95, très négatif -> min_scale
                    scale = max(min_scale, 1.0 + 2.0 * expected_sharpe)
                state["labels"] = hmm.state_labels()

        if scale >= 0.999:
            return base_fn(t, prices_by_ticker)
        base = base_fn(t, prices_by_ticker)
        return {tk: w * scale for tk, w in base.items()}

    return weight_fn
