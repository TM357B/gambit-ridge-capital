"""Campagne de recherche n° 7 (octobre 2026) — règles d'entrée, de sortie et sens des positions.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Question : la couche tendance entre, sort et se retourne au fil d'un signal continu (moyenne
TSMOM 12 mois / EWMA multi-vitesses / Kalman), à la hausse comme à la baisse. Des règles
explicites d'entrée et de sortie (cassures, stops, zone neutre, hystérésis) ou une restriction
du sens des positions (long seul, pas de vente d'actions) font-elles mieux ?

Référence : la stratégie ETF de production (« 60/40 + couche tendance », 20 ETF, socle 50 %,
vol GARCH, covariance EWMA, vol cible 10 %, filtre anti micro-trades 25 % / 0,5 %, rebalancement
tous les 5 jours, 5 bps). Le socle 60/40 ne change pas. Seul change le SIGNAL de la couche
tendance passé à build_weights ; dimensionnement, covariance, filtre, coûts identiques.

Paramètres tirés de la littérature ou fixés par construction, AUCUNE grille, aucun réglage a
posteriori. « ATR » : nous n'avons que des clôtures, donc ATR approchée par la moyenne sur
20 séances de |P_t − P_t−1|. Toutes les règles sont causales (décision à la clôture t avec les
seules clôtures jusqu'à t).

Essais (6) :
  E1 Cassures de Donchian + stop suiveur (Clenow, « Following the Trend », 2013) : achat quand
     la clôture dépasse le plus haut des 50 séances précédentes, vente à découvert quand elle
     passe sous le plus bas ; sortie quand le prix recule de 3 ATR depuis son extrême atteint
     depuis l'entrée. Signal ±1 tant que la position est ouverte, 0 sinon. Remplace l'ensemble.
  E2 Ensemble + stop suiveur 3 ATR : on suit le signal de production, mais si le prix recule
     de 3 ATR depuis son extrême depuis l'entrée, on sort et on reste à plat jusqu'à ce que le
     signal change de signe (nouvelle tendance).
  E3 Zone neutre : signal ramené à 0 quand |ensemble| < 1/3, c'est-à-dire quand les trois
     composantes ne s'accordent pas franchement.
  E4 Hystérésis (entrée confirmée, sortie rapide) : entrée longue quand l'ensemble atteint
     +0,5, tenue jusqu'à ce qu'il repasse sous 0 ; symétrique à la baisse. Hors position : 0.
  L1 Long seul : les signaux négatifs sont ramenés à 0 (la couche tendance n'est jamais
     vendeuse ; elle peut rester à plat).
  L2 Pas de vente à découvert d'actions : signaux négatifs ramenés à 0 sur les 7 ETF actions
     (SPY QQQ IWM EFA EEM EWJ VNQ), ventes autorisées ailleurs (taux, matières, devises).
     Littérature : les ventes d'actions sont la partie la plus faible du suivi de tendance.

Périodes et règle d'acceptation : identiques aux campagnes 1 à 6 (développement -> 2019-12-31
après 260 séances de rodage, validation 2020 -> aujourd'hui ; Sharpe dév. >= réf. + 0,05 ;
DSR >= 0,90 ; Sharpe validation >= réf. − 0,05 ; pire baisse validation pas plus de 3 points
au-delà de la réf.), PLUS un 5e critère : sur l'échantillon 2001-2007 reconstitué de la
campagne 5 (proxys, research/campaign5.PROXY), Sharpe >= réf. − 0,05. La validation 2020-2026
a trop servi : elle ne fait que vérifier qu'elle ne contredit pas, elle ne choisit rien.

Tests multiples : DSR calculé sur tous les Sharpe de développement des campagnes 1, 2, 4 et 6
plus les 6 essais de cette campagne. Un essai accepté n'entre au portefeuille qu'avec
l'accord de Tom.

Usage : python3 -m gambit_ridge.research.campaign7
Sortie : data/research_campaign7_2026-10.json
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
from .campaign import RULES, _core_matrix, _production, _trend_parts
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_campaign7_2026-10.json"
PREVIOUS = [ROOT / "data" / f"research_campaign{n}_2026-10.json" for n in ("", "2", "4", "6")]
ACTIONS = ("SPY", "QQQ", "IWM", "EFA", "EEM", "EWJ", "VNQ")
BREAKOUT, ATR_N, ATR_MULT = 50, 20, 3.0
NEUTRE, ENTREE = 1.0 / 3.0, 0.5


def atr_clotures(P: np.ndarray, n: int = ATR_N) -> np.ndarray:
    """ATR approchée sur clôtures : moyenne glissante de |ΔP| sur n séances (NaN avant)."""
    d = np.abs(np.diff(P, axis=0, prepend=P[:1]))
    c = np.cumsum(d, axis=0)
    out = np.full_like(P, np.nan, dtype=float)
    out[n:] = (c[n:] - c[:-n]) / n
    return out


def donchian_stop(P: np.ndarray, n: int = BREAKOUT, mult: float = ATR_MULT) -> np.ndarray:
    """E1 : entrée sur cassure du plus haut / plus bas de n séances, sortie par stop suiveur."""
    T, N = P.shape
    atr = atr_clotures(P)
    S = np.zeros((T, N))
    for j in range(N):
        pos, ext = 0, 0.0
        for t in range(n, T):
            p, a = P[t, j], atr[t, j]
            if not np.isfinite(a):
                continue
            if pos > 0:
                ext = max(ext, p)
                if p < ext - mult * a:
                    pos = 0
            elif pos < 0:
                ext = min(ext, p)
                if p > ext + mult * a:
                    pos = 0
            if pos == 0:
                fen = P[t - n:t, j]
                if p > fen.max():
                    pos, ext = 1, p
                elif p < fen.min():
                    pos, ext = -1, p
            S[t, j] = pos
    return S


def avec_stop(E: np.ndarray, P: np.ndarray, mult: float = ATR_MULT) -> np.ndarray:
    """E2 : signal d'ensemble, coupé par un stop suiveur ; réentrée au prochain changement de signe."""
    T, N = E.shape
    atr = atr_clotures(P)
    S = E.copy()
    for j in range(N):
        sens, ext, coupe = 0, 0.0, False
        for t in range(T):
            s = int(np.sign(E[t, j]))
            if s != sens:  # nouvelle tendance (ou retour à plat) : on repart de zéro
                sens, ext, coupe = s, P[t, j], False
            elif s != 0 and not coupe and np.isfinite(atr[t, j]):
                ext = max(ext, P[t, j]) if s > 0 else min(ext, P[t, j])
                if (s > 0 and P[t, j] < ext - mult * atr[t, j]) or (s < 0 and P[t, j] > ext + mult * atr[t, j]):
                    coupe = True
            if coupe:
                S[t, j] = 0.0
    return S


