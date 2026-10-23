"""Campagne de recherche n° 5 (octobre 2026) — période 2001-2007 jamais utilisée.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Après 35 essais sur 2008-2026, la validation 2020-2026 a été consultée trop souvent pour
juger de nouvelles idées. Cette campagne construit un échantillon NEUF : les 20 marchés de
la stratégie reconstitués de 2000-09 à 2007-04 (veille du début de l'échantillon actuel)
avec des instruments plus anciens qui suivent les mêmes marchés :

  SPY VFINX · QQQ RYOCX · IWM NAESX · EFA VGTSX · EEM VEIEX · EWJ EWJ · VNQ VGSIX
  TLT VUSTX · IEF VFITX · TIP VIPSX · LQD VWESX · HYG VWEHX
  GLD GC=F · SLV SI=F · DBC ^SPGSCI · USO CL=F · DBA ZC=F
  UUP DX-Y.NYB · FXE 6E=F · FXY 6J=F

Limites connues (identiques pour la référence et les variantes, donc sans effet sur la
comparaison, mais à garder en tête pour les niveaux absolus) : les contrats à terme sont
des séries « premier contrat » sans ajustement de roulement, ^SPGSCI est un indice au
comptant, et le maïs seul représente l'agriculture. Coûts : 5 bps, comme partout.

Mesure : après 260 séances de rodage, soit ~2001-10 -> 2007-04 (fin du krach internet,
reprise 2003-2007).

Partie A — robustesse : la stratégie de production est mesurée telle quelle, à côté de
SPY et du 60/40. Rien n'est choisi ici.

Partie B — variantes rejugées. Seules sont admises les variantes des campagnes 1 et 4 qui
n'avaient dégradé NI le développement (Sharpe >= référence - 0,02) NI la validation
(>= référence - 0,05) — liste arrêtée d'après les rapports déjà commités :
  F  Socle 60/40 géré par la volatilité (vol cible = constante de la campagne 1)
  G  Filtre courbe des taux inversée (socle actions /2 si 10 ans - 3 mois < 0)
  P1 Rebalancement quotidien avec le filtre
  P3 Filtre anti micro-trades élargi (50 % / 1 %)

Règle d'acceptation sur l'échantillon neuf (toutes les conditions) :
  1. Sharpe >= référence + 0,05
  2. pire baisse pas plus de 3 points au-delà de la référence
  3. Deflated Sharpe Ratio >= 0,90, calculé sur toutes les séries testées depuis la campagne 1
     (37 à l'exécution ; le protocole initial annonçait 36, erreur de décompte sans effet sur les calculs)
Une variante acceptée aura donc gagné sur des données neuves ET n'aura perdu sur aucune
des deux périodes précédentes. Elle n'entre au portefeuille qu'avec l'accord de Tom.

Usage : python3 -m gambit_ridge.research.campaign5
Sortie : data/research_campaign5_2026-10.json
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
from .campaign import CORE, RULES, _core_matrix, _fred_on, _realized_vol, _trend_parts
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP, apply_buffer, core_plus_overlay
from .portfolio import build_weights, ewma_covariance

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_campaign5_2026-10.json"
PREVIOUS = [ROOT / "data" / f"research_campaign{n}_2026-10.json" for n in ("", "2", "4")]
SAMPLE_END = "2007-04-10"  # veille du premier jour de l'échantillon ETF actuel

PROXY = {
    "SPY": "VFINX", "QQQ": "RYOCX", "IWM": "NAESX", "EFA": "VGTSX", "EEM": "VEIEX", "EWJ": "EWJ", "VNQ": "VGSIX",
    "TLT": "VUSTX", "IEF": "VFITX", "TIP": "VIPSX", "LQD": "VWESX", "HYG": "VWEHX",
    "GLD": "GC=F", "SLV": "SI=F", "DBC": "^SPGSCI", "USO": "CL=F", "DBA": "ZC=F",
    "UUP": "DX-Y.NYB", "FXE": "6E=F", "FXY": "6J=F",
}


def load_presample() -> tuple[list[str], dict[str, np.ndarray]]:
    from ..data.yahoo import YahooConnector, all_etf_symbols

    conn = YahooConnector()
    order = all_etf_symbols()
    raw = {etf: {d: p for d, p in conn.fetch(PROXY[etf]).items() if d <= SAMPLE_END} for etf in order}
    dates = sorted(set.intersection(*(set(v) for v in raw.values())))
    return dates, {etf: np.array([raw[etf][d] for d in dates], dtype=float) for etf in order}


def _campaign1_vol_target() -> float:
    """Constante de l'essai F : médiane de la vol réalisée 21 j du socle sur le développement 2008-2019."""
    from ..data.yahoo import all_etf_symbols, load_aligned

    d, p = load_aligned(all_etf_symbols(), refresh=False)
    tk = list(p)
    P = np.column_stack([p[t] for t in tk])
    R = np.zeros_like(P)
    R[1:] = P[1:] / P[:-1] - 1.0
    core_ret = sum(w * R[:, tk.index(t)] for t, w in CORE.items())
    return float(np.nanmedian(_realized_vol(core_ret)[: np.searchsorted(d, DEV_END)]))


