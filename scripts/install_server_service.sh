#!/bin/bash
# Fait tourner le serveur du terminal en service permanent (launchd) :
# démarré à l'ouverture de session, relancé automatiquement s'il s'arrête,
# indépendant de l'app Mac. Écoute toujours uniquement sur 127.0.0.1.
# Désinstaller : bash scripts/install_server_service.sh --remove
set -euo pipefail
LABEL="com.gambitridgecapital.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APP_DIR="$HOME/gambit-ridge-capital"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--remove" ]; then rm -f "$PLIST"; echo "✓ Service serveur supprimé."; exit 0; fi
pkill -f gambit_ridge.app.server 2>/dev/null || true
for i in $(seq 1 20); do lsof -i :8765 >/dev/null 2>&1 || break; sleep 1; done
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$APP_DIR/run_server.sh</string></array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$APP_DIR/app.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/app.log</string>
</dict>
</plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$PLIST"
for i in $(seq 1 30); do curl -s -m 3 -o /dev/null http://127.0.0.1:8765/api/market && break; sleep 2; done
echo "✓ Serveur du terminal en service permanent (http://127.0.0.1:8765)."
