"""Campagne de recherche n° 2 (octobre 2026) — nouvelles sources de rendement et agents.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Référence : la stratégie ETF de production (« 60/40 + couche tendance », 20 ETF),
comme dans la campagne n° 1. Chaque essai est une POCHE autonome, ramenée à 10 %
de vol, nette de coûts, ajoutée en surcouche 0,5x : combinaison = production +
0,5 x poche. La référence est mesurée sur EXACTEMENT les mêmes jours que l'essai
(certaines poches ne démarrent qu'en 2011-2012).

Périodes : développement jusqu'au 2019-12-31, validation 2020 -> aujourd'hui.
Coûts : 5 bps (ETF, actions, devises, indices), 20 bps (crypto). Rebalancement
hebdomadaire. Décisions à la clôture t, portées sur t -> t+1 (causal).

Partie 1 — sources de rendement différentes (paramètres de la littérature) :
  V1 Prime de volatilité : SVXY (vente de volatilité VIX court terme) détenu
     seulement quand la structure par terme est en contango (VIX < VIX3M) —
     Simon & Campasano (2014).
  V2 Couverture longue volatilité : VIXY détenu seulement en backwardation
     (VIX > VIX3M), cash sinon.
  R1 Carry de taux : duration (IEF + TLT à risque égal) longue si la pente
     10 ans - 3 mois > 0, courte sinon (Koijen et al. 2018 : carry obligataire
     ~ pente). FRED, décalage d'un jour de publication.
  Q1 Faible volatilité / « betting against beta » : long USMV, short SPY à
     hauteur du bêta 1 an de USMV (Frazzini & Pedersen 2014).

Partie 2 — signaux des agents de recherche, rejoués jour par jour :
  à chaque date, chaque agent reçoit exactement ce qu'il reçoit en production
  (261 dernières clôtures Yahoo de ses tickers ; facteurs FRED T10Y2Y, VIXCLS,
  DGS10 pour macro-dm, décalés d'un jour) ; position = direction x conviction ;
  poids à risque égal (vol EWMA), vol 10 %. Tickers sur calendriers différents :
  prix reportés au dernier connu (jamais de prix futur). US10Y (rendement ^TNX)
  est négocié via IEF en sens inverse (taux en hausse = obligations en baisse).
  A1..A6 Équipes Macro, Micro, IA & Tech, Matières premières, Crypto, Devises
  A7 Conseil complet (moyenne des 6 poches d'équipe)
  A8 Conseil complet avec le correctif du bug d'agrégation (les facteurs
     tri-horizon / Sharpe / drawdown du dernier ticker étaient appliqués à
     tous les tickers de l'agent ; corrigé dans core/agent.py, l'ancien
     comportement est rejoué via QuantAgent.legacy_factor_leak)

Règle d'acceptation : identique à la campagne n° 1 (toutes les conditions) —
  1. Sharpe de développement >= référence (mêmes jours) + 0,05
  2. Deflated Sharpe Ratio (développement, 13 séries) >= 0,90
  3. Sharpe de validation >= référence - 0,05
  4. Pire baisse en validation pas plus de 3 points au-delà de la référence
Un essai accepté n'entre au portefeuille qu'avec l'accord de Tom.

Usage : python3 -m gambit_ridge.research.campaign2
Sortie : data/research_campaign2_2026-10.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from . import signals as sg
from .backtest import deflated_sharpe, period_metrics, simulate
from .campaign import RULES, _fred_on, _production
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP
from .portfolio import build_weights, ewma_covariance

OUT = Path(__file__).resolve().parent.parent.parent / "data" / "research_campaign2_2026-10.json"
OVERLAY = 0.5
CRYPTO_COST_BPS = 20.0
AGENT_WINDOW = 261
AGENT_EVERY = 5


# ---------------------------------------------------------------- données
def _raw(symbol: str) -> dict[str, float]:
    from ..data.yahoo import YahooConnector, complete_cutoff

    cut = complete_cutoff(symbol)
    return {d: p for d, p in YahooConnector().fetch(symbol, refresh=False).items() if d <= cut}


def _panel(symbols: dict[str, str], dates: list[str] | None = None):
    """{ticker: symbole Yahoo} -> (dates, P (T,N) reporté au dernier prix, première date valide par colonne)."""
    raw = {tk: _raw(sym) for tk, sym in symbols.items()}
    dates = dates or sorted(set().union(*(set(v) for v in raw.values())))
    T, N = len(dates), len(symbols)
    P = np.full((T, N), np.nan)
    for j, tk in enumerate(symbols):
        last = np.nan
        for i, d in enumerate(dates):
            last = raw[tk].get(d, last)
            P[i, j] = last
    return dates, P


def _sleeve_returns(P: np.ndarray, W: np.ndarray, cost) -> np.ndarray:
    Pf = np.where(np.isfinite(P), P, 1.0)  # colonnes pas encore cotées : poids nul imposé, prix neutre
    W = np.where(np.isfinite(P), W, 0.0)
    return simulate(Pf, W, cost, rebalance_every=5).returns


def _on_grid(src_dates: list[str], rets: np.ndarray, grid: list[str]) -> np.ndarray:
    """Rendements d'une poche ré-échantillonnés sur la grille de la production (capitalisés)."""
    eq = np.cumprod(1.0 + rets)
    idx = np.searchsorted(np.array(src_dates), np.array(grid), side="right") - 1
    ceq = np.where(idx >= 0, eq[np.clip(idx, 0, None)], np.nan)
    out = np.zeros(len(grid))
    out[1:] = ceq[1:] / ceq[:-1] - 1.0
    return np.nan_to_num(out)


