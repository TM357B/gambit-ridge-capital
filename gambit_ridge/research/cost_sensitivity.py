"""Sensibilité de la stratégie aux coûts de transaction — avec les coûts mesurés en réel.

Ce n'est pas un essai (rien n'est choisi) : la stratégie de production est rejouée telle
quelle avec des coûts croissants, pour savoir si elle survit aux coûts réellement payés.

Mesure sur les ordres exécutés du 5 au 10 octobre 2026 (compte paper Alpaca) :
- crypto : 25,6 bps de frais (289 $ sur 112 772 $ échangés) + environ 22 bps d'écart
  achat-vente par transaction (aller-retour LTC médian : 44,6 bps) => ~48 bps par transaction,
  contre 20 bps supposés dans le banc ;
- ETF : trop peu d'ordres pour mesurer (18) ; hypothèse du banc 5 bps, testée jusqu'à 20.

Usage : python3 -m gambit_ridge.research.cost_sensitivity
Sortie : data/cost_sensitivity.json
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

from .backtest import period_metrics, simulate
from .campaign import _production
from . import signals as sg
from .campaign3 import _fill, _prod_signal
from .portfolio import build_weights, ewma_covariance
from .evaluate import CRYPTO_DEV_END, DEV_END, WARMUP
from .production import CRYPTO_MAX_POSITION, CRYPTO_SHARE, ETF_SHARE

OUT = Path(__file__).resolve().parent.parent.parent / "data" / "cost_sensitivity.json"
MEASURED = {"crypto_frais_bps": 25.6, "crypto_ecart_bps": 22.3, "crypto_total_bps": 48, "periode": "2026-10-05 → 2026-10-10",
            "ordres_crypto": 77, "montant_crypto": 112772, "frais_payes": 289.13}
ETF_COSTS = (0, 5, 10, 20)
CRYPTO_COSTS = (0, 20, 50, 80)


def _row(sim, dev, val, ppy) -> dict:
    d, v = period_metrics(sim.returns, sim, dev, ppy), period_metrics(sim.returns, sim, val, ppy)
    return {"dev_sharpe": d["sharpe"], "val_sharpe": v["sharpe"], "val_cagr": v["cagr"], "val_max_dd": v["max_dd"],
            "couts_annuels": v.get("couts_annuels"), "rotation": v.get("turnover_annuel")}


def run() -> dict:
    from ..data.yahoo import CRYPTO_UNIVERSE, all_etf_symbols, load_aligned

    d, p = load_aligned(all_etf_symbols(), refresh=False)
    tk = list(p)
    P = np.column_stack([p[t] for t in tk])
    W = _production(P, tk)
    da = np.array(d)
    dev, val = (np.arange(len(da)) >= WARMUP) & (da <= DEV_END), da > DEV_END
    etf = {str(c): _row(simulate(P, W, float(c), rebalance_every=5), dev, val, 252) for c in ETF_COSTS}
    etf_sims = {c: simulate(P, W, float(c), rebalance_every=5).returns for c in ETF_COSTS}

    cd, cp = load_aligned(list(CRYPTO_UNIVERSE), refresh=False)
    ctk = list(cp)
    CP = np.column_stack([cp[t] for t in ctk])
    # poche crypto telle qu'en production (plafond par crypto compris)
    CW = build_weights(_prod_signal(CP), sg.garch_vol(_fill(CP)), ewma_covariance(_fill(CP)), port_vol=0.25, max_gross=1.0, max_position=CRYPTO_MAX_POSITION)
    cda = np.array(cd)
    cdev, cval = (np.arange(len(cda)) >= WARMUP) & (cda <= CRYPTO_DEV_END), cda > CRYPTO_DEV_END
    crypto = {str(c): _row(simulate(_fill(CP), CW, float(c), rebalance_every=5), cdev, cval, 365) for c in CRYPTO_COSTS}
    crypto_sims = {c: simulate(_fill(CP), CW, float(c), rebalance_every=5).returns for c in CRYPTO_COSTS}

    # fonds complet (répartition de production) sur la période commune (validation ETF) : banc (5 / 20 bps) contre réel (5 / 50 bps)
    idx = np.searchsorted(cda, da, side="right") - 1

    def fund(e_cost, c_cost):
        ceq = np.cumprod(1.0 + crypto_sims[c_cost])
        on = np.where(idx >= 0, ceq[np.clip(idx, 0, None)], np.nan)
        cr = np.zeros(len(da))
        cr[1:] = np.nan_to_num(on[1:] / on[:-1] - 1.0)
        r = ETF_SHARE * etf_sims[e_cost] + CRYPTO_SHARE * cr
        mask = val & (da >= cd[WARMUP])
        m = period_metrics(r, None, mask, 252)
        return {"sharpe": m["sharpe"], "cagr": m["cagr"], "max_dd": m["max_dd"]}

    fonds = {"banc (ETF 5 bps, crypto 20 bps)": fund(5, 20), "coûts réels (ETF 5 bps, crypto 50 bps)": fund(5, 50),
             "prudent (ETF 10 bps, crypto 80 bps)": fund(10, 80)}
    report = {"genere_le": date.today().isoformat(), "mesure": MEASURED, "etf": etf, "crypto": crypto, "fonds": fonds,
              "repartition": {"etf": ETF_SHARE, "crypto": CRYPTO_SHARE},
              "periodes": {"etf_validation": f"{DEV_END} → {d[-1]}", "crypto_validation": f"{CRYPTO_DEV_END} → {cd[-1]}"}}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    r = run()
    for name, tab in (("ETF", r["etf"]), ("CRYPTO", r["crypto"])):
        print(f"\n{name:<8} {'coût':>6} {'Sharpe dév':>10} {'Sharpe val':>10} {'CAGR val':>9} {'coûts/an':>9}")
        for c, x in tab.items():
            print(f"{'':<8} {c + ' bps':>6} {x['dev_sharpe']:>10.2f} {x['val_sharpe']:>10.2f} {x['val_cagr']:>9.1%} {(x['couts_annuels'] or 0):>9.2%}")
    print(f"\nFONDS {ETF_SHARE:.0%} / {CRYPTO_SHARE:.0%} (validation)")
    for n, x in r["fonds"].items():
        print(f"  {n:<42} Sharpe {x['sharpe']:.2f}  CAGR {x['cagr']:.1%}  pire baisse {x['max_dd']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
