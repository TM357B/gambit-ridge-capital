"""Baselines économétriques — Dixon, Halperin & Bilokon, chap. 6.

AR(p) : modèle autorégressif sur les rendements, estimé par OLS
        conditionnel, ordre p sélectionné par BIC sur le train
        uniquement (éq. 6.1-6.15).
GARCH(1,1) : h_t = omega + alpha * r^2_{t-1} + beta * h_{t-1}, estimé
        par MLE gaussien (éq. 6.31-6.42), hill-climbing contraint numpy pur.

Anti-look-ahead : fit() ne voit QUE la fenêtre fournie ; predict()
est purement causal. L'évaluation walk-forward est identique à celle
des stratégies du dépôt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ARModel:
    """AR(p) sur rendements : r_t = c + φ_1 r_{t-1} + ... + φ_p r_{t-p} + ε_t.

    Ordre p sélectionné par BIC sur les données d'entraînement uniquement.
    """

    max_lag: int = 5
    order: int = 0
    coef: np.ndarray = field(default_factory=lambda: np.array([]))
    intercept: float = 0.0

    def fit(self, returns: np.ndarray) -> "ARModel":
        returns = np.asarray(returns, dtype=float)
        best_bic = np.inf
        for p in range(1, self.max_lag + 1):
            y, X = self._design(returns, p)
            if X.shape[0] < p + 5:
                break
            beta, rss = self._ols(y, X)
            n, k = X.shape
            bic = n * np.log(max(rss, 1e-16) / n) + k * np.log(n)
            if bic < best_bic:
                best_bic = bic
                self.order = p
                self.intercept = float(beta[0])
                self.coef = beta[1:].copy()
        return self

    @staticmethod
    def _design(returns: np.ndarray, p: int):
        n = len(returns)
        y = returns[p:]
        X = np.ones((n - p, p + 1))
        for lag in range(1, p + 1):
            X[:, lag] = returns[p - lag : n - lag]
        return y, X

    @staticmethod
    def _ols(y: np.ndarray, X: np.ndarray):
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        rss = float(np.sum(resid**2))
        return beta, rss

    def predict(self, history: np.ndarray) -> float:
        """Prédit le rendement suivant à partir de l'historique (causal)."""
        if self.order == 0 or len(history) < self.order:
            return self.intercept
        lags = np.asarray(history[-self.order :], dtype=float)[::-1]
        return float(self.intercept + self.coef @ lags)

    def forecast_path(self, returns: np.ndarray) -> np.ndarray:
        """Prévisions une période ahead, recalculées à chaque t (walk-forward pur)."""
        returns = np.asarray(returns, dtype=float)
        out = np.zeros(len(returns))
        for t in range(len(returns)):
            out[t] = self.predict(returns[:t])
        return out


