"""API des agents : inspecter et interroger chaque agent de chaque équipe."""

from __future__ import annotations

import numpy as np

from .core.agent import MarketData
from .data.simulation import all_configured_tickers, simulate_market_data
from .demo import _real_data
from .teams import (
    build_commodities_team,
    build_crypto_team,
    build_forex_team,
    build_ia_tech_team,
    build_macro_team,
    build_micro_team,
)

TEAM_BUILDERS = {
    "Macro": build_macro_team,
    "Micro": build_micro_team,
    "Crypto": build_crypto_team,
    "Forex": build_forex_team,
    "Commodities": build_commodities_team,
    "IA & Tech": build_ia_tech_team,
}


_DATA_CACHE: dict[str, MarketData] = {}
_DATA_CACHE_AT: float = 0.0
_DATA_TTL = 900.0  # 15 minutes : les données sont réutilisées entre les clics


def _merged_data(force: bool = False) -> dict[str, MarketData]:
    """Données fusionnées, en cache mémoire 15 min pour des clics instantanés."""
    import time as _time

    global _DATA_CACHE, _DATA_CACHE_AT
    now = _time.time()
    if not force and _DATA_CACHE and (now - _DATA_CACHE_AT) < _DATA_TTL:
        return _DATA_CACHE
    from .data.real_market import load_agent_market_data

    merged, _sources = load_agent_market_data()
    _DATA_CACHE = merged
    _DATA_CACHE_AT = now
    return merged


def get_agents_roster() -> list[dict]:
    """La liste complète des agents, groupés par équipe et manager."""
    from .staff import display_name, profile
    roster = []
    for team_name, builder in TEAM_BUILDERS.items():
        manager = builder() if team_name != "Macro" else builder(None)
        mgr_id = f"manager-{team_name}"
        roster.append(
            {
                "team": team_name,
                "manager": display_name(mgr_id),
                "manager_id": mgr_id,
                "n_agents": len(manager.agents),
                "agents": [
                    {
                        "id": a.name,
                        "name": display_name(a.name),
                        "school": profile(a.name)["school"],
                        "specialty": profile(a.name)["specialty"],
                        "scope": a.scope,
                        "tickers": list(a.universe()),
                    }
                    for a in manager.agents
                ],
            }
        )
    return roster


def _find_agent(agent_id: str):
    for team_name, builder in TEAM_BUILDERS.items():
        manager = builder() if team_name != "Macro" else builder(None)
        for agent in manager.agents:
            if agent.name == agent_id:
                return agent, manager, team_name
    raise ValueError(f"agent inconnu: {agent_id}")


_DETAILS_CACHE: dict[str, tuple[float, dict]] = {}


def get_agent_details(agent_id: str, data: dict[str, MarketData] | None = None) -> dict:
    import time as _time

    global _DETAILS_CACHE
    if data is None:
        cached = _DETAILS_CACHE.get(agent_id)
        if cached and (_time.time() - cached[0]) < 900.0:
            return cached[1]
    agent, manager, team_name = _find_agent(agent_id)
    data = data or _merged_data()
    report = agent.analyze({t: data[t] for t in agent.universe() if t in data})

    ticker_stats = []
    for tk in agent.universe():
        md = data.get(tk)
        if not md or not md.prices:
            continue
        prices = np.asarray(md.prices, dtype=float)
        stats = {"ticker": tk, "price": float(prices[-1])}
        if len(prices) > 61:
            stats["ret_20d"] = float(prices[-1] / prices[-21] - 1)
            stats["ret_60d"] = float(prices[-1] / prices[-61] - 1)
            stats["vol_annual"] = float(
                np.std(np.diff(np.log(prices[-61:])), ddof=1) * np.sqrt(252)
            )
        ticker_stats.append(stats)

    from .staff import display_name, profile
    prof = profile(agent.name)
    result = {
        "id": agent.name,
        "name": prof["name"],
        "school": prof["school"],
        "specialty": prof["specialty"],
        "scope": agent.scope,
        "team": team_name,
        "manager": display_name(f"manager-{team_name}"),
        "tickers": list(agent.universe()),
        "signals": [s.to_dict() for s in report.signals],
        "ticker_stats": ticker_stats,
        "summary": report.summary if hasattr(report, "summary") else "",
    }
    if data is None:
        _DETAILS_CACHE[agent_id] = (_time.time(), result)
    return result


