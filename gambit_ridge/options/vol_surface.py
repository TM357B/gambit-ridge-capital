"""Surface de volatilité implicite à partir d'une chaîne d'options.

    python -m gambit_ridge.options.vol_surface          # SPY, Yahoo en direct
    python -m gambit_ridge.options.vol_surface AAPL     # autre sous-jacent
    python -m gambit_ridge.options.vol_surface --demo   # chaîne synthétique, hors ligne

1. Inversion : la vol qui redonne le prix mid observé (black_scholes.vol_implicite).
2. Nettoyage, comme sur un desk : prix mid, spreads trop larges rejetés, strikes
   entre 75 % et 125 % du spot, options OTM seulement (puts sous le spot, calls au-dessus).
   Forward de chaque échéance tiré de la parité call-put près du spot.
3. Interpolation : le long de chaque smile, puis entre maturités en variance
   totale (sigma² T). Sans cotation, la surface reste vide (NaN).
4. Sorties dans data_cache/vol_surface/<SYM>_<date>/ : points_iv.csv,
   surface_grille.csv, et si matplotlib est installé (optionnel) surface_3d.png,
   smiles.png, structure_atm.png.

Outil d'analyse : ne pilote pas le portefeuille.
"""

from __future__ import annotations

import argparse
import csv
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from .black_scholes import prix_bs, vol_implicite

NY = ZoneInfo("America/New_York")
DOSSIER_SORTIE = Path(__file__).resolve().parent.parent.parent / "data_cache" / "vol_surface"

MONEYNESS_MIN, MONEYNESS_MAX = 0.75, 1.25
SPREAD_MAX = 0.25  # (ask - bid) / mid au-delà duquel la cotation est rejetée
PRIX_MIN = 0.05  # en dessous, le tick fausse la vol implicite
JOURS_MIN, JOURS_MAX = 7, 730  # maturités retenues
TROU_MAX = 0.05  # pas d'interpolation entre deux cotations distantes de plus de 5 % de moneyness
N_STRIKES_PARITE = 6  # strikes les plus proches du spot utilisés pour le forward
GRILLE_K = np.round(np.arange(MONEYNESS_MIN, MONEYNESS_MAX + 1e-9, 0.01), 4)
N_GRILLE_T = 60
TAUX_DEFAUT = 0.04

# Une chaîne est un dict de colonnes numpy de même longueur :
# echeance, type, strike, bid, ask, volume, open_interest, T (+ colonnes calculées).


def _filtrer(chaine: dict, masque: np.ndarray) -> dict:
    return {k: v[masque] for k, v in chaine.items()}


def _chaine(lignes: list[dict]) -> dict:
    cols = ("echeance", "type", "strike", "bid", "ask", "volume", "open_interest", "T")
    return {k: np.array([l[k] for l in lignes], dtype=object if k in ("echeance", "type") else float)
            for k in cols}


def maturite(echeance: str, maintenant: datetime) -> float:
    """Temps jusqu'à l'échéance (clôture 16 h New York), en années."""
    fin = datetime.combine(date.fromisoformat(echeance), time(16, 0), tzinfo=NY)
    return (fin - maintenant).total_seconds() / (365 * 24 * 3600)


# ---------------------------------------------------------------- données


def charger_marche(symbole: str, refresh: bool = False):
    """Spot, taux (^IRX), dividende et chaîne des maturités retenues, via Yahoo."""
    from ..data.yahoo import YahooConnector
    from ..data.yahoo_options import fetch_option_chain

    brut = fetch_option_chain(symbole, refresh=refresh)
    maintenant = datetime.fromisoformat(brut["fetched_utc"]).astimezone(NY)
    try:
        irx = YahooConnector().fetch("^IRX")
        taux = irx[max(irx)] / 100
    except Exception:
        taux = TAUX_DEFAUT
    div = float(brut.get("dividend_yield") or 0.0)

    lignes = []
    for q in brut["quotes"]:
        T = maturite(q["echeance"], maintenant)
        if JOURS_MIN / 365 <= T <= JOURS_MAX / 365:
            lignes.append({**q, "T": T})
    if not lignes:
        raise ValueError(f"aucune option cotée exploitable pour {symbole}")
    return brut["spot"], taux, div, _chaine(lignes), maintenant