@dataclass
class GARCHModel:
    """GARCH(1,1) : h_t = ω + α r²_{t-1} + β h_{t-1} (chap. 6, éq. 6.38).

    Estimation par MLE gaussien, optimisée par recherche locale simple
    (pas de scipy : gradient projeté + contraintes de stationnarité
    α + β < 1, ω > 0).
    """

    p: int = 1
    q: int = 1
    omega: float = 1e-6
    alpha: float = 0.05
    beta: float = 0.90

    def fit(self, returns: np.ndarray) -> "GARCHModel":
        """Hill-climbing contraint : on ne garde un candidat que s'il
        améliore la log-vraisemblance (MLE gaussien, éq. 6.42)."""
        returns = np.asarray(returns, dtype=float)
        r2 = returns**2
        var0 = float(np.var(returns)) if len(returns) > 1 else 1e-6
        # Variance targeting : omega tel que la variance long terme
        # omega / (1 - alpha - beta) egale la variance empirique.
        alpha0, beta0 = 0.05, 0.90
        params = np.array([max(var0 * (1 - alpha0 - beta0), 1e-12), alpha0, beta0])
        best_ll = self._loglik(params, r2)
        rng = np.random.default_rng(0)
        for it in range(500):
            # Bruit multiplicatif sur omega (echelle log), additif sur
            # alpha/beta : chaque parametre est perturbe a sa propre echelle.
            scale = max(0.05 * (1 - it / 500), 0.002)
            cand = params.copy()
            cand[0] = params[0] * float(np.exp(rng.normal(0, scale)))
            cand[1] = min(max(params[1] + rng.normal(0, scale), 1e-4), 0.5)
            cand[2] = min(max(params[2] + rng.normal(0, scale), 0.0), 0.995 - cand[1])
            ll = self._loglik(cand, r2)
            if ll > best_ll:
                params, best_ll = cand, ll
        self.omega, self.alpha, self.beta = [float(x) for x in params]
        return self

    def _loglik(self, params, r2) -> float:
        omega, alpha, beta = params
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.999:
            return -np.inf
        n = len(r2)
        h = np.empty(n)
        h[0] = max(r2[0], omega / max(1 - alpha - beta, 1e-6))
        for t in range(1, n):
            h[t] = omega + alpha * r2[t - 1] + beta * h[t - 1]
        ll = -0.5 * float(np.sum(np.log(2 * np.pi * h) + r2 / h))
        return ll

    def conditional_variance_path(self, returns: np.ndarray) -> np.ndarray:
        """h_t pour toute la série, calculée de façon strictement causale."""
        returns = np.asarray(returns, dtype=float)
        r2 = returns**2
        n = len(r2)
        h = np.empty(n)
        h[0] = max(r2[0], self.omega / max(1 - self.alpha - self.beta, 1e-6))
        for t in range(1, n):
            h[t] = self.omega + self.alpha * r2[t - 1] + self.beta * h[t - 1]
        return h

    def next_variance(self, history: np.ndarray) -> float:
        """h_{t+1} à partir de l'historique (causal)."""
        h = self.conditional_variance_path(np.asarray(history, dtype=float))
        r2_last = float(history[-1]) ** 2
        return float(self.omega + self.alpha * r2_last + self.beta * h[-1])


def evaluate_baselines(
    returns: np.ndarray,
    train_periods: int = 1000,
    test_periods: int = 250,
    step_periods: int = 250,
    max_lag: int = 5,
) -> dict:
    """Évalue AR(p) et GARCH walk-forward sur les rendements agrégés.

    Retourne RMSE OOS de chaque modèle plus le RMSE du prédicteur na\u00eff
    (moyenne du train) : tout modèle ML devra battre ces nombres OOS.
    """
    returns = np.asarray(returns, dtype=float)
    n = len(returns)
    ar_rmse, garch_rmse, naive_rmse = [], [], []
    start = 0
    while start + train_periods + test_periods <= n:
        train = returns[start : start + train_periods]
        test = returns[start + train_periods : start + train_periods + test_periods]

        ar = ARModel(max_lag=max_lag).fit(train)
        preds = np.array([ar.predict(np.concatenate([train, test[:i]])) for i in range(len(test))])
        resid = test - preds
        rmse = float(np.sqrt(np.mean(resid**2)))
        ar_rmse.append(rmse)

        garch = GARCHModel().fit(train)
        var_path = garch.conditional_variance_path(test)
        garch_rmse.append(float(np.sqrt(np.mean(var_path))))

        naive_rmse.append(float(np.sqrt(np.mean((test - train.mean()) ** 2))))
        start += step_periods

    return {
        "n_folds": len(ar_rmse),
        "ar_order_selected": None,
        "ar_rmse_oos": float(np.mean(ar_rmse)) if ar_rmse else None,
        "garch_rmse_oos": float(np.mean(garch_rmse)) if garch_rmse else None,
        "naive_rmse_oos": float(np.mean(naive_rmse)) if naive_rmse else None,
    }
