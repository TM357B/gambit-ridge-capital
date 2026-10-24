"""Les campagnes de recherche, mises au même format pour le terminal (/api/campaigns).

Chaque campagne a son protocole commité avant calcul (gambit_ridge/research/campaign*.py) et
son rapport dans data/. Ce module ne recalcule rien : il lit les rapports et les présente.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "data"

META = [
    {"n": 1, "file": "research_campaign_2026-10.json", "titre": "Nouveaux signaux et élargissement de l'univers",
     "question": "Peut-on faire mieux avec plus d'ETF (jusqu'à 50) ou des signaux classiques de la littérature ?",
     "lecon": "Élargir l'univers dégrade : les ETF ajoutés sont corrélés aux actions déjà présentes. La tendance multi-horizons brille sur 2008-2019 puis s'effondre en validation : cas d'école du surapprentissage."},
    {"n": 2, "file": "research_campaign2_2026-10.json", "titre": "Sources de rendement différentes et agents",
     "question": "La volatilité, le carry de taux, la faible volatilité ou les signaux des 6 équipes d'agents ajoutent-ils quelque chose ?",
     "lecon": "Aucune poche ne tient sur les deux périodes. Les agents pris seuls dégradent ; le bug d'agrégation de leurs facteurs a été trouvé et corrigé à cette occasion."},
    {"n": 3, "file": "research_campaign3_2026-10.json", "titre": "Équipe Crypto contre la poche crypto",
     "question": "Les signaux des agents crypto font-ils mieux que la poche crypto de production, à construction identique ?",
     "lecon": "Non : meilleurs sur 2018-2022, moins bons partout depuis 2023, pour trois fois plus de rotation."},
    {"n": 4, "file": "research_campaign4_2026-10.json", "titre": "Construction du portefeuille et exécution",
     "question": "Fréquence de rebalancement, filtre anti micro-trades, taille du socle, contrôle du drawdown : les réglages sont-ils au bon endroit ?",
     "lecon": "Oui. S'en écarter dégrade dans un sens ou dans l'autre. Le rebalancement quotidien ne coûte rien en performance."},
    {"n": 5, "file": "research_campaign5_2026-10.json", "titre": "Période 2002-2007 jamais utilisée",
     "question": "La stratégie tient-elle sur des données qui n'ont servi ni à la concevoir ni à aucun essai ? Les variantes restées neutres y gagnent-elles ?",
     "lecon": "La stratégie tient (Sharpe 1,57, pire baisse -8,9 % contre -33 % pour le S&P 500). Aucune variante ne fait mieux : elle est maintenant validée sur trois périodes indépendantes."},
    {"n": 6, "file": "research_campaign6_2026-10.json", "titre": "Volatilité stochastique pour dimensionner les positions",
     "question": "Un modèle de volatilité stochastique avec levier (filtre particulaire, Dixon et al. ch. 7), calibré sur 2000-2007 seulement, dimensionne-t-il mieux que la GARCH ?",
     "lecon": "Non. Il décrit mieux la volatilité (vraisemblance) mais ne gagne rien en stratégie : Sharpe de développement 0,94 à 0,97 contre 0,99. Mieux prévoir la vol au jour le jour ne change presque pas des poids de risque égal ; le gain statistique ne passe pas dans le portefeuille."},
    {"n": 7, "file": "research_campaign7_2026-10.json", "titre": "Règles d'entrée, de sortie et sens des positions",
     "question": "Des cassures de Donchian, des stops suiveurs, une zone neutre, une hystérésis, le long seul ou l'interdiction de vendre des actions font-ils mieux que le signal continu de production ?",
     "lecon": "Non. Les stops coupent les tendances trop tôt (Sharpe de développement 0,62 à 0,87) ; zone neutre et hystérésis font jeu égal (1,02-1,03 contre 0,99, sous le seuil de +0,05) et moins bien sur 2001-2007. Supprimer les ventes à découvert fait monter la pire baisse de validation de -10 % à -17 % : les positions vendeuses servent de couverture."},
]


def _m(d: dict | None) -> dict | None:
    return None if not d else {"sharpe": d.get("sharpe"), "cagr": d.get("cagr"), "max_dd": d.get("max_dd"), "turnover": d.get("turnover_annuel")}


def campaigns() -> dict:
    out = []
    for meta in META:
        path = DATA / meta["file"]
        if not path.exists():
            continue
        rep = json.loads(path.read_text())
        res = rep["resultats"]
        ref_key = next((k for k in ("REF", "C0") if k in res), None)
        trials, curves = [], []
        for key, r in res.items():
            single = "mesure" in r  # campagne 5 : une seule période (échantillon neuf)
            ref = res.get(ref_key) if ref_key else None
            row = {"code": key, "nom": r["nom"], "description": r.get("description", ""),
                   "role": r.get("role") or ("référence" if key == ref_key else "essai"),
                   "dev": _m(r.get("mesure") if single else r.get("developpement")),
                   "val": None if single else _m(r.get("validation")),
                   # campagne 2 : la référence est mesurée sur les mêmes jours que chaque essai
                   "ref_dev": _m((r.get("reference") or {}).get("developpement")) or (_m(ref.get("mesure") if single else ref.get("developpement")) if ref else None),
                   "ref_val": _m((r.get("reference") or {}).get("validation")) or (None if single or not ref else _m(ref.get("validation"))),
                   "dsr": r.get("dsr_developpement", r.get("dsr")), "criteres": r.get("criteres"), "verdict": r.get("verdict")}
            trials.append(row)
            if r.get("courbe") and (single or key == ref_key):
                curves.append({"nom": r["nom"], "dates": r["courbe"]["dates"], "equity": r["courbe"]["equity"], "ref": key == ref_key})
        tested = [t for t in trials if t["verdict"]]
        out.append({**{k: meta[k] for k in ("n", "titre", "question", "lecon")}, "date": rep.get("genere_le"),
                    "periode_unique": any("mesure" in r for r in res.values()),
                    "debut": rep.get("debut_mesure"), "fin": rep.get("fin"),
                    "n_essais": len(tested), "n_acceptes": sum(t["verdict"] == "ACCEPTÉ" for t in tested),
                    "essais": trials, "courbes": curves, "regles": rep.get("regles"), "protocole": rep.get("protocole", "")})
    total = sum(c["n_essais"] for c in out)
    costs = DATA / "cost_sensitivity.json"
    return {"campagnes": out, "total_essais": total, "total_acceptes": sum(c["n_acceptes"] for c in out),
            "couts": json.loads(costs.read_text()) if costs.exists() else None}
