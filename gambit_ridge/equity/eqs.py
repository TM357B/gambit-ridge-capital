"""EQS — screener d'actions américaines sur données officielles (SEC EDGAR, coupes XBRL) + cours Yahoo.

Univers : toutes les sociétés qui déposent à la SEC avec un chiffre d'affaires d'au moins 1 Md$
sur la dernière année civile complète (~1 500 à 2 000 sociétés), rattachées à leur ticker.
Chaque rubrique vient d'une coupe EDGAR (une requête pour toutes les sociétés), les cours d'un
appel groupé. Univers mis en cache une journée.

Champs : capitalisation, PER, cours/ventes, cours/valeur comptable, rendement FCF, VE/EBIT,
ROE, marges, croissance du chiffre d'affaires, dette/fonds propres.
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent.parent / "data_cache" / "edgar" / "eqs_univers.json"
CA_MIN = 1e9

CHAMPS = {  # clé -> (libellé, unité d'affichage)
    "capitalisation": ("Capitalisation", "md"), "per": ("PER", "x"), "prix_ventes": ("Cours / ventes", "x"),
    "prix_vc": ("Cours / valeur comptable", "x"), "rendement_fcf": ("Rendement FCF", "%"), "ve_ebit": ("VE / EBIT", "x"),
    "roe": ("ROE", "%"), "marge_nette": ("Marge nette", "%"), "marge_op": ("Marge opérationnelle", "%"),
    "croissance_ca": ("Croissance du CA", "%"), "dette_fp": ("Dette / fonds propres", "x"), "chiffre_affaires": ("Chiffre d'affaires", "md"),
}

PRESETS = {
    "valeur": {"titre": "Valeur", "filtres": {"per": [0, 15], "prix_vc": [0, 2.5], "roe": [0.08, None]}, "tri": "per", "sens": "asc"},
    "qualite": {"titre": "Qualité", "filtres": {"roe": [0.20, None], "marge_op": [0.20, None], "dette_fp": [None, 0.8]}, "tri": "roe", "sens": "desc"},
    "croissance": {"titre": "Croissance", "filtres": {"croissance_ca": [0.15, None], "marge_op": [0.05, None]}, "tri": "croissance_ca", "sens": "desc"},
    "fcf": {"titre": "Rendement FCF", "filtres": {"rendement_fcf": [0.06, None], "dette_fp": [None, 1.5]}, "tri": "rendement_fcf", "sens": "desc"},
    "geants": {"titre": "Plus grandes capitalisations", "filtres": {}, "tri": "capitalisation", "sens": "desc"},
}


def _fusion(*coupes):
    """CIK -> valeur, en prenant la plus grande valeur parmi plusieurs balises (chiffre d'affaires)."""
    out = {}
    for c in coupes:
        for k, v in c.items():
            if k not in out or v["val"] > out[k]["val"]:
                out[k] = v
    return out


def _premier(*coupes):
    out = {}
    for c in coupes:
        for k, v in c.items():
            out.setdefault(k, v)
    return out


def construire_univers(annee: int | None = None) -> dict:
    """Assemble l'univers (comptes EDGAR de l'année civile + cours). Cache disque d'une journée."""
    from ..data import edgar
    from ..data.yahoo_options import cotations

    if CACHE.exists() and time.time() - CACHE.stat().st_mtime < 86400:
        return json.loads(CACHE.read_text())
    a = annee or date.today().year - 1
    for essai in (a, a - 1):  # début d'année : la coupe de l'année écoulée peut être encore maigre
        ca = _fusion(*(edgar.coupe(b, f"CY{essai}") for b in edgar.FLUX["chiffre_affaires"]))
        if len([v for v in ca.values() if v["val"] >= CA_MIN]) > 800:
            a = essai
            break
    ca_prec = _fusion(*(edgar.coupe(b, f"CY{a - 1}") for b in edgar.FLUX["chiffre_affaires"]))
    rn = _premier(*(edgar.coupe(b, f"CY{a}") for b in edgar.FLUX["resultat_net"]))
    rop = edgar.coupe("OperatingIncomeLoss", f"CY{a}")
    fop = edgar.coupe("NetCashProvidedByUsedInOperatingActivities", f"CY{a}")
    capex = edgar.coupe("PaymentsToAcquirePropertyPlantAndEquipment", f"CY{a}")
    fp = _premier(*(edgar.coupe(b, f"CY{a}Q4I") for b in edgar.STOCKS["capitaux_propres"]))
    tres = _premier(*(edgar.coupe(b, f"CY{a}Q4I") for b in edgar.STOCKS["tresorerie"]))
    dlt = _premier(*(edgar.coupe(b, f"CY{a}Q4I") for b in edgar.STOCKS["dette_lt"]))
    dct = _premier(*(edgar.coupe(b, f"CY{a}Q4I") for b in edgar.STOCKS["dette_ct"]))

    par_cik = {}
    for tk, info in edgar.tickers().items():  # premier ticker rencontré par CIK = action ordinaire principale
        par_cik.setdefault(info["cik"], tk)
    lignes = []
    for cik, v in ca.items():
        if v["val"] < CA_MIN or cik not in par_cik:
            continue
        tk = par_cik[cik]
        val = lambda d: d.get(cik, {}).get("val")
        dette = None if val(dlt) is None and val(dct) is None else (val(dlt) or 0) + (val(dct) or 0)
        f = None if val(fop) is None else val(fop) - (val(capex) or 0)
        lignes.append({"ticker": tk, "nom": v["nom"], "cik": cik, "chiffre_affaires": v["val"], "ca_prec": val(ca_prec), "resultat_net": val(rn),
                       "resultat_op": val(rop), "fcf": f, "fonds_propres": val(fp), "tresorerie": val(tres), "dette": dette, "fin": v["fin"]})
    q = cotations([l["ticker"].replace(".", "-") for l in lignes])
    for l in lignes:
        c = q.get(l["ticker"].replace(".", "-"), {})
        l["cours"], l["capitalisation"], l["devise"] = c.get("prix"), c.get("capitalisation"), c.get("devise")
    univers = {"annee": a, "date": date.today().isoformat(), "lignes": lignes}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(univers))
    return univers


