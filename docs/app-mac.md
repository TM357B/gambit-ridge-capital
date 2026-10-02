# Gambit Ridge Capital — Application Mac

## Installation (2 minutes)

1. Copie le dossier `gambit-ridge-capital` sur ton Mac (par exemple `~/gambit-ridge-capital`)
2. Ouvre Terminal et va dans le dossier :
   ```bash
   cd ~/gambit-ridge-capital
   ```
3. Installe les dépendances (une seule fois) :
   ```bash
   python3 -m pip install --user numpy
   ```
4. Lance l'installation :
   ```bash
   bash install_mac.sh
   ```
5. Le script crée `Gambit Ridge Capital.app` dans `~/Applications`
6. Ouvre le Finder → glisse **Gambit Ridge Capital** dans ton dock
7. Clique sur l'icône : le dashboard s'ouvre dans ton navigateur
   (http://127.0.0.1:8765 — accessible uniquement depuis ton Mac)

## Ce que montre le dashboard

- **KPIs du fonds** : track record paper-trading, poids du thème IA, conformité risque
- **Courbe paper-trading** : chaque réunion journalise l'allocation ; le P&L est
  recalculé automatiquement avec les prix réels du jour
- **Poste de PM** : une carte par équipe (Macro, Micro, Crypto 24/7, Forex,
  Commodities, IA & Tech) avec les signaux du manager, convictions et watchlist
- **Allocation du jour** : après sizing Kelly + vol-target, avec contrôle des limites
- **Bouton "Exécuter la réunion"** : relance l'analyse complète à la demande

## Réunion quotidienne automatique (optionnel)

Pour journaliser le briefing chaque matin sans ouvrir l'app :

```bash
crontab -e
```
Ajoute (exécution à 8h30 du lundi au vendredi) :
```
30 8 * * 1-5 cd ~/gambit-ridge-capital && python3 -m gambit_ridge.daily >> journal/cron.log 2>&1
```

Le module `daily` exécute la réunion, journalise l'allocation et calcule
le P&L cumulé — même sans dashboard ouvert.

## Sécurité

- Le serveur écoute uniquement sur `127.0.0.1` : rien n'est exposé sur le réseau
- La clé Polygon reste dans `.env` (jamais dans l'app)
- Aucune donnée ne quitte ton Mac
