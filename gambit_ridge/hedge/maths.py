"""Mathématiques de la couverture — numpy seul.

Sources (trouvées par l'araignée des docs, scripts/araignee) :
- Dixon, Halperin, Bilokon, « Machine Learning in Finance », ch. 10 § 3.2, éq. (10.9)-(10.10) :
  la couverture optimale minimise la variance conditionnelle du portefeuille couvert,
  u* = Cov(ΔΠ, ΔS | F_t) / Var(ΔS | F_t).  C'est le ratio à variance minimale.
- Belghaieb, « Sales & Trading en banque », p. 11 et 15 : la bonne unité d'une couverture est
  une sensibilité (bêta, DV01), pas un nominal ; contrats ≈ bêta × valeur / notionnel du future ;
  la couverture laisse le risque propre, la base et l'erreur d'estimation du bêta.
- Rockafellar & Uryasev (2000) : CVaR_α(X) = min_c { c + E[(−X − c)+] / (1 − α) } ; pour un seul
  instrument de couverture, on cherche h qui minimise la CVaR historique de r_p − h·r_f.

Conventions : rendements simples quotidiens, tableaux (T,) ou (T, N). Toutes les séries
« _t » sont CAUSALES : la valeur en t n'utilise que les rendements jusqu'à t inclus.
"""

from __future__ import annotations

import math

import numpy as np

JOURS = 252


# ------------------------------------------------------------------ statiques
def ratio_variance_min(r_p: np.ndarray, r_f: np.ndarray) -> dict:
    """h* = Cov(r_p, r_f) / Var(r_f) et efficacité de la couverture.

    efficacite = 1 − Var(r_p − h* r_f) / Var(r_p) = ρ²  (part de variance retirée).
    """
    ok = np.isfinite(r_p) & np.isfinite(r_f)
    p, f = r_p[ok], r_f[ok]
    if len(p) < 3 or np.var(f) <= 0:
        return {"h": 0.0, "rho": 0.0, "efficacite": 0.0, "vol_avant": 0.0, "vol_apres": 0.0, "n": int(len(p))}
    c = np.cov(p, f, ddof=1)
    h = c[0, 1] / c[1, 1]
    rho = c[0, 1] / math.sqrt(c[0, 0] * c[1, 1]) if c[0, 0] > 0 else 0.0
    couvert = p - h * f
    return {"h": float(h), "rho": float(rho), "efficacite": float(1 - np.var(couvert, ddof=1) / c[0, 0]),
            "vol_avant": float(math.sqrt(c[0, 0] * JOURS)), "vol_apres": float(np.std(couvert, ddof=1) * math.sqrt(JOURS)),
            "n": int(len(p))}


def ratio_multi(r_p: np.ndarray, R_f: np.ndarray, ridge: float = 0.0) -> np.ndarray:
    """Couverture à variance minimale avec plusieurs instruments : h = (Σ_ff + λ diag Σ_ff)^-1 σ_fp."""
    ok = np.isfinite(r_p) & np.all(np.isfinite(R_f), axis=1)
    X = np.column_stack([R_f[ok], r_p[ok]])
    C = np.cov(X, rowvar=False, ddof=1)
    S, s = C[:-1, :-1], C[:-1, -1]
    S = S + ridge * np.diag(np.diag(S))
    return np.linalg.solve(S, s)


def beta_baisse(r_p: np.ndarray, r_m: np.ndarray, seuil: float = 0.0) -> float:
    """Bêta de baisse (Ang, Chen & Xing 2006) : bêta estimé sur les seuls jours où le marché baisse.

    C'est le bêta qui compte pour une couverture : en crise les corrélations montent.
    """
    ok = np.isfinite(r_p) & np.isfinite(r_m) & (r_m < seuil)
    if ok.sum() < 10:
        return float("nan")
    c = np.cov(r_p[ok], r_m[ok], ddof=1)
    return float(c[0, 1] / c[1, 1])


def var_cvar(r: np.ndarray, alpha: float = 0.95) -> dict:
    """VaR et CVaR (expected shortfall) historiques à un jour, en perte positive, + Cornish-Fisher."""
    r = r[np.isfinite(r)]
    if len(r) < 20:
        return {"var": float("nan"), "cvar": float("nan"), "var_cf": float("nan")}
    q = np.quantile(r, 1 - alpha)
    queue = r[r <= q]
    mu, sd = r.mean(), r.std(ddof=1)
    s = ((r - mu) ** 3).mean() / sd ** 3
    k = ((r - mu) ** 4).mean() / sd ** 4 - 3
    z = _norm_ppf(1 - alpha)
    zcf = z + (z * z - 1) * s / 6 + (z ** 3 - 3 * z) * k / 24 - (2 * z ** 3 - 5 * z) * s * s / 36
    return {"var": float(-q), "cvar": float(-queue.mean()), "var_cf": float(-(mu + zcf * sd)),
            "asymetrie": float(s), "kurtosis_exces": float(k)}


def cvar(r: np.ndarray, alpha: float = 0.95) -> float:
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return float("nan")
    k = max(1, int(math.floor(len(r) * (1 - alpha))))
    return float(-np.sort(r)[:k].mean())


