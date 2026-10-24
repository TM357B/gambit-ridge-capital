"""Compatibilité Bloomberg pour Excel : BDP, BDH, BDS et BQL, mêmes signatures et mêmes mnémoniques.

  =BDP("AAPL US Equity", "PX_LAST")
  =BDH("SPY US Equity", "PX_LAST", "20240101", "", "Per=W", "Dts=S")
  =BDS("AAPL US Equity", "DVD_HIST_ALL")
  =BQL("members('MAG7')", "px_last")          ou   =BQL("get(px_last) for(['AAPL'])")

Les unités suivent Bloomberg : variations et ratios en %, montants (capitalisation, chiffre
d'affaires, résultat) en millions de la devise de cotation, volatilités annualisées en %.
Les erreurs reprennent les textes Bloomberg (« #N/A Invalid Security », « #N/A Field Not
Applicable »…). Les champs absents des données gratuites (consensus, BVAL, CDS…) renvoient
« #N/A Field Not Available » au lieu d'un chiffre inventé.

Les cours viennent de data/yahoo_ohlc.py (bruts, ajustés des seules divisions, comme PX_LAST),
pas des clôtures ajustées des dividendes qu'utilisent les rendements de la recherche.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta

import numpy as np

from . import grql

INVALIDE = "#N/A Invalid Security"
NON_APPLICABLE = "#N/A Field Not Applicable"
INDISPONIBLE = "#N/A Field Not Available"
ABSENT = "#N/A N/A"


class ErreurBloomberg(ValueError):
    """Erreur renvoyée telle quelle dans la cellule (texte Bloomberg)."""


def _barres(tk: str) -> dict:
    from ..data.yahoo_ohlc import charger

    try:
        return charger(tk)
    except Exception:
        raise ErreurBloomberg(INVALIDE) from None


def _serie(tk: str, col: int = 3):
    b = _barres(tk)["barres"]
    ds = sorted(b)
    v = np.array([b[d][col] if b[d][col] is not None else np.nan for d in ds], dtype=float)
    ok = np.isfinite(v)
    return [d for d, k in zip(ds, ok) if k], v[ok]


def _variation(tk: str, jours: int | None = None, depuis: str | None = None):
    ds, c = _serie(tk)
    if depuis:
        i = max(0, np.searchsorted(ds, depuis) - 1)
    else:
        cible = (date.fromisoformat(ds[-1]) - timedelta(days=jours)).isoformat()
        i = max(0, np.searchsorted(ds, cible, side="right") - 1)
    return 100.0 * (c[-1] / c[i] - 1.0)


def _vol(tk: str, n: int):
    _, c = _serie(tk)
    r = np.diff(np.log(c[-(n + 1):]))
    return float(np.std(r, ddof=1) * math.sqrt(252) * 100) if len(r) > 2 else None


def _rsi(tk: str, n: int = 14):
    _, c = _serie(tk)
    d = np.diff(c[-(10 * n + 1):])
    mu = md_ = None
    for u, v in zip(np.maximum(d, 0), np.maximum(-d, 0)):  # moyenne de Wilder
        mu = u if mu is None else mu + (u - mu) / n
        md_ = v if md_ is None else md_ + (v - md_) / n
    return 100.0 if not md_ else float(100 - 100 / (1 + mu / md_))


def _beta(tk: str, ref: str = "SPY"):
    """Bêta brut Bloomberg : 2 ans de rendements hebdomadaires contre l'indice de référence."""
    ds, c = _serie(tk, 5)
    rds, rc = _serie(ref, 5)
    debut = (date.fromisoformat(ds[-1]) - timedelta(days=730)).isoformat()
    a, b = dict(zip(ds, c)), dict(zip(rds, rc))
    semaines = {}
    for d in sorted(set(a) & set(b)):
        if d >= debut:
            semaines[date.fromisoformat(d).isocalendar()[:2]] = d  # dernière séance de chaque semaine
    jours = sorted(semaines.values())
    if len(jours) < 26:
        return None
    ra = np.diff(np.log([a[d] for d in jours]))
    rb = np.diff(np.log([b[d] for d in jours]))
    return float(np.cov(ra, rb)[0, 1] / np.var(rb, ddof=1))


def _rendement_dividende(tk: str):
    data = _barres(tk)
    fin = sorted(data["barres"])[-1]
    debut = (date.fromisoformat(fin) - timedelta(days=365)).isoformat()
    total = sum(m for d, m in data["dividendes"] if debut < d <= fin)
    return 100.0 * total / data["barres"][fin][3] if total else None


