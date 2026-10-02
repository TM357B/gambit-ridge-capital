#!/bin/bash
# Démarre le serveur dashboard Gambit Ridge Capital (127.0.0.1 uniquement).
set -euo pipefail
cd "$HOME/gambit-ridge-capital"
if command -v /opt/miniconda3/bin/python3 >/dev/null 2>&1; then
  exec /opt/miniconda3/bin/python3 -m gambit_ridge.app.server
fi
exec python3 -m gambit_ridge.app.server
