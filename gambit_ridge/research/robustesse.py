"""Robustesse de la stratégie de production — trois diagnostics, sans rien choisir.

1. RÉFÉRENCE ALÉATOIRE (test de « singe », façon QuantLab / Monte-Carlo de stratégies) :
   des milliers de stratégies identiques à la production — même socle 60/40, mêmes univers,
   dimensionnement par le risque, vol cible, filtre anti micro-trades, rebalancement et coûts —
   dont seule la DIRECTION de la couche tendance est tirée au hasard : signe aléatoire par actif,
   qui change avec la même fréquence moyenne que le vrai signal, multiplié par l'intensité du
   vrai signal (même exposition, même rotation). Question : le timing de la tendance vaut-il
   mieux que le hasard ? Réponse : percentile du fonds dans la distribution, et p-valeur.

2. PROBABILITÉ DE SURAPPRENTISSAGE (PBO, Bailey, Borwein, López de Prado & Zhu, 2015) par
   validation croisée combinatoire symétrique (CSCV) : une grille de variantes de la famille de
   production (signal, part du socle, vol cible, fréquence de rebalancement), 16 blocs de temps,
   toutes les combinaisons 8 / 8 ; pour chaque coupe, la meilleure variante « en échantillon »
   est-elle sous la médiane « hors échantillon » ? PBO = fréquence de ce cas.

3. STATISTIQUES DE TRADING : jours, semaines, mois (taux de gain, profit factor, espérance,
   pires séries, asymétrie) et « trades » de la couche tendance (une position = un actif tenu
   dans le même sens), avant et après coûts.

Diagnostic : la production n'est pas modifiée ; la grille de la PBO couvre 2008-2026 mais ne
sert à choisir aucune variante.

Usage : python3 -m gambit_ridge.research.robustesse    Sortie : data/research_robustesse_2026-10.json
"""

from __future__ import annotations

import itertools
import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from . import signals as sg
from .campaign import CORE
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP
from .portfolio import ewma_covariance

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_robustesse_2026-10.json"
N_ALEATOIRES = 2000
LOT = 50
GRAINE = 2026
JOURS_AN = 252


# ---------------------------------------------------------------- simulation par lots (S stratégies à la fois)


def lot_poids(sig, vol, cov, port_vol=0.10, max_position=0.40, max_gross=2.0):
    """Équivalent vectorisé de portfolio.build_weights pour S signaux : (S, T, N) -> (S, T, N)."""
    S, T, N = sig.shape
    pv = np.broadcast_to(np.asarray(port_vol, dtype=float), (S,))[:, None, None]
    raw = sig * (pv / math.sqrt(N)) / vol[None]
    ex = np.sqrt(np.maximum(np.einsum("stn,tnm,stm->st", raw, cov, raw), 1e-16))
    w = raw * (pv[:, :, 0] / ex)[:, :, None]
    w = np.where(np.any(raw != 0, axis=2, keepdims=True), w, 0.0)
    w = np.clip(w, -max_position, max_position)
    g = np.abs(w).sum(axis=2, keepdims=True)
    return np.where(g > max_gross, w * (max_gross / np.where(g > 0, g, 1.0)), w)


def lot_filtre(W, rel=0.25, abs_min=0.005, every=5):
    """Équivalent vectorisé de evaluate.apply_buffer."""
    S, T, N = W.shape
    out = np.zeros_like(W)
    cur = np.zeros((S, N))
    every = np.broadcast_to(np.asarray(every), (S,))[:, None]
    for t in range(T):
        tgt = W[:, t]
        move = (np.abs(tgt - cur) > np.maximum(rel * np.abs(tgt), abs_min)) & (t % every == 0)
        cur = np.where(move, tgt, cur)
        out[:, t] = cur
    return out


def lot_simuler(P, W, cost_bps, every=5):
    """Équivalent vectorisé de backtest.simulate (dérive des poids, coûts sur le turnover exécuté).
    Renvoie rendements nets (S, T), coûts (S, T) et poids détenus (S, T, N)."""
    S, T, N = W.shape
    R = np.zeros((T, N))
    R[1:] = P[1:] / P[:-1] - 1.0
    cost = np.broadcast_to(np.asarray(cost_bps, dtype=float) / 1e4, (N,))
    every = np.broadcast_to(np.asarray(every), (S,))
    held = np.zeros((S, N))
    ret, couts = np.zeros((S, T)), np.zeros((S, T))
    detenus = np.zeros((S, T, N))
    for t in range(T):
        if t > 0:
            g = held @ R[t]
            ret[:, t] = g
            denom = 1.0 + g
            held = np.where((denom > 1e-9)[:, None], held * (1.0 + R[t]) / np.where(denom > 1e-9, denom, 1.0)[:, None], 0.0)
        reb = (t % every == 0)[:, None]
        trade = np.where(reb, W[:, t] - held, 0.0)
        c = np.abs(trade) @ cost
        couts[:, t] = c
        ret[:, t] -= c
        held = np.where(reb, W[:, t], held)
        detenus[:, t] = held
    return ret, couts, detenus