def ratio_cvar(r_p: np.ndarray, r_f: np.ndarray, alpha: float = 0.95, h_max: float = 1.5, pas: float = 0.05) -> dict:
    """h qui minimise la CVaR historique de r_p − h r_f sur [0, h_max] (recherche sur grille 1-D)."""
    ok = np.isfinite(r_p) & np.isfinite(r_f)
    grille = np.arange(0.0, h_max + 1e-9, pas)
    vals = np.array([cvar(r_p[ok] - h * r_f[ok], alpha) for h in grille])
    i = int(np.nanargmin(vals))
    return {"h": float(grille[i]), "cvar_apres": float(vals[i]), "cvar_avant": float(vals[0])}


def nb_contrats(beta: float, valeur: float, prix_future: float, multiplicateur: float) -> dict:
    """Contrats à vendre ≈ bêta × valeur / (prix × multiplicateur) (Belghaieb p. 15), arrondi au plus proche."""
    notionnel = prix_future * multiplicateur
    exact = beta * valeur / notionnel if notionnel > 0 else 0.0
    n = int(round(exact))
    return {"exact": float(exact), "contrats": n, "notionnel_contrat": float(notionnel),
            "beta_residuel": float(beta - n * notionnel / valeur) if valeur > 0 else 0.0}


# ------------------------------------------------------------------ séries causales
def beta_ewma(r_p: np.ndarray, r_f: np.ndarray, demi_vie: float = 63.0, min_obs: int = 60) -> np.ndarray:
    """Bêta conditionnel h_t = Cov_t / Var_t à moyennes exponentielles (causal, NaN au départ)."""
    a = 1.0 - 0.5 ** (1.0 / demi_vie)
    T = len(r_p)
    out = np.full(T, np.nan)
    cpf = vff = 0.0
    n = 0
    for t in range(T):
        p, f = r_p[t], r_f[t]
        if not (np.isfinite(p) and np.isfinite(f)):
            if n >= min_obs:
                out[t] = out[t - 1]
            continue
        cpf = (1 - a) * cpf + a * p * f
        vff = (1 - a) * vff + a * f * f
        n += 1
        if n >= min_obs and vff > 0:
            out[t] = cpf / vff
    return out


def betas_ewma(R: np.ndarray, r_f: np.ndarray, demi_vie: float = 63.0, min_obs: int = 60) -> np.ndarray:
    """beta_ewma colonne par colonne, vectorisé : (T, N)."""
    a = 1.0 - 0.5 ** (1.0 / demi_vie)
    T, N = R.shape
    out = np.full((T, N), np.nan)
    cpf = np.zeros(N)
    vff = 0.0
    for t in range(T):
        f = r_f[t]
        if not np.isfinite(f):
            out[t] = out[t - 1] if t else np.nan
            continue
        x = np.nan_to_num(R[t])
        cpf = (1 - a) * cpf + a * x * f
        vff = (1 - a) * vff + a * f * f
        if t + 1 >= min_obs and vff > 0:
            out[t] = cpf / vff
    return out


def correlation_ewma(x: np.ndarray, y: np.ndarray, demi_vie: float = 63.0, min_obs: int = 60) -> np.ndarray:
    a = 1.0 - 0.5 ** (1.0 / demi_vie)
    T = len(x)
    out = np.full(T, np.nan)
    cxy = vxx = vyy = 0.0
    for t in range(T):
        if not (np.isfinite(x[t]) and np.isfinite(y[t])):
            out[t] = out[t - 1] if t else np.nan
            continue
        cxy = (1 - a) * cxy + a * x[t] * y[t]
        vxx = (1 - a) * vxx + a * x[t] ** 2
        vyy = (1 - a) * vyy + a * y[t] ** 2
        if t + 1 >= min_obs and vxx > 0 and vyy > 0:
            out[t] = cxy / math.sqrt(vxx * vyy)
    return out


def beta_kalman(r_p: np.ndarray, r_f: np.ndarray, q: float = 1e-5, bruit: float | None = None) -> np.ndarray:
    """Bêta variable dans le temps par filtre de Kalman (marche aléatoire sur β, r_p = β r_f + ε).

    Estimation filtrée (causale) : β_t|t. q = variance de l'innovation de β par jour.
    """
    T = len(r_p)
    out = np.full(T, np.nan)
    ok0 = np.isfinite(r_p[:60]) & np.isfinite(r_f[:60])
    R = bruit if bruit is not None else float(np.var(r_p[:60][ok0])) if ok0.sum() > 5 else 1e-4
    b, P = 1.0, 1.0
    for t in range(T):
        p, f = r_p[t], r_f[t]
        P += q
        if np.isfinite(p) and np.isfinite(f):
            S = f * f * P + R
            K = P * f / S
            b += K * (p - b * f)
            P *= (1 - K * f)
        out[t] = b
    return out


