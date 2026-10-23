"""Filtre particulaire et volatilité stochastique (Dixon, Halperin & Bilokon, ch. 7, § 3-4).

Modèle SVLJ (Malik & Pitt ; éq. 7.13-7.14) sur les log-rendements y_t, x_t = log-variance :
    y_t     = ε_t exp(x_t / 2) + J_t ϖ_t,           J_t ~ Bernoulli(p), ϖ_t ~ N(0, σ_J²)
    x_{t+1} = μ (1 - φ) + φ x_t + σ_v η_t,          corr(ε_t, η_t) = ρ (effet de levier, ρ < 0)

Filtre SIR (§ 3.1) avec rééchantillonnage multinomial (§ 3.2) : M particules de x_t, pondérées par
la densité de y_t, propagées avec la loi conditionnelle de η_t sachant ε_t (levier). La vraisemblance
du filtre sert au calibrage ponctuel (§ 4) : maximum de vraisemblance par Nelder-Mead à nombres
aléatoires communs (même graine à chaque évaluation, sinon la vraisemblance « tremble »).

Fonction terminal svol : vol filtrée (moyenne et bande 5-95 % des particules) d'un ticker réel,
comparée à la GARCH(1,1) et à la vol réalisée ; vraisemblances comparées ; prévision de la
structure par terme de la vol par le modèle. numpy seul.
"""

from __future__ import annotations

import math
import time

import numpy as np

from .optim import nelder_mead

JOURS_AN = 252


def _vers(theta, sauts):
    """Paramètres libres -> contraints : μ réel, φ ∈ (-1, 1), σ_v > 0, ρ ∈ (-1, 1), p ∈ (0, 0,2), σ_J > 0."""
    mu, phi, sv, rho = theta[0], math.tanh(theta[1]), math.exp(theta[2]), math.tanh(theta[3])
    p, sj = (0.2 / (1 + math.exp(-theta[4])), math.exp(theta[5])) if sauts else (0.0, 0.0)
    return mu, phi, sv, rho, p, sj


def filtre(y, mu, phi, sv, rho, p=0.0, sj=0.0, M=1000, graine=1, garder=False):
    """SIR sur les log-rendements y (quotidiens). Renvoie log-vraisemblance et, si garder, la vol filtrée."""
    rng = np.random.default_rng(graine)
    T = len(y)
    x = mu + sv / math.sqrt(max(1 - phi**2, 1e-6)) * rng.standard_normal(M)  # loi stationnaire
    llh = 0.0
    if garder:
        moy, q05, q95 = np.empty(T), np.empty(T), np.empty(T)
    s = math.sqrt(max(1 - rho**2, 1e-12))
    for t in range(T):
        var = np.exp(x)
        dens = (1 - p) * np.exp(-0.5 * y[t] ** 2 / var) / np.sqrt(2 * math.pi * var)
        if p > 0:
            vj = var + sj**2
            dens = dens + p * np.exp(-0.5 * y[t] ** 2 / vj) / np.sqrt(2 * math.pi * vj)
        tot = dens.mean()
        if not np.isfinite(tot) or tot <= 0:
            return -1e12, None
        llh += math.log(tot)
        w = dens / dens.sum()
        if garder:
            vol = np.sqrt(var * JOURS_AN)
            moy[t] = float(w @ vol)
            o = np.argsort(vol)
            cw = np.cumsum(w[o])
            q05[t], q95[t] = vol[o][np.searchsorted(cw, 0.05)], vol[o][min(np.searchsorted(cw, 0.95), M - 1)]
        # rééchantillonnage multinomial (§ 3.2)
        i = np.searchsorted(np.cumsum(w), rng.random(M))
        x = x[np.minimum(i, M - 1)]
        eps = y[t] * np.exp(-x / 2)  # choc de rendement implicite (levier)
        x = mu * (1 - phi) + phi * x + sv * (rho * eps + s * rng.standard_normal(M))
    return llh, ({"moyenne": moy, "q05": q05, "q95": q95, "x_final": x} if garder else None)


def calibrer(y, sauts=False, M=600, graine=1, iter_par_param=60):
    """Maximum de vraisemblance particulaire (§ 4), nombres aléatoires communs."""
    v0 = float(np.var(y))
    theta0 = [math.log(v0), math.atanh(0.97), math.log(0.2), math.atanh(-0.5)] + ([-2.0, math.log(3 * math.sqrt(v0))] if sauts else [])

    def nll(theta):
        llh, _ = filtre(y, *_vers(theta, sauts), M=M, graine=graine)
        return -llh

    theta, val, evals = nelder_mead(nll, theta0, pas=0.4, iter_max=iter_par_param * len(theta0), tol=1e-7)
    return _vers(theta, sauts), -val, evals