def zone_neutre(E: np.ndarray, seuil: float = NEUTRE) -> np.ndarray:
    return np.where(np.abs(E) >= seuil, E, 0.0)


def hysteresis(E: np.ndarray, entree: float = ENTREE) -> np.ndarray:
    T, N = E.shape
    S = np.zeros((T, N))
    for j in range(N):
        etat = 0
        for t in range(T):
            e = E[t, j]
            if etat > 0 and e <= 0:
                etat = 0
            elif etat < 0 and e >= 0:
                etat = 0
            if etat == 0:
                etat = 1 if e >= entree else -1 if e <= -entree else 0
            S[t, j] = e if etat != 0 else 0.0
    return S


def long_seul(E: np.ndarray, colonnes=None) -> np.ndarray:
    S = E.copy()
    cols = slice(None) if colonnes is None else list(colonnes)
    S[:, cols] = np.maximum(S[:, cols], 0.0)
    return S


def signaux(P: np.ndarray, tk: list[str]) -> dict:
    E = _trend_parts(P)
    act = [tk.index(t) for t in ACTIONS if t in tk]
    return {
        "REF": ("Référence — production actuelle", "Ensemble TSMOM / EWMA / Kalman, long et short.", E),
        "E1": ("Cassures de Donchian 50 j + stop suiveur 3 ATR", "Clenow (2013), remplace l'ensemble.", donchian_stop(P)),
        "E2": ("Ensemble + stop suiveur 3 ATR", "Sortie sur recul de 3 ATR, réentrée au changement de signe.", avec_stop(E, P)),
        "E3": ("Zone neutre |signal| < 1/3", "À plat quand les composantes ne s'accordent pas.", zone_neutre(E)),
        "E4": ("Hystérésis : entrée à ±0,5, sortie à 0", "Entrée confirmée, sortie rapide.", hysteresis(E)),
        "L1": ("Long seul", "La couche tendance n'est jamais vendeuse.", long_seul(E)),
        "L2": ("Pas de vente d'actions", "Ventes interdites sur les 7 ETF actions, permises ailleurs.", long_seul(E, act)),
    }


