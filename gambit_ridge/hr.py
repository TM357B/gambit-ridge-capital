"""Pôle RH : hiérarchie du fond, salaires virtuels, évaluations, promotions, recrutement.

Inspiré des vrais fonds : salaire fixe + bonus de performance indexé sur
la contribution OOS du agent/équipe. Le gérant (l'utilisateur) est au sommet.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

HR_FILE = Path(__file__).resolve().parent.parent / "data_cache" / "hr_state.json"

# Barème virtuel (unités arbitraires "k$" par an, purement fictives)
SALARY_GRID = {
    "gerant": 250.0,
    "manager": 180.0,
    "manager_rh": 150.0,
    "agent_senior": 90.0,
    "agent": 60.0,
    "agent_junior": 35.0,
}
BONUS_POOL_RATE = 0.20  # 20% de la "performance" redistribute en bonus


@dataclass
class Employee:
    id: str
    name: str
    role: str            # gerant | manager | manager_rh | agent_senior | agent | agent_junior
    team: str
    scope: str
    base_salary: float    # k$/an fixe
    joined: str           # date ISO
    # Performance simulée : contribution cumulative (score de signaux journaliers)
    contribution: float = 0.0
    streak_days: int = 0
    promotions: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)

    def bonus(self) -> float:
        """Bonus de performance : proportionnel à la contribution, plafonné au fixe."""
        return round(min(max(self.contribution * 50.0, 0.0), self.base_salary), 1)

    def total_comp(self) -> float:
        return round(self.base_salary + self.bonus(), 1)

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "bonus": self.bonus(),
            "total_comp": self.total_comp(),
        }


@dataclass
class HRDecision:
    employee_id: str
    kind: str             # promotion | recrutement | avertissement | felicitation
    reason: str
    date: str


class HRDepartment:
    """Le pôle RH : 3 analystes RH + 1 manager RH, évaluations hebdomadaires."""

    def __init__(self) -> None:
        self.hr_agents = [
            {"id": "rh-analyste-performance", "name": "Analyste Performance",
             "scope": "mesure la contribution de chaque agent (signaux, qualité, fréquence)"},
            {"id": "rh-analyste-competences", "name": "Analyste Compétences",
             "scope": "cartographie les compétences, détecte les doublons et les gaps d'équipe"},
            {"id": "rh-analyste-talent", "name": "Analyste Talent",
             "scope": "identifie les agents à promouvoir et les profils à recruter"},
        ]

    # ---------- évaluations ----------

    def evaluate_team(self, team_name: str, employees: list[Employee],
                      team_score: float) -> list[HRDecision]:
        """Évaluation hebdomadaire d'une équipe par le pôle RH."""
        decisions: list[HRDecision] = []
        today = date.today().isoformat()
        contributions = [e.contribution for e in employees] or [0.0]
        mean_c = sum(contributions) / len(contributions)
        for e in employees:
            if e.contribution > max(mean_c * 1.5, 0.05) and e.role != "gerant":
                if e.role in ("agent_junior", "agent"):
                    new_role = "agent" if e.role == "agent_junior" else "agent_senior"
                    decisions.append(HRDecision(e.id, "promotion", 
                        f"contribution {e.contribution:+.2f} > 150% de la moyenne équipe — "
                        f"promu {e.role} → {new_role}", today))
                    e.role = new_role
                    e.base_salary = SALARY_GRID[new_role]
                    e.promotions.append({"date": today, "to": new_role, "reason": "contribution exceptionnelle"})
                else:
                    decisions.append(HRDecision(e.id, "felicitation",
                        f"contribution {e.contribution:+.2f} exemplaire, maintien au rôle {e.role}", today))
            elif e.contribution < -0.05:
                decisions.append(HRDecision(e.id, "avertissement",
                    f"contribution négative {e.contribution:+.2f} — plan d'amélioration demandé au manager", today))
        return decisions

    def recruitment_proposal(self, team_name: str, team_score: float,
                             n_agents: int, coverage_gaps: list[str]) -> HRDecision | None:
        """Propose un recrutement si l'équipe est sous-dimensionnée."""
        today = date.today().isoformat()
        if team_score > 0.15 and n_agents < 6:
            gap = coverage_gaps[0] if coverage_gaps else "renfort généraliste"
            return HRDecision(f"recrutement-{team_name}", "recrutement",
                f"score équipe {team_score:+.2f} élevé mais seulement {n_agents} agents — "
                f"recruter 1 agent spécialisé ({gap}) pour capter davantage de cet edge", today)
        return None

    def weekly_report(self, roster: dict) -> dict:
        """Rapport hebdo du manager RH (réunion du vendredi)."""
        teams = roster.get("teams", [])
        report = {
            "date": date.today().isoformat(),
            "hr_agents": self.hr_agents,
            "team_evaluations": [],
            "recruitments": [],
            "payroll": self.payroll(teams),
        }
        for team in teams:
            emps = team.get("employees", [])
            if not emps:
                continue
            scores = [e["contribution"] for e in emps]
            decisions = self.evaluate_team(team["team"], 
                                           [self._to_employee(e) for e in emps],
                                           team.get("score", 0.0))
            rec = self.recruitment_proposal(team["team"], team.get("score", 0.0),
                                           len(emps), team.get("coverage_gaps", []))
            if rec:
                report["recruitments"].append(asdict(rec))
            report["team_evaluations"].append({
                "team": team["team"],
                "n_employees": len(emps),
                "mean_contribution": round(sum(scores) / len(scores), 3),
                "top_performer": max(emps, key=lambda e: e["contribution"])["name"] if emps else None,
                "decisions": [asdict(d) for d in decisions],
            })
        return report

    def payroll(self, teams: list[dict]) -> dict:
        """Masse salariale totale (fixe + bonus)."""
        total_fixed = 0.0
        total_bonus = 0.0
        by_team: dict[str, float] = {}
        for team in teams:
            for e in team.get("employees", []):
                total_fixed += e.get("base_salary", 0.0)
                total_bonus += e.get("bonus", 0.0)
                by_team[team["team"]] = by_team.get(team["team"], 0.0) + e.get("total_comp", 0.0)
        return {
            "total_fixed": round(total_fixed, 1),
            "total_bonus": round(total_bonus, 1),
            "total": round(total_fixed + total_bonus, 1),
            "by_team": {k: round(v, 1) for k, v in by_team.items()},
        }

    @staticmethod
    def _to_employee(d: dict) -> Employee:
        return Employee(
            id=d.get("id", ""), name=d.get("name", ""), role=d.get("role", "agent"),
            team=d.get("team", ""), scope=d.get("scope", ""),
            base_salary=d.get("base_salary", 0.0), joined=d.get("joined", ""),
            contribution=d.get("contribution", 0.0),
            promotions=d.get("promotions", []), reviews=d.get("reviews", []),
        )


