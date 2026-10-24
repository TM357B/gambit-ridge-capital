"""Équipes d'agents : chaque agent a un nom, une voix et des données ; la campagne 2 garde ses équipes d'origine."""

import unittest

from gambit_ridge.agents_api import TEAM_BUILDERS
from gambit_ridge.data.simulation import all_configured_tickers
from gambit_ridge import staff
from gambit_ridge.staff import MANAGERS, STAFF

voice_gender = getattr(staff, "voice_gender", None)  # absent de la version publique (rôles, pas de personnes)
from gambit_ridge.teams import build_commodities_team, build_forex_team


class TestEquipes(unittest.TestCase):
    def test_chaque_agent_est_un_employe(self):
        configures = set(all_configured_tickers())
        n = 0
        for nom, build in TEAM_BUILDERS.items():
            equipe = build() if nom != "Macro" else build(None)
            self.assertIn(f"manager-{nom}", MANAGERS)
            if voice_gender:
                self.assertIsNotNone(voice_gender(MANAGERS[f"manager-{nom}"]), nom)
            for a in equipe.agents:
                n += 1
                self.assertIn(a.name, STAFF, a.name)
                if voice_gender:
                    self.assertIsNotNone(voice_gender(STAFF[a.name][0]), a.name)
                for tk in a.universe():
                    self.assertIn(tk, configures, f"{a.name} : {tk} sans données")
        self.assertEqual(n, 50)

    def test_campagne_2_inchangee(self):
        self.assertEqual(len(build_commodities_team(etendue=False).agents), 6)
        self.assertEqual(len(build_forex_team(etendue=False).agents), 6)


if __name__ == "__main__":
    unittest.main()
