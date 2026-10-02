"""Attribution de performance et rapport mensuel du fonds (paper v2).

Attribution : chaque séance du journal stocke le P&L par ligne (coûts de
transaction imputés à la ligne tradée). On agrège par actif, classe d'actifs
et poche. Pour SPY et IEF, le P&L est réparti entre le socle 60/40 et la
couche tendance au prorata des poids détenus (approximation documentée).
"""

from __future__ import annotations

import html
from datetime import date

from .data.yahoo import CRYPTO_UNIVERSE, ETF_UNIVERSE, asset_class_of


def _names() -> dict[str, str]:
    return {s: n for m in ETF_UNIVERSE.values() for s, n in m.items()} | CRYPTO_UNIVERSE


def _core_weights() -> dict[str, float]:
    from .research.production import CORE_SHARE, CORE_WEIGHTS, ETF_SHARE

    return {tk: ETF_SHARE * CORE_SHARE * w for tk, w in CORE_WEIGHTS.items()}


def attribution(start: str | None = None, end: str | None = None) -> dict:
    from .paper import _load_journal

    j = _load_journal()
    core = _core_weights()
    hist = [e for e in j.get("equity_history", []) if (not start or e["date"] >= start) and (not end or e["date"] <= end)]
    by_ticker: dict[str, float] = {}
    by_sleeve = {"Socle 60/40": 0.0, "Couche tendance": 0.0, "Crypto": 0.0}
    costs = 0.0
    for e in hist:
        costs += e.get("costs", 0.0)
        if "attrib" not in e:  # séances enregistrées avant le détail par ligne
            by_sleeve["Non détaillé"] = by_sleeve.get("Non détaillé", 0.0) + e["day_pnl"]
            continue
        wts = e.get("weights", {})
        for tk, pnl in (e.get("attrib") or {}).items():
            by_ticker[tk] = by_ticker.get(tk, 0.0) + pnl
            if tk.endswith("-USD"):
                by_sleeve["Crypto"] += pnl
                continue
            w = wts.get(tk, 0.0)
            cw = core.get(tk, 0.0)
            share = min(1.0, cw / w) if cw > 0 and w > 0 else 0.0
            by_sleeve["Socle 60/40"] += pnl * share
            by_sleeve["Couche tendance"] += pnl * (1.0 - share)
    by_class: dict[str, float] = {}
    for tk, v in by_ticker.items():
        c = asset_class_of(tk)
        by_class[c] = by_class.get(c, 0.0) + v
    names = _names()
    start_eq = (hist[0]["equity"] - hist[0]["day_pnl"]) if hist else j.get("initial_capital", 1e6)
    total = sum(e["day_pnl"] for e in hist)
    return {
        "start": hist[0]["date"] if hist else None, "end": hist[-1]["date"] if hist else None,
        "n_sessions": len(hist), "start_equity": start_eq, "pnl": total,
        "return": total / start_eq if start_eq else 0.0, "costs": costs,
        "by_sleeve": by_sleeve, "by_class": by_class,
        "by_ticker": sorted([{"ticker": t, "name": names.get(t, t), "asset_class": asset_class_of(t), "pnl": v} for t, v in by_ticker.items()], key=lambda x: -x["pnl"]),
        "has_detail": any("attrib" in e for e in hist),
    }


def _svg_curve(points: list[tuple[str, float]], w: int = 700, h: int = 180) -> str:
    if len(points) < 2:
        return "<p class='muted'>Courbe disponible à partir de deux séances.</p>"
    ys = [p[1] for p in points]
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * 0.1 or 1.0
    lo, hi = lo - pad, hi + pad
    xy = " ".join(f"{10 + i * (w - 20) / (len(ys) - 1):.1f},{h - 20 - (y - lo) / (hi - lo) * (h - 40):.1f}" for i, y in enumerate(ys))
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}'><polyline points='{xy}' fill='none' stroke='#c25e00' stroke-width='2'/>"
            f"<text x='10' y='14' font-size='11' fill='#666'>{hi:,.0f} $</text><text x='10' y='{h - 6}' font-size='11' fill='#666'>{points[0][0]} → {points[-1][0]}</text></svg>")


