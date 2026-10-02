"""Note de recherche hebdomadaire du fonds, rédigée par les desks (IA + données réelles).

Rassemble les faits de la semaine : marchés (rendements 1 semaine par classe),
le fonds (performance, attribution, trades), la macro US (ECST), le risque
(vol prévue, VaR, scénario le plus défavorable, santé de la stratégie), la
vue des desks d'agents et les gros titres. Mistral rédige à partir de CES
données uniquement ; sans clé ou hors ligne, une note factuelle est produite.

Stockage : data_cache/notes/<AAAA-Www>.json — onglet « Notes » du terminal.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "data_cache" / "notes"


def week_id(d: date | None = None) -> str:
    y, w, _ = (d or date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def _market_week() -> list[dict]:
    from .data.yahoo import CRYPTO_UNIVERSE, ETF_UNIVERSE, YahooConnector, asset_class_of, complete_cutoff

    names = {s: n for m in ETF_UNIVERSE.values() for s, n in m.items()} | CRYPTO_UNIVERSE
    conn, rows = YahooConnector(), []
    for sym in names:
        try:
            d = conn.fetch(sym, refresh=False)
        except Exception:
            continue
        ds = sorted(x for x in d if x <= complete_cutoff(sym))
        n = 7 if sym.endswith("-USD") else 5
        if len(ds) > n:
            rows.append({"actif": sym, "nom": names[sym], "classe": asset_class_of(sym), "rendement_1_semaine_pct": round((d[ds[-1]] / d[ds[-1 - n]] - 1) * 100, 1)})
    return sorted(rows, key=lambda r: r["rendement_1_semaine_pct"])


def gather(start: str, end: str) -> dict:
    from .paper import _load_journal, summary
    from .reporting import attribution

    j = _load_journal()
    s = summary(j)
    hist = [e for e in j.get("equity_history", []) if start <= e["date"] <= end]
    data: dict = {"periode": {"debut": start, "fin": end}}
    if hist:
        e0 = hist[0]["equity"] - hist[0]["day_pnl"]
        data["fonds"] = {"strategie": s["strategy"],
                         "rendement_semaine_pct": round((hist[-1]["equity"] / e0 - 1) * 100, 2),
                         "rendement_depuis_lancement_pct": round(s["total_return"] * 100, 2),
                         "drawdown_actuel_pct": round(s["current_drawdown"] * 100, 2),
                         "poids_net_par_classe_pct_du_capital": {k: round(v * 100, 1) for k, v in s["exposure_by_class"].items()},
                         "nombre_de_seances": len(hist)}
        a = attribution(start, end)
        data["gains_et_pertes_de_la_semaine_en_dollars"] = {
            "par_poche": {k: round(v) for k, v in a["by_sleeve"].items() if k != "Non détaillé" and round(v)},
            "meilleures_contributions": [{"actif": x["ticker"], "gain_usd": round(x["pnl"])} for x in a["by_ticker"][:3]],
            "pires_contributions": [{"actif": x["ticker"], "gain_usd": round(x["pnl"])} for x in a["by_ticker"][-3:]]}
    data["trades_semaine_poids_avant_apres_pct_du_capital"] = [f"{t['ticker']} : {t['old_weight'] * 100:+.1f} % -> {t['new_weight'] * 100:+.1f} %" for t in j.get("trades", []) if start <= t["date"] <= end][:25]
    mk = _market_week()
    data["marches_meilleurs"] = mk[-5:][::-1]
    data["marches_pires"] = mk[:5]
    try:
        from .market_functions import ecst

        keep = {"CPIAUCSL", "PCEPILFE", "UNRATE", "PAYEMS", "DFF", "DGS10", "T10Y2Y", "BAMLH0A0HYM2", "VIXCLS"}
        data["macro_us"] = [{"indicateur": r["label"], "dernier": r["last"], "precedent": r["prev"], "date": r["date"]}
                            for sec in ecst()["sections"] for r in sec["rows"] if r["id"] in keep]
    except Exception:
        pass
    try:
        from .risk_report import risk_report

        r = risk_report()
        worst = min(r["scenarios"], key=lambda x: x["pnl"])
        data["risque"] = {"volatilite_prevue_annuelle_pct": round(r["vol_ex_ante"] * 100, 1),
                          "var_99_1_jour_pct_du_capital": round(r["var"]["var99"] * 100, 2),
                          "plus_gros_contributeurs_au_risque": [{"actif": p["ticker"], "part_du_risque_total_pct": round(p["risk_contrib"] * 100)} for p in r["positions"][:3]],
                          "scenario_de_crise_le_plus_defavorable": f"{worst['name']} : le portefeuille actuel perdrait {worst['pnl'] * 100:.1f} %",
                          "limites_en_vigilance": [l["label"] for l in r["breaches"]]}
    except Exception:
        pass
    try:
        from .monitoring.health import health

        h = health()
        data["sante_strategie"] = {"statut": h["status"], "detail": h.get("message") or [(x["h"], x["verdict"]) for x in h["horizons"]]}
    except Exception:
        pass
    try:
        st = json.loads((ROOT / "data_cache" / "state_cache.json").read_text())
        data["desks"] = [{"equipe": t["team"], "synthese": t["headline"]} for t in st["briefing"]["teams"]]
    except Exception:
        pass
    try:
        from .news import get_news

        data["titres"] = [f"{n['title']} ({n.get('source', '')})" for n in get_news().get("items", [])[:15]]
    except Exception:
        pass
    return data


PROMPT = """Tu es le responsable de la recherche de Gambit Ridge Capital (fonds quantitatif en paper trading, aucun capital réel).
Rédige la note de recherche HEBDOMADAIRE destinée au gérant, en français, à partir UNIQUEMENT des données JSON ci-dessous.
Format Markdown SANS bloc de code, 350 à 450 mots au total, paragraphes courts (pas de sous-titres ###), sections dans cet ordre :
## Synthèse  (3 phrases : ce qui compte cette semaine)
## Marchés
## Le fonds  (performance, d'où elle vient, trades marquants)
## Macro américaine
## Risques et points de vigilance  (vol prévue, VaR, scénario défavorable, santé de la stratégie)
## Vue des desks  (les signaux des agents sont des pistes de recherche : ils ne pilotent pas le portefeuille, dis-le)
Règles : n'invente AUCUN chiffre, AUCUNE tendance (« en hausse depuis… ») ni événement absent des données ; arrondis (« environ 2 % ») ; si une donnée manque, n'en parle pas ;
chaque nom de champ indique l'unité et le sens : ne confonds JAMAIS un poids en % du capital, un rendement en % et un gain en dollars ;
les titres de presse servent seulement de contexte, cite-les avec prudence ; pas de recommandation d'investissement personnalisée.

Données :
{data}"""


def _fallback(data: dict) -> str:
    f = data.get("fonds", {})
    lines = [f"## Synthèse", f"Semaine du {data['periode']['debut']} au {data['periode']['fin']}. "
             + (f"Le fonds fait {f['rendement_semaine_pct']:+.2f} % sur la semaine ({f['rendement_depuis_lancement_pct']:+.2f} % depuis le lancement)." if f else "Pas encore de séance enregistrée."),
             "## Marchés", "Meilleurs : " + ", ".join(f"{m['nom']} {m['rendement_1_semaine_pct']:+.1f} %" for m in data.get("marches_meilleurs", [])) + ".",
             "Pires : " + ", ".join(f"{m['nom']} {m['rendement_1_semaine_pct']:+.1f} %" for m in data.get("marches_pires", [])) + "."]
    if "risque" in data:
        r = data["risque"]
        lines += ["## Risques et points de vigilance", f"Volatilité prévue {r['volatilite_prevue_annuelle_pct']} %, VaR 99 % à 1 jour {r['var_99_1_jour_pct_du_capital']} % du capital. {r['scenario_de_crise_le_plus_defavorable']}."]
    return "\n\n".join(lines)


def generate(d: date | None = None, force: bool = False) -> dict:
    from .conversation import _mistral

    d = d or date.today()
    wid = week_id(d)
    path = NOTES / f"{wid}.json"
    if path.exists() and not force:
        return json.loads(path.read_text())
    start = (d - timedelta(days=6)).isoformat()
    data = gather(start, d.isoformat())
    text = _mistral([{"role": "user", "content": PROMPT.format(data=json.dumps(data, ensure_ascii=False, default=str)[:12000])}], max_tokens=2000)
    if text:  # retire un éventuel bloc ```markdown
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            text = text.rsplit("```", 1)[0].strip()
    note = {"id": wid, "created": d.isoformat(), "period": data["periode"], "source": "mistral" if text else "local",
            "markdown": text or _fallback(data), "data": data}
    NOTES.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(note, ensure_ascii=False, indent=1, default=str))
    return note


def list_notes() -> list[dict]:
    if not NOTES.exists():
        return []
    out = []
    for p in sorted(NOTES.glob("*.json"), reverse=True):
        try:
            n = json.loads(p.read_text())
            out.append({"id": n["id"], "created": n["created"], "period": n["period"], "source": n["source"]})
        except Exception:
            continue
    return out


def get_note(wid: str) -> dict | None:
    p = NOTES / f"{wid}.json"
    if not (len(wid) == 8 and wid[4:6] == "-W" and p.exists()):
        return None
    return json.loads(p.read_text())
