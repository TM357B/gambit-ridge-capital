"""Macro mondiale sur sources officielles gratuites — fonction GEW (« Global Economy Watch »).

- FMI, World Economic Outlook (API DataMapper) : croissance, inflation, chômage, dette et solde
  publics, balance courante — réalisés ET prévisions officielles du FMI (équivalent public d'ECFC).
- BRI (stats.bis.org, WS_CBPOL) : taux directeurs mensuels des banques centrales.
- FRED (OCDE, IRLTLT01) : taux d'État à 10 ans par pays.
Caches disque : FMI et BRI 1 jour (data_cache/macro/), FRED via son propre cache.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent.parent / "data_cache" / "macro"

# (code FMI, code BRI, code FRED 10 ans, libellé, région)
PAYS = [
    ("USA", "US", "US", "États-Unis", "Amériques"), ("CAN", "CA", "CA", "Canada", "Amériques"),
    ("MEX", "MX", "MX", "Mexique", "Amériques"), ("BRA", "BR", None, "Brésil", "Amériques"),
    ("EURO", "XM", "EZ", "Zone euro", "Europe"), ("DEU", "XM", "DE", "Allemagne", "Europe"), ("FRA", "XM", "FR", "France", "Europe"),
    ("ITA", "XM", "IT", "Italie", "Europe"), ("ESP", "XM", "ES", "Espagne", "Europe"), ("NLD", "XM", "NL", "Pays-Bas", "Europe"),
    ("CHE", "CH", "CH", "Suisse", "Europe"), ("GBR", "GB", "GB", "Royaume-Uni", "Europe"), ("SWE", "SE", "SE", "Suède", "Europe"),
    ("NOR", "NO", "NO", "Norvège", "Europe"), ("TUR", "TR", None, "Turquie", "Europe"),
    ("JPN", "JP", "JP", "Japon", "Asie-Pacifique"), ("CHN", "CN", None, "Chine", "Asie-Pacifique"), ("IND", "IN", "IN", "Inde", "Asie-Pacifique"),
    ("KOR", "KR", "KR", "Corée du Sud", "Asie-Pacifique"), ("AUS", "AU", "AU", "Australie", "Asie-Pacifique"), ("IDN", "ID", None, "Indonésie", "Asie-Pacifique"),
    ("SAU", "SA", None, "Arabie saoudite", "Moyen-Orient / Afrique"), ("ZAF", "ZA", "ZA", "Afrique du Sud", "Moyen-Orient / Afrique"),
]
AGREGATS = [("WEOWORLD", "Monde"), ("ADVEC", "Économies avancées"), ("OEMDC", "Émergents et en développement")]
INDICATEURS = {"croissance": "NGDP_RPCH", "inflation": "PCPIPCH", "chomage": "LUR", "dette": "GGXWDG_NGDP",
               "solde_public": "GGXCNL_NGDP", "balance_courante": "BCA_NGDPD"}


def _get(url: str, nom: str, ttl: float = 86400) -> str:
    chemin = CACHE / nom
    if chemin.exists() and time.time() - chemin.stat().st_mtime < ttl:
        return chemin.read_text()
    try:
        req = urllib.request.Request(url)  # User-Agent par défaut : le FMI refuse un User-Agent de navigateur (403)
        with urllib.request.urlopen(req, timeout=40) as r:
            txt = r.read().decode("utf-8", errors="replace")
    except Exception:
        if chemin.exists():
            return chemin.read_text()
        raise
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(txt)
    return txt


def fmi(indicateur: str) -> dict[str, dict[str, float]]:
    d = json.loads(_get(f"https://www.imf.org/external/datamapper/api/v1/{indicateur}", f"fmi_{indicateur}.json"))
    return {pays: {an: float(v) for an, v in serie.items() if v is not None} for pays, serie in d.get("values", {}).get(indicateur, {}).items()}


def taux_directeurs() -> dict[str, list[tuple[str, float]]]:
    zones = "+".join(sorted({p[1] for p in PAYS}))
    txt = _get(f"https://stats.bis.org/api/v1/data/WS_CBPOL/M.{zones}/all?lastNObservations=13&format=csv", "bis_cbpol.csv")
    out = defaultdict(list)
    for r in csv.DictReader(io.StringIO(txt)):
        try:
            out[r["REF_AREA"]].append((r["TIME_PERIOD"], float(r["OBS_VALUE"])))
        except (KeyError, ValueError):
            continue
    return {k: sorted(v) for k, v in out.items()}


def taux_10ans() -> dict[str, tuple[str, float]]:
    from .fred import FredConnector

    conn = FredConnector()
    out = {}
    for code in {p[2] for p in PAYS if p[2]}:
        try:
            ds, vals = conn.fetch_series(f"IRLTLT01{code}M156N")
            if len(ds):
                out[code] = (ds[-1], float(vals[-1]))
        except Exception:
            continue
    return out


def gew() -> dict:
    t0 = time.time()
    an = date.today().year
    annees = [str(an - 1), str(an), str(an + 1)]
    series = {k: fmi(v) for k, v in INDICATEURS.items()}
    pol = taux_directeurs()
    dix = taux_10ans()

    def ligne(code, nom, region, bis=None, fred=None):
        g = lambda k, a: series[k].get(code, {}).get(a)
        p = pol.get(bis) if bis else None
        taux, var_1a = (p[-1][1], p[-1][1] - p[0][1]) if p else (None, None)
        infl = g("inflation", annees[1])
        y10 = dix.get(fred) if fred else None
        return {"code": code, "pays": nom, "region": region,
                "croissance": [g("croissance", a) for a in annees], "inflation": [g("inflation", a) for a in annees],
                "chomage": g("chomage", annees[1]), "dette": g("dette", annees[1]), "solde_public": g("solde_public", annees[1]),
                "balance_courante": g("balance_courante", annees[1]),
                "taux_directeur": taux, "taux_directeur_var_1a": var_1a, "taux_directeur_date": p[-1][0] if p else None,
                "taux_reel": None if taux is None or infl is None else taux - infl,
                "taux_10a": y10[1] if y10 else None, "taux_10a_date": y10[0] if y10 else None,
                "pente": None if y10 is None or taux is None else y10[1] - taux}

    lignes = [ligne(c, n, r, b, f) for c, b, f, n, r in PAYS]
    agregats = [ligne(c, n, "Agrégats") for c, n in AGREGATS]
    return {"annees": annees, "lignes": lignes, "agregats": agregats, "ms": round((time.time() - t0) * 1000),
            "note": f"{annees[1]} et {annees[2]} : estimations et prévisions du FMI (World Economic Outlook) ; {annees[0]} : réalisé ou dernière estimation.",
            "source": "FMI World Economic Outlook (DataMapper) · BRI, taux directeurs · FRED / OCDE, taux à 10 ans"}