def ask_agent(agent_id: str, question: str, data: dict[str, MarketData] | None = None) -> dict:
    details = get_agent_details(agent_id, data)
    q = question.lower()

    active = [
        f"{s['ticker']} {s['direction']} (conviction {s['conviction']:.0%}, score {s['score']:+.2f})"
        for s in details["signals"]
    ]
    stats = {s["ticker"]: s for s in details["ticker_stats"]}

    if any(k in q for k in ("performance", "rendement", "retour", "evolution")):
        lines = [
            f"{s['ticker']}: {s.get('ret_20d', 0):+.1%} sur 20 j, {s.get('ret_60d', 0):+.1%} sur 60 j"
            for s in details["ticker_stats"]
        ]
        answer = "Performances sous surveillance : " + " ; ".join(lines)
    elif any(k in q for k in ("volatilit", "risque")):
        lines = [
            f"{s['ticker']}: {s.get('vol_annual', 0):.0%} annualisée"
            for s in details["ticker_stats"]
        ]
        answer = "Volatilité mesurée : " + " ; ".join(lines)
    elif any(k in q for k in ("signal", "position", "avis", "conseil", "recommand")):
        answer = "Signaux actuels : " + (" ; ".join(active) if active else "aucun signal actif")
    elif any(k in q for k in ("qui", "role", "rôle", "mission", "present")):
        answer = (
            f"Agent {details['scope']} de l'équipe {details['team']}, "
            f"sous la responsabilité du manager {details['manager']}. "
            f"Périmètre : {', '.join(details['tickers'])}."
        )
    else:
        answer = (
            f"{details['scope']}. Je surveille {', '.join(details['tickers'])}. "
            + ("Signaux actuels : " + " ; ".join(active) if active else "Aucun signal actif.")
        )
    return {"agent": agent_id, "question": question, "answer": answer}


def get_manager_reports() -> list[dict]:
    """Rapports des managers : le travail détaillé de chaque agent."""
    data = _merged_data()
    reports = []
    for team_name, builder in TEAM_BUILDERS.items():
        manager = builder() if team_name != "Macro" else builder(None)
        synthesis = manager.run(
            {t: d for t, d in data.items() if t in {tk for a in manager.agents for tk in a.universe()}}
        )
        agents_work = []
        for agent in manager.agents:
            scoped = {t: d for t, d in data.items() if t in agent.universe()}
            if not scoped:
                continue
            report = agent.analyze(scoped)
            agents_work.append(
                {
                    "agent": agent.name,
                    "scope": agent.scope,
                    "tickers": list(agent.universe()),
                    "signals": [s.to_dict() for s in report.signals],
                }
            )
        reports.append(
            {
                "team": team_name,
                "manager": manager.team,
                "headline": synthesis.headline,
                "top_signals": [s.to_dict() for s in synthesis.top_signals],
                "agents": agents_work,
            }
        )
    return reports


# ================== MANAGERS CLICABLES ==================

def get_manager_details(manager_id: str, data: dict[str, MarketData] | None = None) -> dict:
    """Compte-rendu détaillé d'un manager : synthèse + travail de chaque agent + avis RH."""
    from .staff import display_name
    data = data or _merged_data()
    # manager_id est de la forme "manager-<team>" ou juste "<team>"
    team_name = manager_id.replace("manager-", "", 1) if manager_id.startswith("manager-") else manager_id
    if team_name not in TEAM_BUILDERS:
        # essai insensible à la casse/espaces
        for tn in TEAM_BUILDERS:
            if tn.lower().replace(" ", "-") == team_name.lower().replace(" ", "-"):
                team_name = tn
                break
        else:
            raise ValueError(f"manager inconnu: {manager_id}")
    builder = TEAM_BUILDERS[team_name]
    manager = builder() if team_name != "Macro" else builder(None)
    team_data = {t: d for t, d in data.items() if t in {tk for a in manager.agents for tk in a.universe()}}
    synthesis = manager.run(team_data)
    agents_work = []
    for agent in manager.agents:
        scoped = {t: d for t, d in data.items() if t in agent.universe()}
        if not scoped:
            continue
        report = agent.analyze(scoped)
        sigs = [s.to_dict() for s in report.signals]
        agents_work.append({
            "agent": agent.name,
            "scope": agent.scope,
            "tickers": list(agent.universe()),
            "signals": sigs,
            "n_signals": len(sigs),
            "mean_score": round(sum(s["score"] for s in sigs) / max(len(sigs), 1), 3),
            "summary": report.summary,
        })
    # Données RH de l'équipe
    hr_team = _hr_team_view(team_name)
    return {
        "id": f"manager-{team_name}",
        "team": team_name,
        "manager_name": display_name(f"manager-{team_name}"),
        "headline": synthesis.headline,
        "aggregate_score": synthesis.aggregate_score,
        "top_signals": [s.to_dict() for s in synthesis.top_signals],
        "watchlist": synthesis.watchlist,
        "agents": agents_work,
        "hr": hr_team,
    }


