"""Processus gaussiens (Dixon, Halperin & Bilokon, ch. 3).

- Régression par processus gaussien, noyau RBF à pertinence automatique (une longueur par entrée),
  hyperparamètres par maximum de vraisemblance marginale (§ 3.3, Nelder-Mead sur les log-paramètres).
- Prédiction : moyenne, variance a posteriori, et dérivées premières et secondes de la moyenne
  (§ 5.1 « Greeking ») : le delta et le gamma d'un prix appris sont analytiques, sans différences finies.
- Applications :
  gp_greeks : apprendre le prix Black-Scholes sur quelques points (maillage, § 5 ; nuage sans maillage
              en 2D (S, T), § 5.2) puis comparer prix, delta et gamma aux formules exactes ;
  gp_vol_surface : lisser la surface de vol implicite OVDV (entrées log-moneyness et √T) avec une
              bande d'incertitude — elle s'élargit là où il n'y a pas de cotations.
numpy seul.
"""

from __future__ import annotations

import math
import time

import numpy as np

from .optim import nelder_mead


class GP:
    """GP à noyau RBF-ARD : k(x, x') = s² exp(-½ Σ_d (x_d - x'_d)² / ℓ_d²) + bruit² δ."""

    def __init__(self, longueurs, amplitude=1.0, bruit=1e-3):
        self.l = np.atleast_1d(np.asarray(longueurs, dtype=float))
        self.s = float(amplitude)
        self.b = float(bruit)

    def noyau(self, A, B):
        d = (A[:, None, :] - B[None, :, :]) / self.l
        return self.s**2 * np.exp(-0.5 * np.sum(d * d, axis=2))

    def ajuster(self, X, y, optimiser=True):
        X = np.atleast_2d(np.asarray(X, dtype=float))
        y = np.asarray(y, dtype=float)
        self.moy_y, self.et_y = float(y.mean()), float(y.std() or 1.0)
        yn = (y - self.moy_y) / self.et_y
        if optimiser:
            def nlml(theta):
                self.l, self.s, self.b = np.exp(theta[:-2]), math.exp(theta[-2]), math.exp(theta[-1])
                return -self._log_vraisemblance(X, yn)

            theta0 = np.log(np.concatenate([self.l, [self.s, max(self.b, 1e-4)]]))
            theta, _, _ = nelder_mead(nlml, theta0, pas=0.5, iter_max=200 * len(theta0))
            self.l, self.s, self.b = np.exp(theta[:-2]), math.exp(theta[-2]), math.exp(theta[-1])
        self.X = X
        K = self.noyau(X, X) + (self.b**2 + 1e-10) * np.eye(len(X))
        self.L = np.linalg.cholesky(K)
        self.alpha = np.linalg.solve(self.L.T, np.linalg.solve(self.L, yn))
        self.lml = self._log_vraisemblance(X, yn)
        return self

    def _log_vraisemblance(self, X, yn):
        K = self.noyau(X, X) + (self.b**2 + 1e-10) * np.eye(len(X))
        try:
            L = np.linalg.cholesky(K)
        except np.linalg.LinAlgError:
            return -1e12
        a = np.linalg.solve(L.T, np.linalg.solve(L, yn))
        return float(-0.5 * yn @ a - np.log(np.diag(L)).sum() - 0.5 * len(yn) * math.log(2 * math.pi))

    def predire(self, Xs, variance=True):
        Xs = np.atleast_2d(np.asarray(Xs, dtype=float))
        Ks = self.noyau(Xs, self.X)
        m = Ks @ self.alpha * self.et_y + self.moy_y
        if not variance:
            return m
        v = np.linalg.solve(self.L, Ks.T)
        var = np.maximum(self.s**2 - np.sum(v * v, axis=0), 0.0) * self.et_y**2
        return m, var

    def derivees(self, Xs, d=0):
        """Dérivées première et seconde de la moyenne a posteriori par rapport à l'entrée d."""
        Xs = np.atleast_2d(np.asarray(Xs, dtype=float))
        Ks = self.noyau(Xs, self.X)
        diff = (Xs[:, None, d] - self.X[None, :, d]) / self.l[d] ** 2
        d1 = (-diff * Ks) @ self.alpha * self.et_y
        d2 = ((diff**2 - 1.0 / self.l[d] ** 2) * Ks) @ self.alpha * self.et_y
        return d1, d2


# ---------------------------------------------------------------- pricing et grecques appris


