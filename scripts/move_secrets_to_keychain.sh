#!/bin/bash
# Range les clés du fichier .env dans le Trousseau macOS (service « gambit-ridge-capital »),
# puis propose de supprimer le fichier .env. Les clés ne sont jamais affichées.
set -euo pipefail
ENV="${1:-$HOME/gambit-ridge-capital/.env}"
[ -f "$ENV" ] || { echo "Pas de fichier $ENV"; exit 1; }
seen=""
while IFS= read -r line; do
  [[ "$line" =~ ^[A-Z_]+= ]] || continue
  key="${line%%=*}"; val="${line#*=}"; val="${val%\"}"; val="${val#\"}"
  case " $seen " in *" $key "*) continue;; esac  # première occurrence seulement
  seen="$seen $key"
  security add-generic-password -U -s gambit-ridge-capital -a "$key" -w "$val"
  echo "✓ $key rangée dans le Trousseau"
done < "$ENV"
read -r -p "Supprimer le fichier .env maintenant que les clés sont dans le Trousseau ? (o/N) " ok
if [ "$ok" = "o" ]; then rm -P "$ENV" 2>/dev/null || rm "$ENV"; echo "✓ .env supprimé"; fi
