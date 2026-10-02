"""Filtre de Kalman — Dixon, Halperin & Bilokon, chap. 7 (éq. 7.3-7.13).

Modèle espace-état linéaire-gaussien pour estimer DYNAMIQUEMENT le bêta
et l'alpha de chaque titre, au lieu de régressions statiques glissantes :

    y_t = x_t' * theta_t + eps_t        (équation d'observation)
    theta_t = theta_{t-1} + eta_t       (équation d'état, marche aléatoire)

avec y_t = rendement excédentaire du titre, x_t = [rendement du marché,
1] et theta_t = [beta_t, alpha_t].

Le filtre de Kalman (prediction + mise a jour, éq. 7.8-7.13) est
STRICTEMENT CAUSAL : theta_t n'utilise que les données <= t. C'est le
filtre optimal au sens MMSE pour ce modèle.

Implémentation numpy pure : un pas de filtre = O(d^2), d = dim(theta).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class KalmanBeta:
    """Filtre de Kalman pour bêta/alpha variant dans le temps.

    Paramètres :
        delta : rapport signal/bruit de l'évolution de theta
                (delta grand -> theta change vite ; typiquement 1e-4..1e-2)
        q : variance du bruit d'observation (calibrée sur la vol du titre)
        r : variance du bruit d'état (utilise delta * covariance empirique)
    """

    delta: float = 1e-2
    theta: np.ndarray = field(default_factory=lambda: np.zeros(2))
    P: np.ndarray = field(default_factory=lambda: np.eye(2))
    q: float = 1e-4
    initialized: bool = False

    def initialize(self, asset_returns: np.ndarray, market_returns: np.ndarray) -> "KalmanBeta":
        """Initialise theta par OLS sur la fenêtre fournie (passé uniquement)."""
        y = np.asarray(asset_returns, dtype=float)
        x = np.asarray(market_returns, dtype=float)
        X = np.column_stack([x, np.ones(len(x))])
        theta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ theta
        n, d = X.shape
        sigma2 = max(float(np.sum(resid**2) / max(n - d, 1)), 1e-12)
        self.theta = theta
        # Covariance OLS comme incertitude initiale
        try:
            XtX_inv = np.linalg.inv(X.T @ X)
            self.P = sigma2 * XtX_inv
        except np.linalg.LinAlgError:
            self.P = np.eye(2) * sigma2
        self.q = sigma2
        self.initialized = True
        return self

    def step(self, y_t: float, x_t: float) -> tuple[float, float]:
        """Un pas du filtre (éq. 7.8-7.13). Retourne (beta_t, alpha_t) a posteriori.

        y_t : rendement du titre à t ; x_t : rendement du marché à t.
        Paramétrisation standard de la régression dynamique (chap. 7.3) :
            R (bruit d'observation) = variance résiduelle estimée à l'init
            Q (bruit d'état) = delta/(1-delta) * diag(P) — proportionnel à
            l'incertitude courante, indépendant de l'échelle de x_t.
        """
        if not self.initialized:
            raise RuntimeError("KalmanBeta.initialize() doit être appelé avant step()")
        H = np.array([x_t, 1.0])
        # Prédiction
        theta_pred = self.theta
        Q = (self.delta / max(1.0 - self.delta, 1e-6)) * np.diag(np.diag(self.P))
        P_pred = self.P + Q
        # Mise à jour
        y_hat = float(H @ theta_pred)
        S = float(H @ P_pred @ H) + self.q  # variance de l'innovation
        if S < 1e-15:
            return float(self.theta[0]), float(self.theta[1])
        K = (P_pred @ H) / S  # gain de Kalman
        innov = y_t - y_hat
        self.theta = theta_pred + K * innov
        I_KH = np.eye(2) - np.outer(K, H)
        self.P = I_KH @ P_pred @ I_KH.T + np.outer(K, K) * self.q  # forme Joseph
        return float(self.theta[0]), float(self.theta[1])

    def filter_path(
        self, asset_returns: np.ndarray, market_returns: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Filtre toute la série : retourne (betas, alphas) à chaque t, causaux.

        Le premier point est l'initialisation OLS ; chaque pas suivant
        n'utilise que (y_s, x_s) pour s <= t.
        """
        y = np.asarray(asset_returns, dtype=float)
        x = np.asarray(market_returns, dtype=float)
        if len(y) != len(x):
            raise ValueError("séries de longueurs différentes")
        betas = np.zeros(len(y))
        alphas = np.zeros(len(y))
        for t in range(len(y)):
            if t == 0:
                if not self.initialized:
                    self.initialize(y[: max(len(y) // 4, 30)], x[: max(len(y) // 4, 30)])
                betas[t], alphas[t] = float(self.theta[0]), float(self.theta[1])
                continue
            betas[t], alphas[t] = self.step(float(y[t]), float(x[t]))
        return betas, alphas