def _vol_target(W: np.ndarray, P: np.ndarray, target: float = 0.10) -> np.ndarray:
    """Ramène une poche à `target` de vol ex ante (covariance EWMA), causal."""
    Pf = P.copy()
    for j in range(Pf.shape[1]):  # avant la cotation : premier prix connu (n'affecte que des poids nuls)
        ok = np.isfinite(Pf[:, j]) & (Pf[:, j] > 0)
        Pf[~ok, j] = Pf[ok, j][0] if ok.any() else 1.0
    cov = ewma_covariance(Pf)
    out = np.zeros_like(W)
    for t in range(len(W)):
        w = W[t]
        v = float(np.sqrt(max(w @ cov[t] @ w, 0.0)))
        if v > 1e-9:
            w = w * min(target / v, 3.0)
        out[t] = w
    return out


# ---------------------------------------------------------------- partie 1
def part1(grid: list[str]) -> dict[str, dict]:
    out = {}
    d, P = _panel({"VIX": "^VIX", "VIX3M": "^VIX3M", "SVXY": "SVXY", "VIXY": "VIXY"}, grid)
    contango = np.nan_to_num(P[:, 0] < P[:, 1], nan=False)
    for key, col, on, name, desc in (
        ("V1", 2, contango, "Prime de volatilité (SVXY en contango)", "SVXY quand VIX < VIX3M, cash sinon."),
        ("V2", 3, ~contango & np.isfinite(P[:, 0]) & np.isfinite(P[:, 1]), "Couverture longue volatilité (VIXY en backwardation)",
         "VIXY quand VIX > VIX3M, cash sinon."),
    ):
        Pi = P[:, [col]]
        vol = sg.ewma_vol(np.where(np.isfinite(Pi), Pi, 1.0))
        W = np.where(on[:, None] & np.isfinite(Pi), 0.10 / vol, 0.0)
        W = np.clip(W, 0.0, 1.0)
        out[key] = {"name": name, "desc": desc, "dates": d, "rets": _sleeve_returns(Pi, W, ETF_COST_BPS),
                    "start": d[int(np.argmax(np.isfinite(Pi[:, 0])))]}

    d, P = _panel({"IEF": "IEF", "TLT": "TLT"}, grid)
    slope = _fred_on(d, "DGS10") - _fred_on(d, "DGS3MO")
    sign = np.where(np.nan_to_num(slope, nan=0.0) > 0, 1.0, -1.0)
    vol = sg.ewma_vol(P)
    W = _vol_target(sign[:, None] * (1.0 / vol), P)
    out["R1"] = {"name": "Carry de taux (duration selon la pente)", "desc": "IEF + TLT à risque égal, long si 10a-3m > 0, court sinon.",
                 "dates": d, "rets": _sleeve_returns(P, W, ETF_COST_BPS), "start": d[0]}

    d, P = _panel({"USMV": "USMV", "SPY": "SPY"}, grid)
    r = np.zeros_like(P)
    r[1:] = P[1:] / P[:-1] - 1.0
    beta = np.zeros(len(d))
    for t in range(252, len(d)):
        a, b = r[t - 251: t + 1, 0], r[t - 251: t + 1, 1]
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() > 200 and np.var(b[ok]) > 0:
            beta[t] = np.cov(a[ok], b[ok])[0, 1] / np.var(b[ok], ddof=1)
    W = np.column_stack([np.where(beta > 0, 1.0, 0.0), -beta])
    W = _vol_target(W, P)
    out["Q1"] = {"name": "Faible volatilité (USMV long, SPY short bêta-neutre)", "desc": "Bêta 1 an, poche bêta-neutre à 10 % de vol.",
                 "dates": d, "rets": _sleeve_returns(P, W, ETF_COST_BPS), "start": d[int(np.argmax(beta > 0))]}
    return out


