"""Autoencodeur — Dixon, Halperin & Bilokon, chap. 8
(éq. 8.4-8.15 : architecture, reconstruction, bottleneck).

Généralisation non linéaire de l'ACP : compresse les features dans un
espace latent de dimension réduite. L'espace latent sert à :
1. extraire des facteurs non observables (complément des facteurs
   observés momentum/volatilité),
2. débruiter les features avant le modèle de classement.

Entraîné par gradient (Adam-like avec momentum) sur la perte de
reconstruction MSE, mini-batches, validation séquentielle en fin de
fenêtre (jamais aléatoire). Le fit ne voit QUE la fenêtre fournie.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class AutoEncoder:
    """Autoencodeur à une couche cachée (bottleneck latent)."""

    latent_dim: int = 3
    lr: float = 0.01
    momentum: float = 0.9
    batch_size: int = 64
    max_epochs: int = 150
    l2: float = 1e-4
    seed: int = 42
    patience: int = 20

    W1: np.ndarray = field(default_factory=lambda: np.array([]))
    b1: np.ndarray = field(default_factory=lambda: np.array([]))
    W2: np.ndarray = field(default_factory=lambda: np.array([]))
    b2: np.ndarray = field(default_factory=lambda: np.array([]))
    mu: np.ndarray | None = None
    sd: np.ndarray | None = None
    fitted: bool = False

    def _init(self, d_in: int, rng: np.random.default_rng) -> None:
        x1 = np.sqrt(6.0 / (d_in + self.latent_dim))
        self.W1 = rng.uniform(-x1, x1, size=(d_in, self.latent_dim))
        self.b1 = np.zeros(self.latent_dim)
        x2 = np.sqrt(6.0 / (self.latent_dim + d_in))
        self.W2 = rng.uniform(-x2, x2, size=(self.latent_dim, d_in))
        self.b2 = np.zeros(d_in)

    def fit(self, X: np.ndarray) -> "AutoEncoder":
        X = np.asarray(X, dtype=float)
        X = X[np.isfinite(X).all(axis=1)]
        if len(X) < 2 * self.batch_size:
            return self
        self.mu = X.mean(axis=0)
        self.sd = np.where(X.std(axis=0, ddof=1) < 1e-12, 1.0, X.std(axis=0, ddof=1))
        Xs = (X - self.mu) / self.sd
        n_val = max(int(0.2 * len(Xs)), 1)
        Xtr, Xva = Xs[:-n_val], Xs[-n_val:]
        rng = np.random.default_rng(self.seed)
        self._init(Xs.shape[1], rng)
        v = {"W1": np.zeros_like(self.W1), "b1": np.zeros_like(self.b1),
             "W2": np.zeros_like(self.W2), "b2": np.zeros_like(self.b2)}
        best_val = np.inf
        best = None
        no_improve = 0
        n = len(Xtr)
        for _ in range(self.max_epochs):
            order = rng.permutation(n)
            for start in range(0, n, self.batch_size):
                idx = order[start : start + self.batch_size]
                xb = Xtr[idx]
                z = np.tanh(xb @ self.W1 + self.b1)
                rec = z @ self.W2 + self.b2
                err = rec - xb  # (n_b, d)
                gW2 = z.T @ err / len(idx) + self.l2 * self.W2
                gb2 = err.mean(axis=0)
                gz = (err @ self.W2.T) * (1.0 - z**2)
                gW1 = xb.T @ gz / len(idx) + self.l2 * self.W1
                gb1 = gz.mean(axis=0)
                for k, g in (("W1", gW1), ("b1", gb1), ("W2", gW2), ("b2", gb2)):
                    v[k] = self.momentum * v[k] - self.lr * g
                self.W1 += v["W1"]; self.b1 += v["b1"]
                self.W2 += v["W2"]; self.b2 += v["b2"]
            rec_va = np.tanh(Xva @ self.W1 + self.b1) @ self.W2 + self.b2
            val = float(np.mean((rec_va - Xva) ** 2))
            if val < best_val - 1e-12:
                best_val = val
                best = (self.W1.copy(), self.b1.copy(), self.W2.copy(), self.b2.copy())
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= self.patience:
                    break
        if best is not None:
            self.W1, self.b1, self.W2, self.b2 = best
        self.fitted = True
        return self

    def encode(self, X: np.ndarray) -> np.ndarray:
        """Projection dans l'espace latent (facteurs non observables)."""
        if not self.fitted:
            return np.zeros((len(X), self.latent_dim))
        Xs = (np.asarray(X, dtype=float) - self.mu) / self.sd
        return np.tanh(Xs @ self.W1 + self.b1)

    def reconstruct(self, X: np.ndarray) -> np.ndarray:
        """Reconstruction (pour mesurer l'anomalie de reconstruction)."""
        if not self.fitted:
            return np.asarray(X, dtype=float)
        return self.encode(X) @ self.W2 + self.b2

    def reconstruction_error(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        return np.mean((self.reconstruct(X) - (X - self.mu) / self.sd) ** 2, axis=1)