def cvar_glissante_ratio(r_p: np.ndarray, r_f: np.ndarray, fenetre: int = 252, alpha: float = 0.95,
                         h_max: np.ndarray | float = 1.5, pas: float = 0.05, tous_les: int = 5) -> np.ndarray:
    """h_t = argmin CVaR_α(r_p − h r_f) sur les `fenetre` derniers jours (≤ t), réestimé tous les `tous_les` jours."""
    T = len(r_p)
    out = np.full(T, np.nan)
    hm = np.broadcast_to(np.asarray(h_max, dtype=float), (T,))
    dernier = np.nan
    for t in range(fenetre, T):
        if (t - fenetre) % tous_les == 0 and np.isfinite(hm[t]):
            lim = max(0.0, float(hm[t]))
            dernier = ratio_cvar(r_p[t - fenetre + 1:t + 1], r_f[t - fenetre + 1:t + 1], alpha, h_max=lim, pas=pas)["h"] if lim > 0 else 0.0
        out[t] = dernier
    return out


# ------------------------------------------------------------------ options
def _norm_cdf(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x, dtype=float) / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    # Acklam, suffisant ici
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > 1 - 0.02425:
        return -_norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def bs(S, K, T, r, sigma, put: bool) -> np.ndarray:
    """Black-Scholes vectorisé (prix d'un call ou d'un put européen), à l'échéance = valeur intrinsèque."""
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    intr = np.maximum(K - S, 0.0) if put else np.maximum(S - K, 0.0)
    T_ = np.maximum(T, 1e-12)
    sv = np.maximum(sigma, 1e-6) * np.sqrt(T_)
    d1 = (np.log(S / K) + (r + 0.5 * np.maximum(sigma, 1e-6) ** 2) * T_) / sv
    d2 = d1 - sv
    if put:
        prix = K * np.exp(-r * T_) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
    else:
        prix = S * _norm_cdf(d1) - K * np.exp(-r * T_) * _norm_cdf(d2)
    return np.where(T > 1e-9, prix, intr)


def delta_bs(S, K, T, r, sigma, put: bool) -> np.ndarray:
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    T_ = np.maximum(T, 1e-12)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T_) / (sigma * np.sqrt(T_))
    return _norm_cdf(d1) - (1.0 if put else 0.0)


def overlay_options(S: np.ndarray, vix: np.ndarray, taux: np.ndarray, notionnel: np.ndarray, *,
                    otm_put: float = 0.05, otm_call: float | None = None, echeance: int = 21,
                    skew_put: float = 0.03, skew_call: float = -0.02, frais: float = 0.05) -> dict:
    """Rendement quotidien (en fraction de l'actif) d'une protection par puts (ou collar) roulée.

    Tous les `echeance` jours de bourse : achat de puts de strike (1 − otm_put)·S, maturité
    `echeance` jours, réglés en espèces à l'échéance, sur un notionnel = notionnel_t × actif (fraction de l'actif couverte, connue
    en t) ; si otm_call est donné, vente de calls (1 + otm_call)·S (collar). Valorisation chaque
    jour en Black-Scholes avec la vol implicite VIX/100 + skew (le VIX est la vol à 30 j de
    l'indice à la monnaie ; les puts hors de la monnaie se paient plus cher : skew). Frais :
    `frais` × (prime du put + prime du call) à l'ouverture (écart achat-vente).
    Rendement du jour t = (V_t − V_{t−1}) × quantité / actif, l'actif étant normalisé à 1 à
    chaque roulement (approximation : on ignore la dérive de l'actif sur 21 jours).
    """
    T = len(S)
    r = np.zeros(T)
    prime_payee = np.zeros(T)
    t0 = None
    for t in range(1, T):
        if t0 is not None:
            tau = max(echeance - (t - t0), 0) / JOURS
            v = vix[t] / 100.0 if np.isfinite(vix[t]) else sig0
            vp = bs(S[t], Kp, tau, rf, v + skew_put, True)
            vc = bs(S[t], Kc, tau, rf, max(v + skew_call, 0.05), False) if Kc else 0.0
            val = q * (vp - vc)
            r[t] += float(val - val_prec)
            val_prec = val
            if t - t0 >= echeance:  # échéance : règlement en espèces à la valeur intrinsèque (options d'indice)
                t0 = None
        if t0 is None and np.isfinite(notionnel[t]) and notionnel[t] > 0 and np.isfinite(vix[t]):
            t0 = t
            sig0 = vix[t] / 100.0
            rf = float(taux[t]) if np.isfinite(taux[t]) else 0.0
            Kp = S[t] * (1 - otm_put)
            Kc = S[t] * (1 + otm_call) if otm_call else None
            q = notionnel[t] / S[t]  # nombre d'« unités » d'indice par unité d'actif
            vp = float(bs(S[t], Kp, echeance / JOURS, rf, sig0 + skew_put, True))
            vc = float(bs(S[t], Kc, echeance / JOURS, rf, max(sig0 + skew_call, 0.05), False)) if Kc else 0.0
            val_prec = q * (vp - vc)
            r[t] -= frais * q * (vp + vc)
            prime_payee[t] = q * (vp - vc)
    return {"rendements": r, "prime_nette": prime_payee}