# ---------------------------------------------------------------- partie 2 : agents rejoués
def _team_signals(team, panel_dates, P, tickers, factors, fixed: bool) -> np.ndarray:
    from ..core.agent import MarketData, QuantAgent
    from ..core.signal import SignalDirection

    T, N = P.shape
    S = np.zeros((T, N))
    col = {tk: j for j, tk in enumerate(tickers)}
    QuantAgent.legacy_factor_leak = not fixed  # "brut" = comportement de production avant correctif
    try:
        last = np.zeros(N)
        for t in range(T):
            if t % AGENT_EVERY == 0:
                last = np.zeros(N)
                for agent in team.agents:
                    data = {}
                    for tk in agent.universe():
                        j = col.get(tk)
                        if j is None:
                            continue
                        hist = P[max(0, t - AGENT_WINDOW + 1): t + 1, j]
                        hist = hist[np.isfinite(hist)]
                        if len(hist) >= 64:
                            data[tk] = MarketData(ticker=tk, prices=hist.tolist())
                    if not data:
                        continue
                    if hasattr(agent, "factors") and factors is not None:
                        agent.factors = {k: [x for x in v[: t + 1] if np.isfinite(x)][-AGENT_WINDOW:] for k, v in factors.items()}
                    for s in agent.analyze(data).signals:
                        sgn = {SignalDirection.LONG: 1.0, SignalDirection.SHORT: -1.0}.get(s.direction, 0.0)
                        j = col[s.ticker]
                        last[j] = sgn * s.conviction if last[j] == 0 else (last[j] + sgn * s.conviction) / 2
            S[t] = last
    finally:
        QuantAgent.legacy_factor_leak = False
    return S


def part2(grid: list[str]) -> dict[str, dict]:
    from ..data.real_market import YAHOO_MAP
    from ..teams.commodities import build_commodities_team
    from ..teams.crypto import build_crypto_team
    from ..teams.forex import build_forex_team
    from ..teams.ia_tech import build_ia_tech_team
    from ..teams.macro import build_macro_team
    from ..teams.micro import build_micro_team

    builders = {"A1": ("Équipe Macro", build_macro_team), "A2": ("Équipe Micro", build_micro_team),
                "A3": ("Équipe IA & Tech", build_ia_tech_team), "A4": ("Équipe Matières premières", lambda: build_commodities_team(etendue=False)),
                "A5": ("Équipe Crypto 24/7", build_crypto_team), "A6": ("Équipe Devises", lambda: build_forex_team(etendue=False))}
    out, team_curves = {}, {"brut": [], "corrigé": []}
    for key, (name, build) in builders.items():
        t0 = time.time()
        team = build()
        tickers = sorted({tk for a in team.agents for tk in a.universe()})
        syms = {tk: YAHOO_MAP.get(tk, tk) for tk in tickers}
        if "US10Y" in syms:
            syms["US10Y"] = "^TNX"
        d, P = _panel(syms)
        d = [x for x in d if x >= "2005-01-01"]
        P = P[-len(d):]
        factors = None
        if key == "A1":
            factors = {s: _fred_on(d, s) for s in ("T10Y2Y", "VIXCLS", "DGS10")}
        # instrument négocié pour chaque ticker (US10Y -> IEF inversé)
        Pt, sign = P.copy(), np.ones(len(tickers))
        if "US10Y" in tickers:
            j = tickers.index("US10Y")
            _, ief = _panel({"IEF": "IEF"}, d)
            Pt[:, j], sign[j] = ief[:, 0], -1.0
        crypto = key == "A5"
        Pv = np.where(np.isfinite(Pt) & (Pt > 0), Pt, np.nan)
        vol = sg.ewma_vol(np.where(np.isfinite(Pv), Pv, 1.0))
        for variant, fixed in (("brut", False), ("corrigé", True)):
            S = _team_signals(team, d, P, tickers, factors, fixed) * sign
            W = _vol_target(S * (0.10 / np.sqrt(len(tickers))) / vol, Pv)
            rets = _sleeve_returns(Pv, W, CRYPTO_COST_BPS if crypto else ETF_COST_BPS)
            first = int(np.argmax(np.any(W != 0, axis=1)))
            team_curves[variant].append((d, rets, d[first]))
            if variant == "brut":
                out[key] = {"name": name, "desc": f"{len(team.agents)} agents, {len(tickers)} tickers.", "dates": d, "rets": rets, "start": d[first]}
        print(f"  {key} {name} : {time.time() - t0:.0f}s", file=sys.stderr)
    for key, variant, name in (("A7", "brut", "Conseil complet (6 équipes)"), ("A8", "corrigé", "Conseil complet, bug d'agrégation corrigé")):
        cols = [_on_grid(dd, rr, grid) for dd, rr, _ in team_curves[variant]]
        start = max(s for _, _, s in team_curves[variant][:4])  # équipes non crypto déjà actives
        out[key] = {"name": name, "desc": "Moyenne des 6 poches d'équipe.", "dates": grid, "rets": np.mean(cols, axis=0),
                    "start": start}
    return out


