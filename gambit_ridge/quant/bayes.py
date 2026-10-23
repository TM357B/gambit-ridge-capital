"""Inférence bayésienne, mélanges et sélection de modèles (Dixon, Halperin & Bilokon, ch. 2-3).

- RegressionBayesienne : régression linéaire conjuguée Normale-Gamma inverse (ch. 3 § 2) ; la loi a
  posteriori des coefficients et la prédictive (Student) sont fermées ; mises à jour séquentielles
  (ch. 2 § 6.2) : la loi a posteriori d'hier sert d'a priori aujourd'hui.
- melange_em : mélange gaussien 1-D par EM (ch. 2 § 8.1), K composantes.
- selection : critères BIC / AIC et poids de moyenne de modèles e^{-BIC/2} (ch. 2 § 7.2-7.5,
  rasoir d'Occam : la vraisemblance seule choisirait toujours le modèle le plus gros).
Fonctions terminal : beta (bêta bayésien d'un actif contre un indice), regm (régimes : mélange
i.i.d. contre HMM à persistance, ch. 7). numpy seul.
"""

from __future__ import annotations

import math
import time

import numpy as np

JOURS_AN = 252


class RegressionBayesienne:
    """y = X w + ε, ε ~ N(0, σ²) ; a priori w | σ² ~ N(m0, σ² V0), σ² ~ Gamma-inverse(a0, b0)."""

    def __init__(self, m0, V0, a0=2.0, b0=1e-4):
        self.m, self.V = np.asarray(m0, dtype=float), np.asarray(V0, dtype=float)
        self.a, self.b = float(a0), float(b0)

    def mettre_a_jour(self, X, y):
        X, y = np.atleast_2d(X), np.asarray(y, dtype=float)
        Vi0 = np.linalg.inv(self.V)
        Vi = Vi0 + X.T @ X
        V = np.linalg.inv(Vi)
        m = V @ (Vi0 @ self.m + X.T @ y)
        self.a += len(y) / 2
        self.b += 0.5 * float(y @ y + self.m @ Vi0 @ self.m - m @ Vi @ m)
        self.m, self.V = m, V
        return self

    def intervalle(self, i, niveau=0.95):
        """Intervalle de crédibilité du coefficient i (loi de Student à 2a degrés de liberté)."""
        et = math.sqrt(self.b / self.a * self.V[i, i])
        z = 1.96 if niveau == 0.95 else 2.576  # approximation normale : 2a est grand ici
        return float(self.m[i] - z * et), float(self.m[i] + z * et), et


def melange_em(x, K, iter_max=300, tol=1e-8, graine=0):
    """Mélange gaussien 1-D par EM. Renvoie poids, moyennes, variances, log-vraisemblance, responsabilités."""
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(graine)
    q = np.quantile(x, np.linspace(0.1, 0.9, K)) if K > 1 else np.array([x.mean()])
    mu = q + 1e-6 * rng.standard_normal(K)
    var = np.full(K, x.var())
    pi = np.full(K, 1.0 / K)
    llh_prec = -np.inf
    for _ in range(iter_max):
        dens = pi * np.exp(-0.5 * (x[:, None] - mu) ** 2 / var) / np.sqrt(2 * math.pi * var)
        tot = dens.sum(axis=1) + 1e-300
        llh = float(np.log(tot).sum())
        g = dens / tot[:, None]  # E : responsabilités
        nk = g.sum(axis=0) + 1e-12  # M : estimations pondérées
        pi, mu = nk / len(x), (g * x[:, None]).sum(axis=0) / nk
        var = np.maximum((g * (x[:, None] - mu) ** 2).sum(axis=0) / nk, 1e-10)
        if llh - llh_prec < tol * abs(llh):
            break
        llh_prec = llh
    o = np.argsort(var)
    return {"poids": pi[o], "moyennes": mu[o], "variances": var[o], "llh": llh, "resp": g[:, o]}


def selection(llhs, n_params, n):
    """BIC, AIC et poids de moyenne de modèles (BIC) pour des modèles concurrents."""
    llhs, k = np.asarray(llhs, dtype=float), np.asarray(n_params, dtype=float)
    bic = -2 * llhs + k * math.log(n)
    aic = -2 * llhs + 2 * k
    w = np.exp(-0.5 * (bic - bic.min()))
    return bic, aic, w / w.sum()