def monthly_report_html(month: str | None = None) -> str:
    """Rapport mensuel imprimable (HTML autonome, thème clair, prêt pour « Enregistrer en PDF »)."""
    from .paper import _load_journal, summary

    j = _load_journal()
    s = summary(j)
    hist = j.get("equity_history", [])
    month = month or (hist[-1]["date"][:7] if hist else date.today().isoformat()[:7])
    mh = [e for e in hist if e["date"][:7] == month]
    a = attribution(f"{month}-01", f"{month}-31")
    since = attribution()
    e = html.escape
    pct = lambda x: f"{x * 100:+.2f} %"
    usd = lambda x: f"{x:+,.0f} $".replace(",", " ")
    peak, mdd = 0.0, 0.0
    for x in mh:
        peak = max(peak, x["equity"])
        mdd = max(mdd, 1 - x["equity"] / peak)
    rows_t = "".join(f"<tr><td>{e(r['ticker'])}</td><td>{e(r['name'])}</td><td>{e(r['asset_class'])}</td><td class='n {'p' if r['pnl'] >= 0 else 'm'}'>{usd(r['pnl'])}</td></tr>" for r in a["by_ticker"][:8] + (a["by_ticker"][-5:] if len(a["by_ticker"]) > 8 else []))
    rows_c = "".join(f"<tr><td>{e(k)}</td><td class='n {'p' if v >= 0 else 'm'}'>{usd(v)}</td></tr>" for k, v in sorted(a["by_class"].items(), key=lambda kv: -kv[1]))
    rows_s = "".join(f"<tr><td>{e(k)}</td><td class='n {'p' if v >= 0 else 'm'}'>{usd(v)}</td></tr>" for k, v in a["by_sleeve"].items())
    pos = "".join(f"<tr><td>{e(p['ticker'])}</td><td>{e(p['name'])}</td><td class='n'>{p['weight'] * 100:+.1f} %</td></tr>" for p in s["positions"][:12])
    risk_html = ""
    try:
        from .risk_report import risk_report

        r = risk_report()
        risk_html = (f"<p>Volatilité prévue : <b>{r['vol_ex_ante']:.1%}</b> · VaR 99 % 1 jour : <b>{r['var']['var99']:.2%}</b> · "
                     f"pire scénario rejoué : <b>{min(r['scenarios'], key=lambda x: x['pnl'])['name']}</b> ({min(x['pnl'] for x in r['scenarios']):+.1%}).</p>")
    except Exception:
        pass
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Gambit Ridge Capital — rapport {e(month)}</title>
<style>
body{{font-family:-apple-system,Helvetica,Arial,sans-serif;color:#111;max-width:820px;margin:30px auto;padding:0 20px;font-size:13px}}
h1{{font-size:22px;margin:0}} h2{{font-size:14px;text-transform:uppercase;letter-spacing:1px;color:#c25e00;border-bottom:2px solid #c25e00;padding-bottom:3px;margin-top:26px}}
.sub{{color:#666;margin:4px 0 18px}} .k{{display:flex;gap:10px;flex-wrap:wrap}} .k div{{flex:1;min-width:130px;border:1px solid #ddd;padding:8px 10px}}
.k b{{display:block;font-size:18px;margin-top:2px}} table{{width:100%;border-collapse:collapse}} td,th{{padding:4px 6px;border-bottom:1px solid #eee;text-align:left}}
.n{{text-align:right;font-variant-numeric:tabular-nums}} .p{{color:#0a7a30}} .m{{color:#b00020}} .muted,.foot{{color:#777}} .foot{{font-size:11px;margin-top:30px}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px}} @media print{{.noprint{{display:none}} body{{margin:0}}}}
.btn{{background:#c25e00;color:#fff;border:none;padding:7px 14px;font-weight:600;cursor:pointer}}
</style></head><body>
<p class="noprint"><button class="btn" onclick="window.print()">Imprimer / Enregistrer en PDF</button></p>
<h1>Gambit Ridge Capital — rapport mensuel</h1>
<p class="sub">{e(month)} · {e(s['strategy'])} · portefeuille papier (aucun capital réel)</p>
<div class="k"><div>Performance du mois<b class="{'p' if a['return'] >= 0 else 'm'}">{pct(a['return'])}</b></div>
<div>Depuis le lancement ({e(s.get('started') or '—')})<b class="{'p' if s['total_return'] >= 0 else 'm'}">{pct(s['total_return'])}</b></div>
<div>Équity<b>{s['equity'] / 1e6:.3f} M$</b></div><div>Drawdown max du mois<b>{mdd:.2%}</b></div>
<div>Coûts de transaction (mois)<b>{a['costs']:,.0f} $</b></div></div>
<h2>Évolution</h2>{_svg_curve([(x['date'], x['equity']) for x in mh])}
<h2>D'où vient la performance</h2><div class="cols"><table><tr><th>Poche</th><th class="n">P&amp;L</th></tr>{rows_s}</table>
<table><tr><th>Classe d'actifs</th><th class="n">P&amp;L</th></tr>{rows_c}</table></div>
<h3>Principaux contributeurs</h3><table><tr><th>Actif</th><th></th><th>Classe</th><th class="n">P&amp;L du mois</th></tr>{rows_t}</table>
<h2>Positions en fin de période</h2><table><tr><th>Actif</th><th></th><th class="n">Poids</th></tr>{pos}</table>
<p class="muted">Exposition brute {s['gross']:.0%} · nette {s['net']:.0%} · {len(s['positions'])} lignes.</p>
<h2>Risque</h2>{risk_html or "<p class='muted'>Indisponible.</p>"}
<p class="foot">Depuis le lancement : {since['n_sessions']} séances, P&amp;L {usd(since['pnl'])}, coûts {since['costs']:,.0f} $.
Paper trading : prix de clôture réels (Yahoo), exécution simulée à la clôture, coûts 5 bps ETF / 20 bps crypto. Les performances passées, réelles
ou simulées, ne préjugent pas des performances futures. Document interne, non destiné à la commercialisation.</p>
</body></html>"""