def _cotation(tk: str) -> dict:
    from ..data.yahoo_options import cotations

    try:
        return cotations([tk]).get(tk, {})
    except Exception:
        return {}


_CTX = {}


def _fond(tk: str, cle: str, echelle: float = 1.0):
    import time

    if not _CTX or time.time() - _CTX["t"] > 3600:  # univers SEC chargé une fois par heure
        _CTX.update(t=time.time(), ctx=grql.Contexte({}, None))
    f = _CTX["ctx"].fondamentaux(tk)
    if f is None:
        raise ErreurBloomberg(NON_APPLICABLE)  # hors univers SEC : non américain, ETF, < 1 Md$ de CA
    v = f.get(cle)
    return None if v is None else v * echelle


def _dernier(tk: str, col: int):
    b = _barres(tk)["barres"]
    v = b[sorted(b)[-1]][col]
    return None if v is None else float(v)


def _px_last(tk: str):
    q = _cotation(tk)
    return q.get("prix") or _barres(tk).get("prix") or _dernier(tk, 3)


def _debut_annee(tk: str) -> str:
    return f"{_serie(tk)[0][-1][:4]}-01-01"


# mnémonique Bloomberg -> calcul ; unités Bloomberg
CHAMPS = {
    "PX_LAST": _px_last, "LAST_PRICE": _px_last,
    "PX_OPEN": lambda tk: _dernier(tk, 0), "PX_HIGH": lambda tk: _dernier(tk, 1), "PX_LOW": lambda tk: _dernier(tk, 2),
    "PX_CLOSE_1D": lambda tk: float(_serie(tk)[1][-2]),
    "PX_VOLUME": lambda tk: _dernier(tk, 4), "VOLUME": lambda tk: _dernier(tk, 4),
    "NAME": lambda tk: _cotation(tk).get("nom") or _barres(tk).get("nom") or tk,
    "SECURITY_NAME": lambda tk: _cotation(tk).get("nom") or _barres(tk).get("nom") or tk,
    "LONG_COMP_NAME": lambda tk: _cotation(tk).get("nom") or _barres(tk).get("nom") or tk,
    "CRNCY": lambda tk: (_cotation(tk).get("devise") or _barres(tk).get("devise") or "").upper() or None,
    "CUR_MKT_CAP": lambda tk: (_cotation(tk).get("capitalisation") or 0) / 1e6 or None,
    "HIGH_52WEEK": lambda tk: float(_serie(tk, 1)[1][-252:].max()),
    "LOW_52WEEK": lambda tk: float(_serie(tk, 2)[1][-252:].min()),
    "CHG_PCT_1D": lambda tk: _cotation(tk).get("variation_jour") if _cotation(tk).get("variation_jour") is not None else _variation(tk, 1),
    "CHG_PCT_5D": lambda tk: _variation(tk, 7), "CHG_PCT_1M": lambda tk: _variation(tk, 30), "CHG_PCT_3M": lambda tk: _variation(tk, 91),
    "CHG_PCT_6M": lambda tk: _variation(tk, 182), "CHG_PCT_1YR": lambda tk: _variation(tk, 365),
    "CHG_PCT_YTD": lambda tk: _variation(tk, depuis=_debut_annee(tk)),
    "VOLATILITY_10D": lambda tk: _vol(tk, 10), "VOLATILITY_30D": lambda tk: _vol(tk, 30), "VOLATILITY_60D": lambda tk: _vol(tk, 60),
    "VOLATILITY_90D": lambda tk: _vol(tk, 90), "VOLATILITY_180D": lambda tk: _vol(tk, 180), "VOLATILITY_260D": lambda tk: _vol(tk, 260),
    "MOV_AVG_20D": lambda tk: float(_serie(tk)[1][-20:].mean()), "MOV_AVG_50D": lambda tk: float(_serie(tk)[1][-50:].mean()),
    "MOV_AVG_100D": lambda tk: float(_serie(tk)[1][-100:].mean()), "MOV_AVG_200D": lambda tk: float(_serie(tk)[1][-200:].mean()),
    "RSI_14D": lambda tk: _rsi(tk, 14), "RSI_9D": lambda tk: _rsi(tk, 9), "RSI_30D": lambda tk: _rsi(tk, 30),
    "BETA_RAW_OVERRIDABLE": _beta, "EQY_BETA": _beta,
    "EQY_DVD_YLD_12M": _rendement_dividende,
    "PE_RATIO": lambda tk: _fond(tk, "per"), "PX_TO_BOOK_RATIO": lambda tk: _fond(tk, "prix_vc"),
    "PX_TO_SALES_RATIO": lambda tk: _fond(tk, "prix_ventes"), "CURRENT_EV_TO_T12M_EBIT": lambda tk: _fond(tk, "ve_ebit"),
    "RETURN_COM_EQY": lambda tk: _fond(tk, "roe", 100), "PROF_MARGIN": lambda tk: _fond(tk, "marge_nette", 100),
    "OPER_MARGIN": lambda tk: _fond(tk, "marge_op", 100), "SALES_GROWTH": lambda tk: _fond(tk, "croissance_ca", 100),
    "TOT_DEBT_TO_TOT_EQY": lambda tk: _fond(tk, "dette_fp", 100), "FREE_CASH_FLOW_YIELD": lambda tk: _fond(tk, "rendement_fcf", 100),
    "SALES_REV_TURN": lambda tk: _fond(tk, "chiffre_affaires", 1e-6), "NET_INCOME": lambda tk: _fond(tk, "resultat_net", 1e-6),
}
# champs Bloomberg courants qui exigent des données payantes : on le dit plutôt que d'inventer
PAYANTS = {"BEST_EPS", "BEST_PE_RATIO", "BEST_TARGET_PRICE", "BEST_ANALYST_RATING", "TOT_ANALYST_REC", "EQY_REC_CONS", "BEST_SALES",
           "BEST_EBITDA", "BEST_EPS_NXT_YR", "CDS_SPREAD_MID", "BVAL_MID_PRICE", "YAS_BOND_YLD", "RTG_SP", "RTG_MOODY", "SHORT_INT",
           "EQY_INST_PCT_SH_OUT", "BID", "ASK", "PX_BID", "PX_ASK"}