def _rendements(symbole, ans):
    from ..data.yahoo import YahooConnector

    data = YahooConnector().fetch(symbole, refresh=True)
    return data


def beta(symbole: str, params: dict | None = None) -> dict:
    """Bêta bayésien de symbole contre un indice : a priori (bêta 1 ± 0,5), loi a posteriori séquentielle,
    fenêtre glissante d'un an avec intervalle de crédibilité, comparaison MCO."""
    from ..data.yahoo import YahooConnector

    t0 = time.time()
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}
    indice = str(p.get("indice", "SPY")).upper()
    conn = YahooConnector()
    a, b = conn.fetch(symbole, refresh=True), conn.fetch(indice, refresh=True)
    dates = sorted(set(a) & set(b))[-5 * JOURS_AN - 1:]
    if len(dates) < 300:
        raise ValueError(f"historique commun trop court entre {symbole} et {indice}")
    ra = np.diff(np.log([a[d] for d in dates]))
    rb = np.diff(np.log([b[d] for d in dates]))
    dates = dates[1:]
    X = np.column_stack([np.ones_like(rb), rb])

    # a priori faiblement informatif : alpha ~ 0, bêta ~ 1 (± 0,5 à l'échelle du bruit)
    sigma2 = float(np.var(ra))
    m0, V0 = np.array([0.0, 1.0]), np.diag([1e-6, 0.25]) / sigma2
    # séquentiel : la loi a posteriori après chaque mois sert d'a priori au suivant (ch. 2 § 6.2)
    seq = RegressionBayesienne(m0, V0, a0=2.0, b0=sigma2)
    chemin = []
    for i in range(0, len(ra), 21):
        seq.mettre_a_jour(X[i:i + 21], ra[i:i + 21])
        lo, hi, _ = seq.intervalle(1)
        chemin.append({"date": dates[min(i + 20, len(dates) - 1)], "beta": float(seq.m[1]), "bas": lo, "haut": hi})
    # fenêtre glissante d'un an (régimes changeants), même a priori, et MCO de référence
    glis, mco = [], []
    for i in range(JOURS_AN, len(ra) + 1, 5):
        f = slice(i - JOURS_AN, i)
        reg = RegressionBayesienne(m0, V0, a0=2.0, b0=sigma2).mettre_a_jour(X[f], ra[f])
        lo, hi, _ = reg.intervalle(1)
        w = np.linalg.lstsq(X[f], ra[f], rcond=None)[0]
        glis.append({"date": dates[i - 1], "beta": float(reg.m[1]), "bas": lo, "haut": hi})
        mco.append(float(w[1]))
    fin = RegressionBayesienne(m0, V0, a0=2.0, b0=sigma2).mettre_a_jour(X[-JOURS_AN:], ra[-JOURS_AN:])
    lo, hi, et = fin.intervalle(1)
    resid = ra[-JOURS_AN:] - X[-JOURS_AN:] @ fin.m
    r2 = 1 - resid.var() / ra[-JOURS_AN:].var()
    return {"symbol": symbole, "indice": indice, "asof": dates[-1],
            "beta_1an": float(fin.m[1]), "ic95": [lo, hi], "ecart_type": et, "alpha_an": float(fin.m[0] * JOURS_AN),
            "r2": float(r2), "vol_specifique": float(resid.std() * math.sqrt(JOURS_AN)),
            "beta_5ans": float(seq.m[1]), "sequentiel": chemin, "glissant": glis, "mco": mco,
            "nuage": {"indice": rb[-JOURS_AN:].round(5).tolist(), "actif": ra[-JOURS_AN:].round(5).tolist()},
            "ms": round((time.time() - t0) * 1000)}


