"""Campagne de recherche n° 10 (octobre 2026) — une vraie deuxième source : 52 marchés à terme, données gratuites.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL DE STRATÉGIE (pré-enregistrement) :

Demande de Tom (24/10) : viser ~15 %/an sans s'exposer à la première crise. La campagne 9 a montré que le levier
seul n'y suffit pas (3x : 13,2 %/an pour −34 %) : il faut une source de rendement peu liée à l'existant. Hypothèse :
la même tendance que la production, mais sur ~50 marchés à terme peu corrélés (24 matières premières, 4 échéances
de taux américains, 12 devises, 13 indices actions mondiaux), avec un budget de risque égal par classe — ce que font
les fonds « managed futures ». Seconde hypothèse : ajouter le portage (carry) des devises et des taux.

Données (module data/contrats_gratuits.py, construit et vérifié AVANT ce protocole, sans aucun calcul de stratégie) :
rendements « en excès du monétaire » sur le calendrier de New York ; matières premières = contrats continus Yahoo
corrigés des changements d'échéance, l'ETF témoin faisant foi dès sa création pour 12 d'entre elles, dérive mise à
zéro pour les 11 sans témoin ; taux = reconstruits depuis les rendements FRED ; devises = change FRED + écart de taux
OCDE (mois précédent) ; indices = prix + 2 %/an de dividende − taux local. Les 52 marchés sont tous cotés dès 2002-05.

Programme « contrats à terme » (commun à F1-F3) : signal tendance de production (TSMOM 252 j + EWMA + Kalman) sur
l'indice de rendement de chaque marché ; vol GARCH ; covariance EWMA ; budget de risque égal par classe (10 %/√4
chacune, positions ≤ 3 en notionnel, brut ≤ 10), puis l'ensemble ramené à 10 % de vol ex ante (positions ≤ 3,
brut ≤ 10) ; aucun signal avant 260 séances de cotation. Coûts : 3 bps par unité échangée (rebalancement tous les
5 jours, même filtre 25 % / 0,5 % que la production) + changement d'échéance facturé 2 bps × |position| (chaque
mois pour les matières premières, chaque trimestre pour le reste).

Essais (même structure que la production : socle 60/40 à 50 % + couche tendance à 50 %, vol cible 10 %) :
  REF Production actuelle (20 ETF).
  F1  Couche tendance remplacée par le programme contrats à terme (socle 60/40 ETF inchangé).
  F2  Deux couches tendance à parts égales (ETF actuelle + contrats à terme), remise à l'échelle par
      1/√((1+ρ)/2), ρ = corrélation des deux couches sur les 252 séances précédentes (plafond 1,41).
  F3  F1 avec signal = ½ tendance + ½ portage (devises : écart de taux ; taux : rendement − taux à 3 mois ; signal
      = écart / vol annuelle ×2, borné à ±1 ; portage nul pour actions et matières, faute de données gratuites).

Périodes : dates de la référence (ETF, début 2007-04), rodage 260 séances, développement → 2019-12-31, validation
2020 → aujourd'hui. Échantillon 2003-05 → 2007-04 (proxys ETF de la campagne 5 pour le socle et la référence ;
contrats à terme natifs), même fenêtre pour tous.
Règle d'acceptation : Sharpe dév. >= réf. + 0,05 ; DSR >= 0,90 ; Sharpe validation >= réf. − 0,05 ; pire baisse
validation pas plus de 3 points au-delà de la réf. ; Sharpe 2003-2007 >= réf. − 0,05 ; ET test de robustesse
(nouveau) : avec la dérive de TOUTES les matières premières mise à zéro, gain de développement et validation non
contredite doivent tenir aussi (un biais de données sur les matières ne peut pas fabriquer un succès).
DSR sur tous les Sharpe de développement des campagnes 1, 2, 4, 6, 7, 8, 9 et 10.

Pour information (pas des essais) : programme contrats à terme seul (Sharpe par période et par classe, corrélation
avec la référence) ; menu de risque en contrats à terme (rendement = taux sans risque + k × rendement en excès,
k = 1 à 3, 0,2 %/an × k sur le notionnel brut ETF pour la base), pour REF et F1-F3.

Un essai accepté n'entre au portefeuille qu'avec l'accord de Tom ; passer aux contrats à terme suppose un compte
Interactive Brokers et des données de marché payantes avant tout argent réel.

Usage : python3 -m gambit_ridge.research.campaign10
Sortie : data/research_campaign10_2026-10.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from . import signals as sg
from .backtest import deflated_sharpe, period_metrics, simulate
from .campaign import RULES, _core_matrix, _fred_on, _production, _trend_parts
from .campaign9 import CRISES, LEVIERS
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP, apply_buffer
from .portfolio import build_weights, ewma_covariance

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_campaign10_2026-10.json"
PREVIOUS = [ROOT / "data" / f"research_campaign{n}_2026-10.json" for n in ("", "2", "4", "6", "7", "8", "9")]
COUT_FUT_BPS = 3.0
COUT_ROLL_BPS = 2.0
POS_MAX, BRUT_MAX = 3.0, 10.0
PRESAMPLE = ("2003-05-01", "2007-04-10")


# ---------------------------------------------------------------- briques

def _indices(R: np.ndarray) -> np.ndarray:
    """Indice de rendement de chaque marché (1 avant cotation)."""
    return np.cumprod(1.0 + np.nan_to_num(R, nan=0.0), axis=0)


def _cote_depuis(R: np.ndarray) -> np.ndarray:
    return np.argmax(~np.isnan(R), axis=0)


def signal_portage(u: dict, vol: np.ndarray) -> np.ndarray:
    c = np.nan_to_num(u["portage"], nan=0.0)
    lag = np.vstack([np.zeros((1, c.shape[1])), c[:-1]])
    return np.clip(2.0 * lag / np.maximum(vol, 1e-4), -1.0, 1.0)


def preparer(R: np.ndarray) -> dict:
    P = _indices(R)
    return {"P": P, "vol": sg.garch_vol(P), "cov": ewma_covariance(P), "tendance": _trend_parts(P)}


def programme(u: dict, R: np.ndarray, portage: float = 0.0, port_vol: float = 0.10, prep: dict | None = None) -> np.ndarray:
    """Poids cibles du programme contrats à terme (budget de risque égal par classe, vol cible ex ante)."""
    prep = prep or preparer(R)
    P, vol, cov = prep["P"], prep["vol"], prep["cov"]
    T, N = P.shape
    sig = prep["tendance"].copy()
    if portage:
        sig = (1 - portage) * sig + portage * signal_portage(u, vol)
    debut = _cote_depuis(R) + 260
    for j in range(N):
        sig[: debut[j], j] = 0.0
    cl = u["classes"]
    groupes = sorted(set(cl))
    W = np.zeros((T, N))
    for g in groupes:
        idx = [i for i, c in enumerate(cl) if c == g]
        W[:, idx] = build_weights(sig[:, idx], vol[:, idx], cov[:, idx][:, :, idx], port_vol=port_vol / np.sqrt(len(groupes)),
                                  max_position=POS_MAX, max_gross=BRUT_MAX)
    for t in range(T):
        w = W[t]
        v = float(np.sqrt(max(w @ cov[t] @ w, 0.0)))
        if v > 1e-9:
            w = np.clip(w * port_vol / v, -POS_MAX, POS_MAX)
            g = np.abs(w).sum()
            W[t] = w * (BRUT_MAX / g) if g > BRUT_MAX else w
    return W


def cout_changements(u: dict, held: np.ndarray) -> np.ndarray:
    """2 bps × |position| à chaque changement d'échéance (mensuel matières, trimestriel le reste)."""
    d = u["dates"]
    T = len(d)
    nouveau_mois = np.array([i > 0 and d[i][:7] != d[i - 1][:7] for i in range(T)])
    trimestre = nouveau_mois & np.array([int(x[5:7]) in (3, 6, 9, 12) for x in d])
    mat = np.array([c == "Matières premières" for c in u["classes"]])
    c = np.zeros(T)
    c[nouveau_mois] += np.abs(held[nouveau_mois][:, mat]).sum(axis=1)
    c[trimestre] += np.abs(held[trimestre][:, ~mat]).sum(axis=1)
    return c * COUT_ROLL_BPS / 1e4


