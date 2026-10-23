"""Black-Scholes : prix d'une option européenne et volatilité implicite.

S : spot, K : strike, T : maturité en années, r : taux sans risque,
sigma : volatilité, q : rendement du dividende (continu).

Python standard seulement (math.erf) : le dépôt reste sans scipy. L'inversion
est un Newton sécurisé par bissection — même garantie que brentq (racine
encadrée, convergence assurée) car le prix est croissant en sigma.
"""

from __future__ import annotations

import math

VOL_MIN = 1e-4  # intervalle de recherche de la vol implicite
VOL_MAX = 5.0


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def calcul_d1_d2(S, K, T, r, sigma, q=0.0):
    d1 = (math.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def prix_bs(S, K, T, r, sigma, type_option="call", q=0.0):
    """Prix Black-Scholes d'un call ou d'un put."""
    d1, d2 = calcul_d1_d2(S, K, T, r, sigma, q)
    if type_option == "call":
        return S * math.exp(-q * T) * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * math.exp(-q * T) * _ncdf(-d1)


def vega(S, K, T, r, sigma, q=0.0):
    """Sensibilité du prix à la volatilité (pour 1,00 de vol, pas 1 %)."""
    d1, _ = calcul_d1_d2(S, K, T, r, sigma, q)
    return S * math.exp(-q * T) * _npdf(d1) * math.sqrt(T)


def grecques(S, K, T, r, sigma, type_option="call", q=0.0) -> dict:
    """Prix et grecques Black-Scholes (unités de desk).

    delta : par unité de sous-jacent ; gamma : par unité ; vega : pour 1 point de vol ;
    theta : par jour calendaire ; rho : pour 1 point de taux.
    """
    d1, d2 = calcul_d1_d2(S, K, T, r, sigma, q)
    eq, er = math.exp(-q * T), math.exp(-r * T)
    call = type_option == "call"
    delta = eq * _ncdf(d1) if call else -eq * _ncdf(-d1)
    gamma = eq * _npdf(d1) / (S * sigma * math.sqrt(T))
    commun = -S * eq * _npdf(d1) * sigma / (2 * math.sqrt(T))
    if call:
        theta = commun - r * K * er * _ncdf(d2) + q * S * eq * _ncdf(d1)
        rho = K * T * er * _ncdf(d2)
    else:
        theta = commun + r * K * er * _ncdf(-d2) - q * S * eq * _ncdf(-d1)
        rho = -K * T * er * _ncdf(-d2)
    return {"prix": prix_bs(S, K, T, r, sigma, type_option, q), "delta": delta, "gamma": gamma,
            "vega": vega(S, K, T, r, sigma, q) / 100, "theta": theta / 365, "rho": rho / 100}


def bornes_sans_arbitrage(S, K, T, r, type_option="call", q=0.0):
    """Intervalle où doit se trouver le prix ; en dehors, aucune vol ne le redonne."""
    s_act = S * math.exp(-q * T)
    k_act = K * math.exp(-r * T)
    if type_option == "call":
        return max(s_act - k_act, 0.0), s_act
    return max(k_act - s_act, 0.0), k_act


def vol_implicite(prix, S, K, T, r, type_option="call", q=0.0, tol=1e-10):
    """Inversion : la vol qui redonne le prix observé. NaN si impossible."""
    if T <= 0:
        return math.nan
    bas, haut = bornes_sans_arbitrage(S, K, T, r, type_option, q)
    if not (bas < prix < haut):
        return math.nan
    lo, hi = VOL_MIN, VOL_MAX
    if prix_bs(S, K, T, r, lo, type_option, q) > prix or prix_bs(S, K, T, r, hi, type_option, q) < prix:
        return math.nan
    sigma = 0.25
    for _ in range(200):
        ecart = prix_bs(S, K, T, r, sigma, type_option, q) - prix
        if ecart > 0:
            hi = sigma
        else:
            lo = sigma
        v = vega(S, K, T, r, sigma, q)
        suivant = sigma - ecart / v if v > 1e-12 else math.nan
        if not (lo < suivant < hi):  # Newton sort de l'encadrement : bissection
            suivant = 0.5 * (lo + hi)
        if abs(suivant - sigma) < tol:
            return suivant
        sigma = suivant
    return sigma