def regm(symbole: str, params: dict | None = None) -> dict:
    """Régimes de marché : mélanges gaussiens K = 1..4 (EM, choix BIC) contre HMM à 2-3 états."""
    from ..data.yahoo import YahooConnector
    from ..models.regimes.hmm import GaussianHMM

    t0 = time.time()
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}
    try:
        ans = float(p.get("ans", 10))
    except ValueError:
        raise ValueError("ans invalide") from None
    data = YahooConnector().fetch(symbole, refresh=True)
    dates = sorted(data)[-int(ans * JOURS_AN) - 1:]
    if len(dates) < 500:
        raise ValueError(f"historique trop court pour {symbole}")
    r = np.diff(np.log([data[d] for d in dates]))
    dates = dates[1:]
    n = len(r)

    modeles, llhs, ks = [], [], []
    for K in (1, 2, 3, 4):
        m = melange_em(r, K)
        modeles.append(m); llhs.append(m["llh"]); ks.append(3 * K - 1)
    hmms = []
    for K in (2, 3):
        h = GaussianHMM(n_states=K, seed=1).fit(r)
        ll = _hmm_llh(h, r)
        hmms.append((K, h, ll)); llhs.append(ll); ks.append(K * K + 2 * K - 1)
    noms = ["Mélange 1 (normale)", "Mélange 2", "Mélange 3", "Mélange 4", "HMM 2 états", "HMM 3 états"]
    bic, aic, poids = selection(llhs, ks, n)
    best_mix = int(np.argmin(bic[:4]))
    mix = modeles[best_mix]
    K_h, hmm, _ = min(hmms, key=lambda t: bic[4 + (t[0] - 2)])
    post = hmm.filtered_posteriors(r)
    o = np.argsort(hmm.variances)
    pas = max(1, n // 500)
    sel = list(range(0, n, pas))
    kurt = float(np.mean(((r - r.mean()) / r.std()) ** 4) - 3)
    return {"symbol": symbole, "asof": dates[-1], "n": n, "kurtosis": kurt,
            "modeles": [{"nom": noms[i], "llh": llhs[i], "params": ks[i], "bic": float(bic[i]), "aic": float(aic[i]),
                         "poids": float(poids[i])} for i in range(len(noms))],
            "melange": {"K": best_mix + 1, "poids": mix["poids"].tolist(), "rend_an": (mix["moyennes"] * JOURS_AN).tolist(),
                        "vol_an": np.sqrt(mix["variances"] * JOURS_AN).tolist()},
            "hmm": {"K": K_h, "vol_an": np.sqrt(hmm.variances[o] * JOURS_AN).tolist(), "rend_an": (hmm.means[o] * JOURS_AN).tolist(),
                    "persistance": [float(hmm.transmat[i, i]) for i in o],
                    "duree_jours": [float(1 / max(1 - hmm.transmat[i, i], 1e-9)) for i in o]},
            "dates": [dates[i] for i in sel],
            "prob_stress_melange": [round(float(mix["resp"][i, -1]), 4) for i in sel],
            "prob_stress_hmm": [round(float(post[i, o[-1]]), 4) for i in sel],
            "prix": [round(float(data[dates[i]]), 4) for i in sel],
            "histogramme": _hist(r, mix), "ms": round((time.time() - t0) * 1000)}


def _hmm_llh(h, r):
    """Vraie log-vraisemblance : Σ log c_t + Σ max_k loglik[t, k]. Le forward du HMM (models/regimes) omet le
    second terme (sans effet sur ses paramètres, seulement sur son critère d'arrêt) : on le rajoute ici
    pour comparer HMM et mélanges sur la même échelle."""
    loglik = h._emission_logpdf(r)
    _, c, _ = h._forward(loglik)
    return float(np.sum(np.log(c)) + np.sum(loglik.max(axis=1)))


def _hist(r, mix):
    lo, hi = np.quantile(r, [0.002, 0.998])
    comptes, bords = np.histogram(np.clip(r, lo, hi), bins=70, range=(lo, hi))
    c = (bords[:-1] + bords[1:]) / 2
    larg = bords[1] - bords[0]
    dens = sum(w * np.exp(-0.5 * (c - m) ** 2 / v) / np.sqrt(2 * math.pi * v) for w, m, v in zip(mix["poids"], mix["moyennes"], mix["variances"]))
    norm = np.exp(-0.5 * (c - r.mean()) ** 2 / r.var()) / np.sqrt(2 * math.pi * r.var())
    return {"centres": c.round(6).tolist(), "comptes": comptes.tolist(), "melange": (dens * len(r) * larg).round(3).tolist(),
            "normale": (norm * len(r) * larg).round(3).tolist()}
