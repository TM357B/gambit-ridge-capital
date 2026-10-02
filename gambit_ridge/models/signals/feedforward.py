"""Réseau feedforward — Dixon, Halperin & Bilokon, chap. 4
(éq. 4.28-4.40 : propagation, fonction de coût, backpropagation).

Architecture : entrée -> couche cachée (tanh) -> sortie linéaire
(régression sur le rendement forward cross-sectionnel démeané).

Implémentation numpy pure :
- initialisation Xavier (éq. 4.44),
- descente de gradient avec momentum,
- mini-batches, early stopping sur la perte de validation,
- le lot de validation est TOUJOURS postérieur au train dans le temps
  (découpage séquentiel, jamais aléatoire — règle n°2).

Interprétabilité (chap. 5) : importance des features par sensibilité —
dérivée de la sortie par rapport à chaque entrée, moyennée sur les
données (méthode des gradients simples, éq. 5.9-5.12).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def _tanh(x):
    return np.tanh(x)


def _tanh_grad(x):
    return 1.0 - np.tanh(x) ** 2


@dataclass
class FeedForwardNet:
    """Réseau à UNE couche cachée, régression (chap. 4)."""

    hidden: int = 16
    lr: float = 0.01
    momentum: float = 0.9
    batch_size: int = 64
    max_epochs: int = 200
    l2: float = 1e-4
    seed: int = 42
    patience: int = 20

    W1: np.ndarray = field(default_factory=lambda: np.array([]))
    b1: np.ndarray = field(default_factory=lambda: np.array([]))
    W2: np.ndarray = field(default_factory=lambda: np.array([]))
    b2: float = 0.0
    mu: np.ndarray | None = None
    sd: np.ndarray | None = None
    fitted: bool = False

    def _init(self, d_in: int, rng: np.random.default_rng) -> None:
        xavier1 = np.sqrt(6.0 / (d_in + self.hidden))
        self.W1 = rng.uniform(-xavier1, xavier1, size=(d_in, self.hidden))
        self.b1 = np.zeros(self.hidden)
        xavier2 = np.sqrt(6.0 / (self.hidden + 1))
        self.W2 = rng.uniform(-xavier2, xavier2, size=self.hidden)
        self.b2 = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "FeedForwardNet":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
        X, y = X[mask], y[mask]
        if len(X) < 2 * self.batch_size:
            return self
        self.mu = X.mean(axis=0)
        self.sd = np.where(X.std(axis=0, ddof=1) < 1e-12, 1.0, X.std(axis=0, ddof=1))
        Xs = (X - self.mu) / self.sd
        # découpage SÉQUENTIEL : le dernier 20% sert de validation
        n_val = max(int(0.2 * len(Xs)), 1)
        Xtr, ytr = Xs[:-n_val], y[:-n_val]
        Xva, yva = Xs[-n_val:], y[-n_val:]
        rng = np.random.default_rng(self.seed)
        self._init(Xs.shape[1], rng)
        vW1 = np.zeros_like(self.W1)
        vb1 = np.zeros_like(self.b1)
        vW2 = np.zeros_like(self.W2)
        vb2 = 0.0
        best_val = np.inf
        best_params = None
        epochs_no_improve = 0
        n = len(Xtr)
        for _ in range(self.max_epochs):
            order = rng.permutation(n)
            for start in range(0, n, self.batch_size):
                idx = order[start : start + self.batch_size]
                xb, yb = Xtr[idx], ytr[idx]
                h_pre = xb @ self.W1 + self.b1
                h = _tanh(h_pre)
                pred = h @ self.W2 + self.b2
                err = pred - yb
                # backprop
                gW2 = h.T @ err / len(idx) + self.l2 * self.W2
                gb2 = float(err.mean())
                gh = np.outer(err, self.W2) * _tanh_grad(h_pre)
                gW1 = xb.T @ gh / len(idx) + self.l2 * self.W1
                gb1 = gh.mean(axis=0)
                vW1 = self.momentum * vW1 - self.lr * gW1
                vb1 = self.momentum * vb1 - self.lr * gb1
                vW2 = self.momentum * vW2 - self.lr * gW2
                vb2 = self.momentum * vb2 - self.lr * gb2
                self.W1 += vW1
                self.b1 += vb1
                self.W2 += vW2
                self.b2 += vb2
            val_mse = float(np.mean((self._forward(Xva) - yva) ** 2))
            if val_mse < best_val - 1e-10:
                best_val = val_mse
                best_params = (self.W1.copy(), self.b1.copy(), self.W2.copy(), self.b2)
                epochs_no_improve = 0
            else:
                epochs_no_improve += 1
                if epochs_no_improve >= self.patience:
                    break
        if best_params is not None:
            self.W1, self.b1, self.W2, self.b2 = best_params
        self.fitted = True
        return self

    def _forward(self, Xs: np.ndarray) -> np.ndarray:
        return _tanh(Xs @ self.W1 + self.b1) @ self.W2 + self.b2

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.fitted:
            return np.zeros(len(X))
        Xs = (np.asarray(X, dtype=float) - self.mu) / self.sd
        return self._forward(Xs)

    def feature_importance(self, X: np.ndarray) -> np.ndarray:
        """Sensibilité |dy/dx_k| moyenne sur les données (chap. 5, éq. 5.9-5.12)."""
        if not self.fitted:
            return np.array([])
        Xs = (np.asarray(X, dtype=float) - self.mu) / self.sd
        h_pre = Xs @ self.W1 + self.b1
        dh_dx = _tanh_grad(h_pre)  # (n, hidden)
        # dy/dx_k = somme_h W2_h * dh/dx_pre_h * W1[k, h]
        sens = np.abs(dh_dx @ np.diag(self.W2) @ self.W1.T)  # (n, d)
        return sens.mean(axis=0)
