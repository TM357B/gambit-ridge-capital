"""Laboratoire Monte-Carlo : trajectoires d'un actif réel et pricing d'options.

    python -m gambit_ridge.options.monte_carlo SPY --modele student --horizon 126 --produit asian_call

Tout est paramétrable (fonction MC du terminal, /api/fn/mc) :
- sous-jacent : tout ticker Yahoo, calibré sur son propre historique ;
- modèle : « gbm » (brownien géométrique), « student » (chocs de Student : queues épaisses,
  degrés de liberté tirés du kurtosis observé), « bootstrap » (blocs de 5 séances de
  rendements historiques réels, recentrés : krachs et enchaînements conservés) ;
- volatilité : historique 1 an, implicite ATM de la surface (OVDV) à l'horizon, ou valeur fixée ;
- drift : risque-neutre (r - q, pour pricer), historique (monde réel, 5 ans), ou valeur fixée ;
- horizon, nombre de trajectoires, graine ;
- produit : call / put européens, asiatiques (moyenne arithmétique), barrières (up-and-out
  call, down-and-out put), digital — toujours pricé en risque-neutre, avec variables
  antithétiques et variable de contrôle (S_T actualisé, d'espérance connue), intervalle de
  confiance et courbe de convergence en 1/sqrt(N). Pour un européen en GBM, l'écart au prix
  Black-Scholes exact sert de contrôle.

Outil d'analyse : ne pilote pas le portefeuille. numpy seul.
"""

from __future__ import annotations

import argparse
import math
import time

import numpy as np

from .black_scholes import prix_bs

JOURS_AN = 252
N_MAX = 200_000
HORIZON_MAX = 756  # 3 ans de séances
BLOC = 5  # bootstrap : séances par bloc
N_POINTS = 60  # points de la courbe en éventail
N_EVENTAIL = 20_000  # trajectoires gardées pour l'éventail et les drawdowns
TAILLE_LOT = 20_000
MODELES = ("gbm", "student", "bootstrap")
PRODUITS = ("aucun", "call", "put", "asian_call", "asian_put", "uo_call", "do_put", "digital_call")
TAUX_DEFAUT = 0.04


# ---------------------------------------------------------------- calibration


def historique(symbole: str) -> tuple[list[str], np.ndarray]:
    from ..data.yahoo import YahooConnector

    data = YahooConnector().fetch(symbole, refresh=True)
    dates = sorted(data)
    if len(dates) < 300:
        raise ValueError(f"historique trop court pour {symbole} ({len(dates)} séances)")
    return dates, np.array([data[d] for d in dates], dtype=float)


def calibrer(prix: np.ndarray) -> dict:
    """Paramètres observés : vol 1 an, drift 5 ans, kurtosis, degrés de liberté de Student."""
    r = np.diff(np.log(prix))
    r = r[np.isfinite(r)]
    vol = float(np.std(r[-JOURS_AN:], ddof=1) * math.sqrt(JOURS_AN))
    r5 = r[-5 * JOURS_AN:]
    mu = float(np.mean(r5) * JOURS_AN + 0.5 * np.var(r5, ddof=1) * JOURS_AN)  # drift arithmétique
    z = (r5 - r5.mean()) / r5.std()
    kurt = float(np.mean(z**4) - 3.0)
    ddl = float(np.clip(6.0 / kurt + 4.0, 3.0, 30.0)) if kurt > 0 else 30.0
    return {"vol_hist": vol, "mu_hist": mu, "kurtosis": kurt, "ddl": ddl, "rendements": r[-10 * JOURS_AN:]}


def taux_sans_risque() -> float:
    try:
        from ..data.yahoo import YahooConnector

        irx = YahooConnector().fetch("^IRX")
        return irx[max(irx)] / 100
    except Exception:
        return TAUX_DEFAUT


def vol_implicite_atm(symbole: str, jours: int) -> tuple[float, float]:
    """(vol ATM, dividende implicite) de la surface OVDV à l'horizon (jours calendaires)."""
    from .vol_surface import ovdv

    s = ovdv(symbole)
    jt = np.array([j for j in s["grid"]["days"]], dtype=float)
    i_atm = min(range(len(s["moneyness"])), key=lambda i: abs(s["moneyness"][i] - 1.0))
    v = np.array([np.nan if r[i_atm] is None else r[i_atm] for r in s["grid"]["vols"]], dtype=float)
    ok = np.isfinite(v)
    if not ok.any():
        raise ValueError("surface sans vol ATM")
    vol = float(np.interp(jours, jt[ok], v[ok]))  # bornée aux extrémités cotées
    proche = min(s["expiries"], key=lambda e: abs(e["days"] - jours))
    return vol, float(proche["div"])


