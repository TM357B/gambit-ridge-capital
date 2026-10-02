"""Tests unitaires Phase 1 — HMM (chap. 7) et filtre de Kalman.

Couverture :
- HMM : récupération d'états synthétiques, causalité stricte des
  probabilités filtrées, Viterbi, stationnarité des transitions.
- Kalman : suivi d'un bêta variant dans le temps (vs OLS statique),
  causalité stricte, gestion des séries désalignées.
- Stratégie régime-conditionnée : fonctionne et ne plante pas.
"""
from __future__ import annotations

import numpy as np
import pytest

from gambit_ridge.models.regimes import GaussianHMM, KalmanBeta, regime_conditioned_momentum


def _two_state_series(seed=42, T=1500):
    rng = np.random.default_rng(seed)
    states = np.zeros(T, dtype=int)
    for t in range(1, T):
        states[t] = states[t - 1] if rng.random() > 0.03 else 1 - states[t - 1]
    mus = np.array([0.001, -0.002])
    sds = np.array([0.005, 0.02])
    r = mus[states] + sds[states] * rng.standard_normal(T)
    return r, states


# ---------------- HMM ----------------

def test_hmm_recovers_two_states():
    r, states = _two_state_series()
    hmm = GaussianHMM(n_states=2, seed=42).fit(r)
    path = hmm.viterbi(r)
    acc = max((path == states).mean(), (path == 1 - states).mean())
    assert acc > 0.85, f"précision Viterbi trop faible : {acc:.2f}"


def test_hmm_posteriors_are_probabilities():
    r, _ = _two_state_series()
    hmm = GaussianHMM(n_states=2, seed=42).fit(r)
    post = hmm.filtered_posteriors(r)
    assert post.shape == (len(r), 2)
    assert np.all(post >= -1e-9) and np.all(post <= 1 + 1e-9)
    np.testing.assert_allclose(post.sum(axis=1), 1.0, atol=1e-9)


def test_hmm_filtered_posteriors_are_causal():
    """Modifier le futur ne doit pas changer les posteriors passés."""
    r, _ = _two_state_series()
    hmm = GaussianHMM(n_states=2, seed=42).fit(r[:800])
    post1 = hmm.filtered_posteriors(r)
    r2 = r.copy()
    r2[1200:] += 1.0  # altère le futur
    post2 = hmm.filtered_posteriors(r2)
    np.testing.assert_allclose(post1[:1000], post2[:1000], atol=1e-12)


def test_hmm_transmat_rows_sum_to_one():
    r, _ = _two_state_series(T=600)
    hmm = GaussianHMM(n_states=3, seed=42).fit(r)
    np.testing.assert_allclose(hmm.transmat.sum(axis=1), 1.0, atol=1e-9)
    assert np.all(hmm.variances > 0)
    assert np.all(np.isfinite(hmm.means))


def test_hmm_viterbi_is_not_causal_but_exists():
    """Viterbi regarde toute la série : réservé à l'analyse, pas au trading."""
    r, _ = _two_state_series(T=400)
    hmm = GaussianHMM(n_states=2, seed=42).fit(r[:200])
    path = hmm.viterbi(r)
    assert path.shape == (len(r),)
    assert set(np.unique(path)) <= {0, 1}


# ---------------- Kalman ----------------

def test_kalman_tracks_time_varying_beta():
    rng = np.random.default_rng(0)
    T = 1500
    mkt = rng.normal(0, 0.01, T)
    true_beta = np.linspace(0.5, 1.5, T)
    y = true_beta * mkt + 0.002 + rng.normal(0, 0.005, T)
    kb = KalmanBeta(delta=1e-2).initialize(y[:300], mkt[:300])
    betas, alphas = kb.filter_path(y[300:], mkt[300:])
    assert len(betas) == T - 300
    # doit battre le OLS statique sur la trajectoire du bêta
    X = np.column_stack([mkt[300:], np.ones(T - 300)])
    theta, *_ = np.linalg.lstsq(X, y[300:], rcond=None)
    mae_kalman = float(np.abs(betas - true_beta[300:]).mean())
    mae_ols = float(np.abs(theta[0] - true_beta[300:]).mean())
    assert mae_kalman < mae_ols, f"Kalman ({mae_kalman:.4f}) doit battre OLS statique ({mae_ols:.4f})"
    assert abs(betas[-1] - 1.5) < 0.2


def test_kalman_is_causal():
    rng = np.random.default_rng(1)
    T = 800
    mkt = rng.normal(0, 0.01, T)
    y = 1.0 * mkt + rng.normal(0, 0.005, T)
    kb1 = KalmanBeta(delta=1e-2).initialize(y[:200], mkt[:200])
    b1, _ = kb1.filter_path(y[200:], mkt[200:])
    y2 = y.copy()
    y2[-100:] += 1.0
    kb2 = KalmanBeta(delta=1e-2).initialize(y2[:200], mkt[:200])
    b2, _ = kb2.filter_path(y2[200:], mkt[200:])
    assert np.allclose(b1[:300], b2[:300])


def test_kalman_rejects_misaligned_series():
    kb = KalmanBeta().initialize(np.zeros(50), np.zeros(50))
    with pytest.raises(ValueError):
        kb.filter_path(np.zeros(10), np.zeros(12))


def test_kalman_step_requires_init():
    kb = KalmanBeta()
    with pytest.raises(RuntimeError):
        kb.step(0.01, 0.01)


# ---------------- Stratégie régime-conditionnée ----------------

def test_regime_strategy_runs_and_returns_weights():
    from gambit_ridge.data.synthetic_history import generate_synthetic_history

    prices = generate_synthetic_history(n_years=6)
    fn = regime_conditioned_momentum(hmm_window=500)
    # appelle la stratégie à plusieurs dates : doit renvoyer des poids finis
    n = len(next(iter(prices.values())))
    for t in [300, 700, 1100, n - 2]:
        w = fn(t, {tk: v[: t + 1] for tk, v in prices.items()})
        assert all(np.isfinite(x) for x in w.values())
        total = sum(abs(x) for x in w.values())
        assert total <= 1.0 + 1e-9
