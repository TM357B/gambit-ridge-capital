"""Pôle RH : désactivé dans la version publique (interface conservée)."""

SALARY_GRID = {"manager_rh": 0.0}


class HRDepartment:
    def __init__(self) -> None:
        self.hr_agents: list[dict] = []

    def weekly_report(self, data: dict) -> dict:
        return {"summary": "Désactivé dans la version publique.", "decisions": []}


def build_initial_org(agents_roster: list[dict]) -> list:
    return []


def save_org(employees: list) -> None:
    return None


def load_org() -> list:
    return []


def update_contributions(employees: list, team_syntheses: list[dict]) -> None:
    return None
