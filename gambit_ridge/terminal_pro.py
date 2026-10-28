"""Fonctions « pro » du terminal, d'après le guide pratique Bloomberg de Tom (mémo des fonctions essentielles).

Toutes en données gratuites réelles, rien d'inventé :
  HP    prix historiques en tableau (OHLCV, jour / semaine / mois)          — Yahoo, cours bruts comme PX_LAST
  DVD   historique des dividendes, rendement 12 mois, croissance             — Yahoo
  RG    rendement total (dividendes réinvestis) contre variation du cours    — Yahoo (clôtures ajustées)
  OMON  chaîne d'options : échéances, strikes, calls / puts, vol implicite   — Yahoo v7 + Black-Scholes
  CN    actualités d'une société                                             — Google News RSS
  FLDS  dictionnaire des champs BDP / BDH / BQL (définition, unité, dispo)   — query/bloomberg.py, query/grql.py
  DOCS  l'araignée des docs : concepts ↔ pages des livres ↔ code de GRC,    — data_cache/araignee (local, jamais publié)
        recherche plein texte dans la bibliothèque de Tom

Servi par /api/pro/<fonction>?s=TICKER&… (app/server.py).
"""

from __future__ import annotations

import json
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parent.parent
CACHE = RACINE / "data_cache"
ARAIGNEE = CACHE / "araignee"
SYMBOLE = re.compile(r"^[A-Z0-9^=.\-]{1,20}$")


def _sym(s: str) -> str:
    s = (s or "").strip().upper()
    if not SYMBOLE.match(s):
        raise ValueError(f"ticker invalide : {s!r}")
    return s


def _ohlc(s: str) -> dict:
    from .data.yahoo_ohlc import charger

    try:
        return charger(s)
    except Exception as exc:
        raise ValueError(f"pas de cours pour {s} ({exc})") from None


def _p(params) -> dict:
    return {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}


# --------------------------------------------------------------------- HP : prix historiques en tableau

def hp(sym: str, params=None) -> dict:
    s, p = _sym(sym), _p(params)
    per = (p.get("per") or "D").upper()[:1]
    if per not in "DWM":
        raise ValueError("périodicité : D, W ou M")
    d = _ohlc(s)
    barres = d["barres"]
    lignes = []
    for jour in sorted(barres):
        o, h, l, c, v = barres[jour][:5]
        if c is None:
            continue
        cle = jour if per == "D" else (date.fromisoformat(jour).isocalendar()[:2] if per == "W" else jour[:7])
        if lignes and lignes[-1]["_cle"] == cle:  # agrégation semaine / mois
            g = lignes[-1]
            g.update(date=jour, haut=max(g["haut"], h or c), bas=min(g["bas"], l or c), cloture=c, volume=(g["volume"] or 0) + (v or 0))
        else:
            lignes.append({"_cle": cle, "date": jour, "ouverture": o if o is not None else c, "haut": h or c, "bas": l or c, "cloture": c, "volume": v})
    for i, g in enumerate(lignes):
        g.pop("_cle")
        g["variation"] = g["cloture"] / lignes[i - 1]["cloture"] - 1 if i else None
    n = {"D": 260, "W": 260, "M": 240}[per]
    return {"symbol": s, "nom": d.get("nom") or s, "devise": d.get("devise"), "periodicite": per,
            "lignes": list(reversed(lignes[-n:])), "source": "Yahoo, cours bruts ajustés des seules divisions (comme PX_LAST)"}


# --------------------------------------------------------------------- DVD : dividendes

