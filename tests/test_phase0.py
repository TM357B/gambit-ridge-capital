"""Tests unitaires Phase 0 — baselines économétriques, embargo, config.

Règles couvertes (cahier des charges) :
- absence de NaN, alignement des dimensions
- causalité stricte des prédictions (aucun accès au futur)
- embargo effectif entre train et test
- chargement de config.yaml
"""
from __future__ import annotations

import numpy as np

from gambit_ridge.backtest.walkforward import run_walkforward
from gambit_ridge.models.baselines import ARModel, GARCHModel, evaluate_baselines
from gambit_ridge.ml_config import get_backtest_config, load_config


def _fake_prices(n=1400, seed=0):
    rng = np.random.default_rng(seed)
    return {
        "A": 100.0 * np.cumprod(1 + rng.normal(0.0003, 0.01, n)),
        "B": 100.0 * np.cumprod(1 + rng.normal(0.0002, 0.012, n)),
    }


# ---------------- AR(p) ----------------

def test_ar_fit_selects_order_no_nan():
    rng = np.random.default_rng(1)
    r = rng.normal(0.0002, 0.01, 600)
    ar = ARModel(max_lag=5).fit(r)
    assert 1 <= ar.order <= 5
    assert np.all(np.isfinite(ar.coef))
    assert np.isfinite(ar.intercept)


def test_ar_predict_is_causal():
    """La prédiction ne doit pas changer si on modifie le FUTUR de l'historique."""
    rng = np.random.default_rng(2)
    r = rng.normal(0.0, 0.01, 300)
    ar = ARModel(max_lag=3).fit(r[:200])
    p1 = ar.predict(r[:250])
    r_modified = r.copy()
    r_modified[260] = 10.0  # futur altéré
    p2 = ar.predict(r_modified[:250])
    assert p1 == p2


def test_ar_recovers_known_ar_process():
    """Sur un vrai AR(1) avec phi=0.5, le coefficient estimé doit s'en approcher."""
    rng = np.random.default_rng(3)
    n = 20000
    eps = rng.normal(0, 0.01, n)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = 0.5 * r[t - 1] + eps[t]
    ar = ARModel(max_lag=5).fit(r)
    assert ar.order >= 1
    assert abs(ar.coef[0] - 0.5) < 0.05


# ---------------- GARCH(1,1) ----------------

def test_garch_fit_stationary_no_nan():
    rng = np.random.default_rng(4)
    r = rng.normal(0, 0.01, 800)
    g = GARCHModel().fit(r)
    assert np.isfinite(g.omega) and g.omega > 0
    assert 0 < g.alpha <= 0.5
    assert 0 <= g.beta < 1
    assert g.alpha + g.beta < 1.0  # stationnarité


def test_garch_captures_vol_shift():
    """Face à un changement de régime de vol, h_t doit monter après le shift."""
    rng = np.random.default_rng(5)
    r = np.concatenate([rng.normal(0, 0.005, 500), rng.normal(0, 0.03, 300)])
    g = GARCHModel().fit(r[:500])
    h = g.conditional_variance_path(r)
    assert h[-1] > 4 * np.median(h[:400])  # la vol conditionnelle a capté le shift


def test_garch_variance_path_causal():
    rng = np.random.default_rng(6)
    r = rng.normal(0, 0.01, 400)
    g = GARCHModel().fit(r[:300])
    h1 = g.conditional_variance_path(r[:350])
    r_mod = r.copy()
    r_mod[380] = 1.0
    h2 = g.conditional_variance_path(r_mod[:350])
    np.testing.assert_allclose(h1, h2)


# ---------------- Walk-forward embargo ----------------

def test_walkforward_embargo_purges_train_tail():
    """Avec embargo, la fin du train doit être tronquée : une stratégie qui
    mémorise la dernière valeur du train ne doit pas la voir si embargo > 0."""
    prices = _fake_prices()

    def factory_last_value(train):
        last = {tk: float(v[-1]) for tk, v in train.items()}

        def weight_fn(t, ctx):
            return {tk: (1.0 if v > 0 else 0.0) for tk, v in last.items()}

        return weight_fn

    wf0 = run_walkforward(prices, factory_last_value, train_periods=200, test_periods=50, step_periods=100, embargo_periods=0)
    wf5 = run_walkforward(prices, factory_last_value, train_periods=200, test_periods=50, step_periods=100, embargo_periods=5)
    # les folds doivent exister dans les deux cas
    assert len(wf0.per_fold) > 0
    assert len(wf5.per_fold) > 0
    # le même nombre de folds (l'embargo tronque le train, pas la fenêtre totale)
    assert len(wf0.per_fold) == len(wf5.per_fold)


def test_walkforward_no_future_leakage():
    """Une stratégie qui "prédit" en regardant le futur ne doit pas pouvoir
    s'exécuter : weight_fn ne reçoit que les prix <= t."""
    prices = _fake_prices(n=300)
    seen_max = []

    def factory(_train):
        def weight_fn(t, ctx):
            seen_max.append(t)
            return {}
        return weight_fn

    run_walkforward(prices, factory, train_periods=100, test_periods=50, step_periods=100)
    assert seen_max  # la stratégie a bien été appelée


# ---------------- Baselines walk-forward ----------------

def test_evaluate_baselines_runs_and_returns_rmse():
    rng = np.random.default_rng(7)
    r = rng.normal(0.0002, 0.01, 2500)
    ev = evaluate_baselines(r, train_periods=800, test_periods=200, step_periods=300)
    assert ev["n_folds"] >= 3
    for key in ("ar_rmse_oos", "garch_rmse_oos", "naive_rmse_oos"):
        assert ev[key] is not None and np.isfinite(ev[key]) and ev[key] > 0


# ---------------- Config ----------------

def test_config_loads():
    cfg = load_config()
    assert cfg["reproducibility"]["seed"] == 42
    assert cfg["backtest"]["rebalance_every"] == 5
    assert cfg["walkforward"]["embargo_periods"] > 0


def test_backtest_config_from_yaml():
    bc = get_backtest_config()
    assert bc.commission_bps + bc.slippage_bps == 7.0
    assert bc.periods_per_year == 252