def vol_predictive(y, mu, phi, sv, rho, p=0.0, sj=0.0, M=1000, graine=1, plancher=0.02):
    """Prévision de vol annualisée à 1 jour, causale : out[t] = vol attendue pour y[t+1] connue après y[t]
    (même convention que research.signals.garch_vol). y : log-rendements quotidiens."""
    rng = np.random.default_rng(graine)
    x = mu + sv / math.sqrt(max(1 - phi**2, 1e-6)) * rng.standard_normal(M)
    s = math.sqrt(max(1 - rho**2, 1e-12))
    out = np.empty(len(y))
    for t in range(len(y)):
        var = np.exp(x)
        dens = (1 - p) * np.exp(-0.5 * y[t] ** 2 / var) / np.sqrt(2 * math.pi * var)
        if p > 0:
            vj = var + sj**2
            dens = dens + p * np.exp(-0.5 * y[t] ** 2 / vj) / np.sqrt(2 * math.pi * vj)
        tot = dens.sum()
        w = dens / tot if np.isfinite(tot) and tot > 0 else np.full(M, 1.0 / M)
        i = np.searchsorted(np.cumsum(w), rng.random(M))
        x = x[np.minimum(i, M - 1)]
        eps = y[t] * np.exp(-x / 2)
        x = mu * (1 - phi) + phi * x + sv * (rho * eps + s * rng.standard_normal(M))
        out[t] = math.sqrt(float(np.exp(x).mean()) * JOURS_AN)  # E[variance de t+1 | y_1..t]
    return np.maximum(out, plancher)


def garch_llh(y):
    """Log-vraisemblance gaussienne d'une GARCH(1,1) ajustée (référence du repo, research/signals.py)."""
    from ..research.signals import fit_garch11

    omega, alpha, beta = fit_garch11(y)
    h = np.empty(len(y))
    h[0] = np.var(y)
    for t in range(1, len(y)):
        h[t] = omega + alpha * y[t - 1] ** 2 + beta * h[t - 1]
    return float(-0.5 * np.sum(np.log(2 * math.pi * h) + y**2 / h)), np.sqrt(h * JOURS_AN), (omega, alpha, beta)


def svol(symbole: str, params: dict | None = None) -> dict:
    """Volatilité stochastique d'un actif réel : calibrage, vol filtrée, comparaison GARCH, prévision."""
    from ..data.yahoo import YahooConnector

    t0 = time.time()
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}
    try:
        ans = float(p.get("ans", 3))
    except ValueError:
        raise ValueError("ans invalide") from None
    if not 1 <= ans <= 10:
        raise ValueError("période de 1 à 10 ans")
    sauts = str(p.get("sauts", "0")) in ("1", "true", "oui")
    data = YahooConnector().fetch(symbole, refresh=True)
    dates = sorted(data)
    px = np.array([data[d] for d in dates], dtype=float)
    n = int(ans * JOURS_AN)
    if len(px) < n + 30:
        raise ValueError(f"historique trop court pour {symbole}")
    y = np.diff(np.log(px[-(n + 1):]))
    y = y - y.mean()
    dates = dates[-n:]

    (mu, phi, sv, rho, pj, sj), llh, evals = calibrer(y, sauts=sauts)
    llh_f, f = filtre(y, mu, phi, sv, rho, pj, sj, M=3000, graine=2, garder=True)
    llh_g, vol_g, (om, al, be) = garch_llh(y)
    real = np.full(n, np.nan)
    for t in range(20, n):
        real[t] = y[t - 20:t + 1].std(ddof=1) * math.sqrt(JOURS_AN)

    # prévision de la vol par le modèle : E[x_{t+h}] = μ + φ^h (E[x_t] - μ) (+ ½ Var pour E[e^x])
    xT = f["x_final"]
    horizons = [1, 5, 21, 63, 126, 252]
    prev = []
    for h in horizons:
        mx = mu + phi**h * (xT.mean() - mu)
        vx = phi ** (2 * h) * xT.var() + sv**2 * (1 - phi ** (2 * h)) / max(1 - phi**2, 1e-9)
        prev.append({"jours": h, "vol": math.sqrt(math.exp(mx + vx / 2) * JOURS_AN)})
    demi_vie = math.log(0.5) / math.log(abs(phi)) if 0 < abs(phi) < 1 else None
    pas = max(1, n // 400)  # ~400 points pour l'affichage
    sel = list(range(0, n, pas)) + ([n - 1] if (n - 1) % pas else [])

    def lst(a):
        return [None if not np.isfinite(a[i]) else round(float(a[i]), 5) for i in sel]

    return {"symbol": symbole, "asof": dates[-1], "jours": n, "sauts": sauts,
            "params": {"mu": mu, "vol_long_terme": math.sqrt(math.exp(mu + sv**2 / (2 * max(1 - phi**2, 1e-9))) * JOURS_AN),
                       "phi": phi, "sigma_v": sv, "rho": rho, "p_saut": pj, "sigma_saut": sj, "demi_vie_jours": demi_vie},
            "vraisemblance": {"sv": llh_f, "garch": llh_g, "n_params_sv": 6 if sauts else 4, "n_params_garch": 3,
                              "aic_sv": 2 * (6 if sauts else 4) - 2 * llh_f, "aic_garch": 6 - 2 * llh_g},
            "garch": {"omega": om, "alpha": al, "beta": be},
            "dates": [dates[i] for i in sel], "vol_sv": lst(f["moyenne"]), "q05": lst(f["q05"]), "q95": lst(f["q95"]),
            "vol_garch": lst(vol_g), "vol_realisee": lst(real),
            "derniere": {"sv": float(f["moyenne"][-1]), "garch": float(vol_g[-1]), "realisee": float(real[-1])},
            "prevision": prev, "evaluations": evals, "ms": round((time.time() - t0) * 1000)}
