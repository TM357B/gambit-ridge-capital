"""Campagne de recherche n° 9 (octobre 2026) — diversification par classes d'actifs et niveau de risque.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Demande de Tom (24/10) : viser ~15 % par an sans s'exposer à la première crise, en ajoutant une vraie source de
rendement hors actions (matières premières, devises, obligations hors États-Unis).

Constat préalable : la campagne 1 a déjà ajouté des diversifiants (A3) avec la pondération ACTUELLE (risque égal
actif par actif) et a dégradé (Sharpe dév. 0,91 contre 0,99). Hypothèse testée ici, différente : c'est la RÉPARTITION
du risque qui compte. Les grands fonds de tendance donnent la même part de risque à chaque CLASSE (actions,
obligations, matières premières, devises) ; aujourd'hui les actions et leurs proches (crédit, immobilier) pèsent
davantage parce qu'elles sont plus nombreuses et corrélées.

Référence : stratégie ETF de production (socle 60/40 50 % + couche tendance TSMOM/EWMA/Kalman, vol GARCH, covariance
EWMA, vol cible 10 %, filtre 25 % / 0,5 %, rebalancement 5 jours, 5 bps).

PARTIE A — essais (jugés avec les règles habituelles) :
  K1 Budget de risque par classe, univers actuel (20 ETF) : la couche tendance est construite classe par classe
     (vol cible 10 %/√4 chacune), puis ramenée ensemble à 10 % de vol ex ante (positions ≤ 40 %, brut ≤ 2).
  K2 Univers élargi (30 ETF), pondération actuelle actif par actif — contrôle : + gaz naturel UNG, pétrole DBO,
     métaux industriels DBB, essence UGA, dollar australien FXA, canadien FXC, franc suisse FXF, livre FXB,
     obligations d'États hors US BWX, obligations émergentes EMB (aucune action ajoutée).
  K3 Univers élargi (30 ETF) + budget de risque par classe : l'hypothèse principale.
  Classes : Actions (7), Obligations (5 + BWX, EMB), Matières premières (5 + UNG, DBO, DBB, UGA), Devises (3 + 4).

Périodes : dates communes aux 30 ETF (début ≈ 2007-12) pour TOUS les essais et la référence, rodage 260 séances,
développement → 2019-12-31, validation 2020 → aujourd'hui. Règle d'acceptation inchangée : Sharpe dév. >= réf. + 0,05 ;
DSR >= 0,90 ; Sharpe validation >= réf. − 0,05 ; pire baisse validation pas plus de 3 points au-delà de la réf. ; et,
pour K1 seulement (seul essai sur l'univers actuel), Sharpe 2001-2007 (proxys de la campagne 5) >= réf. − 0,05. Les
10 ETF ajoutés n'ont pas de proxys sur 2001-2007 : ce critère ne peut pas s'appliquer à K2 et K3 (limite assumée).
DSR sur tous les Sharpe de développement des campagnes 1, 2, 4, 6, 7, 8 et 9.

PARTIE B — menu de risque (ce n'est PAS un essai ; aide à la décision de Tom) :
La stratégie de référence (et l'essai accepté s'il y en a un) multipliée par k = 1 ; 1,5 ; 2 ; 2,5 ; 3 sur l'univers
actuel depuis 2008 (crise de 2008 incluse). Coûts : frais de transaction multipliés par k ; intérêts sur la part
achetée à crédit = max(k × exposition acheteuse − 1, 0) × (taux à 3 mois du Trésor + 1 point) ; prêt de titres pour
la part vendeuse : k × exposition vendeuse × 0,5 %/an. Mesures : rendement annuel, volatilité, Sharpe, pire baisse,
pire année glissante, années négatives, baisses pendant 2008-2009, 2020 et 2022, levier brut moyen. Limite
assumée : au-delà d'un levier brut de 2, un compte-titres ne suffit plus (contrats à terme ou marge de portefeuille).

Un essai accepté n'entre au portefeuille qu'avec l'accord de Tom ; un niveau de risque n'est choisi que par Tom.

Usage : python3 -m gambit_ridge.research.campaign9
Sortie : data/research_campaign9_2026-10.json
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
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP, apply_buffer, core_plus_overlay
from .portfolio import build_weights, ewma_covariance

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_campaign9_2026-10.json"
PREVIOUS = [ROOT / "data" / f"research_campaign{n}_2026-10.json" for n in ("", "2", "4", "6", "7", "8")]
AJOUTS = {"UNG": "Matières premières", "DBO": "Matières premières", "DBB": "Matières premières", "UGA": "Matières premières",
          "FXA": "Devises", "FXC": "Devises", "FXF": "Devises", "FXB": "Devises", "BWX": "Obligations", "EMB": "Obligations"}
LEVIERS = (1.0, 1.5, 2.0, 2.5, 3.0)
CRISES = {"2008-2009": ("2008-05-19", "2009-03-09"), "Covid 2020": ("2020-02-19", "2020-03-23"), "2022": ("2022-01-03", "2022-12-30")}


def classes(tk: list[str]) -> list[str]:
    from ..data.yahoo import ETF_UNIVERSE

    base = {s: c for c, m in ETF_UNIVERSE.items() for s in m}
    return [base.get(t) or AJOUTS[t] for t in tk]


def tendance_par_classe(P: np.ndarray, tk: list[str], port_vol: float = 0.10, max_position: float = 0.40,
                        max_gross: float = 2.0) -> np.ndarray:
    """Couche tendance où chaque classe reçoit la même part de risque, puis l'ensemble est ramené à port_vol."""
    sig, vol, cov = _trend_parts(P), sg.garch_vol(P), ewma_covariance(P)
    cl = classes(tk)
    groupes = sorted(set(cl))
    W = np.zeros_like(P)
    for g in groupes:
        idx = [i for i, c in enumerate(cl) if c == g]
        W[:, idx] = build_weights(sig[:, idx], vol[:, idx], cov[:, idx][:, :, idx], port_vol=port_vol / np.sqrt(len(groupes)),
                                  max_position=max_position, max_gross=max_gross)
    for t in range(len(W)):
        w = W[t]
        v = float(np.sqrt(max(w @ cov[t] @ w, 0.0)))
        if v > 1e-9:
            w = np.clip(w * port_vol / v, -max_position, max_position)
            g = np.abs(w).sum()
            W[t] = w * (max_gross / g) if g > max_gross else w
    return W