def titre(s: str) -> str:
    s = (s or "").strip()
    if not s:
        raise ErreurBloomberg(INVALIDE)
    m = re.fullmatch(r"(XBT|ETH|SOL|XRP)USD\s+CURNCY", s.upper())
    if m:
        return {"XBT": "BTC"}.get(m.group(1), m.group(1)) + "-USD"
    return grql.titre(s)


def _num(v):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return ABSENT
    return float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v


def bdp(securite: str, champ: str):
    """Une valeur. Champ inconnu de Bloomberg : essayé comme expression GRQL (ex. sharpe(1y))."""
    tk = titre(securite)
    c = (champ or "").strip()
    cu = c.upper()
    try:
        if cu in CHAMPS:
            return _num(CHAMPS[cu](tk))
        if cu in PAYANTS:
            return INDISPONIBLE
        res = grql.executer(f"get({c}) for(['{tk}'])")
    except ErreurBloomberg as e:
        return str(e)
    except grql.ErreurRequete as e:
        if "inconnu" in str(e):
            return "#N/A Invalid Field"
        return INVALIDE if "historique" in str(e) else f"#N/A {e}"
    except (IndexError, ValueError):
        return ABSENT
    if not res["lignes"]:
        return INVALIDE
    err = res["erreurs"].get(res["lignes"][0]["id"])
    if err:
        return "#N/A Invalid Field" if "inconnu" in err else (INVALIDE if "historique" in err else f"#N/A {err}")
    return _num(res["lignes"][0]["valeurs"][0])


# ---------------------------------------------------------------- BDH

def date_bloomberg(s: str, aujourd_hui: date | None = None) -> date:
    """« 20240115 », « 2024-01-15 », « -1Y », « -6M », « -3W », « -10D », « -1CY » (début d'année), vide = aujourd'hui."""
    t = aujourd_hui or date.today()
    s = (s or "").strip().upper()
    if s in ("", "0D", "TODAY", "ED"):
        return t
    if re.fullmatch(r"\d{8}", s):
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return date.fromisoformat(s)
    m = re.fullmatch(r"([+-]?\d+)(C?)([DWMQY])", s)
    if not m:
        raise ErreurBloomberg(f"#N/A Invalid Date « {s} »")
    n, cal, u = int(m.group(1)), m.group(2), m.group(3)
    if cal and u == "Y":
        return date(t.year + n + 1, 1, 1) if n < 0 else date(t.year + n, 1, 1)
    if u == "D":
        return t + timedelta(days=n)
    if u == "W":
        return t + timedelta(weeks=n)
    mois = n * {"M": 1, "Q": 3, "Y": 12}[u]
    y, mo = divmod(t.month - 1 + mois, 12)
    jour = min(t.day, [31, 29 if (t.year + y) % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo])
    return date(t.year + y, mo + 1, jour)


