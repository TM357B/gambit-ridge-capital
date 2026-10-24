"""FA — fiche financière d'une société cotée aux États-Unis (comptes SEC EDGAR + cours Yahoo).

Comptes annuels sur 15 ans, douze derniers mois (TTM), bilan le plus récent, ratios de
valorisation, dépôts récents (10-K, 10-Q, 8-K…) et transactions des dirigeants (formulaires 4).
"""

from __future__ import annotations

from datetime import date, timedelta


def _div(a, b):
    try:
        return a / b if a is not None and b not in (None, 0) else None
    except TypeError:
        return None


def fa(ticker: str) -> dict:
    from ..data import edgar
    from ..data.yahoo_options import cotations

    t = ticker.upper()
    c = edgar.comptes(t)
    d = edgar.depots(t, 400)
    yahoo = t.replace(".", "-")
    q = cotations([yahoo]).get(yahoo, {})
    prix, cap = q.get("prix"), q.get("capitalisation")
    if cap is None and prix and c.get("actions"):
        cap = prix * c["actions"]

    annuel = []
    prec = None
    for a in c["annuel"]:
        ca, rn = a.get("chiffre_affaires"), a.get("resultat_net")
        fcf = None if a.get("flux_operationnel") is None else a["flux_operationnel"] - (a.get("investissements") or 0)
        dette = (a.get("dette_lt") or 0) + (a.get("dette_ct") or 0) if (a.get("dette_lt") is not None or a.get("dette_ct") is not None) else None
        annuel.append({"annee": a["annee"], "fin": a["fin"], "chiffre_affaires": ca, "resultat_net": rn, "bpa": a.get("bpa"),
                       "marge_brute": _div(a.get("marge_brute"), ca), "marge_operationnelle": _div(a.get("resultat_operationnel"), ca),
                       "marge_nette": _div(rn, ca), "fcf": fcf, "capitaux_propres": a.get("capitaux_propres"), "actif": a.get("actif"),
                       "dette": dette, "tresorerie": a.get("tresorerie"), "roe": _div(rn, a.get("capitaux_propres")),
                       "croissance_ca": _div(ca, prec) - 1 if ca and prec else None, "r_et_d": a.get("r_et_d"),
                       "dividendes": a.get("dividendes"), "rachats": a.get("rachats")})
        prec = ca or prec

    tt, b = c["ttm"], c["bilan"]
    dette = None if b.get("dette_lt") is None and b.get("dette_ct") is None else (b.get("dette_lt") or 0) + (b.get("dette_ct") or 0)
    fcf_ttm = None if tt.get("flux_operationnel") is None else tt["flux_operationnel"] - (tt.get("investissements") or 0)
    ve = None if cap is None else cap + (dette or 0) - (b.get("tresorerie") or 0)
    ratios = {"per": _div(cap, tt.get("resultat_net")) if (tt.get("resultat_net") or 0) > 0 else None,
              "prix_ventes": _div(cap, tt.get("chiffre_affaires")), "prix_valeur_comptable": _div(cap, b.get("capitaux_propres")),
              "rendement_fcf": _div(fcf_ttm, cap), "ve_ebit": _div(ve, tt.get("resultat_operationnel")) if (tt.get("resultat_operationnel") or 0) > 0 else None,
              "roe": _div(tt.get("resultat_net"), b.get("capitaux_propres")), "marge_nette": _div(tt.get("resultat_net"), tt.get("chiffre_affaires")),
              "marge_operationnelle": _div(tt.get("resultat_operationnel"), tt.get("chiffre_affaires")),
              "dette_fp": _div(dette, b.get("capitaux_propres")), "liquidite": b.get("tresorerie"), "dette": dette, "valeur_entreprise": ve}

    try:
        ins = edgar.dirigeants(t, 30)
    except Exception:
        ins = []
    limite = (date.today() - timedelta(days=183)).isoformat()
    marche = [x for x in ins if x["code"] in ("P", "S") and x["date"] >= limite]  # achats / ventes en bourse seulement
    achats = sum(x["montant"] for x in marche if x["code"] == "P")
    ventes = -sum(x["montant"] for x in marche if x["code"] == "S")
    importants = ("10-K", "10-Q", "8-K", "20-F", "6-K", "DEF 14A", "S-1", "SC 13G", "SC 13D", "10-K/A", "8-K/A")
    return {"ticker": t, "nom": c["nom"], "profil": {k: d.get(k) for k in ("secteur", "sic", "bourses", "fin_exercice", "etat", "ville", "site")},
            "cik": c["cik"], "cours": prix, "capitalisation": cap, "devise": q.get("devise") or "USD", "variation_jour": q.get("variation_jour"),
            "plus_haut_52s": q.get("plus_haut_52s"), "plus_bas_52s": q.get("plus_bas_52s"),
            "annuel": annuel, "ttm": {**tt, "fcf": fcf_ttm}, "bilan": b, "ratios": ratios, "actions": c.get("actions"),
            "historique_court": len(annuel) < 3,
            "depots": [x for x in d["tous"] if x["type"] in importants][:20],
            "dirigeants": ins[:40], "dirigeants_6m": {"achats": achats, "ventes": ventes, "net": achats - ventes,
                                                     "acheteurs": len({x["nom"] for x in marche if x["code"] == "P"}),
                                                     "vendeurs": len({x["nom"] for x in marche if x["code"] == "S"})},
            "source": "SEC EDGAR (XBRL des 10-K / 10-Q, formulaires 4) · cours Yahoo"}