def production_lot(P, tk, sig, vol, cov, core_share=0.5, port_vol=0.10, every=5, rel=0.25, abs_min=0.005):
    """Pipeline de production (core_plus_overlay -> apply_buffer -> simulate) pour S signaux."""
    S, T, N = sig.shape
    core = np.zeros((T, N))
    for k, w in CORE.items():
        core[:, tk.index(k)] = w
    cs = np.broadcast_to(np.asarray(core_share, dtype=float), (S,))[:, None, None]
    W = cs * core[None] + (1.0 - cs) * lot_poids(sig, vol, cov, port_vol)
    W = lot_filtre(W, rel, abs_min, every)
    return lot_simuler(P, W, ETF_COST_BPS, every)


# ---------------------------------------------------------------- métriques


def sharpe(r, axis=-1):
    sd = r.std(axis=axis, ddof=1)
    return np.where(sd > 0, r.mean(axis=axis) / np.where(sd > 0, sd, 1.0) * math.sqrt(JOURS_AN), 0.0)


def max_dd(r):
    eq = np.cumprod(1.0 + r, axis=-1)
    return (eq / np.maximum.accumulate(eq, axis=-1) - 1.0).min(axis=-1)


def cagr(r):
    n = r.shape[-1]
    return np.prod(1.0 + r, axis=-1) ** (JOURS_AN / n) - 1.0


def _vrai_signal(P):
    from .campaign import _trend_parts

    return _trend_parts(P)


def signaux_aleatoires(sig, n, rng):
    """Signes aléatoires par actif, de même durée moyenne de tenue que le vrai signe, × |vrai signal|."""
    T, N = sig.shape
    s = np.sign(sig)
    p = np.empty(N)
    for j in range(N):
        a = s[:, j][s[:, j] != 0]
        changements = np.count_nonzero(np.diff(a)) if len(a) > 1 else 0
        p[j] = max(changements, 1) / max(len(a), 1)  # probabilité de retournement par jour
    flips = rng.random((n, T, N)) < p[None, None, :]
    signe = np.where(rng.random((n, 1, N)) < 0.5, -1.0, 1.0) * np.cumprod(np.where(flips, -1.0, 1.0), axis=1)
    return signe * np.abs(sig)[None], p


# ---------------------------------------------------------------- 1. référence aléatoire


def reference_aleatoire(P, tk, dates, vol, cov, sig, n=N_ALEATOIRES):
    d = np.array(dates)
    masques = {"developpement": (np.arange(len(d)) >= WARMUP) & (d <= DEV_END), "validation": d > DEV_END,
               "complet": np.arange(len(d)) >= WARMUP}
    fonds, _, _ = production_lot(P, tk, sig[None], vol, cov)
    fonds = fonds[0]
    socle, _, _ = production_lot(P, tk, np.zeros_like(sig)[None], vol, cov)  # socle 60/40 seul (couche à zéro)
    socle = socle[0]
    rng = np.random.default_rng(GRAINE)
    sh = {k: [] for k in masques}
    autres = {"cagr": [], "max_dd": []}
    p_flip = None
    for i in range(0, n, LOT):
        alea, p_flip = signaux_aleatoires(sig, min(LOT, n - i), rng)
        ret, _, _ = production_lot(P, tk, alea, vol, cov)
        for k, m in masques.items():
            sh[k].extend(sharpe(ret[:, m]).tolist())
        autres["cagr"].extend(cagr(ret[:, masques["complet"]]).tolist())
        autres["max_dd"].extend(max_dd(ret[:, masques["complet"]]).tolist())
        print(f"  aléatoires : {min(i + LOT, n)}/{n}", file=sys.stderr)
    out = {"n": n, "graine": GRAINE, "duree_moyenne_tenue_jours": {t: float(1 / p) for t, p in zip(tk, p_flip)}, "periodes": {}}
    for k, m in masques.items():
        a = np.array(sh[k])
        f = float(sharpe(fonds[m]))
        hist, bords = np.histogram(a, bins=50)
        out["periodes"][k] = {"debut": dates[int(np.argmax(m))], "fin": dates[len(m) - 1 - int(np.argmax(m[::-1]))],
                              "sharpe_fonds": f, "sharpe_socle_seul": float(sharpe(socle[m])),
                              "percentile": float((a < f).mean()), "p_valeur": float((1 + (a >= f).sum()) / (len(a) + 1)),
                              "quantiles": {q: float(np.quantile(a, q / 100)) for q in (1, 5, 25, 50, 75, 95, 99)},
                              "histogramme": {"bords": bords.round(4).tolist(), "comptes": hist.tolist()}}
    c = masques["complet"]
    out["fonds_complet"] = {"cagr": float(cagr(fonds[c])), "max_dd": float(max_dd(fonds[c]))}
    out["aleatoires_complet"] = {"cagr_mediane": float(np.median(autres["cagr"])), "max_dd_median": float(np.median(autres["max_dd"])),
                                 "part_meilleur_cagr": float((np.array(autres["cagr"]) >= out["fonds_complet"]["cagr"]).mean())}
    return out, fonds