def ask_manager(manager_id: str, question: str, data: dict[str, MarketData] | None = None) -> dict:
    """Le manager répond à une question sur son équipe."""
    details = get_manager_details(manager_id, data)
    q = question.lower()
    n_sig = sum(a["n_signals"] for a in details["agents"])
    if any(k in q for k in ("nouveau", "nouveauté", "actu", "info", "quoi de neuf", "brief")):
        lines = []
        for a in details["agents"]:
            if a["n_signals"]:
                best = max(a["signals"], key=lambda s: abs(s["score"]))
                lines.append(f"{a['agent']}: {best['ticker']} {best['direction']} (score {best['score']:+.2f})")
            else:
                lines.append(f"{a['agent']}: rien de nouveau aujourd'hui")
        answer = f"Nouveautés de l'équipe {details['team']} — {n_sig} signaux actifs. " + " ; ".join(lines)
    elif any(k in q for k in ("signal", "position", "top")):
        top = details["top_signals"]
        answer = "Signaux principaux : " + (
            " ; ".join(f"{s['ticker']} {s['direction']} (score {s['score']:+.2f})" for s in top)
            if top else "aucun signal fort aujourd'hui"
        )
    elif any(k in q for k in ("équipe", "team", "agent", "effectif")):
        answer = (
            f"Mon équipe compte {len(details['agents'])} agents : "
            + ", ".join(a["agent"] for a in details["agents"])
            + f". Contribution RH moyenne : {details['hr'].get('mean_contribution', 0):+.2f}."
        )
    elif any(k in q for k in ("risque", "volatilit")):
        answer = f"Score agrégé de l'équipe : {details['aggregate_score']:+.2f}. Watchlist : {', '.join(details['watchlist']) or 'vide'}."
    else:
        answer = (
            f"Manager de l'équipe {details['team']}. Synthèse : {details['headline']} "
            f"{n_sig} signaux actifs sur {len(details['agents'])} agents."
        )
    return {"manager": details["id"], "question": question, "answer": answer}


# ================== POLE RH ==================

def _hr_team_view(team_name: str) -> dict:
    """Vue RH d'une équipe : contributions, salaires, promotions."""
    from . import hr as hr_mod
    org = hr_mod.load_org() or []
    members = [e for e in org if e.team == team_name]
    if not members:
        return {"employees": [], "mean_contribution": 0.0, "payroll": 0.0}
    return {
        "employees": [e.to_dict() for e in members],
        "mean_contribution": round(sum(e.contribution for e in members) / len(members), 3),
        "payroll": round(sum(e.total_comp() for e in members), 1),
    }


def get_hr_overview() -> dict:
    """Vue RH complète : organigramme, masse salariale, pôle RH, décisions récentes."""
    from . import hr as hr_mod
    org = hr_mod.load_org()
    if not org:
        roster = get_agents_roster()
        org = hr_mod.build_initial_org(roster)
        hr_mod.save_org(org)
    teams = []
    for team_name in list(TEAM_BUILDERS):
        members = [e for e in org if e.team == team_name]
        if not members:
            continue
        teams.append({
            "team": team_name,
            "score": 0.0,
            "coverage_gaps": [],
            "employees": [e.to_dict() for e in members],
        })
    dept = hr_mod.HRDepartment()
    from .staff import MANAGERS, RECRUIT_POOL, display_name
    dept.hr_agents = [
        {**a, "name": display_name(a["id"]), "id": a["id"], "scope": a["scope"]}
        for a in dept.hr_agents
    ]
    # Mise à jour des contributions à partir des vrais signaux du jour
    reports = get_manager_reports()
    hr_mod.update_contributions(org, reports)
    # Noms d'affichage pour tout l'organigramme
    for e in org:
        e.name = display_name(e.id) if e.id in ("gerant",) or e.id.startswith("manager-") else (display_name(e.id) if display_name(e.id) != e.id else e.name)
    hr_mod.save_org(org)
    weekly = dept.weekly_report({"teams": teams})
    gerant = next((e for e in org if e.role == "gerant"), None)
    # Vivier de recrutement actif (RH + managers)
    recruit_pool = [
        {**c, "sponsor": MANAGERS.get(f"manager-{c['target_team']}", "—")}
        for c in RECRUIT_POOL
    ]
    return {
        "org": [e.to_dict() for e in org],
        "n_employees": len(org),
        "hr_agents": dept.hr_agents,
        "manager_rh": {
            "id": "manager-rh",
            "name": display_name("manager-RH"),
            "scope": "dirige le pôle RH (3 analystes), rapport hebdomadaire au gérant le vendredi",
            "salary": hr_mod.SALARY_GRID["manager_rh"],
        },
        "weekly_report": weekly,
        "recruit_pool": recruit_pool,
        "gerant": gerant.to_dict() if gerant else None,
        "meeting_day": "vendredi",
    }


