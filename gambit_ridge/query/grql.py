"""GRQL (Gambit Ridge Query Language) — langage de requête façon BQL, sur les données du terminal.

Syntaxe (celle de =BQL.Query de Bloomberg : let / get / for / with) :

    let(#perf = return(1y); #risque = volatility(1y);)
    get(name, px_last, #perf, #perf / #risque, pe_ratio)
    for(filter(members('ETF'), volatility(1y) < 0.20))
    with(dates = range(-1y, 0d), currency = 'EUR')

- for() : liste ['AAPL', 'MSFT'] (formes Bloomberg « AAPL US Equity » acceptées), members('ETF' | 'CRYPTO' |
  'MAG7' | 'FONDS'), screen('valeur' | 'qualite' | 'croissance' | 'fcf' | 'geants') (préréglages EQS),
  filter(univers, condition), top(univers, expression, n, 'desc').
- get() : champs de marché (historique Yahoo ajusté), de risque, fondamentaux (SEC EDGAR, sociétés US
  ≥ 1 Md$ de CA), opérations + - * /, comparaisons, and / or / not, abs(), round(), min(), max().
- with() : dates = range(début, fin) (durées -1y, -6m, -2w, -30d ou dates 'AAAA-MM-JJ') ; currency = 'EUR'…
  Si dates est donné dans with(), px_last renvoie la série ; les autres champs sont calculés sur la fenêtre.

Résultat : tableau (une ligne par titre, une colonne par expression) et, pour les séries, les valeurs datées.
Erreurs de syntaxe signalées avec leur position. Lecture seule : aucune requête ne modifie quoi que ce soit.
"""

from __future__ import annotations

import math
import re
import time
from datetime import date, timedelta

import numpy as np

MAX_TITRES = 200
JOURS_AN = 252