def dvd(sym: str, params=None) -> dict:
    s = _sym(sym)
    d = _ohlc(s)
    div = d.get("dividendes") or []
    px = d.get("prix") or d["barres"][max(d["barres"])][3]
    par_an: dict[str, float] = {}
    for jour, m in div:
        par_an[jour[:4]] = par_an.get(jour[:4], 0.0) + m
    fin = max(d["barres"])
    debut = f"{int(fin[:4]) - 1}{fin[4:]}"
    douze = sum(m for jour, m in div if debut < jour <= fin)
    lignes = []
    for i, (jour, m) in enumerate(div):
        lignes.append({"ex_date": jour, "montant": m, "variation": m / div[i - 1][1] - 1 if i and div[i - 1][1] else None})
    # fréquence : écart médian entre deux détachements
    ecarts = [(date.fromisoformat(b[0]) - date.fromisoformat(a[0])).days for a, b in zip(div[-9:], div[-8:])]
    med = float(np.median(ecarts)) if ecarts else None
    freq = None if med is None else "mensuel" if med < 45 else "trimestriel" if med < 135 else "semestriel" if med < 270 else "annuel"
    annees = sorted(par_an)
    completes = [a for a in annees if a < fin[:4]]
    tcam = None
    if len(completes) >= 6 and par_an[completes[-6]] > 0:
        tcam = (par_an[completes[-1]] / par_an[completes[-6]]) ** (1 / 5) - 1
    return {"symbol": s, "nom": d.get("nom") or s, "devise": d.get("devise"), "prix": px,
            "dividende_12m": douze, "rendement_12m": douze / px if px else None, "frequence": freq,
            "croissance_5a": tcam, "par_annee": [{"annee": a, "total": par_an[a]} for a in annees],
            "lignes": list(reversed(lignes)),
            "source": "Yahoo : date ex et montant seulement (les dates de déclaration et de paiement sont payantes)"}


# --------------------------------------------------------------------- RG : rendement total

RG_PERIODES = {"1M": 30, "3M": 91, "6M": 182, "1A": 365, "3A": 1095, "5A": 1826, "10A": 3652}


