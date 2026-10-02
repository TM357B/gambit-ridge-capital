"""Signaux causaux vectorisés — matrices (T dates x N actifs).

Chaque fonction prend une matrice de prix P (T x N) et renvoie une matrice
de même forme dont la ligne t n'utilise QUE les lignes <= t (filtres
récursifs). Un test dédié vérifie cette propriété en recalculant chaque
signal sur l'historique tronqué (tests/test_research.py).

Références (Dixon, Halperin & Bilokon, "Machine Learning in Finance", 2020) :
- vol EWMA / GARCH(1,1)      : chap. 6 §2.9-2.10 (prévision de variance,
                                demi-vie ln(0.5)/ln(alpha+beta))
- tendance par lissage expo.  : chap. 6 §2.10 (éq. 6.35)
- tendance Kalman            : chap. 7 §2.2 (modèle espace-état linéaire
                                gaussien, niveau + pente)
- régime HMM                 : chap. 7 §2 (probabilités filtrées)
"""

from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def log_returns(P: np.ndarray) -> np.ndarray:
    """r[t] = log(P[t]/P[t-1]), r[0] = 0."""
    r = np.zeros_like(P, dtype=float)
    r[1:] = np.log(P[1:] / P[:-1])
    return r


def ewma(x: np.ndarray, span: float) -> np.ndarray:
    """Lissage exponentiel (éq. 6.35), alpha = 2/(span+1), causal."""
    a = 2.0 / (span + 1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for t in range(1, len(x)):
        out[t] = out[t - 1] + a * (x[t] - out[t - 1])
    return out


def ewma_vol(P: np.ndarray, halflife: float = 30.0, floor: float = 0.02) -> np.ndarray:
    """Vol annualisée EWMA (RiskMetrics) — cas limite IGARCH du GARCH(1,1)."""
    r = log_returns(P)
    lam = 0.5 ** (1.0 / halflife)
    var = np.empty_like(r)
    init_n = min(60, len(r) - 1)
    var[0] = np.var(r[1 : init_n + 1], axis=0) if init_n > 1 else r[0] ** 2 + 1e-8
    for t in range(1, len(r)):
        var[t] = lam * var[t - 1] + (1 - lam) * r[t] ** 2
    return np.maximum(np.sqrt(var * TRADING_DAYS), floor)


def fit_garch11(r: np.ndarray) -> tuple[float, float, float]:
    """GARCH(1,1) par MLE gaussien avec variance targeting (chap. 6 §2.9).

    omega = var(r) * (1 - alpha - beta) : la variance long terme égale la
    variance empirique ; reste une recherche 2-D (alpha, beta) sur grille
    puis raffinement local. Robuste, sans scipy.
    """
    r = np.asarray(r, dtype=float)
    r = r - r.mean()
    v = float(np.var(r))
    r2 = r**2

    def ll(a: float, b: float) -> float:
        if a <= 0 or b < 0 or a + b >= 0.999:
            return -np.inf
        w = v * (1 - a - b)
        h = np.empty_like(r2)
        h[0] = v
        for t in range(1, len(r2)):
            h[t] = w + a * r2[t - 1] + b * h[t - 1]
        return -0.5 * float(np.sum(np.log(h) + r2 / h))

    best = (0.05, 0.90)
    best_ll = ll(*best)
    for a in (0.02, 0.04, 0.06, 0.08, 0.10, 0.14):
        for b in (0.80, 0.85, 0.88, 0.91, 0.93, 0.95, 0.97):
            val = ll(a, b)
            if val > best_ll:
                best, best_ll = (a, b), val
    step = 0.01
    for _ in range(3):
        a0, b0 = best
        for da in (-step, 0, step):
            for db in (-step, 0, step):
                val = ll(a0 + da, b0 + db)
                if val > best_ll:
                    best, best_ll = (a0 + da, b0 + db), val
        step /= 2
    a, b = best
    return v * (1 - a - b), a, b


def garch_vol(
    P: np.ndarray,
    refit_every: int = TRADING_DAYS,
    min_history: int = 500,
    halflife_fallback: float = 30.0,
    floor: float = 0.02,
) -> np.ndarray:
    """Prévision de vol à 1 jour GARCH(1,1), annualisée, causale.

    Les paramètres sont ré-estimés tous les `refit_every` jours sur
    l'historique disponible (fenêtre expansive) puis le filtre avance
    jour par jour. Avant `min_history` jours : EWMA.
    """
    r = log_returns(P)
    T, N = r.shape
    out = ewma_vol(P, halflife_fallback, floor) ** 2 / TRADING_DAYS  # variance journalière
    for j in range(N):
        params = None
        h = out[min_history - 1, j] if T >= min_history else None
        for t in range(min_history, T):
            if params is None or (t - min_history) % refit_every == 0:
                params = fit_garch11(r[1:t, j])
            w, a, b = params
            # h[t] = prévision de var(r[t+1]) connue à la clôture t
            h = w + a * (r[t, j] - 0.0) ** 2 + b * h
            out[t, j] = h
    return np.maximum(np.sqrt(out * TRADING_DAYS), floor)


def tsmom(P: np.ndarray, lookback: int = 252) -> np.ndarray:
    """Time-series momentum (Moskowitz, Ooi & Pedersen 2012) : signe du
    rendement sur `lookback` jours, dans {-1, 0, +1}."""
    S = np.zeros_like(P, dtype=float)
    S[lookback:] = np.sign(np.log(P[lookback:] / P[:-lookback]))
    return S


def ewma_trend(
    P: np.ndarray,
    pairs: tuple[tuple[int, int], ...] = ((8, 24), (16, 48), (32, 96)),
    price_vol_window: int = 63,
    norm_window: int = 252,
) -> np.ndarray:
    """Tendance multi-vitesses par croisement de moyennes exponentielles
    (chap. 6 §2.10), normalisation de Baz et al. (2015).

    x = (EWMA_court - EWMA_long) / écart-type du prix sur 63 j
    y = x / écart-type de x sur 252 j
    réponse phi(y) = y * exp(-y^2/4) / 0.89  (bornée, décroît si
    l'excès de tendance devient extrême — protège des retournements).
    Moyenne des 3 vitesses, dans [-1, 1] environ.
    """
    T, N = P.shape
    out = np.zeros((T, N))
    for j in range(N):
        p = P[:, j]
        sd_p = _rolling_std(p, price_vol_window)
        acc = np.zeros(T)
        for s, l in pairs:
            x = (ewma(p, s) - ewma(p, l)) / np.where(sd_p > 0, sd_p, np.nan)
            x = np.nan_to_num(x)
            sd_x = _rolling_std(x, norm_window)
            y = np.where(sd_x > 0, x / np.where(sd_x > 0, sd_x, 1.0), 0.0)
            acc += y * np.exp(-(y**2) / 4.0) / 0.89
        sig = acc / len(pairs)
        sig[: max(norm_window, max(l for _, l in pairs))] = 0.0
        out[:, j] = sig
    return out


def kalman_trend(
    P: np.ndarray,
    level_noise: float = 1.0,
    slope_noise_ratio: float = 1e-4,
    obs_noise: float = 0.01,
    warmup: int = 252,
) -> np.ndarray:
    """Tendance par filtre de Kalman sur modèle à niveau + pente (chap. 7).

    État x_t = [niveau, pente] du log-prix :
        niveau_t = niveau_{t-1} + pente_{t-1} + eta1
        pente_t  = pente_{t-1} + eta2
        y_t      = niveau_t + eps          (log-prix observé)
    Avec s2 = variance journalière des rendements (EWMA) :
    Var(eta1) = s2 (marche aléatoire du prix), Var(eta2) = ratio * s2,
    Var(eps) = 0.01 * s2 (bruit de microstructure). Le gain sur la pente
    vaut ~sqrt(ratio) = 0.01 : mémoire effective ~100 jours (moyen terme).
    Signal = pente filtrée / écart-type a posteriori de la pente
    (t-stat de la tendance), comprimé dans [-1, 1] par tanh(z/2).
    Contrairement à un momentum brut, le signal intègre l'INCERTITUDE de
    l'estimation : une tendance bruitée donne un signal faible.
    """
    y = np.log(P)
    T, N = y.shape
    vol_d = ewma_vol(P, halflife=60.0, floor=0.01) / np.sqrt(TRADING_DAYS)
    F = np.array([[1.0, 1.0], [0.0, 1.0]])
    H = np.array([1.0, 0.0])
    out = np.zeros((T, N))
    for j in range(N):
        x = np.array([y[0, j], 0.0])
        Pc = np.diag([1.0, 1e-4])
        for t in range(1, T):
            s2 = vol_d[t - 1, j] ** 2
            Q = np.diag([level_noise * s2, slope_noise_ratio * s2])
            r_obs = obs_noise * s2
            # prédiction
            x = F @ x
            Pc = F @ Pc @ F.T + Q
            # mise à jour
            S = H @ Pc @ H + r_obs
            K = Pc @ H / S
            x = x + K * (y[t, j] - H @ x)
            Pc = Pc - np.outer(K, H @ Pc)
            if t >= warmup:
                z = x[1] / np.sqrt(max(Pc[1, 1], 1e-16))
                out[t, j] = np.tanh(z / 2.0)
    return out


def hmm_risk_scale(
    P: np.ndarray,
    refit_every: int = TRADING_DAYS,
    min_history: int = 750,
    floor: float = 0.3,
) -> np.ndarray:
    """Échelle d'exposition globale [floor, 1] selon le régime HMM (chap. 7).

    HMM gaussien 2 états sur le rendement moyen équipondéré de l'univers,
    ré-estimé chaque année (fenêtre expansive). Échelle = 1 - (1-floor) *
    P(état haute vol | données <= t) — probabilité FILTRÉE, jamais lissée.
    Renvoie un vecteur (T,).
    """
    from ..models.regimes.hmm import GaussianHMM

    r = log_returns(P).mean(axis=1)
    T = len(r)
    scale = np.ones(T)
    model = None
    hi = 0
    alpha = None
    for t in range(min_history, T):
        if model is None or (t - min_history) % refit_every == 0:
            model = GaussianHMM(n_states=2, max_iter=60, seed=7).fit(r[1:t])
            hi = int(np.argmax(model.variances))
            # forward jusqu'à t-1 avec les nouveaux paramètres
            alpha = model.filtered_posteriors(r[1:t])[-1]
        # un pas de forward : prédiction puis correction par r[t]
        pred = alpha @ model.transmat
        lik = np.exp(-0.5 * (r[t] - model.means) ** 2 / model.variances) / np.sqrt(model.variances)
        post = pred * lik
        s = post.sum()
        alpha = post / s if s > 0 else pred
        scale[t] = 1.0 - (1.0 - floor) * float(alpha[hi])
    return scale


def _rolling_std(x: np.ndarray, window: int) -> np.ndarray:
    """Écart-type glissant causal (ddof=1), 0 avant la fenêtre."""
    out = np.zeros(len(x))
    if len(x) < window:
        return out
    c1 = np.cumsum(np.insert(x, 0, 0.0))
    c2 = np.cumsum(np.insert(x * x, 0, 0.0))
    s1 = c1[window:] - c1[:-window]
    s2 = c2[window:] - c2[:-window]
    var = (s2 - s1 * s1 / window) / (window - 1)
    out[window - 1 :] = np.sqrt(np.maximum(var, 0.0))
    return out
