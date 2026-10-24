"""SEC EDGAR — données officielles et gratuites des sociétés cotées américaines.

- Table ticker -> CIK (www.sec.gov/files/company_tickers.json).
- États financiers XBRL normalisés (data.sec.gov/api/xbrl/companyfacts) : comptes annuels
  sur ~15 ans et quatre derniers trimestres (TTM), à partir des valeurs « frame » que l'EDGAR
  dédoublonne (une valeur canonique par période civile).
- Coupes transversales (data.sec.gov/api/xbrl/frames) : une rubrique pour TOUTES les sociétés
  sur une période — base du screener EQS.
- Dépôts récents (submissions) : 10-K, 10-Q, 8-K…, et transactions des dirigeants (formulaires 4,
  analysés depuis leur XML).

Règles d'accès de la SEC : User-Agent avec contact obligatoire (variable d'environnement
GRC_SEC_UA, sinon un contact neutre), 10 requêtes par seconde au plus. Cache disque
data_cache/edgar/ avec durées de vie adaptées.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent.parent / "data_cache" / "edgar"
UA = os.environ.get("GRC_SEC_UA", "GambitRidgeCapital research contact@gambitridge.invalid")
_verrou = threading.Lock()
_dernier = [0.0]

# rubrique affichée -> balises us-gaap essayées dans l'ordre (les sociétés n'utilisent pas toutes les mêmes)
FLUX = {
    "chiffre_affaires": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                         "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense"],
    "marge_brute": ["GrossProfit"],
    "resultat_operationnel": ["OperatingIncomeLoss"],
    "resultat_net": ["NetIncomeLoss", "ProfitLoss"],
    "flux_operationnel": ["NetCashProvidedByUsedInOperatingActivities"],
    "investissements": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "dividendes": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "rachats": ["PaymentsForRepurchaseOfCommonStock"],
    "r_et_d": ["ResearchAndDevelopmentExpense"],
}
STOCKS = {
    "actif": ["Assets"],
    "passif": ["Liabilities"],
    "capitaux_propres": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "tresorerie": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "dette_lt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "dette_ct": ["LongTermDebtCurrent", "DebtCurrent"],
}
BPA = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]


def _get(url: str, ttl_s: float, nom: str, texte: bool = False):
    """GET avec cache disque, User-Agent SEC et limite de débit."""
    chemin = CACHE / nom
    if chemin.exists() and time.time() - chemin.stat().st_mtime < ttl_s:
        brut = chemin.read_text()
        return brut if texte else json.loads(brut)
    with _verrou:  # ≤ 8 requêtes/s, sous la limite de 10 de la SEC
        attente = 0.125 - (time.time() - _dernier[0])
        if attente > 0:
            time.sleep(attente)
        _dernier[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            brut = r.read().decode("utf-8", errors="replace")
    except Exception:
        if chemin.exists():  # hors ligne : dernière version connue
            brut = chemin.read_text()
            return brut if texte else json.loads(brut)
        raise
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(brut)
    return brut if texte else json.loads(brut)


def tickers() -> dict[str, dict]:
    """TICKER -> {cik, nom}."""
    d = _get("https://www.sec.gov/files/company_tickers.json", 7 * 86400, "company_tickers.json")
    return {v["ticker"].upper().replace("-", "."): {"cik": int(v["cik_str"]), "nom": v["title"]} for v in d.values()}


def cik_de(ticker: str) -> tuple[int, str]:
    t = ticker.upper().replace("-", ".")
    table = tickers()
    if t not in table:
        raise ValueError(f"{ticker} : société absente de l'EDGAR (seules les sociétés cotées aux États-Unis y figurent)")
    return table[t]["cik"], table[t]["nom"]


def _valeurs(faits: dict, balises: list[str], unite: str = "USD") -> list[dict]:
    for b in balises:
        u = faits.get(b, {}).get("units", {}).get(unite)
        if u:
            return u
    return []


def _par_periode(faits: dict, balises: list[str], motif: str, plus_grande: bool) -> dict[str, tuple[float, str]]:
    """Valeur canonique par période (frame EDGAR) en fusionnant les balises : la première balise qui couvre
    la période l'emporte, ou la plus grande valeur si plus_grande (chiffre d'affaires : le total englobe
    les sous-rubriques, et les banques déclarent un « produit net bancaire »)."""
    out: dict[str, tuple[float, str]] = {}
    for b in balises:
        for x in faits.get(b, {}).get("units", {}).get("USD", []):
            f = x.get("frame", "")
            if not re.fullmatch(motif, f):
                continue
            if f not in out or (plus_grande and x["val"] > out[f][0]):
                out[f] = (x["val"], x["end"])
    return out


def comptes(ticker: str) -> dict:
    """Comptes annuels (≤ 15 ans), TTM et dernier bilan d'une société."""
    cik, nom = cik_de(ticker)
    cf = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", 86400, f"facts_{cik}.json")
    faits = cf.get("facts", {}).get("us-gaap", {})
    annees: dict[str, dict] = {}
    for cle, balises in FLUX.items():
        for periode, (val, fin) in _par_periode(faits, balises, r"CY\d{4}", cle == "chiffre_affaires").items():
            a = annees.setdefault(periode[2:], {"fin": fin})
            a[cle] = val
            if cle == "chiffre_affaires":
                a["fin"] = fin
    for x in _valeurs(faits, BPA, "USD/shares"):
        f = x.get("frame", "")
        if re.fullmatch(r"CY\d{4}", f) and f[2:] in annees:
            annees[f[2:]].setdefault("bpa", x["val"])
    # bilans : valeur à la date de clôture de chaque exercice
    for cle, balises in STOCKS.items():
        par_date = {}
        for x in _valeurs(faits, balises):
            if x.get("form") in ("10-K", "10-Q", "10-K/A", "20-F", "40-F"):
                par_date[x["end"]] = x["val"]
        for a in annees.values():
            if a["fin"] in par_date:
                a[cle] = par_date[a["fin"]]
    lignes = [dict(annee=k, **v) for k, v in sorted(annees.items())][-15:]

    def ttm(cle):
        """Douze derniers mois = dernier exercice + trimestres publiés depuis - mêmes trimestres un an plus tôt
        (le 4e trimestre fiscal est rarement publié seul : il est noyé dans le 10-K)."""
        an = _par_periode(faits, FLUX[cle], r"CY\d{4}", cle == "chiffre_affaires")
        if not an:
            return None, None
        base, (v_an, fin_an) = max(an.items(), key=lambda kv: kv[1][1])
        q = _par_periode(faits, FLUX[cle], r"CY\d{4}Q\d", cle == "chiffre_affaires")
        apres = {p: v for p, v in q.items() if v[1] > fin_an}
        total, fin = float(v_an), fin_an
        for p, (v, e) in apres.items():
            avant = f"CY{int(p[2:6]) - 1}Q{p[7]}"
            if avant not in q:
                return float(v_an), fin_an  # trimestre de comparaison manquant : on s'en tient à l'exercice
            total += v - q[avant][0]
            fin = max(fin, e)
        return total, fin

    def dernier(balises):
        v = sorted((x["end"], x["val"]) for x in _valeurs(faits, balises) if x.get("form") in ("10-K", "10-Q", "20-F", "40-F"))
        return (v[-1][1], v[-1][0]) if v else (None, None)

    actions = None
    for b in ("EntityCommonStockSharesOutstanding",):
        v = cf.get("facts", {}).get("dei", {}).get(b, {}).get("units", {}).get("shares", [])
        if v:
            actions = float(sorted(v, key=lambda x: x["end"])[-1]["val"])
    ttm_out = {}
    for cle in ("chiffre_affaires", "resultat_net", "resultat_operationnel", "flux_operationnel", "investissements", "marge_brute"):
        ttm_out[cle], fin = ttm(cle)
        ttm_out["fin"] = ttm_out.get("fin") or fin
    bilan = {cle: dernier(b)[0] for cle, b in STOCKS.items()}
    bilan["date"] = dernier(STOCKS["actif"])[1]
    return {"cik": cik, "nom": cf.get("entityName", nom), "annuel": lignes, "ttm": ttm_out, "bilan": bilan, "actions": actions}