# ---------------------------------------------------------------------------
# Globe 3D : localisation géographique des trouvailles des agents (v20)
# ---------------------------------------------------------------------------

_TICKER_GEO: dict[str, tuple[float, float]] = {
    # Amérique du Nord
    "SPY": (40.7, -74.0), "US10Y": (38.9, -77.0), "DXY": (38.9, -77.0),
    "AAPL": (37.3, -122.0), "MSFT": (47.4, -122.3), "GOOGL": (37.4, -122.1),
    "META": (37.5, -122.3), "AMZN": (47.3, -122.2), "NVDA": (37.4, -121.9),
    "AMD": (30.3, -97.7), "MU": (37.3, -121.9), "AVGO": (34.1, -118.5),
    "ORCL": (37.4, -122.1), "PLTR": (37.4, -122.1), "ANET": (37.3, -122.0),
    "CRWV": (40.7, -74.0), "MSTR": (38.9, -77.0), "DLR": (37.4, -122.2),
    "EQIX": (37.5, -122.3), "GLD": (40.7, -74.0), "SLV": (40.7, -74.0),
    "USO": (40.7, -74.0), "UNG": (40.7, -74.0), "CPER": (40.7, -74.0),
    "BNO": (40.7, -74.0), "USDCAD": (43.7, -79.4), "USDCHF": (47.4, 8.5),
    # Europe
    "EZU": (50.9, 6.9), "DAX": (50.1, 8.7), "ASML": (51.4, 5.5),
    "SAP": (49.2, 8.7), "MC.PA": (48.9, 2.3), "AI.PA": (48.9, 2.3),
    "EURUSD": (50.1, 8.7), "GBPUSD": (51.5, -0.1),
    # Asie / Pacifique
    "N225": (35.7, 139.7), "7203.T": (35.7, 139.7), "MCHI": (31.2, 121.5),
    "USDCNH": (31.2, 121.5), "TCEHY": (22.5, 114.1), "BABA": (30.3, 120.2),
    "INFY": (12.97, 77.6), "INDA": (28.6, 77.2), "USDJPY": (35.7, 139.7),
    "AUDUSD": (-33.9, 151.2), "VALE": (-22.9, -43.2), "BRL": (-15.8, -47.9),
    "TSM": (25.0, 121.6), "EEM": (40.7, -74.0),
    # Émergents & Moyen-Orient
    "MCHI_E": (0, 0),
    # Crypto : sans frontière — réparti en arc au-dessus de l'Atlantique
    "BTC": (35.0, -40.0), "ETH": (30.0, -35.0), "SOL": (25.0, -45.0),
    "BNB": (20.0, -30.0), "XRP": (40.0, -35.0), "ADA": (15.0, -40.0),
    "AVAX": (10.0, -45.0), "DOGE": (5.0, -30.0),
}

