"""Régression linéaire régularisée (ridge) — Dixon, Halperin & Bilokon,
chap. 4 (éq. 4.11-4.18) : baseline ML que tout réseau devra battre.

Estimation par équation normale fermée avec pénalité L2 :
    theta = (X'X + lambda*I)^-1 X'y
La standardisation des features est faite SUR LE TRAIN uniquement
(moyennes/écarts du train stockés, appliqués tels quels au test).

Les cibles sont démeanées par date (rendement forward cross-sectional
demeaned) : le modèle apprend le CLASSEMENT relatif des actifs, pas la
direction absolue du marché (approche cross-sectionnelle standard).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class RidgeModel:
    """Ridge cross-sectional : prédit le rendement forward relatif."""

    lam: float = 10.0
    theta: np.ndarray | None = None
    mu: np.ndarray | None = None
    sd: np.ndarray | None = None
    fitted: bool = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeModel":
        """X : (n_samples, n_features), y : (n_samples,).

        Les NaN sont éliminés ligne par ligne.
        """
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
        X, y = X[mask], y[mask]
        if len(X) < X.shape[1] + 2:
            return self
        self.mu = X.mean(axis=0)
        self.sd = np.where(X.std(axis=0, ddof=1) < 1e-12, 1.0, X.std(axis=0, ddof=1))
        Xs = (X - self.mu) / self.sd
        Xs = np.column_stack([np.ones(len(Xs)), Xs])
        A = Xs.T @ Xs + self.lam * np.eye(Xs.shape[1])
        A[0, 0] -= self.lam  # pas de pénalité sur l'intercept
        self.theta = np.linalg.solve(A, Xs.T @ y)
        self.fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Scores de classement (rendement forward prédit, relatif)."""
        if not self.fitted or self.theta is None:
            return np.zeros(len(X))
        X = np.asarray(X, dtype=float)
        Xs = (X - self.mu) / self.sd
        Xs = np.column_stack([np.ones(len(Xs)), Xs])
        return Xs @ self.theta

    def feature_importance(self) -> np.ndarray:
        """|theta_k| standardisé : importance relative des features."""
        if not self.fitted or self.theta is None:
            return np.array([])
        return np.abs(self.theta[1:]) / float(np.sum(np.abs(self.theta[1:]))) if np.sum(np.abs(self.theta[1:])) > 0 else np.abs(self.theta[1:])
