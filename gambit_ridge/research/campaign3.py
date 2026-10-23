"""Campagne de recherche n° 3 (octobre 2026) — équipe Crypto contre la poche crypto de production.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Référence C0 : la poche crypto de production (« Tendance crypto long-only » :
ensemble TSMOM/EWMA/Kalman, positions longues seulement, vol GARCH, vol cible
25 %, brut <= 100 %, 50 % max par ligne) sur ses 7 cryptos.

Même construction de portefeuille pour tous les essais : seul le SIGNAL change.
Les signaux de l'équipe Crypto sont rejoués jour par jour exactement comme en
production (261 dernières clôtures quotidiennes par crypto ; position =
direction x conviction), recalculés tous les 5 jours. Ce sont les signaux des
agents AVANT le filtre du manager (qui n'en transmet que 4), comme en campagne 2.

  C1 Équipe Crypto telle quelle (long et short), univers de l'équipe (8 cryptos)
  C2 Équipe Crypto long seulement (shorts ramenés à 0 : Alpaca n'autorise pas
     la vente à découvert crypto), univers de l'équipe
  C3 Équipe Crypto long seulement, univers de PRODUCTION (isole l'effet signal)
  C4 Moyenne 50/50 des signaux production et équipe (long seulement),
     univers de production

Périodes : développement jusqu'au 2022-12-31, validation 2023 -> aujourd'hui
(comme le banc crypto). Coûts 20 bps. 365 jours/an. Cryptos cotées plus tard
(SOL, AVAX) : poids nul tant qu'elles n'ont pas 64 clôtures (règle des agents).

Règle d'acceptation (identique aux campagnes 1 et 2, mesurée contre C0 sur les
mêmes jours) : Sharpe dév. >= C0 + 0,05 ; DSR (5 séries) >= 0,90 ; Sharpe
validation >= C0 - 0,05 ; pire baisse validation pas plus de 3 points au-delà
de C0. Un essai accepté n'entre au portefeuille qu'avec l'accord de Tom.

Usage : python3 -m gambit_ridge.research.campaign3
Sortie : data/research_campaign3_2026-10.json
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
from .campaign import RULES
from .campaign2 import _panel, _team_signals
from .evaluate import CRYPTO_COST_BPS, CRYPTO_DEV_END, WARMUP
from .portfolio import build_weights, ewma_covariance

OUT = Path(__file__).resolve().parent.parent.parent / "data" / "research_campaign3_2026-10.json"
PPY = 365


def _fill(P: np.ndarray) -> np.ndarray:
    """Avant la première cotation : premier prix connu (seulement pour vol/cov ; poids imposés nuls)."""
    Pf = P.copy()
    for j in range(P.shape[1]):
        ok = np.isfinite(Pf[:, j])
        Pf[~ok, j] = Pf[ok, j][0]
    return Pf


def _sleeve(P: np.ndarray, S: np.ndarray) -> np.ndarray:
    """Construction de la poche crypto de production appliquée au signal S."""
    Pf = _fill(P)
    listed = np.isfinite(P)
    W = build_weights(np.where(listed, S, 0.0), sg.garch_vol(Pf), ewma_covariance(Pf),
                      port_vol=0.25, max_gross=1.0, max_position=0.5)
    return np.where(listed, W, 0.0)


def _prod_signal(P: np.ndarray) -> np.ndarray:
    Pf = _fill(P)
    s = (sg.tsmom(Pf, 252) + sg.ewma_trend(Pf) + sg.kalman_trend(Pf)) / 3.0
    return np.where(np.isfinite(P), np.clip(s, 0.0, None), 0.0)


def run() -> dict:
    from ..data.real_market import YAHOO_MAP
    from ..data.yahoo import CRYPTO_UNIVERSE
    from ..teams.crypto import build_crypto_team

    t0 = time.time()
    team = build_crypto_team()
    team_tk = sorted({tk for a in team.agents for tk in a.universe()})          # BTC, ETH, SOL...
    prod_tk = list(CRYPTO_UNIVERSE)                                             # BTC-USD, ETH-USD...
    to_internal = {v: k for k, v in YAHOO_MAP.items()}
    syms = {tk: tk for tk in prod_tk} | {YAHOO_MAP.get(tk, tk): YAHOO_MAP.get(tk, tk) for tk in team_tk}
    dates, P_all = _panel(syms)
    cols = list(syms)
    # grille : à partir de la date où toutes les cryptos de production sont cotées (comme le banc)
    start = max(int(np.argmax(np.isfinite(P_all[:, cols.index(t)]))) for t in prod_tk)
    dates, P_all = dates[start:], P_all[start:]
    Pp = P_all[:, [cols.index(t) for t in prod_tk]]
    Pt = P_all[:, [cols.index(YAHOO_MAP.get(t, t)) for t in team_tk]]
    print(f"grille : {dates[0]} -> {dates[-1]} ; production {prod_tk} ; équipe {team_tk}", file=sys.stderr)

    S_prod = _prod_signal(Pp)
    S_team = _team_signals(team, dates, Pt, team_tk, None, True)
    # équipe rejouée sur l'univers de production : un agent générique par crypto, mêmes réglages
    from ..core.agent import QuantAgent
    from ..core.manager import Manager

    a0 = team.agents[0]  # mêmes réglages que les agents de l'équipe
    prod_internal = [to_internal.get(t, t) for t in prod_tk]
    team_on_prod = Manager("Crypto (univers production)", [
        QuantAgent(f"crypto-{t.lower()}", t, [t], mom_lookback=a0.mom_lookback, mr_lookback=a0.mr_lookback,
                   mom_weight=a0.mom_weight, mr_weight=a0.mr_weight) for t in prod_internal])
    S_team_p = _team_signals(team_on_prod, dates, Pp, prod_internal, None, True)

    series = {
        "C0": ("Référence — poche crypto de production", Pp, S_prod, "Ensemble tendance long-only, 7 cryptos."),
        "C1": ("Équipe Crypto telle quelle (long/short, 8 cryptos)", Pt, S_team, "Signaux des agents, univers de l'équipe."),
        "C2": ("Équipe Crypto long seulement (8 cryptos)", Pt, np.clip(S_team, 0.0, None), "Shorts ramenés à 0."),
        "C3": ("Équipe Crypto long seulement, univers de production", Pp, np.clip(S_team_p, 0.0, None), "Isole l'effet du signal."),
        "C4": ("Mix 50/50 production + équipe (univers de production)", Pp, 0.5 * S_prod + 0.5 * np.clip(S_team_p, 0.0, None),
               "Moyenne des deux signaux, long seulement."),
    }
    d = np.array(dates)
    rets = {}
    for key, (_, P, S, _) in series.items():
        W = _sleeve(P, S)
        rets[key] = simulate(_fill(P), W, CRYPTO_COST_BPS, rebalance_every=5)
    dev = (np.arange(len(d)) >= WARMUP) & (d <= CRYPTO_DEV_END)
    val = d > CRYPTO_DEV_END
    res = {}
    for key, (name, _, _, desc) in series.items():
        sim = rets[key]
        res[key] = {"nom": f"{key} — {name}", "description": desc,
                    "developpement": period_metrics(sim.returns, sim, dev, PPY),
                    "validation": period_metrics(sim.returns, sim, val, PPY),
                    "correlation_avec_C0": float(np.corrcoef(sim.returns[dev | val], rets["C0"].returns[dev | val])[0, 1])}
    sharpes = [r["developpement"]["sharpe"] for r in res.values()]
    ref = res["C0"]
    for key, r in res.items():
        r["dsr_developpement"] = deflated_sharpe(rets[key].returns[dev], sharpes, PPY)
        if key == "C0":
            continue
        checks = {
            "gain_developpement": r["developpement"]["sharpe"] >= ref["developpement"]["sharpe"] + RULES["dev_gain"],
            "dsr": r["dsr_developpement"] >= RULES["dsr"],
            "validation_non_contredite": r["validation"]["sharpe"] >= ref["validation"]["sharpe"] - RULES["val_tol"],
            "drawdown_validation": r["validation"]["max_dd"] >= ref["validation"]["max_dd"] - RULES["dd_tol"],
        }
        r["criteres"] = {k: bool(v) for k, v in checks.items()}
        r["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"
    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES,
              "debut_mesure": str(d[WARMUP]), "fin": str(d[-1]), "duree_s": round(time.time() - t0), "resultats": res}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\nMesure : {rep['debut_mesure']} -> {rep['fin']} (développement jusqu'au {CRYPTO_DEV_END})")
    print(f"{'Essai':<62} {'DEV Sh':>6} {'DEV DD':>7} {'DSR':>5} {'VAL Sh':>6} {'VAL CAGR':>8} {'VAL DD':>7} {'TO/an':>6} {'corr':>5}  Verdict")
    for k, r in rep["resultats"].items():
        dv, va = r["developpement"], r["validation"]
        print(f"{r['nom'][:62]:<62} {dv['sharpe']:>6.2f} {dv['max_dd']:>7.1%} {r['dsr_developpement']:>5.2f} {va['sharpe']:>6.2f} "
              f"{va['cagr']:>8.1%} {va['max_dd']:>7.1%} {va.get('turnover_annuel', 0):>6.1f} {r['correlation_avec_C0']:>5.2f}  {r.get('verdict', 'référence')}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