# ---------------------------------------------------------------- simulation


def _chocs(modele, rng, n, pas, ddl, rendements, antithetique):
    """Chocs quotidiens réduits (variance 1), ou rendements historiques recentrés (bootstrap)."""
    m = n // 2 if antithetique and modele != "bootstrap" else n
    if modele == "gbm":
        z = rng.standard_normal((m, pas))
    elif modele == "student":
        z = rng.standard_t(ddl, size=(m, pas)) * math.sqrt((ddl - 2.0) / ddl)
    else:  # bootstrap par blocs : tirages de débuts de blocs dans l'historique
        nb = -(-pas // BLOC)
        debuts = rng.integers(0, len(rendements) - BLOC + 1, size=(n, nb))
        idx = (debuts[:, :, None] + np.arange(BLOC)[None, None, :]).reshape(n, -1)[:, :pas]
        return rendements[idx]
    return np.concatenate([z, -z]) if m != n else z


def simuler(S0, jours, n, modele, mu, sigma, *, ddl=5.0, rendements=None, graine=7, antithetique=True,
            produit="aucun", K=None, B=None):
    """Simule par lots. Renvoie les quantités par trajectoire et un éventail de N_POINTS dates.

    Les log-rendements quotidiens valent (mu - sigma²/2) dt + sigma sqrt(dt) z ; en bootstrap,
    les rendements réels sont recentrés puis décalés du même drift (leur vol reste la vraie).
    """
    rng = np.random.default_rng(graine)
    dt = 1.0 / JOURS_AN
    if modele == "bootstrap":
        r_hist = np.asarray(rendements, dtype=float)
        sigma = float(np.std(r_hist, ddof=1) * math.sqrt(JOURS_AN))
        r_hist = r_hist - r_hist.mean()
    derive = (mu - 0.5 * sigma**2) * dt
    pts = np.unique(np.linspace(0, jours, N_POINTS + 1).round().astype(int))
    terminal, moyenne, extreme, dd_max, eventail = [], [], [], [], []
    for debut in range(0, n, TAILLE_LOT):
        m = min(TAILLE_LOT, n - debut)
        if modele == "bootstrap":
            lr = derive + _chocs(modele, rng, m, jours, ddl, r_hist, False)
        else:
            lr = derive + sigma * math.sqrt(dt) * _chocs(modele, rng, m, jours, ddl, None, antithetique)
        chemin = S0 * np.exp(np.cumsum(lr, axis=1))
        terminal.append(chemin[:, -1])
        if produit.startswith("asian"):
            moyenne.append(chemin.mean(axis=1))
        if produit == "uo_call":
            extreme.append(chemin.max(axis=1))
        elif produit == "do_put":
            extreme.append(chemin.min(axis=1))
        if debut < N_EVENTAIL:
            plein = np.concatenate([np.full((m, 1), S0), chemin], axis=1)
            eventail.append(plein[:, pts].astype(np.float32))
            sommet = np.maximum.accumulate(plein, axis=1)
            dd_max.append((plein / sommet - 1.0).min(axis=1))
    return {
        "terminal": np.concatenate(terminal),
        "moyenne": np.concatenate(moyenne) if moyenne else None,
        "extreme": np.concatenate(extreme) if extreme else None,
        "dd_max": np.concatenate(dd_max),
        "eventail": np.concatenate(eventail),
        "points": pts,
        "sigma": sigma,
    }


# ---------------------------------------------------------------- pricing


def gains(produit, sim, K, B):
    ST = sim["terminal"]
    if produit == "call":
        return np.maximum(ST - K, 0.0)
    if produit == "put":
        return np.maximum(K - ST, 0.0)
    if produit == "asian_call":
        return np.maximum(sim["moyenne"] - K, 0.0)
    if produit == "asian_put":
        return np.maximum(K - sim["moyenne"], 0.0)
    if produit == "uo_call":  # désactivé si le sous-jacent touche B (surveillance quotidienne)
        return np.where(sim["extreme"] < B, np.maximum(ST - K, 0.0), 0.0)
    if produit == "do_put":
        return np.where(sim["extreme"] > B, np.maximum(K - ST, 0.0), 0.0)
    if produit == "digital_call":
        return (ST > K).astype(float)
    raise ValueError(f"produit inconnu : {produit}")


def pricer(produit, sim, S0, K, B, T, r, q, modele, sigma) -> dict:
    """Prix actualisé, erreur standard, variable de contrôle, convergence, contrôle BS."""
    act = math.exp(-r * T)
    y = act * gains(produit, sim, K, B)
    n = len(y)
    prix, se = float(y.mean()), float(y.std(ddof=1) / math.sqrt(n))
    # Variable de contrôle : S_T actualisé, d'espérance exacte S0 e^{-qT} sous risque-neutre.
    x = act * sim["terminal"]
    cov = np.cov(y, x)
    b = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 0.0
    yc = y - b * (x - S0 * math.exp(-q * T))
    prix_cv, se_cv = float(yc.mean()), float(yc.std(ddof=1) / math.sqrt(n))
    # Convergence : estimation cumulée sur un échantillon mélangé (les lots antithétiques
    # sont rangés par paires) — l'intervalle se resserre en 1/sqrt(N).
    perm = np.random.default_rng(0).permutation(n)
    ys = y[perm]
    grille = np.unique(np.geomspace(min(500, n), n, 40).astype(int))
    cs, cs2 = np.cumsum(ys), np.cumsum(ys**2)
    moy = cs[grille - 1] / grille
    et = np.sqrt(np.maximum(cs2[grille - 1] / grille - moy**2, 0.0) / grille)
    out = {"produit": produit, "K": K, "B": B, "prix": prix, "se": se, "ic95": [prix - 1.96 * se, prix + 1.96 * se],
           "prix_cv": prix_cv, "se_cv": se_cv, "gain_variance": float((se / se_cv) ** 2) if se_cv > 0 else None,
           "n": n, "convergence": {"n": grille.tolist(), "prix": moy.tolist(), "bas": (moy - 1.96 * et).tolist(),
                                   "haut": (moy + 1.96 * et).tolist()}, "bs": None}
    if produit in ("call", "put") and modele == "gbm":
        out["bs"] = prix_bs(S0, K, T, r, sigma, produit, q)
    return out


# ---------------------------------------------------------------- fonction terminal


def _nombre(p, cle, defaut, lo, hi, entier=False):
    v = p.get(cle, defaut)
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"paramètre {cle} invalide : {v!r}") from None
    if not (lo <= v <= hi):
        raise ValueError(f"{cle} doit être entre {lo} et {hi}")
    return int(v) if entier else v