def vol_demo(k, T):
    """Vraie surface de la démo : vol ATM décroissante, skew et smile qui s'aplatissent."""
    atm = 0.15 + 0.06 * np.exp(-T / 0.25)
    lk = np.log(k)
    return atm - 0.30 * lk / np.sqrt(1 + 4 * T) + 0.50 * lk**2 / (1 + 2 * T)


def marche_demo(graine: int = 0):
    """Chaîne synthétique : prix Black-Scholes de vol_demo, bruit de spread, trous."""
    rng = np.random.default_rng(graine)
    spot, taux, div = 100.0, 0.04, 0.01
    maintenant = datetime(2026, 10, 23, 12, 0, tzinfo=NY)
    lignes = []
    for jours in (14, 30, 45, 63, 91, 126, 182, 273, 365, 547, 730):
        T = jours / 365
        echeance = (maintenant.date() + timedelta(days=jours)).isoformat()
        for K in np.arange(60.0, 141.0, 1.0):
            if rng.random() < 0.08:  # strike non coté
                continue
            for type_option in ("call", "put"):
                juste = prix_bs(spot, K, T, taux, float(vol_demo(K / spot, T)), type_option, div)
                demi = max(0.005, 0.02 * juste) * (8 if rng.random() < 0.05 else 1)
                lignes.append(dict(echeance=echeance, type=type_option, strike=K,
                                   bid=max(round(juste - demi, 2), 0.0), ask=round(juste + demi, 2),
                                   volume=0, open_interest=0, T=T))
    return spot, taux, div, _chaine(lignes), maintenant


# ---------------------------------------------------------------- nettoyage + inversion


def nettoyer(brut: dict, spot: float, spread_max: float = SPREAD_MAX):
    """Filtres du desk. Renvoie les cotations gardées et le nombre de rejets par motif."""
    d = dict(brut)
    d["mid"] = (d["bid"] + d["ask"]) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        d["spread_rel"] = np.where(d["mid"] > 0, (d["ask"] - d["bid"]) / d["mid"], np.inf)
    d["moneyness"] = d["strike"] / spot
    put, call = d["type"] == "put", d["type"] == "call"

    filtres = [
        ("pas de bid/ask valide", (d["bid"] > 0) & (d["ask"] > d["bid"])),
        (f"prix mid < {PRIX_MIN}", d["mid"] >= PRIX_MIN),
        (f"spread > {spread_max:.0%} du mid", d["spread_rel"] <= spread_max),
        ("strike hors 75-125 % du spot", (d["moneyness"] >= MONEYNESS_MIN) & (d["moneyness"] <= MONEYNESS_MAX)),
        ("option dans la monnaie (ITM)", (put & (d["strike"] < spot)) | (call & (d["strike"] >= spot))),
    ]
    garde = np.ones(len(d["strike"]), dtype=bool)
    rejets = {}
    for motif, ok in filtres:
        rejets[motif] = int((garde & ~ok).sum())
        garde &= ok
    return _filtrer(d, garde), rejets