def run() -> dict:
    t0 = time.time()
    dates, p = load_presample()
    tk = list(p)
    P = np.column_stack([p[t] for t in tk])
    T = len(dates)
    print(f"échantillon neuf : {len(tk)} marchés, {dates[0]} -> {dates[-1]} ({T} séances)", file=sys.stderr)
    vol, cov = sg.garch_vol(P), ewma_covariance(P)
    trend = build_weights(_trend_parts(P), vol, cov)

    def prod(core=None, rel=0.25, abs_min=0.005, every=5):
        core = _core_matrix(T, tk) if core is None else core
        return apply_buffer(core_plus_overlay(core, trend), rel=rel, abs_min=abs_min, every=every)

    R = np.zeros_like(P)
    R[1:] = P[1:] / P[:-1] - 1.0
    core_ret = sum(w * R[:, tk.index(t)] for t, w in CORE.items())
    target = _campaign1_vol_target()
    scale_f = np.clip(np.nan_to_num(target / _realized_vol(core_ret), nan=1.0), 0.5, 1.5)
    slope = _fred_on(dates, "DGS10") - _fred_on(dates, "DGS3MO")
    scale_g = np.where(np.nan_to_num(slope, nan=1.0) < 0, 0.5, 1.0)

    W_spy = np.zeros((T, len(tk)))
    W_spy[:, tk.index("SPY")] = 1.0
    series = {
        "REF": ("Stratégie de production (60/40 + couche tendance)", prod(), 5, "référence"),
        "SPY": ("Repère — S&P 500", W_spy, 5, "repère"),
        "6040": ("Repère — 60/40", _core_matrix(T, tk), 5, "repère"),
        "F": (f"F — Socle géré par la volatilité (cible {target:.1%})", prod(core=_core_matrix(T, tk, scale_all=scale_f)), 5, "variante"),
        "G": (f"G — Filtre courbe inversée ({(scale_g < 1).mean():.0%} des jours)", prod(core=_core_matrix(T, tk, scale_equity=scale_g)), 5, "variante"),
        "P1": ("P1 — Rebalancement quotidien", prod(every=1), 1, "variante"),
        "P3": ("P3 — Filtre anti micro-trades élargi", prod(rel=0.5, abs_min=0.01), 5, "variante"),
    }
    d = np.array(dates)
    mask = np.arange(T) >= WARMUP
    res, sims = {}, {}
    for key, (name, W, every, role) in series.items():
        sim = simulate(P, W, ETF_COST_BPS, rebalance_every=every)
        sims[key] = sim
        eq = np.cumprod(1.0 + sim.returns[mask])
        step = max(1, len(eq) // 250)
        res[key] = {"nom": name, "role": role, "mesure": period_metrics(sim.returns, sim, mask, 252),
                    "courbe": {"dates": [str(x) for x in d[mask][::step]], "equity": [round(float(x), 4) for x in eq[::step]]}}
    previous = []
    for path in PREVIOUS:
        try:
            previous += [r["developpement"]["sharpe"] for r in json.loads(path.read_text())["resultats"].values()]
        except Exception as exc:
            print(f"campagne précédente illisible ({path.name}) : {exc}", file=sys.stderr)
    variants = [k for k, v in res.items() if v["role"] == "variante"]
    trial_sharpes = previous + [res[k]["mesure"]["sharpe"] for k in variants]
    ref = res["REF"]["mesure"]
    for key in variants + ["REF"]:
        res[key]["dsr"] = deflated_sharpe(sims[key].returns[mask], trial_sharpes, 252)
    for key in variants:
        m = res[key]["mesure"]
        checks = {"gain": m["sharpe"] >= ref["sharpe"] + RULES["dev_gain"],
                  "drawdown": m["max_dd"] >= ref["max_dd"] - RULES["dd_tol"],
                  "dsr": res[key]["dsr"] >= RULES["dsr"]}
        res[key]["criteres"] = {k: bool(v) for k, v in checks.items()}
        res[key]["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"
    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES,
              "debut_mesure": str(d[WARMUP]), "fin": str(d[-1]), "proxys": PROXY,
              "essais_comptes_dans_le_dsr": len(trial_sharpes), "duree_s": round(time.time() - t0), "resultats": res}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\nÉchantillon neuf : {rep['debut_mesure']} -> {rep['fin']} · DSR sur {rep['essais_comptes_dans_le_dsr']} séries")
    print(f"{'Série':<56} {'Sharpe':>6} {'CAGR':>7} {'Vol':>6} {'MaxDD':>7} {'TO/an':>6} {'DSR':>5}  Verdict")
    for k, r in rep["resultats"].items():
        m = r["mesure"]
        print(f"{r['nom'][:56]:<56} {m['sharpe']:>6.2f} {m['cagr']:>7.1%} {m['vol']:>6.1%} {m['max_dd']:>7.1%} "
              f"{m.get('turnover_annuel', 0):>6.1f} {r.get('dsr', float('nan')):>5.2f}  {r.get('verdict', r['role'])}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
