"""QLBS — Q-Learner in the Black-Scholes(-Merton) world (Halperin ; Dixon, Halperin & Bilokon, ch. 10).

Le vendeur d'une option la couvre en temps discret avec l'action et un compte en banque. Le prix
n'est plus unique : il dépend du pas de couverture Δt et de l'aversion au risque λ du vendeur.
Formulé comme un processus de décision markovien :

- état X_t = log S_t - (μ - σ²/2) t Δt (stationnarisé, éq. 10.26), action a_t = couverture ;
- portefeuille de couverture Π_t = γ (Π_{t+1} - a_t ΔS_t), Π_T = gain de l'option, γ = e^{-rΔt} (10.5) ;
- récompense R_t = γ a_t ΔS_t - λ Var[Π_t] (10.35) : risque-sensible façon Markowitz ;
- couverture optimale (10.45) et fonction Q (10.47) développées sur une base de B-splines cubiques
  en X, coefficients par moindres carrés transversaux (10.50-10.57) ;
- prix QLBS = -Q_0(X_0, a*_0) (10.48) : prix « ask » du vendeur, prime de risque de couverture incluse.

Solution par programmation dynamique (dynamique connue : Monte-Carlo + régressions, § 4.4) : elle
reproduit l'exemple du livre (put à la monnaie, λ = 0,001, Δt = 1/24 : 4,90 ± 0,12 ; ici ≈ 4,92).
La variante « RL » (Fitted Q Iteration hors politique, § 4.5) n'est pas exposée : testée trajectoire
par trajectoire, la courbure de Q en l'action (≈ λγ²E[ΔŜ²] ≈ 0,02) est noyée dans le bruit de la
cible (écart-type ≈ 5, celui du gain de l'option) — il faudrait de l'ordre de 10⁷ trajectoires pour
l'identifier ; l'afficher aurait produit des prix aberrants (constat du 2026-10-23).

Contrôles : λ -> 0 et μ = r : prix équitable -> Black-Scholes ; Δt -> 0 : couverture -> delta BS.
numpy seul.
"""

from __future__ import annotations

import math
import time

import numpy as np

from ..options.black_scholes import grecques, prix_bs


def bsplines(x: np.ndarray, n_noeuds: int = 12, degre: int = 3) -> np.ndarray:
    """Base de B-splines (Cox-de Boor, nœuds bloqués) sur l'étendue de x : matrice (len(x), n_noeuds + degre - 1)."""
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-12:
        hi = lo + 1e-6
    interieurs = np.linspace(lo, hi, n_noeuds)
    t = np.concatenate([[lo] * degre, interieurs, [hi] * degre])
    xx = np.clip(x, lo, hi - 1e-12 * (hi - lo))
    B = np.array([(t[i] <= xx) & (xx < t[i + 1]) for i in range(len(t) - 1)], dtype=float).T
    for k in range(1, degre + 1):
        nb = len(t) - 1 - k
        nouveau = np.zeros((len(x), nb))
        for i in range(nb):
            d1, d2 = t[i + k] - t[i], t[i + k + 1] - t[i + 1]
            g = (xx - t[i]) / d1 * B[:, i] if d1 > 0 else 0.0
            dr = (t[i + k + 1] - xx) / d2 * B[:, i + 1] if d2 > 0 else 0.0
            nouveau[:, i] = g + dr
        B = nouveau
    return B


def _ols(Phi, y, reg=1e-3):
    A = Phi.T @ Phi
    return np.linalg.solve(A + reg * np.trace(A) / A.shape[0] * np.eye(A.shape[0]), Phi.T @ y)