def forwards_implicites(brut: dict, spot: float, taux: float, div: float, spread_max: float = SPREAD_MAX):
    """Dividende implicite par échéance, tiré du forward de la parité call-put.

    C - P = D (F - K), avec D = exp(-r T) pris sur le taux du marché. Pour chaque
    strike proche du spot où call et put sont bien cotés : F = K + (C - P) / D ;
    on garde la médiane, puis q_T = r - ln(F / S) / T. Seuls les strikes proches
    du spot servent : les options SPY sont américaines et la prime d'exercice
    anticipé des puts (forte loin de la monnaie) fausserait la parité — une
    régression de C - P sur K donne d'ailleurs D > 1 sur SPY.
    Repli sur le dividende fourni si les cotations ne suffisent pas.
    """
    mid = (brut["bid"] + brut["ask"]) / 2
    ok = (brut["bid"] > 0) & (brut["ask"] > brut["bid"]) & ((brut["ask"] - brut["bid"]) <= spread_max * mid)
    ok &= np.abs(brut["strike"] / spot - 1) <= 0.05
    resultat = {}
    for echeance in np.unique(brut["echeance"]):
        de_e = brut["echeance"] == echeance
        T = float(brut["T"][de_e][0])
        c = {k: m for k, m in zip(brut["strike"][de_e & ok & (brut["type"] == "call")],
                                   mid[de_e & ok & (brut["type"] == "call")])}
        p = {k: m for k, m in zip(brut["strike"][de_e & ok & (brut["type"] == "put")],
                                   mid[de_e & ok & (brut["type"] == "put")])}
        K = sorted(set(c) & set(p), key=lambda k: abs(k - spot))[:N_STRIKES_PARITE]
        q_T, source = div, "repli"
        if len(K) >= 3:
            F = float(np.median([k + (c[k] - p[k]) * math.exp(taux * T) for k in K]))
            if 0.90 < F / spot < 1.10:
                q_T = taux - math.log(F / spot) / T
                source = "parité"
        resultat[str(echeance)] = (taux, q_T, source)
    return resultat


def calculer_iv(propre: dict, spot: float, forwards: dict):
    d = dict(propre)
    d["taux_T"] = np.array([forwards[e][0] for e in d["echeance"]], dtype=float)
    d["div_T"] = np.array([forwards[e][1] for e in d["echeance"]], dtype=float)
    d["iv"] = np.array([vol_implicite(m, spot, k, t, r, ty, q) for m, k, t, r, ty, q in
                        zip(d["mid"], d["strike"], d["T"], d["taux_T"], d["type"], d["div_T"])])
    ok = np.isfinite(d["iv"])
    d = _filtrer(d, ok)
    ordre = np.lexsort((d["strike"], d["T"]))
    return _filtrer(d, ordre), int((~ok).sum())


# ---------------------------------------------------------------- interpolation


def interpoler_smile(moneyness, iv, grille=GRILLE_K, trou_max=TROU_MAX):
    """Vol sur la grille de moneyness, linéaire entre cotations voisines.

    NaN hors de la plage cotée et dans les trous de plus de trou_max."""
    ordre = np.argsort(moneyness)
    x, y = np.asarray(moneyness, dtype=float)[ordre], np.asarray(iv, dtype=float)[ordre]
    sortie = np.full(len(grille), np.nan)
    if len(x) < 2:
        return sortie
    j = np.searchsorted(x, grille)  # x[j-1] < g <= x[j]
    for i, g in enumerate(grille):
        if g < x[0] or g > x[-1]:
            continue
        if x[j[i]] == g:  # strike coté pile sur la grille
            sortie[i] = y[j[i]]
            continue
        a, b = j[i] - 1, j[i]
        if x[b] - x[a] > trou_max:
            continue
        sortie[i] = y[a] + (y[b] - y[a]) * (g - x[a]) / (x[b] - x[a])
    return sortie


def construire_surface(points: dict) -> dict:
    """Smiles par échéance, puis interpolation entre maturités en variance totale."""
    echeances = sorted(np.unique(points["echeance"]), key=lambda e: points["T"][points["echeance"] == e][0])
    T_cotes = np.array([points["T"][points["echeance"] == e][0] for e in echeances])
    smiles = np.vstack([interpoler_smile(points["moneyness"][points["echeance"] == e],
                                         points["iv"][points["echeance"] == e]) for e in echeances])
    W = smiles**2 * T_cotes[:, None]  # variance totale aux échéances cotées

    grille_T = np.linspace(T_cotes[0], T_cotes[-1], N_GRILLE_T)
    surface = np.full((len(grille_T), len(GRILLE_K)), np.nan)
    for i, t in enumerate(grille_T):
        b = min(int(np.searchsorted(T_cotes, t)), len(T_cotes) - 1)
        a = b if T_cotes[b] == t else b - 1
        poids = 0.0 if a == b else (t - T_cotes[a]) / (T_cotes[b] - T_cotes[a])
        w = W[a] + poids * (W[b] - W[a])  # NaN dès qu'une des deux échéances n'est pas cotée
        surface[i] = np.sqrt(w / t)

    # Arbitrage calendaire : la variance totale doit croître avec la maturité.
    dW = np.diff(W, axis=0)
    n_calendaire = int(np.sum(dW[np.isfinite(dW)] < -1e-6))
    i_atm = int(np.argmin(np.abs(GRILLE_K - 1.0)))
    return dict(echeances=[str(e) for e in echeances], T_cotes=T_cotes, smiles=smiles, atm=smiles[:, i_atm],
                grille_T=grille_T, surface=surface, n_calendaire=n_calendaire)