def options(args) -> dict:
    """« Per=W », « Dts=H »… ou paires (nom, valeur) -> {'PER': 'W', ...}. Accepte aussi periodicitySelection=WEEKLY."""
    out = {}
    for a in args:
        if not a or "=" not in a:
            continue
        k, v = a.split("=", 1)
        out[k.strip().upper()] = v.strip().upper()
    if "PERIODICITYSELECTION" in out:
        out.setdefault("PER", out["PERIODICITYSELECTION"][:1])
    return out


COLONNES = {"PX_OPEN": 0, "PX_HIGH": 1, "PX_LOW": 2, "PX_LAST": 3, "PX_VOLUME": 4, "VOLUME": 4, "TOT_RETURN_INDEX_GROSS_DVDS": 5}


def _periode(d: str, per: str):
    j = date.fromisoformat(d)
    return {"D": d, "W": j.isocalendar()[:2], "M": (j.year, j.month), "Q": (j.year, (j.month - 1) // 3), "S": (j.year, (j.month - 1) // 6),
            "Y": j.year}[per]


def bdh(securite: str, champs: list[str], debut: str = "-1Y", fin: str = "", opts: list[str] | None = None) -> list[list]:
    """Tableau : [date, champ1, champ2…] par ligne (sens et en-têtes selon Dts, Sort, Dir)."""
    o = options(opts or [])
    tk = titre(securite)
    champs = [c.strip().upper() for c in champs if c.strip()]
    for c in champs:
        if c not in COLONNES:
            raise ErreurBloomberg("#N/A Invalid Field" if c not in PAYANTS else INDISPONIBLE)
    d0, d1 = date_bloomberg(debut), date_bloomberg(fin)
    if d0 > d1:
        raise ErreurBloomberg("#N/A Invalid Date Range")
    b = _barres(tk)
    if o.get("CSHADJNORMAL") == "Y" and "PX_LAST" in champs:
        champs = ["TOT_RETURN_INDEX_GROSS_DVDS" if c == "PX_LAST" else c for c in champs]
    jours = [d for d in sorted(b["barres"]) if d0.isoformat() <= d <= d1.isoformat()]
    per = o.get("PER", "D")[:1]
    if per not in "DWMQSY":
        raise ErreurBloomberg(f"#N/A Invalid Periodicity « {per} »")
    if per != "D":  # dernière séance de chaque période, comme Bloomberg (valeurs de fin de période)
        dernier = {}
        for d in jours:
            dernier[_periode(d, per)] = d
        jours = sorted(dernier.values())
    lignes = [[d] + [b["barres"][d][COLONNES[c]] for c in champs] for d in jours]
    if not lignes:
        return [[ABSENT]]
    if o.get("SORT", "A")[:1] == "D":
        lignes.reverse()
    if o.get("DTS", "S")[:1] == "H":
        lignes = [l[1:] for l in lignes]
    if o.get("DIR", "V")[:1] == "H":
        lignes = [list(x) for x in zip(*lignes)]
    return [[ABSENT if v is None else v for v in l] for l in lignes]


# ---------------------------------------------------------------- BDS

def bds(securite: str, champ: str, opts: list[str] | None = None) -> list[list]:
    o = options(opts or [])
    c = (champ or "").strip().upper()
    entetes = o.get("HEADERS", "N")[:1] == "Y"
    if c == "INDX_MEMBERS":
        cle = re.sub(r"\s+INDEX$", "", securite.strip().upper())
        membres = _membres(cle)
        return ([["Member Ticker and Exchange Code"]] if entetes else []) + [[m if "-" in m else f"{m} US"] for m in membres]
    tk = titre(securite)
    if c in ("DVD_HIST_ALL", "DVD_HIST"):
        div = _barres(tk)["dividendes"]
        if not div:
            return [[ABSENT]]
        # colonnes de Bloomberg dans le même ordre ; seules la date ex et le montant sont publiés gratuitement
        lignes = [["", d, "", "", m, "", "Regular Cash"] for d, m in reversed(div)]
        tete = [["Declared Date", "Ex-Date", "Record Date", "Payable Date", "Dividend Amount", "Dividend Frequency", "Dividend Type"]]
        return (tete if entetes else []) + lignes
    if c == "OPT_CHAIN":
        from ..data.yahoo_options import fetch_option_chain

        try:
            ch = fetch_option_chain(tk)
        except Exception:
            raise ErreurBloomberg(INVALIDE) from None
        vus = sorted({(q["echeance"], q["type"], q["strike"]) for q in ch["quotes"]})
        fmt = lambda e: f"{e[5:7]}/{e[8:10]}/{e[2:4]}"
        k = lambda s: f"{s:g}"
        lignes = [[f"{tk} US {fmt(e)} {'C' if t == 'call' else 'P'}{k(s)} Equity"] for e, t, s in vus]
        return ([["Security Description"]] if entetes else []) + lignes
    if c in PAYANTS or c in ("TOP_20_HOLDERS_PUBLIC_FILINGS", "EARN_ANN_DT_TIME_HIST_WITH_EPS", "SUPPLY_CHAIN_CUSTOMERS"):
        return [[INDISPONIBLE]]
    return [["#N/A Invalid Field"]]


def _membres(cle: str) -> list[str]:
    from ..data.yahoo import CRYPTO_UNIVERSE, all_etf_symbols

    if cle in grql.MEMBRES:
        return grql.MEMBRES[cle]
    if cle in ("ETF", "GRC", "GRC ETF"):
        return all_etf_symbols()
    if cle in ("CRYPTO", "GRC CRYPTO"):
        return list(CRYPTO_UNIVERSE)
    raise ErreurBloomberg("#N/A Index Members Not Available (indices disponibles : MAG7, ETF, CRYPTO)")


# ---------------------------------------------------------------- BQL

def bql(premier: str, expression: str = "", params: list[str] | None = None) -> list[list]:
    """=BQL(univers, expression[, paramètres…]) ou =BQL("get(...) for(...)") — tableau avec en-têtes."""
    p = (premier or "").strip()
    if re.match(r"(let|get)\s*\(", p, re.I):
        src = p
    else:
        univ = p if re.search(r"[(\[]", p) else "[" + ", ".join(f"'{x.strip()}'" for x in p.split(",")) + "]"
        src = f"get({expression}) for({univ})"
        avec = [x for x in (params or []) if x and "=" in x]
        if avec:
            src += " with(" + ", ".join(avec) + ")"
    try:
        res = grql.executer(src)
    except grql.ErreurRequete as e:
        raise ErreurBloomberg(f"#N/A {e}") from None
    if res["series"]:
        lab, s = next(iter(res["series"].items()))
        ids = list(s["par_id"])
        return [["Date"] + ids] + [[d] + [s["par_id"][i][k] for i in ids] for k, d in enumerate(s["dates"])]
    lignes = [["ID"] + res["colonnes"]]
    for l in res["lignes"]:
        err = res["erreurs"].get(l["id"])
        lignes.append([l["id"]] + [(f"#N/A {err}" if err else ABSENT) if v is None else v for v in l["valeurs"]])
    return lignes


# ---------------------------------------------------------------- format d'échange avec le complément Excel

def en_tsv(tableau) -> str:
    """Une ligne par rangée, valeurs séparées par des tabulations ; nombres au format 1.5E-3, dates AAAA-MM-JJ."""
    def cell(v):
        if v is None:
            return ""
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float, np.floating, np.integer)):
            return ABSENT if not math.isfinite(float(v)) else repr(float(v)).upper()
        return str(v).replace("\t", " ").replace("\n", " ")
    if not isinstance(tableau, list):
        tableau = [[tableau]]
    return "\n".join("\t".join(cell(v) for v in l) for l in tableau)


def repondre(fn: str, qs: dict) -> str:
    """Point d'entrée HTTP (/api/xl) : renvoie le TSV, ou le texte d'erreur Bloomberg dans une seule cellule."""
    fn = (fn or "").lower()
    o = [x for x in (qs.get("o") or "").split("|") if x]
    try:
        if fn == "bdp":
            return en_tsv(bdp(qs.get("s", ""), qs.get("f", "PX_LAST")))
        if fn == "bdh":
            return en_tsv(bdh(qs.get("s", ""), (qs.get("f") or "PX_LAST").split(","), qs.get("d", "-1Y"), qs.get("e", ""), o))
        if fn == "bds":
            return en_tsv(bds(qs.get("s", ""), qs.get("f", ""), o))
        if fn == "bql":
            return en_tsv(bql(qs.get("u", ""), qs.get("x", ""), o))
        return "#N/A Unknown Function"
    except ErreurBloomberg as e:
        return str(e)