# ---------------------------------------------------------------- évaluation
def run() -> dict:
    from ..data.yahoo import all_etf_symbols, load_aligned

    t_all = time.time()
    grid, p0 = load_aligned(all_etf_symbols(), refresh=False)
    tk0 = list(p0)
    P0 = np.column_stack([p0[t] for t in tk0])
    ref = simulate(P0, _production(P0, tk0), ETF_COST_BPS, rebalance_every=5).returns
    print(f"référence : {len(tk0)} ETF, {grid[0]} -> {grid[-1]}", file=sys.stderr)

    trials = part1(grid) | part2(grid)
    g = np.array(grid)
    res, combos = {}, {}
    for key, tr in trials.items():
        sleeve = _on_grid(tr["dates"], tr["rets"], grid) if tr["dates"] is not grid else tr["rets"]
        start = max(tr["start"], grid[WARMUP])
        window = g >= start
        # 260 séances de rodage de la poche elle-même avant de mesurer
        first = int(np.argmax(window)) + 260
        window = np.arange(len(g)) >= first
        dev, val = window & (g <= DEV_END), window & (g > DEV_END)
        combo = ref + OVERLAY * sleeve
        combos[key] = (combo, dev)
        res[key] = {"nom": f"{key} — {tr['name']}", "description": tr["desc"], "debut_mesure": str(g[first]),
                    "reference": {"developpement": period_metrics(ref, None, dev, 252), "validation": period_metrics(ref, None, val, 252)},
                    "poche_seule": {"developpement": period_metrics(sleeve, None, dev, 252), "validation": period_metrics(sleeve, None, val, 252)},
                    "developpement": period_metrics(combo, None, dev, 252), "validation": period_metrics(combo, None, val, 252),
                    "correlation_poche_production": float(np.corrcoef(sleeve[window], ref[window])[0, 1]) if sleeve[window].std() > 0 else 0.0}
    full_dev = (np.arange(len(g)) >= WARMUP) & (g <= DEV_END)
    trial_sharpes = [period_metrics(ref, None, full_dev, 252)["sharpe"]] + [r["developpement"]["sharpe"] for r in res.values()]
    for key, r in res.items():
        combo, dev = combos[key]
        r["dsr_developpement"] = deflated_sharpe(combo[dev], trial_sharpes, 252)
        rf = r["reference"]
        checks = {
            "gain_developpement": r["developpement"]["sharpe"] >= rf["developpement"]["sharpe"] + RULES["dev_gain"],
            "dsr": r["dsr_developpement"] >= RULES["dsr"],
            "validation_non_contredite": r["validation"]["sharpe"] >= rf["validation"]["sharpe"] - RULES["val_tol"],
            "drawdown_validation": r["validation"]["max_dd"] >= rf["validation"]["max_dd"] - RULES["dd_tol"],
        }
        r["criteres"] = {k: bool(v) for k, v in checks.items()}
        r["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"
    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES,
              "duree_s": round(time.time() - t_all), "resultats": res}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\n{'Essai':<56} {'depuis':>10} {'Réf DEV':>7} {'DEV':>5} {'DSR':>5} {'Réf VAL':>7} {'VAL':>5} {'VAL DD':>7} {'Poche VAL':>9} {'corr':>5}  Verdict")
    for k, r in rep["resultats"].items():
        print(f"{r['nom'][:56]:<56} {r['debut_mesure']:>10} {r['reference']['developpement']['sharpe']:>7.2f} {r['developpement']['sharpe']:>5.2f} "
              f"{r['dsr_developpement']:>5.2f} {r['reference']['validation']['sharpe']:>7.2f} {r['validation']['sharpe']:>5.2f} "
              f"{r['validation']['max_dd']:>7.1%} {r['poche_seule']['validation']['sharpe']:>9.2f} {r['correlation_poche_production']:>5.2f}  {r['verdict']}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