def depots(ticker: str, n: int = 40) -> dict:
    """Profil et dépôts récents (10-K, 10-Q, 8-K, 4…) avec liens vers les documents."""
    cik, nom = cik_de(ticker)
    s = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", 3600, f"sub_{cik}.json")
    r = s["filings"]["recent"]
    out = []
    for i in range(min(len(r["form"]), 400)):
        acc = r["accessionNumber"][i].replace("-", "")
        out.append({"type": r["form"][i], "date": r["filingDate"][i], "description": r.get("primaryDocDescription", [""] * 400)[i] or "",
                    "lien": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{r['primaryDocument'][i]}",
                    "accession": r["accessionNumber"][i], "document": r["primaryDocument"][i], "items": (r.get("items") or [""] * 400)[i]})
    adresse = (s.get("addresses") or {}).get("business") or {}
    return {"cik": cik, "nom": s.get("name", nom), "secteur": s.get("sicDescription"), "sic": s.get("sic"),
            "bourses": s.get("exchanges"), "fin_exercice": s.get("fiscalYearEnd"), "etat": s.get("stateOfIncorporation"),
            "ville": adresse.get("city"), "site": s.get("website") or "", "depots": out[:n], "tous": out}


CODES = {"P": "Achat", "S": "Vente", "A": "Attribution", "M": "Exercice d'options", "F": "Retenue fiscale", "G": "Donation",
         "D": "Cession à l'émetteur", "C": "Conversion", "J": "Autre", "X": "Exercice d'options"}


