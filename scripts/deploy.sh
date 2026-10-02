#!/bin/bash
# Déploie la branche de travail vers l'app installée, en une commande.
# Usage (depuis le dépôt) : bash scripts/deploy.sh
# - sauvegarde l'install (5 dernières conservées)
# - copie les fichiers suivis par Git (ne touche jamais .env, data_cache/, journal/)
# - redémarre le serveur ; recompile l'app Mac seulement si le Swift a changé
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/gambit-ridge-capital"
BK="$HOME/.gambit-ridge-capital-backups"
mkdir -p "$BK" "$DEST"
STAMP=$(date +%Y%m%d-%H%M%S)
rsync -a --exclude data_cache --exclude journal --exclude '.env' --exclude 'mac/Gambit Ridge Capital.app' "$DEST/" "$BK/$STAMP/"
N=$(ls -1d "$BK"/*/ | wc -l); ls -1d "$BK"/*/ | sort | awk -v n="$N" 'NR <= n - 5' | while read -r d; do rm -rf "$d"; done
OLD_SWIFT=$(shasum "$DEST/mac/GambitRidgeCapital.swift" 2>/dev/null | cut -d' ' -f1 || true)
cd "$SRC" && git ls-files | grep -v -e '^HANDOFF.md$' -e '^CLAUDE.md$' -e '^\.github/' | rsync -a --files-from=- . "$DEST/"
echo "✓ Code copié (sauvegarde : $BK/$STAMP)"
if [ -f "$HOME/Library/LaunchAgents/com.gambitridgecapital.server.plist" ]; then
  launchctl kickstart -k "gui/$(id -u)/com.gambitridgecapital.server"   # service permanent : redémarrage propre
else
  pkill -f gambit_ridge.app.server 2>/dev/null || true
  for i in $(seq 1 20); do lsof -i :8765 >/dev/null 2>&1 || break; sleep 1; done
  (cd "$DEST" && exec nohup ./run_server.sh >> app.log 2>&1 < /dev/null) &
fi
for i in $(seq 1 30); do curl -s -m 3 -o /dev/null http://127.0.0.1:8765/api/market && break; sleep 2; done
echo "✓ Serveur redémarré"
if [ "$OLD_SWIFT" != "$(shasum "$DEST/mac/GambitRidgeCapital.swift" | cut -d' ' -f1)" ]; then
  (cd "$DEST" && bash mac/build_mac_app.sh | tail -1)
  echo "  App Mac recompilée : quitte-la (Cmd+Q) et rouvre-la."
fi
[ -f "$HOME/Library/LaunchAgents/com.gambitridgecapital.daily.plist" ] || bash "$DEST/scripts/install_daily_job.sh"
echo "✓ Déploiement terminé."
