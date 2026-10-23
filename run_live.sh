#!/bin/bash
# Démarre le moteur live (stratégie en continu sur prix en direct, compte paper Alpaca).
set -euo pipefail
cd "$HOME/gambit-ridge-capital"
if command -v /opt/miniconda3/bin/python3 >/dev/null 2>&1; then
  exec /opt/miniconda3/bin/python3 -u -m gambit_ridge.live.engine
fi
exec python3 -u -m gambit_ridge.live.engine