def _mesurer(P, tk, dates, sigs, masques):
    res, sims = {}, {}
    for key, (name, desc, S) in sigs.items():
        sim = simulate(P, _production(P, tk, signal=S), ETF_COST_BPS, rebalance_every=5)
        sims[key] = sim
        res[key] = {"nom": f"{key} — {name}", "description": desc,
                    **{k: period_metrics(sim.returns, sim, m, 252) for k, m in masques.items()},
                    "exposition_tendance": float(np.mean(np.abs(S[WARMUP:]) > 0)),
                    "part_vendeuse": float(np.mean(S[WARMUP:] < 0))}
    return res, sims


def run() -> dict:
    from ..data.yahoo import all_etf_symbols, load_aligned
    from .campaign5 import load_presample

    t0 = time.time()
    dates, p = load_aligned(all_etf_symbols(), refresh=False)
    tk = list(p)
    P = np.column_stack([p[t] for t in tk])
    T = len(dates)
    d = np.array(dates)
    print(f"univers : {len(tk)} ETF, {dates[0]} -> {dates[-1]}", file=sys.stderr)
    dev = (np.arange(T) >= WARMUP) & (d <= DEV_END)
    val = d > DEV_END
    res, sims = _mesurer(P, tk, dates, signaux(P, tk), {"developpement": dev, "validation": val})

    pd_, pp = load_presample()
    P0 = np.column_stack([pp[t] for t in tk])
    pre = np.arange(len(pd_)) >= WARMUP
    res0, _ = _mesurer(P0, tk, pd_, signaux(P0, tk), {"echantillon_2001_2007": pre})
    for k in res:
        res[k]["echantillon_2001_2007"] = res0[k]["echantillon_2001_2007"]
    print(f"mesures terminées ({time.time() - t0:.0f}s)", file=sys.stderr)

    previous = []
    for path in PREVIOUS:
        try:
            previous += [r["developpement"]["sharpe"] for r in json.loads(path.read_text())["resultats"].values()]
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
            "echantillon_2001_2007": r["echantillon_2001_2007"]["sharpe"] >= ref["echantillon_2001_2007"]["sharpe"] - RULES["val_tol"],
        }
        r["criteres"] = {k: bool(v) for k, v in checks.items()}
        r["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"
    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES,
              "parametres": {"cassure": BREAKOUT, "atr": ATR_N, "stop_atr": ATR_MULT, "zone_neutre": NEUTRE, "entree_hysteresis": ENTREE},
              "essais_comptes_dans_le_dsr": len(trial_sharpes), "duree_s": round(time.time() - t0), "resultats": res}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\nDSR calculé sur {rep['essais_comptes_dans_le_dsr']} essais (campagnes 1, 2, 4, 6 et 7)")
    print(f"{'Essai':<52} {'DEV Sh':>6} {'DSR':>5} {'VAL Sh':>6} {'VAL DD':>7} {'01-07':>6} {'expo':>5} {'vend.':>5}  Verdict")
    for k, r in rep["resultats"].items():
        dv, va, pr = r["developpement"], r["validation"], r["echantillon_2001_2007"]
        print(f"{r['nom'][:52]:<52} {dv['sharpe']:>6.2f} {r['dsr_developpement']:>5.2f} {va['sharpe']:>6.2f} {va['max_dd']:>7.1%} "
              f"{pr['sharpe']:>6.2f} {r['exposition_tendance']:>5.0%} {r['part_vendeuse']:>5.0%}  {r.get('verdict', 'référence')}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
