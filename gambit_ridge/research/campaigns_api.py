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
    {"n": 8, "file": "research_campaign8_2026-10.json", "titre": "Diversification : socle en parité de risque et effets de calendrier",
     "question": "Un socle « All Weather » (actions, obligations, indexées, or, matières premières à risque égal) ou une source de rendement liée au calendrier (tournant de mois, veilles de fériés, Sell in May) améliorent-ils le fonds ?",
     "lecon": "Non. Le socle en parité de risque fait mieux sur 2001-2007 (1,71 contre 1,57, années de flambée des matières premières) mais nettement moins bien ensuite (0,72-0,76 contre 0,99) : les matières premières ont pesé et le 60/40 a profité des actions américaines. Les effets de calendrier ne rapportent plus rien depuis 2008 (poches seules : Sharpe -0,13 à -0,01) : effets publiés dans les années 1990, arbitrés depuis."},
    {"n": 9, "file": "research_campaign9_2026-10.json", "titre": "Diversification par classes d'actifs et niveau de risque",
     "question": "Donner la même part de risque à chaque classe (actions, obligations, matières premières, devises), et ajouter 10 ETF hors actions (gaz, pétrole, métaux, essence, 4 devises, obligations hors US et émergentes), fait-il mieux ? Et quel rendement à quel risque si l'on augmente l'exposition ?",
     "lecon": "Rejeté. Le budget par classe fait mieux en validation (Sharpe 1,16 contre 1,06, pire baisse -7,9 % contre -10,3 %) et sur 2001-2007, mais moins bien en développement (1,20 contre 1,24) : sous le seuil. Les 10 ETF ajoutés n'apportent rien (paniers trop corrélés). Menu de risque : même à 3 fois l'exposition, 13,2 %/an pour une pire baisse de -34 % ; les intérêts d'emprunt font baisser le Sharpe de 0,92 à 0,71. 15 %/an avec un risque contenu exige une nouvelle source de rendement, pas plus de levier."},
    {"n": 10, "file": "research_campaign10_2026-10.json", "titre": "Deuxième source : 52 marchés à terme en données gratuites",
     "question": "La même tendance, appliquée à 52 marchés à terme peu corrélés (24 matières premières, 4 taux américains, 12 devises, 13 indices actions mondiaux), avec un budget de risque par classe et éventuellement le portage des devises et des taux, apporte-t-elle la source de rendement qui manque ?",
     "lecon": "Non, pas sur 2008-2019. Seul, le programme contrats à terme ne fait que Sharpe 0,19 (1,5 %/an, pire baisse -27 %) en développement, 0,40 depuis 2020 : la décennie difficile des fonds « managed futures ». Mis à la place de la couche tendance ETF, il dégrade le fonds (0,71 contre 0,99) ; à parts égales avec elle, il fait presque jeu égal (0,92, validation 1,01) sans gain. Le portage n'aide pas. Les données gratuites exigent de lourdes corrections (changements d'échéance) : un test sans dérive des matières premières confirme le verdict. Leçon pratique du menu : en contrats à terme, sans intérêts d'emprunt, la production elle-même atteint 14 %/an à 2,5x et 16 % à 3x, pour une pire baisse de -28 % et -34 %."},
    {"n": 11, "file": "research_campaign11_2026-10.json", "titre": "Production en contrats à terme à 2 / 2,5x et limiteurs de baisse",
     "question": "Que donne la production actuelle mise en contrats à terme à 2 ou 2,5 fois l'exposition, avec la grille publique d'Interactive Brokers (commissions, taux d'emprunt, dépôt de garantie) ? Et réduire l'exposition quand le fonds baisse limite-t-il la pire baisse sans trop coûter ?",
     "lecon": "En contrats à terme (11 des 20 ETF ont un équivalent), 2x rapporte 11,3 %/an pour une pire baisse de -24 %, 2,5x 13,5 % pour -29 % (tout en ETF : 9,3 % et 10,6 %, à cause des intérêts d'emprunt). Le dépôt de garantie immobilise 44 % de l'actif net en médiane à 2,5x, 60 % au pire : jamais d'appel de marge, même avec des marges doublées en crise. Mais il faut un compte assez gros : à 100 000 $, l'arrondi au contrat près fausse les positions de 33 % en moyenne (écart de suivi 2,6 %/an), 1 000 000 $ pour descendre à 0,5 %. Les trois limiteurs sont rejetés : réduire selon la baisse retire 8 points de pire baisse mais coûte 3,4 points de rendement, moins bien que de viser 2x directement ; le filtre de tendance coupe 2008 (-15 % au lieu de -29 %) mais coûte du rendement ; viser la volatilité ne réduit pas la pire baisse."},
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