# ---------------------------------------------------------------- 2. PBO par CSCV


def grille_variantes(P):
    """Famille de production : 4 signaux × 3 parts de socle × 3 vols cibles × 3 rebalancements = 108 variantes."""
    parts = {"tsmom": sg.tsmom(P, 252), "ewma": sg.ewma_trend(P), "kalman": sg.kalman_trend(P)}
    parts["ensemble"] = (parts["tsmom"] + parts["ewma"] + parts["kalman"]) / 3
    v = []
    for nom_sig, cs, pv, ev in itertools.product(["ensemble", "tsmom", "ewma", "kalman"], [0.3, 0.5, 0.7], [0.08, 0.10, 0.12], [1, 5, 21]):
        v.append({"signal": nom_sig, "socle": cs, "vol_cible": pv, "rebalancement": ev})
    return parts, v


def cscv(R, S=16):
    """PBO (CSCV). R : (T, M) rendements. Renvoie PBO, logits, et Sharpe IS du meilleur / OOS correspondant."""
    T, M = R.shape
    blocs = np.array_split(np.arange(T), S)
    som = np.array([R[b].sum(axis=0) for b in blocs])          # (S, M)
    som2 = np.array([(R[b] ** 2).sum(axis=0) for b in blocs])
    nb = np.array([len(b) for b in blocs], dtype=float)
    logits, is_best, oos_best = [], [], []
    for combo in itertools.combinations(range(S), S // 2):
        m = np.zeros(S, dtype=bool)
        m[list(combo)] = True

        def sh(mask):
            n = nb[mask].sum()
            mu = som[mask].sum(axis=0) / n
            var = som2[mask].sum(axis=0) / n - mu**2
            return mu / np.sqrt(np.maximum(var, 1e-18)) * math.sqrt(JOURS_AN)

        si, so = sh(m), sh(~m)
        best = int(np.argmax(si))
        rang = (so < so[best]).sum() + 0.5 * ((so == so[best]).sum() - 1)  # rang relatif OOS (0 = pire)
        w = (rang + 1) / (M + 1)
        logits.append(math.log(w / (1 - w)))
        is_best.append(float(si[best]))
        oos_best.append(float(so[best]))
    logits = np.array(logits)
    pente = float(np.polyfit(is_best, oos_best, 1)[0])
    return {"pbo": float((logits < 0).mean()), "n_combinaisons": len(logits), "blocs": S,
            "logit_median": float(np.median(logits)), "histogramme_logits": dict(zip(("comptes", "bords"),
                [x.tolist() for x in np.histogram(logits, bins=30)])),
            "pente_degradation": pente, "sharpe_is_meilleur_median": float(np.median(is_best)),
            "sharpe_oos_meilleur_median": float(np.median(oos_best)), "perte_oos_moyenne": float(np.mean(oos_best) - np.mean(is_best)),
            "nuage": {"is": is_best[::40], "oos": oos_best[::40]}}


def pbo(P, tk, dates, vol, cov):
    parts, variantes = grille_variantes(P)
    rets = []
    for i in range(0, len(variantes), 27):
        bloc = variantes[i:i + 27]
        sig = np.stack([parts[v["signal"]] for v in bloc])
        ret, _, _ = production_lot(P, tk, sig, vol, cov, core_share=np.array([v["socle"] for v in bloc]),
                                   port_vol=np.array([v["vol_cible"] for v in bloc]), every=np.array([v["rebalancement"] for v in bloc]))
        rets.append(ret)
        print(f"  variantes : {min(i + 27, len(variantes))}/{len(variantes)}", file=sys.stderr)
    R = np.concatenate(rets)[:, WARMUP:].T  # (T, M)
    res = cscv(R)
    sh_all = sharpe(R.T)
    prod = next(i for i, v in enumerate(variantes) if v == {"signal": "ensemble", "socle": 0.5, "vol_cible": 0.10, "rebalancement": 5})
    ordre = np.argsort(-sh_all)
    res.update({"n_variantes": len(variantes), "periode": [dates[WARMUP], dates[-1]],
                "production": {"rang": int(np.where(ordre == prod)[0][0]) + 1, "sharpe": float(sh_all[prod])},
                "sharpe_variantes": {"min": float(sh_all.min()), "median": float(np.median(sh_all)), "max": float(sh_all.max())},
                "meilleure": {**variantes[int(ordre[0])], "sharpe": float(sh_all[ordre[0]])},
                "variantes": [{**v, "sharpe": round(float(s), 3)} for v, s in zip(variantes, sh_all)]})
    return res


# ---------------------------------------------------------------- 3. statistiques de trading


def stats_rendements(r, dates):
    """Statistiques d'une série de rendements quotidiens nets : jours, semaines, mois."""
    r = np.asarray(r, dtype=float)

    def bloc(x):
        g, p = x[x > 0], x[x < 0]
        serie, pire = 0, 0
        for v in x:
            serie = serie + 1 if v < 0 else 0
            pire = max(pire, serie)
        return {"n": int(len(x)), "taux_gain": float((x > 0).mean()), "profit_factor": float(g.sum() / -p.sum()) if p.size else None,
                "gain_moyen": float(g.mean()) if g.size else None, "perte_moyenne": float(p.mean()) if p.size else None,
                "ratio_gain_perte": float(g.mean() / -p.mean()) if g.size and p.size else None, "esperance": float(x.mean()),
                "meilleur": float(x.max()), "pire": float(x.min()), "pire_serie_pertes": pire}

    mois, sem = {}, {}
    for d, v in zip(dates, r):
        mois.setdefault(d[:7], []).append(v)
        sem.setdefault(date.fromisoformat(d).isocalendar()[:2], []).append(v)
    rm = np.array([np.prod(1 + np.array(v)) - 1 for v in mois.values()])
    rs = np.array([np.prod(1 + np.array(v)) - 1 for v in sem.values()])
    z = (r - r.mean()) / r.std()
    return {"jours": bloc(r), "semaines": bloc(rs), "mois": bloc(rm), "asymetrie": float(np.mean(z**3)), "kurtosis": float(np.mean(z**4) - 3),
            "sharpe": float(sharpe(r)), "cagr": float(cagr(r)), "max_dd": float(max_dd(r)),
            "mois_detail": [{"mois": k, "rendement": float(v)} for k, v in zip(mois.keys(), rm)]}


def trades_tendance(P, tk, dates, detenus, couts):
    """Une « position » de la couche tendance = un actif tenu dans le même sens, du premier au dernier jour.
    P&L = poids tendance de la veille × rendement de l'actif (socle retiré), coûts répartis au prorata du turnover."""
    T, N = P.shape
    R = np.zeros((T, N))
    R[1:] = P[1:] / P[:-1] - 1.0
    core = np.zeros(N)
    for k, w in CORE.items():
        core[tk.index(k)] = 0.5 * w
    tend = detenus - core[None]
    tend[np.abs(tend) < 1e-6] = 0.0
    pnl = np.zeros((T, N))
    pnl[1:] = tend[:-1] * R[1:]
    trades = []
    for j in range(N):
        signe = np.sign(tend[:, j])
        debut = None
        for t in range(WARMUP, T + 1):
            s = signe[t] if t < T else 0.0  # fin des données : on clôt la position ouverte
            if debut is not None and s != signe[debut]:
                trades.append({"actif": tk[j], "sens": "acheteur" if signe[debut] > 0 else "vendeur", "debut": dates[debut],
                               "fin": dates[t - 1], "jours": t - debut, "pnl": float(pnl[debut + 1:t + 1, j].sum())})
                debut = None
            if debut is None and s != 0:
                debut = t
    x = np.array([t["pnl"] for t in trades])
    g, p = x[x > 0], x[x < 0]
    serie, pire = 0, 0
    for t in sorted(trades, key=lambda t: t["fin"]):
        serie = serie + 1 if t["pnl"] < 0 else 0
        pire = max(pire, serie)
    par_actif = {}
    for t in trades:
        a = par_actif.setdefault(t["actif"], {"n": 0, "pnl": 0.0, "gagnants": 0})
        a["n"] += 1
        a["pnl"] += t["pnl"]
        a["gagnants"] += t["pnl"] > 0
    meilleurs = sorted(trades, key=lambda t: -t["pnl"])[:5]
    pires = sorted(trades, key=lambda t: t["pnl"])[:5]
    return {"n": len(trades), "taux_gain": float((x > 0).mean()), "profit_factor": float(g.sum() / -p.sum()) if p.size else None,
            "gain_moyen_pb": float(g.mean() * 1e4) if g.size else None, "perte_moyenne_pb": float(p.mean() * 1e4) if p.size else None,
            "ratio_gain_perte": float(g.mean() / -p.mean()) if g.size and p.size else None, "esperance_pb": float(x.mean() * 1e4),
            "duree_moyenne_jours": float(np.mean([t["jours"] for t in trades])), "pire_serie_pertes": pire,
            "couts_totaux_pb_an": float(couts[WARMUP:].sum() / ((T - WARMUP) / JOURS_AN) * 1e4),
            "par_actif": {k: {**v, "pnl_pb": round(v["pnl"] * 1e4, 1), "taux_gain": v["gagnants"] / v["n"]} for k, v in par_actif.items()},
            "meilleurs": meilleurs, "pires": pires}


# ---------------------------------------------------------------- rapport


def run(n_aleatoires: int = N_ALEATOIRES) -> dict:
    from ..data.yahoo import all_etf_symbols, load_aligned

    t0 = time.time()
    dates, p = load_aligned(all_etf_symbols(), refresh=False)
    tk = list(p)
    P = np.column_stack([p[t] for t in tk])
    print(f"univers : {len(tk)} ETF, {dates[0]} -> {dates[-1]}", file=sys.stderr)
    vol, cov = sg.garch_vol(P), ewma_covariance(P)
    sig = _vrai_signal(P)
    print(f"vol et covariance prêtes ({time.time() - t0:.0f}s)", file=sys.stderr)
    alea, fonds = reference_aleatoire(P, tk, dates, vol, cov, sig, n_aleatoires)
    ret, couts, detenus = production_lot(P, tk, sig[None], vol, cov)
    sans_couts, _, _ = lot_simuler(P, lot_filtre(0.5 * np.broadcast_to(_core(tk, len(P)), P.shape)[None] + 0.5 * lot_poids(sig[None], vol, cov)), 0.0)
    stats = {"etf_2008_2026": stats_rendements(ret[0, WARMUP:], dates[WARMUP:]),
             "etf_avant_couts": {"sharpe": float(sharpe(sans_couts[0, WARMUP:])), "cagr": float(cagr(sans_couts[0, WARMUP:]))},
             "trades_tendance": trades_tendance(P, tk, dates, detenus[0], couts[0])}
    fb = json.loads((ROOT / "data" / "fund_backtest.json").read_text())
    stats["fonds_95_5_2018_2026"] = stats_rendements(np.array(fb["returns"]), fb["dates"])
    print("PBO…", file=sys.stderr)
    res_pbo = pbo(P, tk, dates, vol, cov)
    rapport = {"genere_le": date.today().isoformat(), "protocole": __doc__, "aleatoire": alea, "pbo": res_pbo, "trading": stats,
               "duree_s": round(time.time() - t0)}
    OUT.write_text(json.dumps(rapport, ensure_ascii=False, indent=1))
    return rapport


def _core(tk, T):
    c = np.zeros(len(tk))
    for k, w in CORE.items():
        c[tk.index(k)] = w
    return c


def main() -> int:
    r = run(int(sys.argv[1]) if len(sys.argv) > 1 else N_ALEATOIRES)
    a = r["aleatoire"]["periodes"]
    for k, v in a.items():
        print(f"{k:14s} fonds Sharpe {v['sharpe_fonds']:.2f} · socle seul {v['sharpe_socle_seul']:.2f} · médiane aléatoire {v['quantiles'][50]:.2f} "
              f"· percentile {v['percentile']:.1%} · p = {v['p_valeur']:.4f}")
    b = r["pbo"]
    print(f"PBO {b['pbo']:.1%} sur {b['n_combinaisons']} coupes · {b['n_variantes']} variantes · production {b['production']['rang']}e "
          f"(Sharpe {b['production']['sharpe']:.2f}) · meilleure {b['meilleure']}")
    t = r["trading"]["trades_tendance"]
    print(f"Trades tendance : {t['n']} · taux de gain {t['taux_gain']:.1%} · profit factor {t['profit_factor']:.2f} · pire série {t['pire_serie_pertes']}")
    print(f"({r['duree_s']} s) -> {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