def mc(symbole: str, p: dict | None = None) -> dict:
    """Simulation complète au format du terminal. p : paramètres (chaînes, comme l'URL)."""
    t0 = time.time()
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (p or {}).items()}
    modele = p.get("modele", "gbm")
    if modele not in MODELES:
        raise ValueError(f"modèle inconnu : {modele} ({', '.join(MODELES)})")
    produit = p.get("produit", "aucun")
    if produit not in PRODUITS:
        raise ValueError(f"produit inconnu : {produit}")
    jours = _nombre(p, "horizon", 252, 5, HORIZON_MAX, entier=True)
    n = _nombre(p, "n", 50_000, 1_000, N_MAX, entier=True)
    graine = _nombre(p, "graine", 7, 0, 10**9, entier=True)
    k_pct = _nombre(p, "strike", 100, 20, 300) / 100
    b_pct = _nombre(p, "barriere", 120 if produit == "uo_call" else 80, 20, 300) / 100

    dates, px = historique(symbole)
    cal = calibrer(px)
    S0 = float(px[-1])
    T = jours / JOURS_AN
    r = taux_sans_risque()
    q = _nombre(p, "dividende", 0, -10, 20) / 100

    source_vol = p.get("vol", "hist")
    note_vol = ""
    if source_vol == "hist":
        sigma = cal["vol_hist"]
    elif source_vol == "impl":
        try:
            sigma, q_impl = vol_implicite_atm(symbole, round(jours * 365 / JOURS_AN))
            if "dividende" not in p:
                q = q_impl
        except Exception as exc:  # pas d'options cotées : repli explicite sur l'historique
            sigma, note_vol = cal["vol_hist"], f"vol implicite indisponible ({exc}) : vol historique utilisée"
    else:
        sigma = _nombre(p, "vol", 20, 1, 300) / 100

    source_mu = p.get("drift", "rn")
    mu = {"rn": r - q, "hist": cal["mu_hist"]}.get(source_mu)
    if mu is None:
        mu = _nombre(p, "drift", 5, -100, 100) / 100

    commun = dict(ddl=cal["ddl"], rendements=cal["rendements"], graine=graine)
    sim = simuler(S0, jours, n, modele, mu, sigma, **commun)
    sigma_eff = sim["sigma"]

    ST = sim["terminal"]
    rend = ST / S0 - 1.0
    pertes = -rend
    var95, var99 = float(np.quantile(pertes, 0.95)), float(np.quantile(pertes, 0.99))
    cvar95 = float(pertes[pertes >= var95].mean())
    ev = sim["eventail"]
    q_ev = np.quantile(ev, [0.05, 0.25, 0.5, 0.75, 0.95], axis=0)
    h_bords = np.quantile(rend, [0.001, 0.999])
    comptes, bords = np.histogram(np.clip(rend, *h_bords), bins=60, range=tuple(h_bords))

    sortie = {
        "symbol": symbole, "asof": dates[-1], "spot": S0, "params": {
            "modele": modele, "horizon": jours, "n": n, "graine": graine, "vol": source_vol, "drift": source_mu,
            "sigma": sigma_eff, "mu": mu, "taux": r, "dividende": q, "ddl": cal["ddl"] if modele == "student" else None,
            "kurtosis": cal["kurtosis"], "vol_hist": cal["vol_hist"], "mu_hist": cal["mu_hist"], "note_vol": note_vol},
        "kpi": {"esperance": float(ST.mean()), "mediane": float(np.median(ST)), "p_gain": float((ST > S0).mean()),
                "var95": var95, "var99": var99, "cvar95": cvar95, "q05": float(np.quantile(ST, 0.05)),
                "q95": float(np.quantile(ST, 0.95)), "dd_median": float(np.median(sim["dd_max"])),
                "p_dd20": float((sim["dd_max"] <= -0.20).mean())},
        "eventail": {"jours": sim["points"].tolist(), "q05": q_ev[0].tolist(), "q25": q_ev[1].tolist(),
                     "q50": q_ev[2].tolist(), "q75": q_ev[3].tolist(), "q95": q_ev[4].tolist(),
                     "trajectoires": ev[:25].round(4).tolist()},
        "histogramme": {"bords": bords.tolist(), "comptes": comptes.tolist()},
        "pricing": None,
    }
    if produit != "aucun":
        rn = sim if source_mu == "rn" else simuler(S0, jours, n, modele, r - q, sigma, produit=produit, **commun)
        if rn is sim and produit not in ("call", "put", "digital_call"):  # chemins nécessaires
            rn = simuler(S0, jours, n, modele, r - q, sigma, produit=produit, **commun)
        B = b_pct * S0 if produit in ("uo_call", "do_put") else None
        sortie["pricing"] = pricer(produit, rn, S0, k_pct * S0, B, T, r, q, modele, rn["sigma"])
    sortie["ms"] = round((time.time() - t0) * 1000)
    return _json(sortie)


