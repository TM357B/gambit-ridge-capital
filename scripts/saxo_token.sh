#!/bin/bash
# Range le jeton Saxo (simulation) dans le Trousseau macOS, en saisie masquée.
# 1. Va sur https://www.developer.saxo/openapi/token (connecté à ton compte démo)
# 2. Copie le « 24-hour token », puis lance : bash scripts/saxo_token.sh
set -euo pipefail
read -r -s -p "Colle le jeton Saxo (rien ne s'affiche) puis Entrée : " TOKEN; echo
[ ${#TOKEN} -gt 100 ] || { echo "Jeton trop court — vérifie le copier-coller."; exit 1; }
security add-generic-password -U -s gambit-ridge-capital -a SAXO_TOKEN -w "$TOKEN"
echo "✓ Jeton rangé dans le Trousseau (valable 24 h)."