def manche(u: dict, R: np.ndarray, W: np.ndarray, part: float):
    """Simulation d'une part du programme (poids × part, filtre de production), coûts de changement d'échéance inclus."""
    sim = simulate(_indices(R), apply_buffer(part * W), COUT_FUT_BPS, rebalance_every=5)
    sim.returns[:] = sim.returns - cout_changements(u, sim.weights)
    return sim


def sur_dates(u_dates: list[str], r: np.ndarray, cibles: list[str]) -> np.ndarray:
    """Rendements quotidiens d'une manche ramenés sur un autre calendrier (cumul entre deux dates cibles)."""
    pos = np.searchsorted(cibles, u_dates, side="left")
    out = np.zeros(len(cibles))
    ok = (pos < len(cibles)) & (np.array(u_dates) >= cibles[0])  # rien d'antérieur au calendrier cible
    np.add.at(out, pos[ok], np.log1p(r[ok]))
    return np.expm1(out)


def _corr_glissante(a: np.ndarray, b: np.ndarray, n: int = 252) -> np.ndarray:
    rho = np.zeros(len(a))
    for t in range(n + 1, len(a)):
        x, y = a[t - n - 1:t - 1], b[t - n - 1:t - 1]
        if x.std() > 0 and y.std() > 0:
            rho[t] = float(np.corrcoef(x, y)[0, 1])
    return rho


