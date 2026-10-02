"""Rôles des desks d'agents (version publique : rôles, pas de personnes)."""

MANAGERS = {
    'manager-Macro': 'Responsable desk Macro',
    'manager-Micro': 'Responsable desk Micro',
    'manager-IA & Tech': 'Responsable desk IA & Tech',
    'manager-Commodities': 'Responsable desk Commodities',
    'manager-Crypto 24/7': 'Responsable desk Crypto 24/7',
    'manager-Forex': 'Responsable desk Forex',
    'manager-RH': 'Responsable desk RH',
}

STAFF = {
    'macro-dm': ('Analyste — Régimes de taux et cycles économiques développés', "—", 'régimes de taux et cycles économiques développés'),
    'macro-em': ('Analyste — Macro émergents, flux de capitaux', "—", 'macro émergents, flux de capitaux'),
    'micro-dm': ('Analyste — Microstructure, actions développées', "—", 'microstructure, actions développées'),
    'micro-em': ('Analyste — Actions émergentes, risques pays', "—", 'actions émergentes, risques pays'),
    'ia-semi-conducteurs': ('Analyste — Chaîne de valeur semi-conducteurs', "—", 'chaîne de valeur semi-conducteurs'),
    'ia-datacenters-infra': ('Analyste — Infra datacenters et REITs tech', "—", 'infra datacenters et REITs tech'),
    'ia-cloud-hyperscalers': ('Analyste — Cloud, capex IA et hyperscalers', "—", 'cloud, capex IA et hyperscalers'),
    'ia-modeles-applications': ('Analyste — Éditeurs de modèles et applications IA', "—", 'éditeurs de modèles et applications IA'),
    'commodity-gld': ('Analyste — Métaux précieux, or physique', "—", 'métaux précieux, or physique'),
    'commodity-slv': ('Analyste — Argent industriel', "—", 'argent industriel'),
    'commodity-uso': ('Analyste — Pétrole WTI, term structure', "—", 'pétrole WTI, term structure'),
    'commodity-bno': ('Analyste — Pétrole Brent, freight', "—", 'pétrole Brent, freight'),
    'commodity-ung': ('Analyste — Gaz naturel, saisonnalité', "—", 'gaz naturel, saisonnalité'),
    'commodity-cper': ('Analyste — Cuivre et métaux de transition', "—", 'cuivre et métaux de transition'),
    'crypto-btc': ('Analyste — BTC, flux on-chain', "—", 'BTC, flux on-chain'),
    'crypto-eth': ('Analyste — ETH, finance décentralisée', "—", 'ETH, finance décentralisée'),
    'crypto-sol': ('Analyste — Solana, écosystème DeFi', "—", 'Solana, écosystème DeFi'),
    'crypto-bnb': ('Analyste — BNB, écosystème BNB Chain', "—", 'BNB, écosystème BNB Chain'),
    'crypto-xrp': ('Analyste — XRP, paiements institutionnels', "—", 'XRP, paiements institutionnels'),
    'crypto-ada': ('Analyste — Cardano, gouvernance on-chain', "—", 'Cardano, gouvernance on-chain'),
    'crypto-avax': ('Analyste — Avalanche, subnets', "—", 'Avalanche, subnets'),
    'crypto-doge': ('Analyste — Meme coins, psychologie de marché', "—", 'meme coins, psychologie de marché'),
    'fx-eurusd': ('Analyste — EUR/USD, différentiel de taux', "—", 'EUR/USD, différentiel de taux'),
    'fx-usdjpy': ('Analyste — USD/JPY, carry et BoJ', "—", 'USD/JPY, carry et BoJ'),
    'fx-gbpusd': ('Analyste — GBP/USD, événements politiques', "—", 'GBP/USD, événements politiques'),
    'fx-audusd': ('Analyste — AUD/USD, matières premières', "—", 'AUD/USD, matières premières'),
    'fx-usdchf': ('Analyste — USD/CHF, refuge et SNB', "—", 'USD/CHF, refuge et SNB'),
    'fx-usdcad': ('Analyste — USD/CAD, pétrole et BoC', "—", 'USD/CAD, pétrole et BoC'),
    'rh-analyste-performance': ('Analyste — Mesure de contribution des agents', "—", 'mesure de contribution des agents'),
    'rh-analyste-competences': ('Analyste — Cartographie des compétences', "—", 'cartographie des compétences'),
    'rh-analyste-talent': ('Analyste — Détection et recrutement de talents', "—", 'détection et recrutement de talents'),
    "gerant": ("Gérant", "—", "vision et décision finale"),
}

RECRUIT_POOL: list[dict] = []

def display_name(agent_id: str) -> str:
    """Nom d'affichage d'un employé à partir de son id."""
    if agent_id in STAFF:
        return STAFF[agent_id][0]
    if agent_id in MANAGERS:
        return MANAGERS[agent_id]
    return agent_id


def profile(agent_id: str) -> dict:
    """Profil complet (nom, école, spécialité) d'un employé."""
    if agent_id in STAFF:
        name, school, specialty = STAFF[agent_id]
        return {"name": name, "school": school, "specialty": specialty}
    if agent_id in MANAGERS:
        return {"name": MANAGERS[agent_id], "school": "—", "specialty": "management"}
    return {"name": agent_id, "school": "—", "specialty": "—"}