def gp_greeks(params: dict | None = None) -> dict:
    """§ 5 du chapitre 3 : un GP apprend le prix BS sur n points, puis donne prix, delta, gamma."""
    from ..options.black_scholes import grecques, prix_bs

    t0 = time.time()
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}
    try:
        n = int(float(p.get("points", 12)))
        K = float(p.get("strike", 100))
        T = float(p.get("maturite", 1))
        r = float(p.get("taux", 3)) / 100
        sigma = float(p.get("vol", 20)) / 100
    except ValueError:
        raise ValueError("paramètres numériques invalides") from None
    typ = p.get("type", "call")
    if not (4 <= n <= 60 and 0.05 <= T <= 5 and 0.02 <= sigma <= 1.5 and typ in ("call", "put")):
        raise ValueError("points 4-60, maturité 0,05-5 ans, vol 2-150 %, type call/put")

    lo, hi = 0.5 * K, 1.5 * K
    Sx = np.linspace(lo, hi, n)
    y = np.array([prix_bs(s, K, T, r, sigma, typ) for s in Sx])
    gp = GP(longueurs=[0.3 * K], amplitude=1.0, bruit=1e-4).ajuster(Sx[:, None], y)
    St = np.linspace(lo, hi, 161)
    m, v = gp.predire(St[:, None])
    d1, d2 = gp.derivees(St[:, None])
    exact = [grecques(s, K, T, r, sigma, typ) for s in St]
    px, dl, gm = (np.array([e[k] for e in exact]) for k in ("prix", "delta", "gamma"))

    # sans maillage (§ 5.2) : nuage aléatoire en 2D (S, T), test sur une grille
    rng = np.random.default_rng(3)
    X2 = np.column_stack([rng.uniform(lo, hi, 5 * n), rng.uniform(0.1, 2 * T, 5 * n)])
    y2 = np.array([prix_bs(s, K, tt, r, sigma, typ) for s, tt in X2])
    gp2 = GP(longueurs=[0.3 * K, 0.5 * T], bruit=1e-4).ajuster(X2, y2)
    Sg, Tg = np.meshgrid(np.linspace(lo, hi, 30), np.linspace(0.15, 1.9 * T, 20))
    G = np.column_stack([Sg.ravel(), Tg.ravel()])
    m2 = gp2.predire(G, variance=False)
    e2 = np.array([prix_bs(s, K, tt, r, sigma, typ) for s, tt in G])

    return {"params": {"points": n, "strike": K, "maturite": T, "taux": r, "vol": sigma, "type": typ},
            "hyper": {"longueur": float(gp.l[0]), "amplitude": float(gp.s), "bruit": float(gp.b), "log_vraisemblance": gp.lml},
            "entrainement": {"spot": Sx.tolist(), "prix": y.tolist()},
            "test": {"spot": St.round(4).tolist(), "prix_gp": m.tolist(), "ic": (1.96 * np.sqrt(v)).tolist(), "prix_bs": px.tolist(),
                     "delta_gp": d1.tolist(), "delta_bs": dl.tolist(), "gamma_gp": d2.tolist(), "gamma_bs": gm.tolist()},
            "erreurs": {"prix_max": float(np.abs(m - px).max()), "delta_max": float(np.abs(d1 - dl).max()),
                        "gamma_max": float(np.abs(d2 - gm).max()), "gamma_ref": float(gm.max())},
            "maillage_libre": {"points": 5 * n, "erreur_max": float(np.abs(m2 - e2).max()), "erreur_moy": float(np.abs(m2 - e2).mean()),
                               "longueurs": gp2.l.tolist(), "spot": np.linspace(lo, hi, 30).round(3).tolist(),
                               "maturites": np.linspace(0.15, 1.9 * T, 20).round(4).tolist(),
                               "prix": m2.reshape(Sg.shape).round(5).tolist(), "erreur": np.abs(m2 - e2).reshape(Sg.shape).round(6).tolist()},
            "ms": round((time.time() - t0) * 1000)}


# ---------------------------------------------------------------- surface de vol lissée


def gp_vol_surface(symbole: str, n_points: int = 450) -> dict:
    """Lissage GP de la surface OVDV : (log K/S, √T) -> vol implicite, avec incertitude a posteriori."""
    from ..options.vol_surface import GRILLE_K, calculer, charger_marche

    t0 = time.time()
    spot, taux, div, brut, maintenant = charger_marche(symbole)
    points, surf, _, _ = calculer(spot, taux, div, brut)
    k, T, iv = np.log(points["moneyness"]), points["T"].astype(float), points["iv"].astype(float)
    # sous-échantillon stratifié par échéance (le GP exact coûte n³)
    rng = np.random.default_rng(0)
    idx = []
    echeances = np.unique(points["echeance"])
    par = max(4, n_points // len(echeances))
    for e in echeances:
        ie = np.flatnonzero(points["echeance"] == e)
        idx.extend(ie if len(ie) <= par else rng.choice(ie, par, replace=False))
    idx = np.array(sorted(idx))
    X = np.column_stack([k[idx], np.sqrt(T[idx])])
    gp = GP(longueurs=[0.08, 0.3], amplitude=1.0, bruit=0.05).ajuster(X, iv[idx])
    jours = np.linspace(T.min(), T.max(), 40) * 365
    Kg, Jg = np.meshgrid(GRILLE_K, jours)
    G = np.column_stack([np.log(Kg.ravel()), np.sqrt(Jg.ravel() / 365)])
    m, v = gp.predire(G)
    resid = iv[idx] - gp.predire(X, variance=False)
    return {"symbol": symbole, "spot": float(spot), "asof": maintenant.strftime("%Y-%m-%d %H:%M"),
            "n_points": int(len(points["iv"])), "n_appris": int(len(idx)),
            "hyper": {"longueur_moneyness": float(gp.l[0]), "longueur_racine_T": float(gp.l[1]),
                      "amplitude": float(gp.s * gp.et_y), "bruit": float(gp.b * gp.et_y), "log_vraisemblance": gp.lml},
            "residus": {"rmse_pts": float(np.sqrt(np.mean(resid**2)) * 100), "max_pts": float(np.abs(resid).max() * 100)},
            "moneyness": GRILLE_K.tolist(), "jours": jours.round(1).tolist(),
            "vol": (m.reshape(Kg.shape) * 100).round(3).tolist(), "incertitude": (1.96 * np.sqrt(v).reshape(Kg.shape) * 100).round(3).tolist(),
            "cotations": {"k": points["moneyness"][idx].round(4).tolist(), "jours": (T[idx] * 365).round(2).tolist(), "iv": (iv[idx] * 100).round(3).tolist()},
            "ms": round((time.time() - t0) * 1000)}