def menu_contrats(nom: str, r: np.ndarray, n_etf: np.ndarray, g_etf: np.ndarray, dates: list[str], rf: np.ndarray,
                  masque: np.ndarray) -> dict:
    d = np.array(dates)
    rfj = np.nan_to_num(rf, nan=0.02) / 252
    exces = r - rfj * n_etf
    lignes = []
    for k in LEVIERS:
        rk = rfj + k * exces - k * 0.002 / 252 * g_etf
        m = period_metrics(rk, None, masque, 252)
        rr, dm = rk[masque], d[masque]
        eq = np.cumprod(1 + rr)
        glissant = eq[252:] / eq[:-252] - 1
        crises = {}
        for cn, (a, b) in CRISES.items():
            sel = (dm >= a) & (dm <= b)
            if sel.sum() > 5:
                e = np.cumprod(1 + rr[sel])
                crises[cn] = float((e / np.maximum.accumulate(e) - 1).min())
        lignes.append({"levier": k, "cagr": m["cagr"], "vol": m["vol"], "sharpe": m["sharpe"], "max_dd": m["max_dd"],
                       "pire_annee_glissante": float(np.min(glissant)), "crises": crises})
    cible = next((l for l in lignes if l["cagr"] >= 0.15), None)
    return {"nom": nom, "debut": str(d[masque][0]), "fin": str(d[masque][-1]), "lignes": lignes,
            "premier_levier_a_15_pourcent": cible["levier"] if cible else None}


# ---------------------------------------------------------------- campagne