# ---------------------------------------------------------------- sorties


def exporter(points: dict, surf: dict, dossier: Path) -> None:
    colonnes = ["echeance", "T", "type", "strike", "moneyness", "bid", "ask", "mid", "spread_rel",
                "taux_T", "div_T", "iv", "volume", "open_interest"]
    with open(dossier / "points_iv.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(colonnes)
        for i in range(len(points["iv"])):
            w.writerow([round(float(points[c][i]), 6) if c not in ("echeance", "type") else points[c][i]
                        for c in colonnes])
    with open(dossier / "surface_grille.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["jours"] + [f"{k:.2f}" for k in GRILLE_K])
        for t, ligne in zip(surf["grille_T"], surf["surface"]):
            w.writerow([round(t * 365, 2)] + ["" if np.isnan(v) else round(float(v), 6) for v in ligne])


def tracer(points: dict, surf: dict, titre: str, dossier: Path) -> bool:
    """Trois graphiques PNG. matplotlib est optionnel : sans lui, CSV seulement."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    jours_cotes = surf["T_cotes"] * 365
    norme = plt.Normalize(jours_cotes.min(), jours_cotes.max())
    cmap = plt.cm.viridis

    # 1. Surface 3D
    X, Y = np.meshgrid(GRILLE_K * 100, surf["grille_T"] * 365)
    Z = surf["surface"] * 100
    fig = plt.figure(figsize=(11, 7.5))
    ax = fig.add_subplot(projection="3d")
    ax.plot_surface(X, Y, np.ma.masked_invalid(Z), cmap="viridis", vmin=np.nanmin(Z), vmax=np.nanmax(Z),
                    rstride=1, cstride=1, linewidth=0, antialiased=True, alpha=0.9)
    ax.scatter(points["moneyness"] * 100, points["T"] * 365, points["iv"] * 100, s=3, c="k", alpha=0.35)
    ax.set_xlabel("Strike / spot (%)")
    ax.set_ylabel("Maturité (jours)")
    ax.set_zlabel("Vol implicite (%)")
    ax.set_title(f"{titre} — surface de volatilité implicite")
    ax.view_init(elev=24, azim=-128)
    fig.tight_layout()
    fig.savefig(dossier / "surface_3d.png", dpi=150)
    plt.close(fig)

    # 2. Smiles
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for e, T, smile in zip(surf["echeances"], surf["T_cotes"], surf["smiles"]):
        c = cmap(norme(T * 365))
        de_e = points["echeance"] == e
        ax.plot(GRILLE_K * 100, smile * 100, color=c, lw=1.4)
        ax.scatter(points["moneyness"][de_e] * 100, points["iv"][de_e] * 100, color=c, s=7)
    ax.axvline(100, color="grey", lw=0.8, ls="--")
    ax.set_xlabel("Strike / spot (%)   —   puts à gauche, calls à droite")
    ax.set_ylabel("Vol implicite (%)")
    ax.set_title(f"{titre} — smile par maturité")
    ax.grid(alpha=0.3)
    fig.colorbar(plt.cm.ScalarMappable(norm=norme, cmap=cmap), ax=ax, label="Maturité (jours)")
    fig.tight_layout()
    fig.savefig(dossier / "smiles.png", dpi=150)
    plt.close(fig)

    # 3. Structure par terme ATM
    atm = surf["atm"] * 100
    ok = np.isfinite(atm)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(jours_cotes[ok], atm[ok], "o-", color="#1f6f8b")
    for j, v in zip(jours_cotes[ok], atm[ok]):
        ax.annotate(f"{v:.1f}", (j, v), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
    ax.set_xlabel("Maturité (jours)")
    ax.set_ylabel("Vol implicite ATM (%)")
    ax.set_title(f"{titre} — structure par terme de la vol ATM")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(dossier / "structure_atm.png", dpi=150)
    plt.close(fig)
    return True


# ---------------------------------------------------------------- programme


def calculer(spot, taux, div, brut, spread_max=SPREAD_MAX, forcer_taux_div=False):
    """Pipeline complet : nettoyage, forwards, inversion, surface."""
    propre, rejets = nettoyer(brut, spot, spread_max)
    forwards = forwards_implicites(brut, spot, taux, div, spread_max)
    if forcer_taux_div:
        forwards = {e: (taux, div, "forcé") for e in forwards}
    points, n_echec = calculer_iv(propre, spot, forwards)
    rejets["inversion impossible (prix hors bornes)"] = n_echec
    if len(np.unique(points["echeance"])) < 2:
        raise ValueError("moins de deux échéances exploitables : pas de surface")
    return points, construire_surface(points), forwards, rejets


def _nombres(x, chiffres=4):
    """Tableau numpy -> listes JSON, NaN -> None (JSON.parse refuse NaN)."""
    a = np.asarray(x, dtype=float)
    if a.ndim == 0:
        return None if not np.isfinite(a) else round(float(a), chiffres)
    return [_nombres(v, chiffres) for v in a]


def resume_json(symbole, spot, taux, brut, points, surf, forwards, rejets, maintenant) -> dict:
    """Ce que sert /api/fn/ovdv : smiles, structure ATM, grille, chiffres clés."""
    jours_grille = surf["grille_T"] * 365
    i_atm = int(np.argmin(np.abs(GRILLE_K - 1.0)))
    atm_grille = surf["surface"][:, i_atm]
    ok = np.isfinite(atm_grille)

    def atm_a(jours):  # vol ATM interpolée sur la grille, None hors plage
        if not ok.any() or not jours_grille[ok][0] <= jours <= jours_grille[ok][-1]:
            return None
        return float(np.interp(jours, jours_grille[ok], atm_grille[ok]))

    # Skew à 1 mois : vol 95 % - vol 105 % sur l'échéance cotée la plus proche de 30 jours
    # (à 1 mois, les calls à 110 % valent souvent moins que PRIX_MIN et ne sont pas cotés).
    i_1m = int(np.argmin(np.abs(surf["T_cotes"] * 365 - 30)))
    smile_1m = surf["smiles"][i_1m]
    k95, k105 = int(np.argmin(np.abs(GRILLE_K - 0.95))), int(np.argmin(np.abs(GRILLE_K - 1.05)))
    skew = smile_1m[k95] - smile_1m[k105]
    atm_1m, atm_1a = atm_a(30), atm_a(365)
    return {
        "symbol": symbole,
        "spot": round(float(spot), 4),
        "asof": maintenant.strftime("%Y-%m-%d %H:%M"),
        "rate": round(float(taux), 5),
        "n_quotes": int(len(brut["strike"])),
        "n_points": int(len(points["iv"])),
        "rejets": rejets,
        "filled": round(float(np.isfinite(surf["surface"]).mean()), 4),
        "calendar_violations": surf["n_calendaire"],
        "kpi": {"atm_1m": atm_1m, "atm_1y": atm_1a,
                "skew_1m": None if not np.isfinite(skew) else float(skew),
                "skew_1m_expiry": surf["echeances"][i_1m],
                "slope": None if atm_1m is None or atm_1a is None else atm_1a - atm_1m},
        "moneyness": _nombres(GRILLE_K),
        "expiries": [{"expiry": e, "days": round(float(T * 365), 1), "atm": _nombres(a),
                      "div": round(float(forwards[e][1]), 5), "source": forwards[e][2], "smile": _nombres(s)}
                     for e, T, a, s in zip(surf["echeances"], surf["T_cotes"], surf["atm"], surf["smiles"])],
        "grid": {"days": _nombres(jours_grille, 1), "vols": _nombres(surf["surface"])},
    }


def ovdv(symbole: str) -> dict:
    """Surface de vol implicite d'un sous-jacent coté, au format du terminal."""
    spot, taux, div, brut, maintenant = charger_marche(symbole)
    points, surf, forwards, rejets = calculer(spot, taux, div, brut)
    return resume_json(symbole, spot, taux, brut, points, surf, forwards, rejets, maintenant)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Surface de volatilité implicite")
    parser.add_argument("symbole", nargs="?", default="SPY")
    parser.add_argument("--demo", action="store_true", help="chaîne synthétique, sans internet")
    parser.add_argument("--refresh", action="store_true", help="ignorer le cache de 15 min")
    parser.add_argument("--taux", type=float, help="taux sans risque forcé (ex. 0.04)")
    parser.add_argument("--dividende", type=float, help="dividende forcé (ex. 0.012), sinon parité call-put")
    parser.add_argument("--spread-max", type=float, default=SPREAD_MAX, help="spread max en fraction du mid")
    args = parser.parse_args(argv)

    try:
        if args.demo:
            nom = "DEMO"
            spot, taux, div, brut, maintenant = marche_demo()
        else:
            nom = args.symbole.upper()
            print(f"Chaîne d'options {nom} (Yahoo)…")
            spot, taux, div, brut, maintenant = charger_marche(nom, refresh=args.refresh)
        taux = args.taux if args.taux is not None else taux
        div = args.dividende if args.dividende is not None else div
        print(f"{nom} : spot {spot:.2f}, taux {taux:.2%}, dividende {div:.2%}, "
              f"{len(np.unique(brut['echeance']))} échéances, {len(brut['strike'])} cotations brutes")

        points, surf, forwards, rejets = calculer(
            spot, taux, div, brut, args.spread_max, args.taux is not None or args.dividende is not None)
    except ValueError as exc:
        raise SystemExit(f"Erreur : {exc}") from exc
    print("Nettoyage :")
    for motif, n in rejets.items():
        print(f"  - {n:5d} rejetées : {motif}")
    print(f"  = {len(points['iv'])} vols implicites calculées")

    dossier = DOSSIER_SORTIE / f"{nom}_{maintenant:%Y-%m-%d_%H%M}"
    dossier.mkdir(parents=True, exist_ok=True)
    exporter(points, surf, dossier)
    graphiques = tracer(points, surf, f"{nom} au {maintenant:%d/%m/%Y %H:%M} NY (spot {spot:.2f})", dossier)

    print("\nÉchéance        jours   vol ATM   taux   div.   (source)")
    for e, T, v in zip(surf["echeances"], surf["T_cotes"], surf["atm"] * 100):
        r_T, q_T, source = forwards[e]
        vol = "   —   " if np.isnan(v) else f"{v:5.1f} %"
        print(f"  {e}  {T * 365:6.0f}   {vol}  {r_T:5.2%}  {q_T:5.2%}  ({source})")
    print(f"\nSurface remplie à {np.isfinite(surf['surface']).mean():.0%} (le reste : pas de cotation).")
    if surf["n_calendaire"]:
        print(f"Attention : {surf['n_calendaire']} points où la variance totale baisse avec la maturité "
              f"(arbitrage calendaire apparent).")
    if args.demo:
        err = np.abs(points["iv"] - vol_demo(points["moneyness"], points["T"])) * 100
        print(f"Démo — écart avec la vraie vol : médian {np.median(err):.2f} pt, max {err.max():.2f} pt")
    if not graphiques:
        print("matplotlib absent : CSV seulement (pip install matplotlib pour les graphiques).")
    print(f"\nFichiers dans {dossier} :")
    for f in sorted(dossier.iterdir()):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