def production_par_classe(P: np.ndarray, tk: list[str]) -> np.ndarray:
    return apply_buffer(core_plus_overlay(_core_matrix(len(P), tk), tendance_par_classe(P, tk)))


def _avec_levier(sim, k: float, taux: np.ndarray) -> np.ndarray:
    """Rendements au levier k : tout multiplié par k (frais compris), moins intérêts et prêt de titres."""
    W = sim.weights
    longs, shorts = np.clip(W, 0, None).sum(axis=1), -np.clip(W, None, 0).sum(axis=1)
    emprunt = np.maximum(k * longs - 1.0, 0.0)
    cout = np.zeros(len(W))
    cout[1:] = (emprunt[:-1] * (np.nan_to_num(taux[1:], nan=0.02) + 0.01) + k * shorts[:-1] * 0.005) / 252
    return k * sim.returns - cout


def menu_risque(nom: str, sim, dates: list[str], taux: np.ndarray, masque: np.ndarray) -> dict:
    d = np.array(dates)
    lignes = []
    for k in LEVIERS:
        r = _avec_levier(sim, k, taux)
        m = period_metrics(r, None, masque, 252)
        rr = r[masque]
        eq = np.cumprod(1 + rr)
        dm = d[masque]
        glissant = eq[252:] / eq[:-252] - 1 if len(eq) > 252 else np.array([np.nan])
        annees = {}
        for di, v in zip(dm, rr):
            annees.setdefault(di[:4], []).append(v)
        ann = {a: float(np.prod(1 + np.array(v)) - 1) for a, v in annees.items() if len(v) > 200}
        crises = {}
        for cn, (a, b) in CRISES.items():
            sel = (dm >= a) & (dm <= b)
            if sel.sum() > 5:
                e = np.cumprod(1 + rr[sel])
                crises[cn] = float((e / np.maximum.accumulate(e) - 1).min())
        lignes.append({"levier": k, "cagr": m["cagr"], "vol": m["vol"], "sharpe": m["sharpe"], "max_dd": m["max_dd"],
                       "pire_annee_glissante": float(np.nanmin(glissant)), "annees_negatives": sum(v < 0 for v in ann.values()),
                       "annees": len(ann), "crises": crises, "levier_brut_moyen": float(k * np.abs(sim.weights[masque]).sum(axis=1).mean())})
    cible = next((l for l in lignes if l["cagr"] >= 0.15), None)
    return {"nom": nom, "debut": str(d[masque][0]), "fin": str(d[masque][-1]), "lignes": lignes,
            "premier_levier_a_15_pourcent": cible["levier"] if cible else None}