_TICKER_GEO_LABEL: dict[str, tuple[str, str]] = {
    "SPY": ("États-Unis", "Amérique du Nord"), "US10Y": ("États-Unis", "Amérique du Nord"),
    "DXY": ("États-Unis", "Amérique du Nord"), "AAPL": ("États-Unis", "Amérique du Nord"),
    "MSFT": ("États-Unis", "Amérique du Nord"), "GOOGL": ("États-Unis", "Amérique du Nord"),
    "META": ("États-Unis", "Amérique du Nord"), "AMZN": ("États-Unis", "Amérique du Nord"),
    "NVDA": ("États-Unis", "Amérique du Nord"), "AMD": ("États-Unis", "Amérique du Nord"),
    "MU": ("États-Unis", "Amérique du Nord"), "AVGO": ("États-Unis", "Amérique du Nord"),
    "ORCL": ("États-Unis", "Amérique du Nord"), "PLTR": ("États-Unis", "Amérique du Nord"),
    "ANET": ("États-Unis", "Amérique du Nord"), "CRWV": ("États-Unis", "Amérique du Nord"),
    "MSTR": ("États-Unis", "Amérique du Nord"), "DLR": ("États-Unis", "Amérique du Nord"),
    "EQIX": ("États-Unis", "Amérique du Nord"), "GLD": ("États-Unis", "Amérique du Nord"),
    "SLV": ("États-Unis", "Amérique du Nord"), "USO": ("États-Unis", "Amérique du Nord"),
    "UNG": ("États-Unis", "Amérique du Nord"), "CPER": ("États-Unis", "Amérique du Nord"),
    "BNO": ("États-Unis", "Amérique du Nord"), "EEM": ("Monde émergent", "Global"),
    "USDCAD": ("Canada", "Amérique du Nord"), "USDCHF": ("Suisse", "Europe"),
    "EZU": ("Zone euro", "Europe"), "DAX": ("Allemagne", "Europe"),
    "ASML": ("Pays-Bas", "Europe"), "SAP": ("Allemagne", "Europe"),
    "MC.PA": ("France", "Europe"), "AI.PA": ("France", "Europe"),
    "EURUSD": ("Zone euro", "Europe"), "GBPUSD": ("Royaume-Uni", "Europe"),
    "N225": ("Japon", "Asie-Pacifique"), "7203.T": ("Japon", "Asie-Pacifique"),
    "USDJPY": ("Japon", "Asie-Pacifique"), "MCHI": ("Chine", "Asie-Pacifique"),
    "MCHI_E": ("Chine", "Asie-Pacifique"), "USDCNH": ("Chine", "Asie-Pacifique"),
    "TCEHY": ("Chine", "Asie-Pacifique"), "BABA": ("Chine", "Asie-Pacifique"),
    "TSM": ("Taïwan", "Asie-Pacifique"), "INFY": ("Inde", "Asie-Pacifique"),
    "INDA": ("Inde", "Asie-Pacifique"), "AUDUSD": ("Australie", "Asie-Pacifique"),
    "VALE": ("Brésil", "Amérique latine"), "BRL": ("Brésil", "Amérique latine"),
    "BTC": ("Global", "Crypto"), "ETH": ("Global", "Crypto"), "SOL": ("Global", "Crypto"),
    "BNB": ("Global", "Crypto"), "XRP": ("Global", "Crypto"), "ADA": ("Global", "Crypto"),
    "AVAX": ("Global", "Crypto"), "DOGE": ("Global", "Crypto"),
}
_GLOBE_PALETTE = [
    "#ff9900", "#ff5252", "#40c4ff", "#69f0ae", "#ffd740", "#e040fb",
    "#ff6d00", "#00e5ff", "#b2ff59", "#ff4081", "#8c9eff", "#64ffda",
    "#f50057", "#304ffe", "#aeea00", "#ffab40", "#e6ee9c", "#ce93d8",
]


def get_globe_data() -> dict:
    """Épingles du globe : une par signal d'agent, couleur unique par agent."""
    data = _merged_data()
    pins = []
    legend = []
    agents_seen: dict[str, str] = {}
    color_idx = 0
    for team_name, builder in TEAM_BUILDERS.items():
        manager = builder(None) if team_name == "Macro" else builder()
        try:
            synthesis = manager.run(data)
        except Exception:
            synthesis = None
        for agent in manager.agents:
            try:
                report = agent.analyze({t: data[t] for t in agent.universe() if t in data})
            except Exception:
                continue
            if agent.name not in agents_seen:
                agents_seen[agent.name] = _GLOBE_PALETTE[color_idx % len(_GLOBE_PALETTE)]
                color_idx += 1
            color = agents_seen[agent.name]
            legend.append({
                "agent": agent.name,
                "team": team_name,
                "color": color,
                "n_pins": 0,
            })
            for s in report.signals:
                geo = _TICKER_GEO.get(s.ticker)
                if geo is None:
                    continue
                label = _TICKER_GEO_LABEL.get(s.ticker, ("—", "—"))
                legend[-1]["n_pins"] += 1
                pins.append({
                    "agent": agent.name,
                    "team": team_name,
                    "color": color,
                    "ticker": s.ticker,
                    "lat": geo[0],
                    "lon": geo[1],
                    "country": label[0],
                    "region": label[1],
                    "direction": s.direction.value if hasattr(s.direction, "value") else str(s.direction),
                    "conviction": round(float(s.conviction() if callable(s.conviction) else s.conviction), 3),
                    "score": round(float(s.score() if callable(s.score) else s.score), 3),
                    "thesis": getattr(s, "thesis", ""),
                })
    legend = [l for l in legend if l["n_pins"] > 0]
    return {"pins": pins, "legend": legend, "n_agents": len(agents_seen)}
