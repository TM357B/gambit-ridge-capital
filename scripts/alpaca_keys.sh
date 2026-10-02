#!/bin/bash
# Range les clés API du compte PAPER Alpaca dans le Trousseau macOS (saisie masquée).
# Où les trouver : app.alpaca.markets > compte « Paper » > Home > API Keys > Generate New Keys
set -euo pipefail
read -r -s -p "Colle l'API Key ID (commence par PK…) puis Entrée : " KID; echo
read -r -s -p "Colle la Secret Key puis Entrée : " SEC; echo
[[ "$KID" == PK* ]] || { echo "L'identifiant d'un compte PAPER commence par PK — vérifie que tu es bien sur le compte Paper."; exit 1; }
security add-generic-password -U -s gambit-ridge-capital -a ALPACA_KEY_ID -w "$KID"
security add-generic-password -U -s gambit-ridge-capital -a ALPACA_SECRET -w "$SEC"
echo "✓ Clés Alpaca (paper) rangées dans le Trousseau."