def simuler(S0, mu, sigma, T, pas, n, graine=42):
    """Trajectoires sous la mesure physique (GBM, antithétiques) et état stationnarisé X."""
    rng = np.random.default_rng(graine)
    dt = T / pas
    z = rng.standard_normal((n // 2, pas))
    z = np.concatenate([z, -z])
    lr = (mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z
    S = S0 * np.exp(np.concatenate([np.zeros((len(z), 1)), np.cumsum(lr, axis=1)], axis=1))
    X = np.log(S) - (mu - 0.5 * sigma**2) * dt * np.arange(pas + 1)[None, :]
    return S, X


def gain(S, K, type_option):
    return np.maximum(K - S, 0.0) if type_option == "put" else np.maximum(S - K, 0.0)


def resoudre_dp(S, X, K, r, T, lam, type_option="put", n_noeuds=12, speculative=False):
    """Programmation dynamique QLBS (10.45, 10.47) : couvertures a[k, t], portefeuilles Π, fonction Q.

    speculative=False : couverture purement de risque (terme de drift de 10.45 omis), comme les exemples
    du livre (§ 4.6) ; True : couverture complète, qui ajoute (μ - r) / (2 λ σ² S) actions (10.46).
    """
    n, N1 = S.shape
    pas = N1 - 1
    dt = T / pas
    g = math.exp(-r * dt)
    dS = S[:, 1:] - S[:, :-1] / g  # ΔS_t = S_{t+1} - e^{rΔt} S_t
    dSh = dS - dS.mean(axis=0)
    a = np.zeros((n, N1))
    Pi = np.zeros((n, N1))
    Pi[:, -1] = gain(S[:, -1], K, type_option)
    Q = np.zeros((n, N1))
    Q[:, -1] = -Pi[:, -1] - lam * Pi[:, -1].var()
    for t in range(pas - 1, -1, -1):
        Phi = bsplines(X[:, t], n_noeuds)
        Pih = Pi[:, t + 1] - Pi[:, t + 1].mean()
        A = (Phi * (dSh[:, t] ** 2)[:, None]).T @ Phi
        b = Phi.T @ (Pih * dSh[:, t] + (dS[:, t] / (2 * g * lam) if speculative and lam > 0 else 0.0))
        A += 1e-3 * np.trace(A) / A.shape[0] * np.eye(A.shape[0])
        a[:, t] = Phi @ np.linalg.solve(A, b)  # couverture optimale (10.45, 10.53)
        Pi[:, t] = g * (Pi[:, t + 1] - a[:, t] * dS[:, t])
        # récompense par trajectoire (10.35) : γ a ΔS - λ γ² (Π̂_{t+1} - a ΔŜ)², d'espérance γ a E[ΔS] - λ Var[Π_t]
        R = g * a[:, t] * dS[:, t] - lam * (g * (Pih - a[:, t] * dSh[:, t])) ** 2
        Q[:, t] = Phi @ _ols(Phi, R + g * Q[:, t + 1])  # Bellman comme régression (10.54-10.57)
    return {"a": a, "Pi": Pi, "Q": Q, "dS": dS}


def qlbs(params: dict | None = None) -> dict:
    """Pricing QLBS complet au format du terminal. Paramètres en pourcentages comme l'interface."""
    t0 = time.time()
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}

    def num(cle, defaut, lo, hi):
        try:
            v = float(p.get(cle, defaut))
        except (TypeError, ValueError):
            raise ValueError(f"paramètre {cle} invalide") from None
        if not lo <= v <= hi:
            raise ValueError(f"{cle} doit être entre {lo} et {hi}")
        return v

    typ = p.get("type", "put")
    if typ not in ("call", "put"):
        raise ValueError("type : call ou put")
    S0 = num("spot", 100, 1, 1e6)
    K = num("strike", 100, 1, 1e6)
    T = num("maturite", 1, 0.02, 5)
    pas = int(num("pas", 24, 2, 252))
    mu = num("mu", 5, -50, 50) / 100
    sigma = num("vol", 15, 1, 150) / 100
    r = num("taux", 3, -5, 20) / 100
    lam = num("lambda", 0.001, 0, 1)
    n = int(num("n", 20000, 2000, 60000))
    spec = p.get("couverture", "risque") == "speculative"

    S, X = simuler(S0, mu, sigma, T, pas, n)
    dp = resoudre_dp(S, X, K, r, T, lam, typ, speculative=spec)
    prix_qlbs = float(-dp["Q"][:, 0].mean())
    prix_equitable = float(dp["Pi"][:, 0].mean())
    bs = prix_bs(S0, K, T, r, sigma, typ)
    delta_bs0 = grecques(S0, K, T, r, sigma, typ)["delta"]

    # couverture en fonction du spot à mi-vie : QLBS vs delta BS
    tm = pas // 2
    tau = T - tm * T / pas
    ordre = np.argsort(S[:, tm])
    sel = ordre[np.linspace(0, n - 1, 120).astype(int)]
    Sm = S[sel, tm]
    courbe = {"spot": Sm.round(4).tolist(), "dp": dp["a"][sel, tm].round(5).tolist(),
              "bs": [round(grecques(s, K, tau, r, sigma, typ)["delta"], 5) for s in Sm], "jours_restants": round(tau * 365)}

    # sensibilité à l'aversion au risque et au pas de couverture (même graine)
    lambdas = [0.0, 0.0005, 0.001, 0.002, 0.005, 0.01]
    sens_l = []
    for lv in lambdas:
        d = resoudre_dp(S, X, K, r, T, lv, typ, speculative=spec)
        sens_l.append({"lambda": lv, "prix": float(-d["Q"][:, 0].mean()), "equitable": float(d["Pi"][:, 0].mean())})
    sens_p = []
    for pv in (4, 12, 24, 52):
        Sx, Xx = simuler(S0, mu, sigma, T, pv, min(n, 20000))
        d = resoudre_dp(Sx, Xx, K, r, T, lam, typ, speculative=spec)
        sens_p.append({"pas": pv, "prix": float(-d["Q"][:, 0].mean()), "equitable": float(d["Pi"][:, 0].mean()),
                       "couverture0": float(d["a"][:, 0].mean())})

    Pi0 = dp["Pi"][:, 0]
    h, bords = np.histogram(Pi0, bins=50)
    return {
        "params": {"type": typ, "spot": S0, "strike": K, "maturite": T, "pas": pas, "mu": mu, "vol": sigma, "taux": r,
                   "lambda": lam, "n": n, "couverture": "speculative" if spec else "risque"},
        "prix": {"qlbs": prix_qlbs, "equitable": prix_equitable, "bs": bs, "prime_risque": prix_qlbs - prix_equitable},
        "couverture0": {"qlbs": float(dp["a"][:, 0].mean()), "bs": delta_bs0},
        "courbe": courbe, "sens_lambda": sens_l, "sens_pas": sens_p,
        "cout_couverture": {"bords": bords.round(5).tolist(), "comptes": h.tolist(), "ecart_type": float(Pi0.std())},
        "ms": round((time.time() - t0) * 1000),
    }