def run() -> dict:
    from ..data import contrats_gratuits as cg
    from ..data.yahoo import all_etf_symbols, load_aligned
    from .campaign5 import load_presample

    t0 = time.time()
    u = cg.charger(rafraichir=True)
    print(f"univers : {len(u['noms'])} marchés, {u['dates'][0]} -> {u['dates'][-1]} ({time.time() - t0:.0f}s)", file=sys.stderr)
    base = all_etf_symbols()
    dates, p = load_aligned(base, refresh=True)
    d = np.array(dates)
    P20 = np.column_stack([p[t] for t in base])
    dev = (np.arange(len(d)) >= WARMUP) & (d <= DEV_END)
    val = d > DEV_END

    # référence et manches ETF
    sim_ref = simulate(P20, _production(P20, base), ETF_COST_BPS, rebalance_every=5)
    core = _core_matrix(len(P20), base)
    sim_socle = simulate(P20, apply_buffer(0.5 * core), ETF_COST_BPS, rebalance_every=5)
    W_tend_etf = build_weights(_trend_parts(P20), sg.garch_vol(P20), ewma_covariance(P20))

    def essais_sur(R: np.ndarray) -> tuple[dict, dict]:
        prep = preparer(R)
        W_t = programme(u, R, prep=prep)
        W_tp = programme(u, R, portage=0.5, prep=prep)
        f1 = manche(u, R, W_t, 0.5)
        f3 = manche(u, R, W_tp, 0.5)
        r_f1, r_f3 = sur_dates(u["dates"], f1.returns, dates), sur_dates(u["dates"], f3.returns, dates)
        # F2 : deux couches tendance à parts égales, remise à l'échelle par la corrélation passée
        e_brut = simulate(P20, apply_buffer(0.5 * W_tend_etf), ETF_COST_BPS, rebalance_every=5).returns
        rho = _corr_glissante(e_brut, r_f1)
        echelle = np.minimum(1.0 / np.sqrt((1.0 + np.clip(rho, -0.9, 1.0)) / 2.0), 1.41)
        sim_e2 = simulate(P20, apply_buffer(0.25 * W_tend_etf * echelle[:, None]), ETF_COST_BPS, rebalance_every=5)
        ech_u = np.interp(np.arange(len(u["dates"])), np.searchsorted(u["dates"], dates).clip(0, len(u["dates"]) - 1), echelle)
        ech_u[: np.searchsorted(u["dates"], dates[0])] = 1.0
        f2_fut = manche(u, R, W_t * ech_u[:, None], 0.25)
        r_f2 = sim_e2.returns + sur_dates(u["dates"], f2_fut.returns, dates)
        rend = {"F1": sim_socle.returns + r_f1, "F2": sim_socle.returns + r_f2, "F3": sim_socle.returns + r_f3}
        info = {"W_t": W_t, "W_tp": W_tp, "seul": manche(u, R, W_t, 1.0), "sim_e2": sim_e2, "f1": f1, "f2_fut": f2_fut, "f3": f3}
        return rend, info

    rend, info = essais_sur(u["rendements"])
    print(f"  essais calculés ({time.time() - t0:.0f}s)", file=sys.stderr)
    rend_rob, _ = essais_sur(cg.sans_derive(u))
    print(f"  robustesse calculée ({time.time() - t0:.0f}s)", file=sys.stderr)

    noms = {"REF": ("Référence — production actuelle (20 ETF)", "Socle 60/40 + tendance sur 20 ETF."),
            "F1": ("Tendance sur 52 marchés à terme", "Socle 60/40 ETF + couche tendance remplacée par le programme contrats à terme."),
            "F2": ("Deux couches tendance (ETF + contrats à terme)", "Parts égales, remise à l'échelle par la corrélation passée."),
            "F3": ("Tendance + portage sur 52 marchés à terme", "F1 avec ½ tendance + ½ portage (devises, taux).")}
    res, retours = {}, {"REF": sim_ref.returns, **rend}
    for k, r in retours.items():
        res[k] = {"nom": f"{k} — {noms[k][0]}", "description": noms[k][1],
                  "developpement": period_metrics(r, sim_ref if k == "REF" else None, dev, 252),
                  "validation": period_metrics(r, sim_ref if k == "REF" else None, val, 252)}
        if k != "REF":
            res[k]["robustesse_sans_derive_matieres"] = {"developpement": period_metrics(rend_rob[k], None, dev, 252),
                                                         "validation": period_metrics(rend_rob[k], None, val, 252)}

    # échantillon 2003-05 -> 2007-04 (proxys pour le socle et la référence)
    pd_, pp = load_presample()
    P0 = np.column_stack([pp[t] for t in base])
    dp = np.array(pd_)
    pre = (np.arange(len(pd_)) >= WARMUP) & (dp >= PRESAMPLE[0]) & (dp <= PRESAMPLE[1])
    ref0 = simulate(P0, _production(P0, base), ETF_COST_BPS, rebalance_every=5).returns
    socle0 = simulate(P0, apply_buffer(0.5 * _core_matrix(len(P0), base)), ETF_COST_BPS, rebalance_every=5).returns
    tend0 = build_weights(_trend_parts(P0), sg.garch_vol(P0), ewma_covariance(P0))
    f1_0 = sur_dates(u["dates"], info["f1"].returns, pd_)
    rho0 = _corr_glissante(simulate(P0, apply_buffer(0.5 * tend0), ETF_COST_BPS, rebalance_every=5).returns, f1_0)
    ech0 = np.minimum(1.0 / np.sqrt((1.0 + np.clip(rho0, -0.9, 1.0)) / 2.0), 1.41)
    e0 = simulate(P0, apply_buffer(0.25 * tend0 * ech0[:, None]), ETF_COST_BPS, rebalance_every=5).returns
    ech0_u = np.interp(np.arange(len(u["dates"])), np.searchsorted(u["dates"], pd_).clip(0, len(u["dates"]) - 1), ech0)
    f2_0 = manche(u, u["rendements"], info["W_t"] * ech0_u[:, None], 0.25).returns
    pre_r = {"REF": ref0, "F1": socle0 + f1_0, "F2": socle0 + e0 + sur_dates(u["dates"], f2_0, pd_),
             "F3": socle0 + sur_dates(u["dates"], info["f3"].returns, pd_)}
    for k, r in pre_r.items():
        res[k]["echantillon_2003_2007"] = period_metrics(r, None, pre, 252)

    # DSR et verdicts
    previous = []
    for path in PREVIOUS:
        try:
            previous += [r["developpement"]["sharpe"] for r in json.loads(path.read_text())["resultats"].values() if "developpement" in r]
        except Exception as exc:
            print(f"campagne précédente illisible ({path.name}) : {exc}", file=sys.stderr)
    trial_sharpes = previous + [r["developpement"]["sharpe"] for k, r in res.items() if k != "REF"]
    ref = res["REF"]
    for k, r in res.items():
        r["dsr_developpement"] = deflated_sharpe(retours[k][dev], trial_sharpes, 252)
        if k == "REF":
            continue
        rob = r["robustesse_sans_derive_matieres"]
        checks = {
            "gain_developpement": r["developpement"]["sharpe"] >= ref["developpement"]["sharpe"] + RULES["dev_gain"],
            "dsr": r["dsr_developpement"] >= RULES["dsr"],
            "validation_non_contredite": r["validation"]["sharpe"] >= ref["validation"]["sharpe"] - RULES["val_tol"],
            "drawdown_validation": r["validation"]["max_dd"] >= ref["validation"]["max_dd"] - RULES["dd_tol"],
            "echantillon_2003_2007": r["echantillon_2003_2007"]["sharpe"] >= ref["echantillon_2003_2007"]["sharpe"] - RULES["val_tol"],
            "robustesse_developpement": rob["developpement"]["sharpe"] >= ref["developpement"]["sharpe"] + RULES["dev_gain"],
            "robustesse_validation": rob["validation"]["sharpe"] >= ref["validation"]["sharpe"] - RULES["val_tol"],
        }
        r["criteres"] = {c: bool(v) for c, v in checks.items()}
        r["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"

    # information : programme seul, par classe, corrélation avec la référence
    seul = info["seul"]
    du = np.array(u["dates"])
    debut_prog = int(np.max(_cote_depuis(u["rendements"]))) + 260
    masques_u = {"2003_2007": (np.arange(len(du)) >= debut_prog) & (du <= "2007-12-31"),
                 "developpement_2008_2019": (du >= str(d[WARMUP])) & (du <= DEV_END), "validation": du > DEV_END}
    par_classe = {}
    R = u["rendements"]
    for g in sorted(set(u["classes"])):
        idx = [i for i, c in enumerate(u["classes"]) if c == g]
        rg = (np.vstack([np.zeros((1, R.shape[1])), seul.weights[:-1]])[:, idx] * np.nan_to_num(R[:, idx])).sum(axis=1)
        par_classe[g] = {p: period_metrics(rg, None, m, 252)["sharpe"] for p, m in masques_u.items()}
    seul_ref = sur_dates(u["dates"], seul.returns, dates)
    information = {
        "programme_seul": {p: period_metrics(seul.returns, seul, m, 252) for p, m in masques_u.items()},
        "programme_seul_par_classe_sharpe": par_classe,
        "correlation_avec_reference": {"developpement": float(np.corrcoef(seul_ref[dev], sim_ref.returns[dev])[0, 1]),
                                       "validation": float(np.corrcoef(seul_ref[val], sim_ref.returns[val])[0, 1])},
        "calage_changements": u["calage"],
        "controle_etf": cg.controle_etf(u),
    }

    # menu de risque en contrats à terme (information)
    rf = _fred_on(dates, "DGS3MO") / 100.0
    masque = np.arange(len(d)) >= WARMUP
    def expo(sims):
        Wn = sum(s.weights for s in sims)
        return Wn.sum(axis=1), np.abs(Wn).sum(axis=1)
    n_ref, g_ref = expo([sim_ref])
    n_socle, g_socle = expo([sim_socle])
    n_f2, g_f2 = expo([sim_socle, info["sim_e2"]])
    menus = [menu_contrats(res["REF"]["nom"], sim_ref.returns, n_ref, g_ref, dates, rf, masque)]
    for k, (n_, g_) in (("F1", (n_socle, g_socle)), ("F2", (n_f2, g_f2)), ("F3", (n_socle, g_socle))):
        menus.append(menu_contrats(res[k]["nom"], retours[k], n_, g_, dates, rf, masque))

    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES,
              "univers": [{"marche": n, "classe": c} for n, c in zip(u["noms"], u["classes"])],
              "periode_essais": [str(d[WARMUP]), dates[-1]], "essais_comptes_dans_le_dsr": len(trial_sharpes),
              "duree_s": round(time.time() - t0), "resultats": res, "information": information, "menu_risque": menus}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\nDSR calculé sur {rep['essais_comptes_dans_le_dsr']} essais · essais du {rep['periode_essais'][0]} au {rep['periode_essais'][1]}")
    print(f"{'Essai':<58} {'DEV Sh':>6} {'DSR':>5} {'VAL Sh':>6} {'VAL DD':>7} {'03-07':>6} {'rob D':>6} {'rob V':>6}  Verdict")
    for k, r in rep["resultats"].items():
        dv, va, rob = r["developpement"], r["validation"], r.get("robustesse_sans_derive_matieres")
        print(f"{r['nom'][:58]:<58} {dv['sharpe']:>6.2f} {r['dsr_developpement']:>5.2f} {va['sharpe']:>6.2f} {va['max_dd']:>7.1%} "
              f"{r['echantillon_2003_2007']['sharpe']:>6.2f} {rob['developpement']['sharpe'] if rob else float('nan'):>6.2f} "
              f"{rob['validation']['sharpe'] if rob else float('nan'):>6.2f}  {r.get('verdict', 'référence')}")
        if "criteres" in r:
            print("      critères :", r["criteres"])
    inf = rep["information"]
    print("\nProgramme contrats à terme seul :", {p: (round(m["sharpe"], 2), f"{m['cagr']:.1%}", f"{m['max_dd']:.1%}") for p, m in inf["programme_seul"].items()})
    print("Par classe (Sharpe) :", {g: {p: round(v, 2) for p, v in x.items()} for g, x in inf["programme_seul_par_classe_sharpe"].items()})
    print("Corrélation avec la référence :", {k: round(v, 2) for k, v in inf["correlation_avec_reference"].items()})
    for m in rep["menu_risque"]:
        print(f"\nMenu en contrats à terme — {m['nom']} ({m['debut']} → {m['fin']}) ; 15 %/an au levier {m['premier_levier_a_15_pourcent']}")
        print(f"{'levier':>6} {'rend.':>7} {'vol':>6} {'Sharpe':>6} {'pire b.':>8} {'pire 12m':>9} {'2008-09':>8} {'2020':>7} {'2022':>7}")
        for l in m["lignes"]:
            c = l["crises"]
            print(f"{l['levier']:>6} {l['cagr']:>7.1%} {l['vol']:>6.1%} {l['sharpe']:>6.2f} {l['max_dd']:>8.1%} {l['pire_annee_glissante']:>9.1%} "
                  f"{c.get('2008-2009', float('nan')):>8.1%} {c.get('Covid 2020', float('nan')):>7.1%} {c.get('2022', float('nan')):>7.1%}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