def rg(sym: str, params=None) -> dict:
    p = _p(params)
    titres = [_sym(x) for x in re.split(r"[,\s]+", (p.get("l") or sym or "SPY").upper()) if x][:6]
    per = (p.get("p") or "1A").upper()
    if per not in RG_PERIODES and per != "YTD":
        raise ValueError("période : " + ", ".join(list(RG_PERIODES) + ["YTD"]))
    series, tableau = [], []
    for s in titres:
        d = _ohlc(s)
        b = d["barres"]
        jours = sorted(j for j in b if b[j][3] is not None and b[j][5] is not None)
        fin = jours[-1]
        borne = f"{fin[:4]}-01-01" if per == "YTD" else (date.fromisoformat(fin) - timedelta(days=RG_PERIODES[per])).isoformat()
        jours = [j for j in jours if j >= borne]
        if len(jours) < 2:
            continue
        c0, a0 = b[jours[0]][3], b[jours[0]][5]
        prix = [b[j][3] / c0 - 1 for j in jours]
        total = [b[j][5] / a0 - 1 for j in jours]
        ans = max((date.fromisoformat(fin) - date.fromisoformat(jours[0])).days / 365.25, 1e-9)
        tr = total[-1]
        tableau.append({"symbol": s, "nom": d.get("nom") or s, "debut": jours[0], "fin": fin, "variation_cours": prix[-1],
                        "rendement_total": tr, "apport_dividendes": tr - prix[-1],
                        "annualise": (1 + tr) ** (1 / ans) - 1 if ans >= 1 else None})
        pas = max(1, len(jours) // 400)
        series.append({"symbol": s, "dates": jours[::pas] + ([jours[-1]] if (len(jours) - 1) % pas else []),
                       "total": total[::pas] + ([total[-1]] if (len(jours) - 1) % pas else [])})
    if not tableau:
        raise ValueError("aucun historique sur la période")
    return {"periode": per, "tableau": tableau, "series": series,
            "note": "Rendement total = clôtures ajustées (dividendes réinvestis à la date ex) ; variation du cours = clôtures brutes."}


# --------------------------------------------------------------------- OMON : chaîne d'options

def omon(sym: str, params=None) -> dict:
    from .data.yahoo_options import fetch_option_chain
    from .options.black_scholes import vol_implicite
    from .options.monte_carlo import taux_sans_risque

    s, p = _sym(sym), _p(params)
    try:
        ch = fetch_option_chain(s)
    except Exception as exc:
        raise ValueError(f"pas d'options cotées pour {s} ({exc})") from None
    spot, q = float(ch["spot"]), float(ch.get("dividend_yield") or 0.0)
    r = taux_sans_risque()
    echeances = sorted({x["echeance"] for x in ch["quotes"]})
    if not echeances:
        raise ValueError(f"pas d'options cotées pour {s}")
    aujourd_hui = datetime.now(timezone.utc).date()
    futures = [e for e in echeances if date.fromisoformat(e) > aujourd_hui] or echeances
    choix = p.get("e") if p.get("e") in echeances else min(futures, key=lambda e: abs((date.fromisoformat(e) - aujourd_hui).days - 30))
    T = max((date.fromisoformat(choix) - aujourd_hui).days, 0.5) / 365.0
    largeur = float(p.get("k") or 0.25)  # strikes à ±25 % du spot par défaut
    lignes: dict[float, dict] = {}
    hors_seance = [False]
    for x in ch["quotes"]:
        if x["echeance"] != choix or abs(x["strike"] / spot - 1) > largeur:
            continue
        bid, ask = x.get("bid") or 0.0, x.get("ask") or 0.0
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else None
        if mid is None and x.get("last"):  # hors séance Yahoo met les fourchettes à zéro : dernier prix traité
            mid, hors_seance[0] = x["last"], True
        iv = vol_implicite(mid, spot, x["strike"], T, r, x["type"], q) if mid else math.nan
        lignes.setdefault(x["strike"], {"strike": x["strike"]})[x["type"]] = {
            "bid": bid or None, "ask": ask or None, "mid": mid, "iv": None if not math.isfinite(iv) else iv,
            "volume": x.get("volume") or 0, "oi": x.get("open_interest") or 0, "dernier": x.get("last")}
    tab = sorted(lignes.values(), key=lambda l: l["strike"])
    atm = min(tab, key=lambda l: abs(l["strike"] - spot))["strike"] if tab else None
    # ratio put / call en volume et en positions ouvertes, sur l'échéance
    vol_c = sum((l.get("call") or {}).get("volume", 0) for l in tab)
    vol_p = sum((l.get("put") or {}).get("volume", 0) for l in tab)
    oi_c = sum((l.get("call") or {}).get("oi", 0) for l in tab)
    oi_p = sum((l.get("put") or {}).get("oi", 0) for l in tab)
    return {"symbol": s, "spot": spot, "taux": r, "dividende": q, "echeance": choix, "jours": round(T * 365),
            "echeances": echeances, "atm": atm, "lignes": tab, "releve": ch.get("fetched_utc"), "hors_seance": hors_seance[0],
            "put_call_volume": vol_p / vol_c if vol_c else None, "put_call_oi": oi_p / oi_c if oi_c else None,
            "source": "Yahoo (différé ~15 min) ; vol implicite Black-Scholes du milieu de fourchette, dividende continu"}


# --------------------------------------------------------------------- CN : actualités d'une société

def cn(sym: str, params=None) -> dict:
    import urllib.parse

    from .news import _fetch_rss

    s = _sym(sym)
    fichier = CACHE / f"cn_{s.replace('^', '_')}.json"
    if fichier.exists() and time.time() - fichier.stat().st_mtime < 1800:
        return json.loads(fichier.read_text())
    nom = s
    try:
        nom = _ohlc(s).get("nom") or s
    except ValueError:
        pass
    court = re.sub(r",?\s+(Inc\.?|Corporation|Corp\.?|Ltd\.?|plc|S\.A\.|SE|N\.V\.|Co\.?|Holdings?|Group|Trust|ETF)\b.*$", "", nom, flags=re.I).strip() or s
    requete = f'"{court}" OR {s.split("=")[0].lstrip("^")} stock' if court.upper() != s else f"{s} stock"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": requete, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    items = _fetch_rss({"name": s, "url": url}, limit=25)
    out = {"symbol": s, "nom": nom, "requete": requete, "items": items, "ts": time.time()}
    if items:
        fichier.parent.mkdir(exist_ok=True)
        fichier.write_text(json.dumps(out, ensure_ascii=False))
    return out


# --------------------------------------------------------------------- FLDS : dictionnaire des champs

FLDS_DEF = {
    "PX_LAST": ("Dernier cours (clôture de la dernière séance)", "devise"), "LAST_PRICE": ("Dernier cours", "devise"),
    "PX_OPEN": ("Cours d'ouverture", "devise"), "PX_HIGH": ("Plus haut du jour", "devise"), "PX_LOW": ("Plus bas du jour", "devise"),
    "PX_CLOSE_1D": ("Clôture de la veille", "devise"), "PX_VOLUME": ("Volume échangé", "titres"), "VOLUME": ("Volume échangé", "titres"),
    "NAME": ("Nom de l'instrument", "texte"), "SECURITY_NAME": ("Nom de l'instrument", "texte"), "LONG_COMP_NAME": ("Raison sociale", "texte"),
    "CRNCY": ("Devise de cotation", "texte"), "CUR_MKT_CAP": ("Capitalisation boursière", "millions"),
    "HIGH_52WEEK": ("Plus haut sur 52 semaines", "devise"), "LOW_52WEEK": ("Plus bas sur 52 semaines", "devise"),
    "CHG_PCT_1D": ("Variation sur 1 jour", "%"), "CHG_PCT_5D": ("Variation sur 5 jours", "%"), "CHG_PCT_1M": ("Variation sur 1 mois", "%"),
    "CHG_PCT_3M": ("Variation sur 3 mois", "%"), "CHG_PCT_6M": ("Variation sur 6 mois", "%"), "CHG_PCT_1YR": ("Variation sur 1 an", "%"),
    "CHG_PCT_YTD": ("Variation depuis le 1er janvier", "%"),
    "VOLATILITY_10D": ("Volatilité historique 10 j, annualisée", "%"), "VOLATILITY_30D": ("Volatilité historique 30 j, annualisée", "%"),
    "VOLATILITY_60D": ("Volatilité historique 60 j", "%"), "VOLATILITY_90D": ("Volatilité historique 90 j", "%"),
    "VOLATILITY_180D": ("Volatilité historique 180 j", "%"), "VOLATILITY_260D": ("Volatilité historique 260 j", "%"),
    "MOV_AVG_20D": ("Moyenne mobile 20 j", "devise"), "MOV_AVG_50D": ("Moyenne mobile 50 j", "devise"),
    "MOV_AVG_100D": ("Moyenne mobile 100 j", "devise"), "MOV_AVG_200D": ("Moyenne mobile 200 j", "devise"),
    "RSI_14D": ("RSI 14 j (Wilder)", "0-100"), "RSI_9D": ("RSI 9 j", "0-100"), "RSI_30D": ("RSI 30 j", "0-100"),
    "BETA_RAW_OVERRIDABLE": ("Bêta brut contre le S&P 500 (2 ans hebdo)", "nombre"), "EQY_BETA": ("Bêta contre le S&P 500", "nombre"),
    "EQY_DVD_YLD_12M": ("Rendement du dividende sur 12 mois glissants", "%"),
    "PE_RATIO": ("Cours / bénéfice (TTM, SEC)", "x"), "PX_TO_BOOK_RATIO": ("Cours / valeur comptable", "x"),
    "PX_TO_SALES_RATIO": ("Cours / chiffre d'affaires", "x"), "CURRENT_EV_TO_T12M_EBIT": ("Valeur d'entreprise / EBIT 12 mois", "x"),
    "RETURN_COM_EQY": ("Rentabilité des capitaux propres (ROE)", "%"), "PROF_MARGIN": ("Marge nette", "%"),
    "OPER_MARGIN": ("Marge opérationnelle", "%"), "SALES_GROWTH": ("Croissance du chiffre d'affaires sur 1 an", "%"),
    "TOT_DEBT_TO_TOT_EQY": ("Dette totale / capitaux propres", "%"), "FREE_CASH_FLOW_YIELD": ("Rendement du flux de trésorerie disponible", "%"),
    "SALES_REV_TURN": ("Chiffre d'affaires 12 mois", "millions"), "NET_INCOME": ("Résultat net 12 mois", "millions"),
}
FLDS_BDS = {"DVD_HIST_ALL": "Historique des dividendes (date ex, montant)", "DVD_HIST": "Historique des dividendes",
            "INDX_MEMBERS": "Membres d'un indice ou d'un univers (SPX, NDX, MAG7, ETF, CRYPTO)", "OPT_CHAIN": "Liste des options cotées"}


def flds(sym: str = "", params=None) -> dict:
    from .query.bloomberg import CHAMPS, PAYANTS
    from .query.grql import CHAMPS as GRQL

    q = (_p(params).get("q") or "").strip().upper()
    out = []
    for c in CHAMPS:
        d, u = FLDS_DEF.get(c, (c.replace("_", " ").title(), ""))
        out.append({"champ": c, "type": "BDP / BDH", "definition": d, "unite": u, "dispo": True})
    for c, d in FLDS_BDS.items():
        out.append({"champ": c, "type": "BDS", "definition": d, "unite": "table", "dispo": True})
    for c in sorted(PAYANTS):
        out.append({"champ": c, "type": "BDP", "definition": "Exige des données payantes (consensus, BVAL, notations, fourchettes)", "unite": "",
                    "dispo": False})
    for fam, cs in GRQL.items():
        for c in cs:
            out.append({"champ": c, "type": "BQL · " + fam, "definition": "", "unite": "", "dispo": True})
    if q:
        out = [x for x in out if q in x["champ"].upper() or q in _plat(x["definition"]).upper() or q in x["type"].upper()]
    return {"champs": out, "n": len(out),
            "aide": "=BDP(\"AAPL US Equity\";\"PX_LAST\") · =BDH(\"SPY US Equity\";\"PX_LAST\";\"-1Y\") · =BDS(\"AAPL US Equity\";\"DVD_HIST_ALL\")"}


def _plat(t: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c))


