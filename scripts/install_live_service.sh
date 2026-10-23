#!/bin/bash
# Fait tourner le moteur live en service permanent (launchd) : démarré à
# l'ouverture de session, relancé automatiquement s'il s'arrête.
# Il n'envoie des ordres qu'une fois activé : python3 -m gambit_ridge.live.engine enable
# Désinstaller : bash scripts/install_live_service.sh --remove
set -euo pipefail
LABEL="com.gambitridgecapital.live"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APP_DIR="$HOME/gambit-ridge-capital"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--remove" ]; then rm -f "$PLIST"; echo "✓ Service moteur live supprimé."; exit 0; fi
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$APP_DIR/run_live.sh</string></array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$APP_DIR/data_cache/live.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/data_cache/live.log</string>
</dict>
</plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "✓ Moteur live en service permanent (journal : $APP_DIR/data_cache/live.log)."