def _txt(e, chemin):
    x = e.find(chemin)
    return (x.text or "").strip() if x is not None and x.text else ""


def dirigeants(ticker: str, n: int = 25) -> list[dict]:
    """Transactions des dirigeants : les n derniers formulaires 4, analysés depuis leur XML (cache permanent)."""
    d = depots(ticker, 400)
    cik = d["cik"]
    out = []
    for f in [x for x in d["tous"] if x["type"] == "4"][:n]:
        acc = f["accession"].replace("-", "")
        doc = f["document"].split("/")[-1]  # le document principal est une mise en forme XSL du XML brut
        try:
            xml = _get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}", 365 * 86400, f"f4_{acc}.xml", texte=True)
            racine = ET.fromstring(xml)
        except Exception:
            continue
        nom = _txt(racine, "reportingOwner/reportingOwnerId/rptOwnerName")
        rel = racine.find("reportingOwner/reportingOwnerRelationship")
        role = []
        if rel is not None:
            if _txt(rel, "isDirector") in ("1", "true"):
                role.append("Administrateur")
            if _txt(rel, "isOfficer") in ("1", "true"):
                role.append(_txt(rel, "officerTitle") or "Dirigeant")
            if _txt(rel, "isTenPercentOwner") in ("1", "true"):
                role.append("Actionnaire > 10 %")
        for t in racine.findall("nonDerivativeTable/nonDerivativeTransaction"):
            code = _txt(t, "transactionCoding/transactionCode")
            try:
                qte = float(_txt(t, "transactionAmounts/transactionShares/value") or 0)
                prix = float(_txt(t, "transactionAmounts/transactionPricePerShare/value") or 0)
                apres = float(_txt(t, "postTransactionAmounts/sharesOwnedFollowingTransaction/value") or 0)
            except ValueError:
                continue
            sens = _txt(t, "transactionAmounts/transactionAcquiredDisposedCode/value")
            out.append({"date": _txt(t, "transactionDate/value"), "nom": nom.title(), "role": ", ".join(role), "code": code,
                        "type": CODES.get(code, code), "actions": qte if sens == "A" else -qte, "prix": prix,
                        "montant": qte * prix * (1 if sens == "A" else -1), "detenu_apres": apres, "lien": f["lien"]})
    return sorted(out, key=lambda x: x["date"], reverse=True)


def coupe(balise: str, periode: str, unite: str = "USD") -> dict[int, dict]:
    """Une rubrique pour toutes les sociétés sur une période (ex. CY2025 ou CY2025Q4I) : CIK -> {val, fin, nom}."""
    import urllib.error

    try:
        d = _get(f"https://data.sec.gov/api/xbrl/frames/us-gaap/{balise}/{unite}/{periode}.json", 7 * 86400, f"frame_{balise}_{periode}.json")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        nom = CACHE / f"frame_{balise}_{periode}.json"  # balise abandonnée sur la période : coupe vide, mise en cache
        nom.parent.mkdir(parents=True, exist_ok=True)
        nom.write_text('{"data": []}')
        return {}
    return {int(x["cik"]): {"val": x["val"], "fin": x["end"], "nom": x["entityName"]} for x in d.get("data", [])}
