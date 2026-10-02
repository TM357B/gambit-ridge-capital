#!/bin/bash
# Installe le passage quotidien automatique (launchd, sans privilèges admin).
# Tous les soirs à 23 h 15 (après la clôture de Wall Street), à 8 h 30 (envoi des
# ordres Alpaca pour l'ouverture) et à l'ouverture de session ; si le Mac dormait à l'heure prévue, macOS le lance au réveil.
# Désinstaller : bash scripts/install_daily_job.sh --remove
set -euo pipefail
LABEL="com.gambitridgecapital.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APP_DIR="$HOME/gambit-ridge-capital"
PY="/opt/miniconda3/bin/python3"; [ -x "$PY" ] || PY="$(command -v python3)"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--remove" ]; then rm -f "$PLIST"; echo "✓ Tâche quotidienne supprimée."; exit 0; fi

mkdir -p "$HOME/Library/LaunchAgents" "$APP_DIR/data_cache"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>-m</string><string>gambit_ridge.ops.daily_run</string></array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>15</integer></dict>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$APP_DIR/data_cache/ops.stdout.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/data_cache/ops.stdout.log</string>
</dict>
</plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "✓ Passages automatiques installés : 23 h 15 (décision après la clôture) et 8 h 30 (ordres Alpaca pour l'ouverture), plus à chaque ouverture de session."
echo "  Journal : $APP_DIR/data_cache/ops.log"