# ---------- état persistant ----------

def build_initial_org(agents_roster: list[dict]) -> list[Employee]:
    """Construit l'organigramme initial depuis le roster des agents."""
    employees: list[Employee] = []
    today = date.today().isoformat()
    employees.append(Employee(
        id="gerant", name="Tom — Gérant", role="gerant", team="Direction",
        scope="propriétaire/gérant du fond — décide en dernier ressort",
        base_salary=SALARY_GRID["gerant"], joined=today,
    ))
    for team in agents_roster:
        employees.append(Employee(
            id=f"manager-{team['team']}", name=f"Manager {team['team']}",
            role="manager", team=team["team"],
            scope=f"dirige l'équipe {team['team']} et rend compte au gérant",
            base_salary=SALARY_GRID["manager"], joined=today,
        ))
        for i, a in enumerate(team["agents"]):
            role = "agent_senior" if i == 0 else "agent"
            employees.append(Employee(
                id=a["id"], name=a["id"], role=role, team=team["team"],
                scope=a["scope"], base_salary=SALARY_GRID[role], joined=today,
            ))
    return employees


def save_org(employees: list[Employee]) -> None:
    HR_FILE.parent.mkdir(exist_ok=True, parents=True)
    HR_FILE.write_text(json.dumps([e.to_dict() for e in employees], ensure_ascii=False))


def load_org() -> list[Employee] | None:
    try:
        if HR_FILE.exists():
            data = json.loads(HR_FILE.read_text())
            return [HRDepartment._to_employee(e) for e in data]
    except Exception:
        pass
    return None


def update_contributions(employees: list[Employee], team_syntheses: list[dict]) -> None:
    """Met à jour la contribution cumulée de chaque agent selon les scores réels du jour."""
    by_team = {t["team"]: t for t in team_syntheses}
    for e in employees:
        if e.role == "gerant":
            total = sum(t.get("aggregate_score", 0.0) for t in team_syntheses)
            e.contribution = round(e.contribution + total * 0.1, 4)
            continue
        team = by_team.get(e.team)
        if not team:
            continue
        agent_work = next((a for a in team.get("agents", []) if a.get("agent") == e.id), None)
        if agent_work:
            sigs = agent_work.get("signals", [])
            score = sum(s.get("score", 0.0) for s in sigs) / max(len(sigs), 1)
            e.contribution = round(e.contribution + score * 0.05, 4)
