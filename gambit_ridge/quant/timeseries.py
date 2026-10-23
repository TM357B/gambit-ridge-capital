"""Séries temporelles : méthode de Box-Jenkins et ACP (Dixon, Halperin & Bilokon, ch. 6).

- acf, pacf (Durbin-Levinson), Ljung-Box, test de Dickey-Fuller augmenté (stationnarité, § 3.1),
  AR(p) par moindres carrés avec choix de p par AIC / BIC (identification, § 3.3), diagnostics des
  résidus (§ 3.4), prévision avec intervalles (§ 4), validation croisée temporelle (§ 4.2).
- acp : analyse en composantes principales (§ 5) — appliquée aux variations de la courbe des taux :
  niveau, pente, courbure.
Fonction terminal tsa (analyse d'un ticker). numpy seul.
"""

from __future__ import annotations

import math
import time

import numpy as np

JOURS_AN = 252
# Valeurs critiques de MacKinnon (1996), ADF avec constante, grand échantillon
ADF_CRITIQUES = {"1 %": -3.43, "5 %": -2.86, "10 %": -2.57}


def acf(x, nlags=20):
    x = np.asarray(x, dtype=float) - np.mean(x)
    v = float(x @ x)
    return np.array([1.0] + [float(x[k:] @ x[:-k]) / v for k in range(1, nlags + 1)])


def pacf(x, nlags=20):
    """Autocorrélations partielles par la récursion de Durbin-Levinson."""
    r = acf(x, nlags)
    out = [1.0]
    phi_prec = np.array([])
    for k in range(1, nlags + 1):
        if k == 1:
            phi_kk = r[1]
            phi = np.array([phi_kk])
        else:
            num = r[k] - phi_prec @ r[k - 1:0:-1]
            den = 1 - phi_prec @ r[1:k]
            phi_kk = num / den
            phi = np.concatenate([phi_prec - phi_kk * phi_prec[::-1], [phi_kk]])
        out.append(float(phi_kk))
        phi_prec = phi
    return np.array(out)


def ljung_box(x, lags=10, ddl_retires=0):
    """Statistique Q de Ljung-Box et p-valeur (loi du χ² à lags - ddl_retires degrés)."""
    n = len(x)
    r = acf(x, lags)[1:]
    Q = n * (n + 2) * float(np.sum(r**2 / (n - np.arange(1, lags + 1))))
    return Q, _chi2_sf(Q, max(lags - ddl_retires, 1))


def _chi2_sf(q, k):
    """P(χ²_k > q) par l'approximation de Wilson-Hilferty (précise au-delà de quelques degrés)."""
    z = ((q / k) ** (1 / 3) - (1 - 2 / (9 * k))) / math.sqrt(2 / (9 * k))
    return 0.5 * math.erfc(z / math.sqrt(2))


def adf(x, lags=None):
    """Dickey-Fuller augmenté avec constante : Δx_t = a + γ x_{t-1} + Σ δ_i Δx_{t-i} + e_t ; H0 : γ = 0 (racine unitaire)."""
    x = np.asarray(x, dtype=float)
    dx = np.diff(x)
    p = lags if lags is not None else int(12 * (len(x) / 100) ** 0.25)
    Y = dx[p:]
    cols = [np.ones_like(Y), x[p:-1]] + [dx[p - i:-i] for i in range(1, p + 1)]
    X = np.column_stack(cols)
    b, *_ = np.linalg.lstsq(X, Y, rcond=None)
    e = Y - X @ b
    s2 = float(e @ e) / (len(Y) - X.shape[1])
    se = math.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
    t = float(b[1] / se)
    return {"stat": t, "retards": p, "critiques": ADF_CRITIQUES, "stationnaire_5pct": t < ADF_CRITIQUES["5 %"]}


def ajuster_ar(x, p):
    """AR(p) avec constante par moindres carrés. Renvoie coefficients, variance des résidus, résidus, AIC, BIC."""
    x = np.asarray(x, dtype=float)
    if p == 0:
        e = x - x.mean()
        s2 = float(e.var())
        n = len(x)
        return {"p": 0, "c": float(x.mean()), "phi": np.array([]), "s2": s2, "resid": e,
                "aic": n * math.log(s2) + 2, "bic": n * math.log(s2) + math.log(n)}
    Y = x[p:]
    X = np.column_stack([np.ones_like(Y)] + [x[p - i:-i] for i in range(1, p + 1)])
    b, *_ = np.linalg.lstsq(X, Y, rcond=None)
    e = Y - X @ b
    n, k = len(Y), p + 1
    s2 = float(e @ e) / n
    return {"p": p, "c": float(b[0]), "phi": b[1:], "s2": s2, "resid": e,
            "aic": n * math.log(s2) + 2 * k, "bic": n * math.log(s2) + k * math.log(n)}


