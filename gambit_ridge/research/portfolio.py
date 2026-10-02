"""Construction de portefeuille : signaux -> poids, budget de risque.

Chaîne (toutes les étapes sont causales, ligne t = données <= t) :
1. sizing par actif : w_i = signal_i * vol_cible_actif / vol_prévue_i
   (chaque position contribue à risque égal, quel que soit l'actif :
   1 % de pente sur le gaz ne pèse pas 10x le dollar index)
2. vol cible du portefeuille : covariance EWMA (rétrécie vers sa
   diagonale) -> facteur d'échelle pour viser `port_vol`
3. garde-fous : plafond par position et d'exposition brute
"""

from __future__ import annotations

import numpy as np

from .signals import TRADING_DAYS, log_returns


def ewma_covariance(P: np.ndarray, halflife: float = 60.0, shrink: float = 0.3) -> np.ndarray:
    """Covariance annualisée EWMA (T, N, N), rétrécie vers la diagonale."""
    r = log_returns(P)
    T, N = r.shape
    lam = 0.5 ** (1.0 / halflife)
    C = np.zeros((T, N, N))
    init = r[1 : min(61, T)]
    c = np.cov(init.T) if len(init) > 2 else np.eye(N) * 1e-4
    for t in range(T):
        if t > 0:
            c = lam * c + (1 - lam) * np.outer(r[t], r[t])
        d = np.diag(np.diag(c))
        C[t] = ((1 - shrink) * c + shrink * d) * TRADING_DAYS
    return C


def build_weights(
    signal: np.ndarray,
    vol: np.ndarray,
    cov: np.ndarray,
    *,
    port_vol: float = 0.10,
    max_gross: float = 2.0,
    max_position: float = 0.40,
    risk_scale: np.ndarray | None = None,
) -> np.ndarray:
    T, N = signal.shape
    raw = signal * (port_vol / np.sqrt(N)) / vol
    W = np.zeros_like(raw)
    for t in range(T):
        w = raw[t]
        if not np.any(w):
            continue
        ex_ante = float(np.sqrt(max(w @ cov[t] @ w, 1e-16)))
        w = w * (port_vol / ex_ante)
        w = np.clip(w, -max_position, max_position)
        gross = np.abs(w).sum()
        if gross > max_gross:
            w = w * (max_gross / gross)
        if risk_scale is not None:
            w = w * risk_scale[t]
        W[t] = w
    return W


def risk_parity_long_only(vol: np.ndarray, cov: np.ndarray, port_vol: float = 0.10, max_gross: float = 2.0) -> np.ndarray:
    """Benchmark : parité de risque naïve long-only (inverse vol), vol cible."""
    sig = np.ones_like(vol)
    return build_weights(sig, vol, cov, port_vol=port_vol, max_gross=max_gross, max_position=1.0)