# --------------------------------------------------------------------- DOCS : l'araignée dans le terminal

_INDEX = {"t": 0.0, "idx": None}


def _araignee():
    import importlib.util

    chemin = RACINE / "scripts" / "araignee" / "araignee.py"
    if not chemin.exists():  # version publique : l'araignée (bibliothèque personnelle) n'est pas livrée
        return None
    spec = importlib.util.spec_from_file_location("grc_araignee", chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pages_en_cache() -> list[dict]:
    """Pages déjà extraites par l'araignée (data_cache/araignee/textes) — sans relire les PDF."""
    pages = []
    for f in sorted((ARAIGNEE / "textes").glob("*.json")):
        if f.name.startswith("._"):
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        nom = Path(d.get("fichier", f.stem)).name
        if re.search(r"b64|gambit-ridge-capital", nom, re.I):
            continue
        for i, t in enumerate(d.get("pages") or []):
            if len((t or "").strip()) > 40:
                pages.append({"doc": nom, "page": i + 1, "texte": t})
    # un même livre copié à deux endroits = une fois
    vus, uniques = set(), []
    for p in pages:
        k = (p["doc"], p["page"])
        if k not in vus:
            vus.add(k)
            uniques.append(p)
    return uniques


def _index():
    dossier = ARAIGNEE / "textes"
    stamp = max((f.stat().st_mtime for f in dossier.glob("*.json")), default=0.0) if dossier.exists() else 0.0
    if _INDEX["idx"] is None or stamp > _INDEX["t"]:
        pages = _pages_en_cache()
        mod = _araignee() if pages else None
        _INDEX.update(t=stamp, idx=mod.Index(pages) if mod else None)
    return _INDEX["idx"]


def _commandes_du_code(fichiers: list[str]) -> list[str]:
    """Fonctions du terminal qui montrent le code relié à un concept (catalogue MODL)."""
    from .market_functions import CATALOGUE

    out = []
    for f in fichiers:
        rel = f.replace("gambit_ridge/", "")
        for _, rows in CATALOGUE:
            for _, motif, _, _, cmd in rows:
                if re.fullmatch(motif.replace(".", r"\.").replace("*", ".*"), rel) and cmd not in out and cmd != "—":
                    out.append(cmd)
    if any("hedge" in f for f in fichiers) and "HEDGE" not in out:
        out.insert(0, "HEDGE")
    return out[:6]


def docs(sym: str = "", params=None) -> dict:
    p = _p(params)
    toile_f = ARAIGNEE / "toile.json"
    if not toile_f.exists():
        return {"disponible": False, "message": "L'araignée n'a pas encore tissé sa toile sur cette machine : "
                "lancer « .venv/bin/python scripts/araignee/araignee.py explorer » sur le Mac (lit la bibliothèque de documents locale)."}
    toile = json.loads(toile_f.read_text())
    for c in toile:
        c["commandes"] = _commandes_du_code(c.get("code") or [])
    idx = _index()
    out = {"disponible": True, "plein_texte": idx is not None, "maj": datetime.fromtimestamp(toile_f.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
           "concepts": sorted(toile, key=lambda c: -c["score_trou"])}
    if idx is not None:
        from collections import Counter

        n = Counter(x["doc"] for x in idx.pages)
        out["documents"] = [{"doc": d, "pages": k} for d, k in n.most_common()]
        out["n_pages"] = len(idx.pages)
    q = (p.get("q") or "").strip()
    if q and idx is not None:
        mod = _araignee()
        premier = re.escape(q.split()[0])
        res = []
        # TF-IDF puis bonus pour chaque paire de mots consécutifs de la requête trouvée sur la page
        # (« hedge ratio » pèse plus que « variance » seul, très fréquent dans les cours de statistiques)
        mots = mod._mots(q)
        paires = [f"{a} {b}" for a, b in zip(mots, mots[1:])]
        cands = []
        for score, pg in idx.chercher(q, 80):
            plat = " ".join(mod._mots(pg["texte"]))
            cands.append((score + 0.35 * sum(plat.count(x) > 0 for x in paires), pg))
        cands.sort(key=lambda x: -x[0])
        for score, pg in cands[: int(p.get("n") or 12)]:
            res.append({"score": round(score, 3), "doc": pg["doc"], "page": pg["page"], "extrait": mod._extrait(pg["texte"], premier, 320)})
        out["requete"], out["resultats"] = q, res
    if p.get("doc") and p.get("page") and idx is not None:
        pg = next((x for x in idx.pages if x["doc"] == p["doc"] and x["page"] == int(p["page"])), None)
        if pg:
            nb = max(x["page"] for x in idx.pages if x["doc"] == p["doc"])
            out["lecture"] = {"doc": pg["doc"], "page": pg["page"], "pages": nb, "texte": pg["texte"]}
    return out


# --------------------------------------------------------------------- aiguillage

FONCTIONS = {"hp": hp, "dvd": dvd, "rg": rg, "omon": omon, "cn": cn, "flds": flds, "docs": docs}


def repondre(nom: str, sym: str, params: dict) -> dict:
    if nom not in FONCTIONS:
        raise KeyError(nom)
    return FONCTIONS[nom](sym, params)