# ---------------------------------------------------------------- lexer

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<dur>\d+(?:\.\d+)?[dwmyDWMY](?![A-Za-z0-9_]))
  | (?P<num>\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)
  | (?P<str>'[^']*'|"[^"]*")
  | (?P<var>\#[A-Za-z_][A-Za-z0-9_]*)
  | (?P<id>[A-Za-z_][A-Za-z0-9_.]*)
  | (?P<op><=|>=|==|!=|[()\[\],;=+\-*/<>])
""", re.VERBOSE)


class ErreurRequete(ValueError):
    pass


def lexer(src: str) -> list[tuple[str, str, int]]:
    out, i = [], 0
    while i < len(src):
        m = _TOKEN.match(src, i)
        if not m:
            raise ErreurRequete(f"caractère inattendu « {src[i]} » en position {i + 1}")
        kind = m.lastgroup
        if kind != "ws":
            out.append((kind, m.group(), i))
        i = m.end()
    out.append(("fin", "", len(src)))
    return out


# ---------------------------------------------------------------- parseur

class Parseur:
    def __init__(self, src: str):
        self.src, self.t, self.i = src, lexer(src), 0

    def voir(self, k=0):
        return self.t[min(self.i + k, len(self.t) - 1)]

    def prendre(self, valeur=None, genre=None):
        tok = self.voir()
        if (valeur is not None and tok[1].lower() != valeur) or (genre is not None and tok[0] != genre):
            attendu = valeur or genre
            vu = tok[1] or "la fin de la requête"
            raise ErreurRequete(f"« {attendu} » attendu en position {tok[2] + 1}, trouvé « {vu} »")
        self.i += 1
        return tok

    def requete(self) -> dict:
        q = {"let": [], "get": [], "for": None, "with": {}}
        vus = set()
        while self.voir()[0] != "fin":
            mot = self.prendre(genre="id")[1].lower()
            if mot not in ("let", "get", "for", "with"):
                raise ErreurRequete(f"clause inconnue « {mot} » : let, get, for ou with")
            if mot in vus:
                raise ErreurRequete(f"clause « {mot} » en double")
            vus.add(mot)
            self.prendre("(")
            if mot == "let":
                while self.voir()[1] != ")":
                    nom = self.prendre(genre="var")[1]
                    self.prendre("=")
                    q["let"].append((nom, self.expr()))
                    if self.voir()[1] == ";":
                        self.prendre(";")
            elif mot == "get":
                while True:
                    debut = self.voir()[2]
                    e = self.expr()
                    fin = self.t[self.i - 1][2] + len(self.t[self.i - 1][1])
                    q["get"].append((self.src[debut:fin].strip(), e))
                    if self.voir()[1] != ",":
                        break
                    self.prendre(",")
            elif mot == "for":
                q["for"] = self.expr()
            else:
                while self.voir()[1] != ")":
                    cle = self.prendre(genre="id")[1].lower()
                    self.prendre("=")
                    q["with"][cle] = self.expr()
                    if self.voir()[1] == ",":
                        self.prendre(",")
            self.prendre(")")
        if not q["get"]:
            raise ErreurRequete("clause get(...) manquante")
        if q["for"] is None:
            raise ErreurRequete("clause for(...) manquante")
        return q

    # précédence : or < and < not < comparaison < + - < * / < unaire
    def expr(self):
        g = self.et()
        while self.voir()[0] == "id" and self.voir()[1].lower() == "or":
            self.prendre()
            g = ("bin", "or", g, self.et())
        return g

    def et(self):
        g = self.non()
        while self.voir()[0] == "id" and self.voir()[1].lower() == "and":
            self.prendre()
            g = ("bin", "and", g, self.non())
        return g

    def non(self):
        if self.voir()[0] == "id" and self.voir()[1].lower() == "not":
            self.prendre()
            return ("not", self.non())
        return self.comparaison()

    def comparaison(self):
        g = self.somme()
        if self.voir()[1] in ("<", ">", "<=", ">=", "==", "!="):
            op = self.prendre()[1]
            g = ("bin", op, g, self.somme())
        return g

    def somme(self):
        g = self.produit()
        while self.voir()[1] in ("+", "-"):
            op = self.prendre()[1]
            g = ("bin", op, g, self.produit())
        return g

    def produit(self):
        g = self.unaire()
        while self.voir()[1] in ("*", "/"):
            op = self.prendre()[1]
            g = ("bin", op, g, self.unaire())
        return g

    def unaire(self):
        if self.voir()[1] == "-":
            self.prendre()
            return ("neg", self.unaire())
        return self.atome()

    def atome(self):
        k, v, pos = self.voir()
        if k == "num":
            self.prendre()
            return ("num", float(v))
        if k == "dur":
            self.prendre()
            return ("dur", float(v[:-1]), v[-1].lower())
        if k == "str":
            self.prendre()
            return ("str", v[1:-1])
        if k == "var":
            self.prendre()
            return ("var", v)
        if v == "(":
            self.prendre()
            e = self.expr()
            self.prendre(")")
            return e
        if v == "[":
            self.prendre()
            items = []
            while self.voir()[1] != "]":
                items.append(self.expr())
                if self.voir()[1] == ",":
                    self.prendre(",")
            self.prendre("]")
            return ("list", items)
        if k == "id":
            self.prendre()
            nom = v.lower()
            args, kwargs = [], {}
            if self.voir()[1] == "(":
                self.prendre("(")
                while self.voir()[1] != ")":
                    if self.voir()[0] == "id" and self.voir(1)[1] == "=":
                        cle = self.prendre()[1].lower()
                        self.prendre("=")
                        kwargs[cle] = self.expr()
                    else:
                        args.append(self.expr())
                    if self.voir()[1] == ",":
                        self.prendre(",")
                self.prendre(")")
            return ("call", nom, args, kwargs)
        raise ErreurRequete(f"expression attendue en position {pos + 1}, trouvé « {v or 'fin'} »")


def analyser(src: str) -> dict:
    return Parseur(src.strip().lstrip("=")).requete()


# ---------------------------------------------------------------- données

ALIAS = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "XRP": "XRP-USD", "SPX": "^GSPC", "NDX": "^NDX", "VIX": "^VIX",
         "DAX": "^GDAXI", "CAC": "^FCHI", "SX5E": "^STOXX50E", "NKY": "^N225", "UKX": "^FTSE", "SMI": "^SSMI", "GOLD": "GC=F", "OIL": "CL=F"}
MEMBRES = {"MAG7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]}


def titre(s: str) -> str:
    """Normalise un identifiant : « AAPL US Equity » -> AAPL, « SPX Index » -> ^GSPC, « EURUSD Curncy » -> EURUSD=X."""
    s = s.strip().upper()
    s = re.sub(r"\s+(US|UN|UW|UQ|LN|FP|GY|SW|JP|HK)?\s*(EQUITY|INDEX|CURNCY|COMDTY)$", lambda m: "" if "CURNCY" not in m.group(0) else " CURNCY", s)
    if s.endswith(" CURNCY"):
        s = s[:-7].replace(" ", "")
        return s + "=X" if len(s) == 6 else s
    s = s.replace(" ", "")
    return ALIAS.get(s, s)


class Contexte:
    """Fenêtre de dates, devise, caches de la requête (historiques, cotations, fondamentaux)."""

    def __init__(self, with_: dict, ev):
        self.ev = ev
        self.debut, self.fin, self.dates_explicites = date.today() - timedelta(days=365), date.today(), False
        self.devise = None
        if "dates" in with_:
            d = with_["dates"]
            if not (d[0] == "call" and d[1] == "range" and len(d[2]) == 2):
                raise ErreurRequete("dates = range(début, fin) attendu, ex. range(-1y, 0d)")
            self.debut, self.fin = (self._date(x) for x in d[2])
            self.dates_explicites = True
        if "currency" in with_:
            c = with_["currency"]
            if c[0] != "str" or not re.fullmatch(r"[A-Za-z]{3}", c[1]):
                raise ErreurRequete("currency = 'EUR' attendu (code ISO à trois lettres)")
            self.devise = c[1].upper()
        if self.debut >= self.fin:
            raise ErreurRequete("la date de début doit précéder la date de fin")
        self._hist, self._cot, self._fond = {}, None, None

    @staticmethod
    def _date(n) -> date:
        if n[0] == "str":
            try:
                return date.fromisoformat(n[1])
            except ValueError:
                raise ErreurRequete(f"date invalide « {n[1]} » (AAAA-MM-JJ)") from None
        signe = 1
        if n[0] == "neg":
            signe, n = -1, n[1]
        if n[0] != "dur":
            raise ErreurRequete("durée attendue dans range(), ex. -1y, -6m, -30d, 0d")
        return date.today() + signe * duree(n)

    def historique(self, tk: str):
        if tk not in self._hist:
            from ..data.yahoo import YahooConnector

            data = YahooConnector().fetch(tk)
            if not data:
                raise ErreurRequete(f"{tk} : aucun historique de prix")
            ds = sorted(data)
            self._hist[tk] = (ds, np.array([data[d] for d in ds], dtype=float))
        return self._hist[tk]

    def fenetre(self, tk: str, periode=None):
        """Cours dans la fenêtre (ou sur la période donnée, finissant à la fin de fenêtre)."""
        ds, px = self.historique(tk)
        fin = self.fin.isoformat()
        debut = (self.fin - duree(periode)).isoformat() if periode is not None else self.debut.isoformat()
        sel = [i for i, d in enumerate(ds) if debut <= d <= fin]
        if len(sel) < 2:
            raise ErreurRequete(f"{tk} : pas assez de cours entre {debut} et {fin}")
        return [ds[i] for i in sel], px[sel]

    def cotation(self, tk: str) -> dict:
        if self._cot is None:
            from ..data.yahoo_options import cotations

            self._cot = cotations(self.ev.univers_courant)
        return self._cot.get(tk, {})

    def fondamentaux(self, tk: str) -> dict | None:
        if self._fond is None:
            from ..equity.eqs import _ratios, construire_univers

            self._fond = {}
            for l in construire_univers()["lignes"]:
                self._fond[l["ticker"].replace(".", "-")] = {**_ratios(l), "resultat_net": l.get("resultat_net"), "nom": l["nom"]}
        return self._fond.get(tk)

    def change(self, de: str):
        """Taux de change de -> devise demandée, série datée (cours Yahoo DEVISE1DEVISE2=X)."""
        if not self.devise or de == self.devise:
            return None
        return self.historique(f"{de}{self.devise}=X")


def duree(n) -> timedelta:
    if n is None:
        return timedelta(days=365)
    if n[0] != "dur":
        raise ErreurRequete("durée attendue, ex. 1y, 6m, 2w, 30d")
    v, u = n[1], n[2]
    return timedelta(days=v * {"d": 1, "w": 7, "m": 30.4375, "y": 365.25}[u])


class Serie:
    """Valeurs datées (une série par titre)."""

    def __init__(self, dates, vals):
        self.dates, self.vals = list(dates), np.asarray(vals, dtype=float)

    def dernier(self):
        return float(self.vals[-1]) if len(self.vals) else None


# ---------------------------------------------------------------- champs

def _r(px):
    return np.diff(np.log(px))


def _en_devise(ctx, tk, dates, vals):
    """Convertit des montants en dollars (ou devise de cotation) dans la devise demandée, date par date."""
    if not ctx.devise:
        return vals
    de = (ctx.cotation(tk).get("devise") or "USD").upper()
    fx = ctx.change(de)
    if fx is None:
        return vals
    fds, fpx = fx
    j = np.searchsorted(fds, dates, side="right") - 1
    if (j < 0).any():
        raise ErreurRequete(f"pas de taux de change {de}{ctx.devise} au début de la fenêtre")
    return vals * fpx[j]


def _scal_devise(ctx, tk, v):
    if v is None or not ctx.devise:
        return v
    return float(_en_devise(ctx, tk, [ctx.fin.isoformat()], np.array([v]))[0])


def champ(nom, ctx, tk, args, kw):
    a0 = args[0] if args else None
    per = kw.get("period") or (a0 if a0 is not None and a0[0] == "dur" else None)
    if nom == "px_last":
        if ctx.dates_explicites or "dates" in kw:
            if "dates" in kw:
                sous = Contexte({"dates": kw["dates"], **({"currency": ("str", ctx.devise)} if ctx.devise else {})}, ctx.ev)
                sous._hist, sous._cot = ctx._hist, ctx._cot
                ds, px = sous.fenetre(tk)
            else:
                ds, px = ctx.fenetre(tk)
            return Serie(ds, _en_devise(ctx, tk, ds, px))
        ds, px = ctx.historique(tk)
        return float(_en_devise(ctx, tk, ds[-1:], px[-1:])[0])
    if nom in ("return", "chg_pct", "total_return"):
        _, px = ctx.fenetre(tk, per)
        return float(px[-1] / px[0] - 1)
    if nom in ("volatility", "vol"):
        _, px = ctx.fenetre(tk, per)
        return float(np.std(_r(px), ddof=1) * math.sqrt(JOURS_AN))
    if nom in ("max_drawdown", "drawdown"):
        _, px = ctx.fenetre(tk, per)
        return float((px / np.maximum.accumulate(px) - 1).min())
    if nom == "sharpe":
        _, px = ctx.fenetre(tk, per)
        r = _r(px)
        return float(r.mean() / r.std(ddof=1) * math.sqrt(JOURS_AN)) if r.std() > 0 else None
    if nom in ("beta", "correlation", "corr"):
        ref = titre(kw["benchmark"][1]) if "benchmark" in kw else (titre(a0[1]) if a0 is not None and a0[0] == "str" else "SPY")
        ds, px = ctx.fenetre(tk, per)
        rds, rpx = ctx.fenetre(ref, per)
        commun = sorted(set(ds) & set(rds))
        if len(commun) < 20:
            raise ErreurRequete(f"{tk} : trop peu de dates communes avec {ref}")
        a = np.array([px[ds.index(d)] for d in commun])
        b = np.array([rpx[rds.index(d)] for d in commun])
        ra, rb = _r(a), _r(b)
        if nom == "beta":
            return float(np.cov(ra, rb)[0, 1] / np.var(rb, ddof=1))
        return float(np.corrcoef(ra, rb)[0, 1])
    if nom == "sma":
        n = int(a0[1]) if a0 is not None and a0[0] == "num" else 50
        ds, px = ctx.historique(tk)
        return _scal_devise(ctx, tk, float(px[-n:].mean()))
    if nom == "rsi":
        n = int(a0[1]) if a0 is not None and a0[0] == "num" else 14
        _, px = ctx.historique(tk)
        d = np.diff(px[-(5 * n + 1):])
        up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
        a = 1 / n
        mu = md_ = None
        for u, v in zip(up, dn):  # moyenne de Wilder
            mu = u if mu is None else (1 - a) * mu + a * u
            md_ = v if md_ is None else (1 - a) * md_ + a * v
        return float(100 - 100 / (1 + mu / md_)) if md_ else 100.0
    if nom in ("high", "low"):
        _, px = ctx.fenetre(tk, per or ("dur", 1, "y"))
        return _scal_devise(ctx, tk, float(px.max() if nom == "high" else px.min()))
    if nom == "name":
        f = ctx.fondamentaux(tk)
        return ctx.cotation(tk).get("nom") or (f or {}).get("nom") or tk
    if nom in ("market_cap", "cur_mkt_cap"):
        return _scal_devise(ctx, tk, ctx.cotation(tk).get("capitalisation"))
    fond = {"pe_ratio": "per", "pb_ratio": "prix_vc", "px_to_book_ratio": "prix_vc", "ps_ratio": "prix_ventes", "fcf_yield": "rendement_fcf",
            "return_com_eqy": "roe", "roe": "roe", "net_margin": "marge_nette", "oper_margin": "marge_op", "sales_growth": "croissance_ca",
            "debt_to_equity": "dette_fp", "ev_to_ebit": "ve_ebit", "sales_rev_turn": "chiffre_affaires", "sales": "chiffre_affaires",
            "net_income": "resultat_net"}
    if nom in fond:
        f = ctx.fondamentaux(tk)
        if f is None:
            return None  # hors univers SEC (non américain ou < 1 Md$ de CA)
        v = f.get(fond[nom])
        return _scal_devise(ctx, tk, v) if nom in ("sales", "sales_rev_turn", "net_income") else v
    raise ErreurRequete(f"champ ou fonction inconnu : {nom}")


CHAMPS = {
    "Marché": ["px_last", "return(1y)", "volatility(1y)", "max_drawdown(1y)", "sharpe(1y)", "beta('SPY', 1y)", "correlation('SPY', 1y)",
               "sma(50)", "rsi(14)", "high(1y)", "low(1y)", "market_cap", "name"],
    "Fondamentaux (SEC, sociétés US)": ["pe_ratio", "pb_ratio", "ps_ratio", "fcf_yield", "roe", "net_margin", "oper_margin", "sales_growth",
                                        "debt_to_equity", "ev_to_ebit", "sales", "net_income"],
    "Fonctions": ["abs(x)", "round(x, 2)", "min(a, b)", "max(a, b)", "and / or / not", "+ - * /", "< > <= >= == !="],
    "Univers": ["['AAPL', 'MSFT']", "['AAPL US Equity', 'SPX Index']", "members('ETF')", "members('CRYPTO')", "members('MAG7')",
                "screen('qualite')", "filter(univers, condition)", "top(univers, expression, 10)"],
}


# ---------------------------------------------------------------- évaluation

class Evaluateur:
    def __init__(self, q: dict):
        self.q = q
        self.univers_courant: list[str] = []
        self.ctx = Contexte(q["with"], self)
        self.vars = {}

    def univers(self, n) -> list[str]:
        if n[0] == "str":
            return [titre(n[1])]
        if n[0] == "list":
            out = []
            for x in n[1]:
                if x[0] != "str":
                    raise ErreurRequete("liste de titres entre guillemets attendue : ['AAPL', 'MSFT']")
                out.append(titre(x[1]))
            return out
        if n[0] == "call" and n[1] == "members":
            from ..data.yahoo import CRYPTO_UNIVERSE, all_etf_symbols

            nom = (n[2][0][1] if n[2] and n[2][0][0] == "str" else "").upper()
            if nom in ("ETF", "FONDS"):
                return all_etf_symbols()
            if nom == "CRYPTO":
                return list(CRYPTO_UNIVERSE)
            if nom in MEMBRES:
                return MEMBRES[nom]
            raise ErreurRequete(f"members('{nom}') inconnu : ETF, CRYPTO, MAG7 (la composition des indices boursiers n'est pas disponible gratuitement ; utilise screen())")
        if n[0] == "call" and n[1] == "screen":
            from ..equity.eqs import PRESETS, eqs

            nom = n[2][0][1] if n[2] and n[2][0][0] == "str" else ""
            if nom not in PRESETS:
                raise ErreurRequete(f"screen('{nom}') inconnu : {', '.join(PRESETS)}")
            return [l["ticker"].replace(".", "-") for l in eqs({"preset": nom, "n": str(MAX_TITRES)})["lignes"]]
        if n[0] == "call" and n[1] in ("filter", "top"):
            if not n[2]:
                raise ErreurRequete(f"{n[1]}(univers, …) attendu")
            base = self.univers(n[2][0])
            self.univers_courant = base
            if n[1] == "filter":
                if len(n[2]) < 2:
                    raise ErreurRequete("filter(univers, condition) attendu")
                return [tk for tk in base if self._vrai(self.valeur(n[2][1], tk))]
            expr = n[2][1] if len(n[2]) > 1 else ("call", "market_cap", [], {})
            k = int(n[2][2][1]) if len(n[2]) > 2 and n[2][2][0] == "num" else 10
            sens = n[2][3][1] if len(n[2]) > 3 and n[2][3][0] == "str" else "desc"
            notes = []
            for tk in base:
                try:
                    v = self.valeur(expr, tk)
                    v = v.dernier() if isinstance(v, Serie) else v
                    if v is not None:
                        notes.append((v, tk))
                except ErreurRequete:
                    continue
            notes.sort(reverse=(sens != "asc"))
            return [tk for _, tk in notes[:k]]
        raise ErreurRequete("for() attend une liste, members(), screen(), filter() ou top()")

    @staticmethod
    def _vrai(v):
        v = v.dernier() if isinstance(v, Serie) else v
        return bool(v) if v is not None and not (isinstance(v, float) and math.isnan(v)) else False

    def valeur(self, n, tk):
        k = n[0]
        if k == "num":
            return n[1]
        if k == "str":
            return n[1]
        if k == "dur":
            raise ErreurRequete("une durée (1y, 6m…) n'est valable qu'en argument de fonction")
        if k == "var":
            if n[1] not in self.vars:
                raise ErreurRequete(f"variable {n[1]} non définie dans let()")
            return self.valeur(self.vars[n[1]], tk)
        if k == "neg":
            return self._op("*", -1.0, self.valeur(n[1], tk))
        if k == "not":
            return not self._vrai(self.valeur(n[1], tk))
        if k == "bin":
            a = self.valeur(n[2], tk)
            if n[1] == "and" and not self._vrai(a):
                return False
            if n[1] == "or" and self._vrai(a):
                return True
            return self._op(n[1], a, self.valeur(n[3], tk))
        if k == "call":
            nom, args, kw = n[1], n[2], n[3]
            if nom in ("abs", "round", "min", "max"):
                vals = [self.valeur(a, tk) for a in args]
                vals = [v.dernier() if isinstance(v, Serie) else v for v in vals]
                if any(v is None for v in vals):
                    return None
                if nom == "abs":
                    return abs(vals[0])
                if nom == "round":
                    return round(vals[0], int(vals[1]) if len(vals) > 1 else 0)
                return min(vals) if nom == "min" else max(vals)
            return champ(nom, self.ctx, tk, args, kw)
        if k == "list":
            raise ErreurRequete("une liste n'est valable que dans for()")
        raise ErreurRequete("expression non évaluable")

    @staticmethod
    def _op(op, a, b):
        if a is None or b is None:
            return None
        if isinstance(a, str) or isinstance(b, str):
            if op in ("==", "!="):
                return (a == b) if op == "==" else (a != b)
            raise ErreurRequete("opération impossible sur du texte")
        sa, sb = isinstance(a, Serie), isinstance(b, Serie)
        if sa and sb:
            commun = sorted(set(a.dates) & set(b.dates))
            ia, ib = [a.dates.index(d) for d in commun], [b.dates.index(d) for d in commun]
            return Serie(commun, Evaluateur._num(op, a.vals[ia], b.vals[ib]))
        if sa:
            return Serie(a.dates, Evaluateur._num(op, a.vals, b))
        if sb:
            return Serie(b.dates, Evaluateur._num(op, a, b.vals))
        r = Evaluateur._num(op, np.array([a], dtype=float), b)
        return float(r[0]) if op not in ("<", ">", "<=", ">=", "==", "!=", "and", "or") else bool(r[0])

    @staticmethod
    def _num(op, a, b):
        with np.errstate(divide="ignore", invalid="ignore"):
            r = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "/": lambda: a / b, "<": lambda: a < b, ">": lambda: a > b,
                 "<=": lambda: a <= b, ">=": lambda: a >= b, "==": lambda: a == b, "!=": lambda: a != b,
                 "and": lambda: np.logical_and(a, b), "or": lambda: np.logical_or(a, b)}[op]()
        return r

    def executer(self) -> dict:
        t0 = time.time()
        for nom, e in self.q["let"]:
            self.vars[nom] = e
        tks = self.univers(self.q["for"])
        if len(tks) > MAX_TITRES:
            raise ErreurRequete(f"univers trop large ({len(tks)} titres, maximum {MAX_TITRES})")
        self.univers_courant = tks
        colonnes = [lab for lab, _ in self.q["get"]]
        lignes, series, erreurs = [], {}, {}
        for tk in tks:
            vals = []
            for lab, e in self.q["get"]:
                try:
                    v = self.valeur(e, tk)
                except ErreurRequete as exc:
                    erreurs.setdefault(tk, str(exc))
                    v = None
                except Exception as exc:  # données indisponibles pour ce titre : la requête continue
                    erreurs.setdefault(tk, f"données indisponibles ({exc})")
                    v = None
                if isinstance(v, Serie):
                    s = series.setdefault(lab, {})
                    s[tk] = (v.dates, [None if not np.isfinite(x) else round(float(x), 6) for x in v.vals])
                    v = v.dernier()
                if isinstance(v, (float, np.floating)):
                    v = None if not math.isfinite(float(v)) else round(float(v), 6)
                elif isinstance(v, (bool, np.bool_)):
                    v = bool(v)
                vals.append(v)
            lignes.append({"id": tk, "valeurs": vals})
        out_series = {}
        for lab, par in series.items():
            dates = sorted({d for ds, _ in par.values() for d in ds})
            idx = {tk: dict(zip(ds, vs)) for tk, (ds, vs) in par.items()}
            out_series[lab] = {"dates": dates, "par_id": {tk: [idx[tk].get(d) for d in dates] for tk in idx}}
        return {"colonnes": colonnes, "lignes": lignes, "series": out_series, "erreurs": erreurs, "n": len(tks),
                "fenetre": [self.ctx.debut.isoformat(), self.ctx.fin.isoformat()], "devise": self.ctx.devise,
                "ms": round((time.time() - t0) * 1000)}


def executer(src: str) -> dict:
    if not src or not src.strip():
        raise ErreurRequete("requête vide")
    if len(src) > 4000:
        raise ErreurRequete("requête trop longue (4 000 caractères au plus)")
    return Evaluateur(analyser(src)).executer()


def en_csv(res: dict) -> str:
    """CSV pour Excel / Power Query : tableau, ou série datée (dates × titres) si une seule colonne est une série."""
    import csv
    import io

    f = io.StringIO()
    w = csv.writer(f)
    if len(res["colonnes"]) == 1 and res["series"]:
        s = next(iter(res["series"].values()))
        ids = list(s["par_id"])
        w.writerow(["date"] + ids)
        for i, d in enumerate(s["dates"]):
            w.writerow([d] + ["" if s["par_id"][tk][i] is None else s["par_id"][tk][i] for tk in ids])
    else:
        w.writerow(["id"] + res["colonnes"])
        for l in res["lignes"]:
            w.writerow([l["id"]] + ["" if v is None else v for v in l["valeurs"]])
    return f.getvalue()