def run() -> dict:
    from ..data.yahoo import all_etf_symbols, load_aligned
    from .campaign5 import load_presample

    t0 = time.time()
    base = all_etf_symbols()
    elargi = base + list(AJOUTS)
    dates, p = load_aligned(elargi, refresh=True)
    d = np.array(dates)
    T = len(dates)
    P30 = np.column_stack([p[t] for t in elargi])
    P20 = np.column_stack([p[t] for t in base])
    print(f"univers élargi : {len(elargi)} ETF, {dates[0]} -> {dates[-1]}", file=sys.stderr)
    dev = (np.arange(T) >= WARMUP) & (d <= DEV_END)
    val = d > DEV_END

    essais = {
        "REF": ("Référence — production actuelle (20 ETF)", "Risque égal actif par actif.", lambda: (P20, _production(P20, base))),
        "K1": ("Budget de risque par classe, univers actuel (20 ETF)", "Même part de risque pour actions, obligations, matières, devises.",
               lambda: (P20, production_par_classe(P20, base))),
        "K2": ("Univers élargi (30 ETF), pondération actuelle", "Contrôle : + matières, devises, obligations hors US, risque actif par actif.",
               lambda: (P30, _production(P30, elargi))),
        "K3": ("Univers élargi (30 ETF) + budget de risque par classe", "Hypothèse principale.",
               lambda: (P30, production_par_classe(P30, elargi))),
    }
    res, sims = {}, {}
    for key, (nom, desc, f) in essais.items():
        P, W = f()
        sim = simulate(P, W, ETF_COST_BPS, rebalance_every=5)
        sims[key] = sim
        poids_classe = {}
        tk = base if P is P20 else elargi
        for c, j in zip(classes(tk), range(len(tk))):
            poids_classe[c] = poids_classe.get(c, 0.0) + float(np.abs(sim.weights[WARMUP:, j]).mean())
        res[key] = {"nom": f"{key} — {nom}", "description": desc, "developpement": period_metrics(sim.returns, sim, dev, 252),
                    "validation": period_metrics(sim.returns, sim, val, 252), "exposition_moyenne_par_classe": poids_classe}
        print(f"  {key} fait ({time.time() - t0:.0f}s)", file=sys.stderr)

    # échantillon 2001-2007 (proxys) : référence et K1 seulement
    pd_, pp = load_presample()
    P0 = np.column_stack([pp[t] for t in base])
    pre = np.arange(len(pd_)) >= WARMUP
    for key, W in (("REF", _production(P0, base)), ("K1", production_par_classe(P0, base))):
        res[key]["echantillon_2001_2007"] = period_metrics(simulate(P0, W, ETF_COST_BPS, rebalance_every=5).returns, None, pre, 252)

    previous = []
    for path in PREVIOUS:
        try:
            previous += [r["developpement"]["sharpe"] for r in json.loads(path.read_text())["resultats"].values()
                         if "developpement" in r]
        except Exception as exc:
            print(f"campagne précédente illisible ({path.name}) : {exc}", file=sys.stderr)
    trial_sharpes = previous + [r["developpement"]["sharpe"] for k, r in res.items() if k != "REF"]
    ref = res["REF"]
    for key, r in res.items():
        r["dsr_developpement"] = deflated_sharpe(sims[key].returns[dev], trial_sharpes, 252)
        if key == "REF":
            continue
        checks = {
            "gain_developpement": r["developpement"]["sharpe"] >= ref["developpement"]["sharpe"] + RULES["dev_gain"],
            "dsr": r["dsr_developpement"] >= RULES["dsr"],
            "validation_non_contredite": r["validation"]["sharpe"] >= ref["validation"]["sharpe"] - RULES["val_tol"],
            "drawdown_validation": r["validation"]["max_dd"] >= ref["validation"]["max_dd"] - RULES["dd_tol"],
        }
        if "echantillon_2001_2007" in r:
            checks["echantillon_2001_2007"] = r["echantillon_2001_2007"]["sharpe"] >= ref["echantillon_2001_2007"]["sharpe"] - RULES["val_tol"]
        r["criteres"] = {k: bool(v) for k, v in checks.items()}
        r["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"

    # PARTIE B : menu de risque sur l'univers actuel depuis 2007 (crise de 2008 incluse)
    dates20, p20 = load_aligned(base, refresh=False)
    d20 = np.array(dates20)
    Pb = np.column_stack([p20[t] for t in base])
    masque = np.arange(len(dates20)) >= WARMUP
    taux = _fred_on(dates20, "DGS3MO") / 100.0
    menus = [menu_risque("Référence — production actuelle", simulate(Pb, _production(Pb, base), ETF_COST_BPS, rebalance_every=5),
                         dates20, taux, masque)]
    acceptes = [k for k, r in res.items() if r.get("verdict") == "ACCEPTÉ" and k == "K1"]  # K1 seul a l'univers actuel
    for k in acceptes:
        menus.append(menu_risque(res[k]["nom"], simulate(Pb, production_par_classe(Pb, base), ETF_COST_BPS, rebalance_every=5),
                                 dates20, taux, masque))
    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES, "ajouts": AJOUTS,
              "periode_essais": [str(d[WARMUP]), dates[-1]], "essais_comptes_dans_le_dsr": len(trial_sharpes),
              "duree_s": round(time.time() - t0), "resultats": res, "menu_risque": menus}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\nDSR calculé sur {rep['essais_comptes_dans_le_dsr']} essais · essais du {rep['periode_essais'][0]} au {rep['periode_essais'][1]}")
    print(f"{'Essai':<62} {'DEV Sh':>6} {'DSR':>5} {'VAL Sh':>6} {'VAL DD':>7} {'01-07':>6}  Verdict")
    for k, r in rep["resultats"].items():
        dv, va = r["developpement"], r["validation"]
        pre = r.get("echantillon_2001_2007", {}).get("sharpe")
        print(f"{r['nom'][:62]:<62} {dv['sharpe']:>6.2f} {r['dsr_developpement']:>5.2f} {va['sharpe']:>6.2f} {va['max_dd']:>7.1%} "
              f"{pre if pre is None else round(pre, 2)!s:>6}  {r.get('verdict', 'référence')}")
        print("      exposition moyenne par classe :", {c: round(v, 2) for c, v in r["exposition_moyenne_par_classe"].items()})
    for m in rep["menu_risque"]:
        print(f"\nMenu de risque — {m['nom']} ({m['debut']} → {m['fin']}) ; 15 %/an atteint au levier {m['premier_levier_a_15_pourcent']}")
        print(f"{'levier':>6} {'rend.':>7} {'vol':>6} {'Sharpe':>6} {'pire b.':>8} {'pire 12m':>9} {'années <0':>10} {'2008-09':>8} {'2020':>7} {'2022':>7} {'brut':>5}")
        for l in m["lignes"]:
            c = l["crises"]
            print(f"{l['levier']:>6} {l['cagr']:>7.1%} {l['vol']:>6.1%} {l['sharpe']:>6.2f} {l['max_dd']:>8.1%} {l['pire_annee_glissante']:>9.1%} "
                  f"{l['annees_negatives']:>4}/{l['annees']:<5} {c.get('2008-2009', float('nan')):>8.1%} {c.get('Covid 2020', float('nan')):>7.1%} "
                  f"{c.get('2022', float('nan')):>7.1%} {l['levier_brut_moyen']:>5.2f}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