def _ratios(l: dict) -> dict:
    cap, ca, rn = l.get("capitalisation"), l.get("chiffre_affaires"), l.get("resultat_net")
    d = lambda a, b: a / b if a is not None and b not in (None, 0) else None
    ve = None if cap is None else cap + (l.get("dette") or 0) - (l.get("tresorerie") or 0)
    fp = l.get("fonds_propres")
    per = d(cap, rn) if (rn or 0) > 0 else None
    rfcf = d(l.get("fcf"), cap)
    vee = d(ve, l.get("resultat_op")) if (l.get("resultat_op") or 0) > 0 else None
    # valeurs non plausibles masquées : PER < 1 (sociétés sous tutelle, résultats exceptionnels),
    # rendement FCF > 40 % (flux de trésorerie des banques et assureurs, sans sens économique ici)
    return {"capitalisation": cap, "chiffre_affaires": ca, "per": per if per is None or per >= 1 else None, "prix_ventes": d(cap, ca),
            "prix_vc": d(cap, fp) if (fp or 0) > 0 else None, "rendement_fcf": rfcf if rfcf is None or abs(rfcf) <= 0.4 else None,
            "ve_ebit": vee if vee is None or vee >= 1 else None,
            "roe": d(rn, fp) if (fp or 0) > 0 else None, "marge_nette": d(rn, ca), "marge_op": d(l.get("resultat_op"), ca),
            "croissance_ca": d(ca, l.get("ca_prec")) - 1 if ca and l.get("ca_prec") else None,
            "dette_fp": d(l.get("dette"), fp) if (fp or 0) > 0 else None}


def eqs(params: dict | None = None) -> dict:
    """Filtre l'univers. params : preset, <champ>_min, <champ>_max, cap_min (Md$), tri, sens, n."""
    t0 = time.time()
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}
    preset = PRESETS.get(p.get("preset", ""))
    filtres = dict(preset["filtres"]) if preset else {}
    for k in CHAMPS:
        lo, hi = p.get(f"{k}_min"), p.get(f"{k}_max")
        if lo not in (None, "") or hi not in (None, ""):
            try:
                filtres[k] = [None if lo in (None, "") else float(lo), None if hi in (None, "") else float(hi)]
            except ValueError:
                raise ValueError(f"filtre {k} invalide") from None
    try:
        cap_min = float(p.get("cap_min", 2)) * 1e9
        n = int(float(p.get("n", 50)))
    except ValueError:
        raise ValueError("cap_min et n doivent être des nombres") from None
    tri = p.get("tri") or (preset["tri"] if preset else "capitalisation")
    sens = p.get("sens") or (preset["sens"] if preset else "desc")
    if tri not in CHAMPS or sens not in ("asc", "desc"):
        raise ValueError("tri inconnu")

    u = construire_univers()
    rows = []
    for l in u["lignes"]:
        if (l.get("capitalisation") or 0) < cap_min:
            continue
        r = _ratios(l)
        ok = True
        for k, (lo, hi) in filtres.items():
            v = r.get(k)
            if v is None or (lo is not None and v < lo) or (hi is not None and v > hi):
                ok = False
                break
        if ok:
            rows.append({"ticker": l["ticker"], "nom": l["nom"], "fin": l["fin"], **r})
    eligibles = sum(1 for l in u["lignes"] if (l.get("capitalisation") or 0) >= cap_min)
    rows.sort(key=lambda r: (r.get(tri) is None, (r.get(tri) or 0) * (1 if sens == "asc" else -1)))
    return {"annee": u["annee"], "univers": len(u["lignes"]), "eligibles": eligibles, "resultats": len(rows), "lignes": rows[:min(n, 300)],
            "filtres": filtres, "tri": tri, "sens": sens, "cap_min_md": cap_min / 1e9, "preset": p.get("preset", ""),
            "champs": {k: {"libelle": v[0], "unite": v[1]} for k, v in CHAMPS.items()},
            "presets": {k: v["titre"] for k, v in PRESETS.items()}, "ms": round((time.time() - t0) * 1000),
            "source": f"SEC EDGAR, comptes de l'année civile {u['annee']} (coupes XBRL) · cours Yahoo du {u['date']}"}
