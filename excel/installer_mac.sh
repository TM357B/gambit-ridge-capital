#!/bin/bash
# Installe le complément Excel Gambit Ridge sur ce Mac : script de transport + complément .xlam.
set -euo pipefail
ici="$(cd "$(dirname "$0")" && pwd)"
dest="$HOME/Library/Application Scripts/com.microsoft.Excel"
mkdir -p "$dest"
osacompile -o "$dest/GambitRidge.scpt" "$ici/recuperer.applescript"
mkdir -p "$HOME/Library/Group Containers/UBF8T346G9.Office/User Content.localized/Add-Ins.localized"
if [ -f "$ici/GambitRidge.xlam" ]; then
  cp "$ici/GambitRidge.xlam" "$HOME/Library/Group Containers/UBF8T346G9.Office/User Content.localized/Add-Ins.localized/"
fi
echo "Installé. Dans Excel : Outils > Compléments Excel… > cocher GambitRidge."