def prevoir_ar(modele, historique, h):
    """Prévision AR(p) récursive et écart-type de l'erreur (par les poids psi de la représentation MA∞)."""
    p, c, phi = modele["p"], modele["c"], modele["phi"]
    hist = list(np.asarray(historique, dtype=float)[-max(p, 1):])
    prev = []
    for _ in range(h):
        v = c + sum(phi[i] * hist[-1 - i] for i in range(p))
        prev.append(v)
        hist.append(v)
    psi = [1.0]
    for j in range(1, h):
        psi.append(sum(phi[i] * psi[j - 1 - i] for i in range(min(p, j))))
    et = np.sqrt(modele["s2"] * np.cumsum(np.square(psi)))
    return np.array(prev), et


def validation_croisee(x, p_max=8, plis=5):
    """Validation croisée temporelle (§ 4.2) : fenêtre croissante, erreur de prévision à 1 pas hors échantillon."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    bornes = np.linspace(n // 2, n, plis + 1).astype(int)
    out = []
    for p in range(p_max + 1):
        err = []
        for a, b in zip(bornes[:-1], bornes[1:]):
            m = ajuster_ar(x[:a], p)
            for t in range(a, b):
                f = m["c"] + sum(m["phi"][i] * x[t - 1 - i] for i in range(p))
                err.append(x[t] - f)
        out.append(float(np.sqrt(np.mean(np.square(err)))))
    return out


def acp(M):
    """ACP sur les colonnes de M (observations en lignes) : valeurs propres, vecteurs, scores, part expliquée."""
    Mc = M - M.mean(axis=0)
    C = Mc.T @ Mc / (len(M) - 1)
    vals, vecs = np.linalg.eigh(C)
    o = np.argsort(vals)[::-1]
    vals, vecs = vals[o], vecs[:, o]
    # signe conventionnel : niveau positif, pente montante, courbure creuse au milieu
    for j in range(vecs.shape[1]):
        if (j == 0 and vecs[:, j].sum() < 0) or (j == 1 and vecs[-1, j] < vecs[0, j]) or (j == 2 and vecs[len(vecs) // 2, j] > 0):
            vecs[:, j] *= -1
    return {"valeurs": vals, "vecteurs": vecs, "scores": Mc @ vecs, "part": vals / vals.sum()}


def tsa(symbole: str, params: dict | None = None) -> dict:
    """Box-Jenkins complet sur un ticker : stationnarité, identification, estimation, diagnostics, prévision."""
    from ..data.yahoo import YahooConnector

    t0 = time.time()
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}
    try:
        ans = float(p.get("ans", 5))
    except ValueError:
        raise ValueError("ans invalide") from None
    data = YahooConnector().fetch(symbole, refresh=True)
    dates = sorted(data)[-int(ans * JOURS_AN) - 1:]
    if len(dates) < 300:
        raise ValueError(f"historique trop court pour {symbole}")
    px = np.array([data[d] for d in dates], dtype=float)
    lp = np.log(px)
    r = np.diff(lp)
    nl = 20
    candidats = [ajuster_ar(r, k) for k in range(0, 11)]
    best_aic = min(candidats, key=lambda m: m["aic"])
    best_bic = min(candidats, key=lambda m: m["bic"])
    m = best_bic  # BIC : parcimonie (Occam), comme au ch. 2
    lb_res = ljung_box(m["resid"], 10, m["p"])
    lb_carre = ljung_box(m["resid"] ** 2, 10)
    cv = validation_croisee(r, 8)
    h = 10
    prev, et = prevoir_ar(m, r, h)
    bande = 1.96 / math.sqrt(len(r))
    return {"symbol": symbole, "asof": dates[-1], "n": len(r),
            "adf_prix": adf(lp), "adf_rendements": adf(r),
            "acf": acf(r, nl).tolist(), "pacf": pacf(r, nl).tolist(), "acf_carres": acf(r**2, nl).tolist(), "bande": bande,
            "candidats": [{"p": c["p"], "aic": c["aic"], "bic": c["bic"]} for c in candidats],
            "choix": {"aic": best_aic["p"], "bic": best_bic["p"]},
            "modele": {"p": m["p"], "c": m["c"], "phi": m["phi"].tolist(), "vol_resid_an": math.sqrt(m["s2"] * JOURS_AN)},
            "ljung_box": {"residus": {"Q": lb_res[0], "p": lb_res[1]}, "residus_carres": {"Q": lb_carre[0], "p": lb_carre[1]}},
            "validation_croisee": cv, "cv_meilleur_p": int(np.argmin(cv)),
            "prevision": {"rend": prev.tolist(), "ic": (1.96 * et).tolist()},
            "kurtosis": float(np.mean(((r - r.mean()) / r.std()) ** 4) - 3), "asymetrie": float(np.mean(((r - r.mean()) / r.std()) ** 3)),
            "ms": round((time.time() - t0) * 1000)}
