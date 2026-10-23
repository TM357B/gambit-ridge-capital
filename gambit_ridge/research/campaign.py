"""Campagne de recherche d'octobre 2026 — nouveaux signaux et élargissement de l'univers.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Référence : la stratégie ETF de production, « 60/40 + couche tendance »
(socle 30 % SPY / 20 % IEF + 50 % d'ensemble tendance TSMOM/EWMA/Kalman à
10 % de vol, filtre anti micro-trades), sur l'univers actuel de 20 ETF.

Périodes et coûts : identiques au banc (evaluate.py) — développement jusqu'au
2019-12-31, validation (holdout) 2020 -> aujourd'hui, 5 bps par unité de
turnover, rebalancement hebdomadaire, dérive des poids.

Paramètres : tirés de la littérature, AUCUNE grille, aucun réglage a posteriori.

Essais (11) :
  A1 Univers élargi complet (50 ETF : + secteurs US, pays, devises, oblig.
     courtes, immobilier international, matières premières détaillées)
  A2 Univers + secteurs US seulement
  A3 Univers + diversifiants hors actions US (pays, devises, matières, oblig.)
  B  Momentum relatif 12-1 au sein des classes d'actifs (Asness, Moskowitz &
     Pedersen 2013), surcouche 0,5x
  C  Value cross-asset : retournement 5 ans (rendement t-5a -> t-1a, inversé ;
     AMP 2013), surcouche 0,5x
  D  Retour à la moyenne court terme : rendement 5 jours inversé, relatif au
     sein des classes (Jegadeesh 1990), surcouche 0,5x
  E  Tendance multi-horizons : TSMOM 1, 3 et 12 mois + EWMA + Kalman dans
     l'ensemble (au lieu de TSMOM 12 mois seul)
  F  Socle géré par la volatilité (Moreira & Muir 2017) : socle 60/40 multiplié
     par vol cible / vol réalisée 21 j du socle, borné [0,5 ; 1,5]
  G  Filtre courbe des taux : socle actions divisé par 2 quand 10 ans - 3 mois
     < 0 (FRED DGS10 / DGS3MO, décalage d'un jour de publication)
  H  Filtre crédit : socle actions divisé par 2 quand HYG sous-performe IEF
     sur 3 mois (stress de crédit ; proxy de marché du spread high yield)
  I  Saisonnalité « Halloween » (Bouman & Jacobsen 2002) : socle actions
     divisé par 2 de mai à octobre

Règle d'acceptation (toutes les conditions) :
  1. Sharpe de développement >= référence + 0,05
  2. Deflated Sharpe Ratio (développement, sur les 12 séries testées) >= 0,90
  3. Sharpe de validation >= référence - 0,05 (le holdout ne contredit pas)
  4. Pire baisse en validation pas plus de 3 points au-delà de la référence
La validation n'est consultée qu'une fois, comme garde-fou, jamais pour choisir.
Un essai accepté n'entre au portefeuille qu'avec l'accord de Tom.

Usage : python3 -m gambit_ridge.research.campaign
Sortie : data/research_campaign_2026-10.json
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
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP, apply_buffer, core_plus_overlay
from .portfolio import build_weights, ewma_covariance

OUT = Path(__file__).resolve().parent.parent.parent / "data" / "research_campaign_2026-10.json"

EXPANSION: dict[str, dict[str, str]] = {
    "Secteurs US": {"XLK": "Technologie", "XLF": "Finance", "XLE": "Énergie", "XLV": "Santé", "XLI": "Industrie",
                    "XLY": "Conso. discrétionnaire", "XLP": "Conso. de base", "XLU": "Services publics", "XLB": "Matériaux"},
    "Pays": {"EWZ": "Brésil", "EWG": "Allemagne", "EWU": "Royaume-Uni", "EWY": "Corée", "EWT": "Taïwan",
             "EWC": "Canada", "EWA": "Australie", "EWH": "Hong Kong", "EWW": "Mexique", "FXI": "Chine"},
    "Obligations courtes": {"SHY": "Treasuries 1-3 ans", "IEI": "Treasuries 3-7 ans"},
    "Devises+": {"FXA": "Dollar australien", "FXC": "Dollar canadien", "FXF": "Franc suisse", "FXB": "Livre sterling"},
    "Immobilier intl": {"RWX": "Immobilier international"},
    "Matières+": {"UNG": "Gaz naturel", "DBB": "Métaux industriels", "DBE": "Énergie (panier)", "DBP": "Métaux précieux"},
}
# classe utilisée pour les signaux relatifs (B, C, D)
CLASS_OF_EXPANSION = {"Secteurs US": "Actions", "Pays": "Actions", "Obligations courtes": "Obligations",
                      "Devises+": "Devises", "Immobilier intl": "Actions", "Matières+": "Matières premières"}

CORE = {"SPY": 0.60, "IEF": 0.40}
EQUITY_CORE = "SPY"
OVERLAY = 0.5
RULES = {"dev_gain": 0.05, "dsr": 0.90, "val_tol": 0.05, "dd_tol": 0.03}


# ---------------------------------------------------------------- données
def _load(symbols: list[str]):
    from ..data.yahoo import load_aligned

    return load_aligned(symbols, refresh=False)


def _classes(tickers: list[str]) -> list[str]:
    from ..data.yahoo import ETF_UNIVERSE

    base = {s: c for c, m in ETF_UNIVERSE.items() for s in m}
    ext = {s: CLASS_OF_EXPANSION[g] for g, m in EXPANSION.items() for s in m}
    return [base.get(t) or ext[t] for t in tickers]


def _fred_on(dates: list[str], series: str, lag_days: int = 1) -> np.ndarray:
    """Valeur FRED connue à chaque date (dernière observation antérieure de `lag_days` jours)."""
    from datetime import timedelta

    root = Path(__file__).resolve().parent.parent
    path = next(p for p in (root / "data_cache" / f"fred_{series}.csv", root.parent / "data_cache" / f"fred_{series}.csv") if p.exists())
    obs = []
    for line in path.read_text().splitlines()[1:]:
        d, _, v = line.partition(",")
        try:
            obs.append((d, float(v)))
        except ValueError:
            continue
    obs.sort()
    od = [o[0] for o in obs]
    out = np.full(len(dates), np.nan)
    for i, d in enumerate(dates):
        cutoff = (date.fromisoformat(d) - timedelta(days=lag_days)).isoformat()
        k = np.searchsorted(od, cutoff, side="right") - 1
        if k >= 0:
            out[i] = obs[k][1]
    return out


# ---------------------------------------------------------------- briques
def _trend_parts(P: np.ndarray, multi_horizon: bool = False) -> np.ndarray:
    parts = [sg.tsmom(P, 252), sg.ewma_trend(P), sg.kalman_trend(P)]
    if multi_horizon:
        parts += [sg.tsmom(P, 21), sg.tsmom(P, 63)]
    return sum(parts) / len(parts)


def _core_matrix(T: int, tickers: list[str], scale_equity: np.ndarray | None = None,
                 scale_all: np.ndarray | None = None) -> np.ndarray:
    W = np.zeros((T, len(tickers)))
    for tk, w in CORE.items():
        W[:, tickers.index(tk)] = w
    if scale_equity is not None:
        W[:, tickers.index(EQUITY_CORE)] *= scale_equity
    if scale_all is not None:
        W *= scale_all[:, None]
    return W


def _production(P: np.ndarray, tickers: list[str], *, vol=None, cov=None, signal=None, core=None) -> np.ndarray:
    vol = sg.garch_vol(P) if vol is None else vol
    cov = ewma_covariance(P) if cov is None else cov
    signal = _trend_parts(P) if signal is None else signal
    core = _core_matrix(len(P), tickers) if core is None else core
    return apply_buffer(core_plus_overlay(core, build_weights(signal, vol, cov)))


def cross_sectional(score: np.ndarray, classes: list[str]) -> np.ndarray:
    """Rang relatif au sein de chaque classe (>= 3 membres), centré, dans [-1, 1]. NaN -> neutre."""
    T, N = score.shape
    out = np.zeros((T, N))
    groups = {}
    for j, c in enumerate(classes):
        groups.setdefault(c, []).append(j)
    for idx in groups.values():
        if len(idx) < 3:
            continue
        sub = score[:, idx]
        for t in range(T):
            row = sub[t]
            ok = np.isfinite(row)
            if ok.sum() < 3:
                continue
            ranks = np.argsort(np.argsort(row[ok])).astype(float)
            out[t, np.array(idx)[ok]] = 2.0 * ranks / (ok.sum() - 1) - 1.0
    return out


def _past_return(P: np.ndarray, start_lag: int, end_lag: int) -> np.ndarray:
    """Rendement de t-start_lag à t-end_lag (NaN avant d'avoir l'historique)."""
    T, _ = P.shape
    out = np.full(P.shape, np.nan)
    if T > start_lag:
        out[start_lag:] = P[start_lag - end_lag: T - end_lag] / P[: T - start_lag] - 1.0
    return out


def _realized_vol(r: np.ndarray, window: int = 21) -> np.ndarray:
    out = np.full(len(r), np.nan)
    for t in range(window, len(r)):
        out[t] = np.std(r[t - window + 1: t + 1], ddof=1) * np.sqrt(252)
    return out


# ---------------------------------------------------------------- essais
def run() -> dict:
    from ..data.yahoo import all_etf_symbols

    t_all = time.time()
    base_syms = all_etf_symbols()
    d0, p0 = _load(base_syms)
    T0 = len(d0)
    tk0 = list(p0)
    P0 = np.column_stack([p0[t] for t in tk0])
    cls0 = _classes(tk0)
    vol0, cov0 = sg.garch_vol(P0), ewma_covariance(P0)
    trend0 = _trend_parts(P0)
    print(f"univers de référence : {len(tk0)} ETF, {d0[0]} -> {d0[-1]}", file=sys.stderr)

    series: dict[str, dict] = {}  # nom -> {dates, P, W, desc}

    def add(key, name, dates, P, W, desc):
        series[key] = {"name": name, "dates": dates, "P": P, "W": W, "desc": desc}

    W_ref = _production(P0, tk0, vol=vol0, cov=cov0, signal=trend0)
    add("REF", "Référence — production actuelle (20 ETF)", d0, P0, W_ref, "60/40 + couche tendance, univers actuel.")

    # A — élargissement de l'univers (même stratégie, mêmes paramètres)
    groups_a = {
        "A1": ("Univers élargi complet", list(EXPANSION)),
        "A2": ("Univers + secteurs US", ["Secteurs US"]),
        "A3": ("Univers + diversifiants hors actions US", ["Pays", "Obligations courtes", "Devises+", "Immobilier intl", "Matières+"]),
    }
    for key, (name, groups) in groups_a.items():
        t0 = time.time()
        syms = base_syms + [s for g in groups for s in EXPANSION[g]]
        d, p = _load(syms)
        tk = list(p)
        P = np.column_stack([p[t] for t in tk])
        add(key, f"{key} — {name} ({len(tk)} ETF)", d, P, _production(P, tk),
            f"Production appliquée à {len(tk)} ETF, à partir du {d[0]}.")
        print(f"  {key} : {len(tk)} ETF, {time.time() - t0:.0f}s", file=sys.stderr)

    # B, C, D — signaux relatifs en surcouche 0,5x de la production
    rel = {
        "B": ("Momentum relatif 12-1", cross_sectional(_past_return(P0, 252, 21), cls0),
              "Classement 12 mois hors dernier mois, au sein des classes, risque égal, vol 10 %."),
        "C": ("Value cross-asset (retournement 5 ans)", cross_sectional(-_past_return(P0, 1260, 252), cls0),
              "Inverse du rendement t-5 ans -> t-1 an, au sein des classes, risque égal, vol 10 %."),
        "D": ("Retour à la moyenne 1 semaine", cross_sectional(-_past_return(P0, 5, 0), cls0),
              "Inverse du rendement 5 jours, au sein des classes, risque égal, vol 10 %."),
    }
    for key, (name, sig, desc) in rel.items():
        W_sig = build_weights(sig, vol0, cov0)
        add(key, f"{key} — {name} (surcouche 0,5x)", d0, P0, apply_buffer(W_ref + OVERLAY * W_sig), desc)

    # E — tendance multi-horizons
    add("E", "E — Tendance multi-horizons (1, 3, 12 mois)", d0, P0,
        _production(P0, tk0, vol=vol0, cov=cov0, signal=_trend_parts(P0, multi_horizon=True)),
        "TSMOM 1, 3 et 12 mois ajoutés à l'ensemble EWMA + Kalman.")

    # F — socle géré par la volatilité
    R0 = np.zeros_like(P0)
    R0[1:] = P0[1:] / P0[:-1] - 1.0
    core_ret = sum(w * R0[:, tk0.index(tk)] for tk, w in CORE.items())
    rv = _realized_vol(core_ret)
    target = np.nanmedian(rv[: np.searchsorted(d0, DEV_END)])  # vol cible = médiane du développement (pas du holdout)
    scale_f = np.clip(np.nan_to_num(target / rv, nan=1.0), 0.5, 1.5)
    add("F", "F — Socle 60/40 géré par la volatilité", d0, P0,
        _production(P0, tk0, vol=vol0, cov=cov0, signal=trend0, core=_core_matrix(T0, tk0, scale_all=scale_f)),
        f"Socle x vol cible ({target:.1%}, médiane du développement) / vol réalisée 21 j, borné [0,5 ; 1,5].")

    # G — courbe des taux
    slope = _fred_on(d0, "DGS10") - _fred_on(d0, "DGS3MO")
    scale_g = np.where(np.nan_to_num(slope, nan=1.0) < 0, 0.5, 1.0)
    add("G", "G — Filtre courbe des taux inversée", d0, P0,
        _production(P0, tk0, vol=vol0, cov=cov0, signal=trend0, core=_core_matrix(T0, tk0, scale_equity=scale_g)),
        f"Socle actions /2 quand 10 ans - 3 mois < 0 ({(scale_g < 1).mean():.0%} des jours).")

    # H — stress de crédit
    i_h, i_i = tk0.index("HYG"), tk0.index("IEF")
    rel_credit = _past_return(P0[:, [i_h]], 63, 0)[:, 0] - _past_return(P0[:, [i_i]], 63, 0)[:, 0]
    scale_h = np.where(np.nan_to_num(rel_credit, nan=0.0) < 0, 0.5, 1.0)
    add("H", "H — Filtre stress de crédit (HYG vs IEF)", d0, P0,
        _production(P0, tk0, vol=vol0, cov=cov0, signal=trend0, core=_core_matrix(T0, tk0, scale_equity=scale_h)),
        f"Socle actions /2 quand HYG sous-performe IEF sur 3 mois ({(scale_h < 1).mean():.0%} des jours).")

    # I — Halloween
    months = np.array([int(d[5:7]) for d in d0])
    scale_i = np.where((months >= 5) & (months <= 10), 0.5, 1.0)
    add("I", "I — Saisonnalité « Halloween »", d0, P0,
        _production(P0, tk0, vol=vol0, cov=cov0, signal=trend0, core=_core_matrix(T0, tk0, scale_equity=scale_i)),
        "Socle actions /2 de mai à octobre.")

    # ---- évaluation : chaque série sur sa propre grille de dates, même découpage
    res = {}
    sims = {}
    for key, s in series.items():
        d = np.array(s["dates"])
        sim = simulate(s["P"], s["W"], ETF_COST_BPS, rebalance_every=5)
        dev = (np.arange(len(d)) >= WARMUP) & (d <= DEV_END)
        val = d > DEV_END
        sims[key] = (sim, dev, val, d)
        res[key] = {"nom": s["name"], "description": s["desc"], "debut": str(d[WARMUP]), "fin": str(d[-1]),
                    "developpement": period_metrics(sim.returns, sim, dev, 252),
                    "validation": period_metrics(sim.returns, sim, val, 252)}
    trial_sharpes = [r["developpement"]["sharpe"] for r in res.values()]
    for key, (sim, dev, val, d) in sims.items():
        res[key]["dsr_developpement"] = deflated_sharpe(sim.returns[dev], trial_sharpes, 252)
        full = np.arange(len(d)) >= WARMUP
        eq = np.cumprod(1.0 + sim.returns[full])
        step = max(1, len(eq) // 300)
        res[key]["courbe"] = {"dates": [str(x) for x in d[full][::step]], "equity": [round(float(x), 4) for x in eq[::step]]}

    ref = res["REF"]
    for key, r in res.items():
        if key == "REF":
            continue
        checks = {
            "gain_developpement": r["developpement"]["sharpe"] >= ref["developpement"]["sharpe"] + RULES["dev_gain"],
            "dsr": r["dsr_developpement"] >= RULES["dsr"],
            "validation_non_contredite": r["validation"]["sharpe"] >= ref["validation"]["sharpe"] - RULES["val_tol"],
            "drawdown_validation": r["validation"]["max_dd"] >= ref["validation"]["max_dd"] - RULES["dd_tol"],
        }
        r["criteres"] = checks = {k: bool(v) for k, v in checks.items()}  # booléens numpy -> JSON
        r["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"
    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES,
              "duree_s": round(time.time() - t_all), "resultats": res}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    res = rep["resultats"]
    print(f"\n{'Essai':<58} {'DEV Sh':>6} {'DSR':>5} {'VAL Sh':>6} {'VAL CAGR':>8} {'VAL DD':>7} {'TO/an':>6}  Verdict")
    for k, r in res.items():
        dv, va = r["developpement"], r["validation"]
        print(f"{r['nom'][:58]:<58} {dv['sharpe']:>6.2f} {r['dsr_developpement']:>5.2f} {va['sharpe']:>6.2f} "
              f"{va['cagr']:>8.1%} {va['max_dd']:>7.1%} {va.get('turnover_annuel', 0):>6.1f}  {r.get('verdict', 'référence')}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