def _json(x):
    """NaN / inf -> None, numpy -> Python (JSON.parse refuse NaN)."""
    if isinstance(x, dict):
        return {k: _json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else round(float(x), 6)
    if isinstance(x, np.integer):
        return int(x)
    return x


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Monte-Carlo sur un actif réel")
    ap.add_argument("symbole", nargs="?", default="SPY")
    ap.add_argument("--modele", default="gbm", choices=MODELES)
    ap.add_argument("--horizon", type=int, default=252, help="séances")
    ap.add_argument("--n", type=int, default=50_000)
    ap.add_argument("--vol", default="hist", help="hist, impl ou valeur en %%")
    ap.add_argument("--drift", default="rn", help="rn, hist ou valeur en %%")
    ap.add_argument("--produit", default="aucun", choices=PRODUITS)
    ap.add_argument("--strike", type=float, default=100, help="%% du spot")
    ap.add_argument("--barriere", type=float, help="%% du spot")
    a = ap.parse_args(argv)
    p = {k: v for k, v in vars(a).items() if v is not None and k != "symbole"}
    try:
        d = mc(a.symbole.upper(), p)
    except ValueError as exc:
        raise SystemExit(f"Erreur : {exc}") from exc
    k, pr = d["kpi"], d["params"]
    print(f"{d['symbol']} {d['asof']} spot {d['spot']:.2f} · {pr['modele']} · vol {pr['sigma']:.1%} · "
          f"drift {pr['mu']:.2%} · {pr['horizon']} séances · {pr['n']:,} trajectoires ({d['ms']} ms)")
    print(f"  médiane {k['mediane']:.2f}  [5 % {k['q05']:.2f} ; 95 % {k['q95']:.2f}]  P(gain) {k['p_gain']:.0%}")
    print(f"  VaR 95 % {k['var95']:.1%}  VaR 99 % {k['var99']:.1%}  CVaR 95 % {k['cvar95']:.1%}  "
          f"drawdown médian {k['dd_median']:.1%}")
    if d["pricing"]:
        x = d["pricing"]
        bs = f" · Black-Scholes {x['bs']:.4f}" if x["bs"] is not None else ""
        print(f"  {x['produit']} K={x['K']:.2f} : {x['prix']:.4f} ± {1.96 * x['se']:.4f} · "
              f"variable de contrôle {x['prix_cv']:.4f} ± {1.96 * x['se_cv']:.4f}{bs}")


if __name__ == "__main__":
    main()
