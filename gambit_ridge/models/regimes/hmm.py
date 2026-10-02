"""Modèles à états latents — Dixon, Halperin & Bilokon, chap. 7
(Probabilistic Sequence Modeling).

GaussianHMM : Hidden Markov Model gaussien à K états sur les rendements.
    - Entraînement : algorithme EM de Baum-Welch (éq. 7.30-7.42) :
      forward-backward avec scaling anti-underflow, M-step fermée pour
      les moyennes/covariances/transitions gaussiennes.
    - Décodage : Viterbi (éq. 7.16-7.19) pour le chemin d'états le plus
      probable, et forward filtré pour les probabilités a posteriori
      P(state_t | y_1..t) — STRICTEMENT CAUSALES, utilisables comme
      features sans fuite (contrairement au smoothed qui regarde t+1..T).

Anti-look-ahead : fit() ne voit que la fenêtre fournie ;
filtered_posteriors() recalcule le forward à chaque t avec les
observations passées uniquement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class GaussianHMM:
    """HMM gaussien à K états, émissions 1-D (rendements).

    États typiques pour K=3 : haussier (mu > 0, vol faible),
    baissier (mu < 0, vol moyenne), haute volatilité (mu ~ 0, vol élevée).
    """

    n_states: int = 3
    max_iter: int = 100
    tol: float = 1e-6
    seed: int = 42

    # Paramètres estimés
    means: np.ndarray = field(default_factory=lambda: np.array([]))
    variances: np.ndarray = field(default_factory=lambda: np.array([]))
    transmat: np.ndarray = field(default_factory=lambda: np.array([]))
    startprob: np.ndarray = field(default_factory=lambda: np.array([]))
    fitted: bool = False

    def _init_params(self, y: np.ndarray, rng: np.random.default_rng) -> None:
        n = len(y)
        # Quantiles pour initialiser les moyennes : robuste et déterministe
        qs = np.quantile(y, [0.2, 0.5, 0.8, 1.0])[: self.n_states]
        self.means = qs.copy()
        self.variances = np.full(self.n_states, max(np.var(y), 1e-10))
        self.transmat = np.full((self.n_states, self.n_states), 1.0 / self.n_states)
        self.startprob = np.full(self.n_states, 1.0 / self.n_states)
        # Petite perturbation pour briser la symétrie initiale
        self.transmat += rng.normal(0, 0.01, self.transmat.shape)
        self.transmat = np.clip(self.transmat, 1e-6, None)
        self.transmat /= self.transmat.sum(axis=1, keepdims=True)
        self.startprob = np.full(self.n_states, 1.0 / self.n_states)

    def _emission_logpdf(self, y: np.ndarray) -> np.ndarray:
        """log N(y_t | mu_k, var_k) -> matrice (T, K)."""
        T = len(y)
        out = np.empty((T, self.n_states))
        for k in range(self.n_states):
            var = max(self.variances[k], 1e-12)
            out[:, k] = -0.5 * (np.log(2 * np.pi * var) + (y - self.means[k]) ** 2 / var)
        return out

    # ---------------- Forward-backward (Baum-Welch, éq. 7.30-7.38) ----------------

    def _forward(self, loglik: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Forward avec scaling (anti-underflow, éq. 7.30-7.33).

        Retourne (alpha_scaled, normalisateurs c, log_likelihood).
        """
        T, K = loglik.shape
        alpha = np.zeros((T, K))
        c = np.zeros(T)
        alpha[0] = self.startprob * np.exp(loglik[0] - loglik[0].max())
        c[0] = max(alpha[0].sum(), 1e-300)
        alpha[0] /= c[0]
        for t in range(1, T):
            a = (alpha[t - 1] @ self.transmat) * np.exp(loglik[t] - loglik[t].max())
            c[t] = max(a.sum(), 1e-300)
            alpha[t] = a / c[t]
        # log P(y_1..T) = somme des log des normalisateurs + somme des maxima
        log_ll = float(np.sum(np.log(c)))
        return alpha, c, log_ll

    def _backward(self, loglik: np.ndarray, c: np.ndarray) -> np.ndarray:
        """Backward avec le même scaling que le forward (éq. 7.34-7.35).

        beta[T-1] = 1 (scalé) ; récursion descendante avec c[t+1].
        """
        T, K = loglik.shape
        beta = np.zeros((T, K))
        beta[T - 1] = 1.0
        for t in range(T - 2, -1, -1):
            b = self.transmat @ (np.exp(loglik[t + 1] - loglik[t + 1].max()) * beta[t + 1])
            beta[t] = b / max(c[t + 1], 1e-300)
        return beta

    def fit(self, returns: np.ndarray) -> "GaussianHMM":
        """Baum-Welch (EM) sur la fenêtre fournie uniquement."""
        y = np.asarray(returns, dtype=float)
        rng = np.random.default_rng(self.seed)
        self._init_params(y, rng)
        prev_ll = -np.inf
        for _ in range(self.max_iter):
            loglik = self._emission_logpdf(y)
            alpha, c, ll = self._forward(loglik)
            beta = self._backward(loglik, c)
            # gamma_t(k) = alpha_t(k) * beta_t(k), normalisé par ligne
            gamma = alpha * beta
            gamma /= np.clip(gamma.sum(axis=1, keepdims=True), 1e-300, None)

            # xi_t(i,j) proportionnel à alpha_t(i)*a_ij*N(y_{t+1}|j)*beta_{t+1}(j)
            T = len(y)
            log_trans = np.log(np.clip(self.transmat, 1e-300, None))
            xi_log = (
                np.log(np.clip(alpha[:-1], 1e-300, None))[:, :, None]
                + log_trans[None, :, :]
                + loglik[1:][:, None, :]
                + np.log(np.clip(beta[1:], 1e-300, None))[:, None, :]
            )
            xi = np.exp(xi_log - xi_log.max(axis=(1, 2), keepdims=True))
            xi /= np.clip(xi.sum(axis=(1, 2), keepdims=True), 1e-300, None)

            # M-step (éq. 7.39-7.42)
            self.startprob = np.clip(gamma[0], 1e-10, None)
            self.startprob /= self.startprob.sum()
            # M-step des transitions : xi agrégé par (i, j)
            xi_sum = xi.sum(axis=0)  # (K, K)
            self.transmat = xi_sum / np.clip(xi_sum.sum(axis=1, keepdims=True), 1e-300, None)
            self.transmat = np.clip(self.transmat, 1e-10, None)
            self.transmat /= self.transmat.sum(axis=1, keepdims=True)
            for k in range(self.n_states):
                gk = gamma[:, k]
                s = gk.sum()
                if s < 1e-10:
                    continue
                self.means[k] = float(np.dot(gk, y) / s)
                self.variances[k] = max(float(np.dot(gk, (y - self.means[k]) ** 2) / s), 1e-10)

            if abs(ll - prev_ll) < self.tol * max(abs(prev_ll), 1.0):
                prev_ll = ll
                break
            prev_ll = ll
        self.fitted = True
        return self

    # ---------------- Décodage ----------------

    def filtered_posteriors(self, returns: np.ndarray) -> np.ndarray:
        """P(state_t | y_1..t) — CAUSAL, utilisable comme feature.

        Recalcule le forward sur toute la série : à chaque ligne t,
        seules les observations <= t sont utilisées.
        """
        y = np.asarray(returns, dtype=float)
        loglik = self._emission_logpdf(y)
        alpha, _, _ = self._forward(loglik)
        return alpha  # déjà normalisé par le scaling

    def viterbi(self, returns: np.ndarray) -> np.ndarray:
        """Chemin d'états le plus probable (éq. 7.16-7.19).

        ATTENTION : non causal (utilise toute la série) — réservé à
        l'analyse hors backtest, jamais comme feature de trading.
        """
        y = np.asarray(returns, dtype=float)
        loglik = self._emission_logpdf(y)
        T, K = loglik.shape
        log_trans = np.log(np.clip(self.transmat, 1e-300, None))
        log_start = np.log(np.clip(self.startprob, 1e-300, None))
        delta = log_start + loglik[0]
        psi = np.zeros((T, K), dtype=int)
        for t in range(1, T):
            scores = delta[:, None] + log_trans  # (K, K)
            psi[t] = np.argmax(scores, axis=0)
            delta = scores.max(axis=0) + loglik[t]
        path = np.zeros(T, dtype=int)
        path[T - 1] = int(np.argmax(delta))
        for t in range(T - 2, -1, -1):
            path[t] = psi[t + 1, path[t + 1]]
        return path

    def state_labels(self) -> dict[int, str]:
        """Étiquette les états après fit : haussier / baissier / haute vol."""
        if not self.fitted:
            return {}
        order = np.argsort(self.means)  # moyen -> élevé
        labels = {}
        vol_median = float(np.median(np.sqrt(self.variances)))
        for k in range(self.n_states):
            if np.sqrt(self.variances[k]) > 1.5 * vol_median:
                labels[k] = "haute-volatilité"
            elif self.means[k] >= np.median(self.means):
                labels[k] = "haussier"
            else:
                labels[k] = "baissier"
        return labels
