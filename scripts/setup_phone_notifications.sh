#!/bin/bash
# Notifications iPhone via ntfy (gratuit, sans compte).
# 1. Installe l'app « ntfy » sur l'iPhone (App Store).
# 2. Lance ce script : il crée un canal privé au nom aléatoire et l'affiche.
# 3. Dans l'app : « + » > Subscribe to topic > colle le nom du canal.
# Le nom du canal fait office de mot de passe : ne le partage pas.
set -euo pipefail
TOPIC=$(security find-generic-password -s gambit-ridge-capital -a NTFY_TOPIC -w 2>/dev/null || true)
if [ -z "$TOPIC" ]; then
  TOPIC="grc-$(openssl rand -hex 12)"
  security add-generic-password -U -s gambit-ridge-capital -a NTFY_TOPIC -w "$TOPIC"
fi
echo "Canal à saisir dans l'app ntfy (Subscribe to topic) :"
echo
echo "    $TOPIC"
echo
read -r -p "Appuie sur Entrée une fois abonné dans l'app pour recevoir un message de test… "
curl -s -o /dev/null -w "%{http_code}" -d "Notifications du terminal Gambit Ridge Capital activées." "https://ntfy.sh/$TOPIC?title=Gambit%20Ridge%20Capital&tags=white_check_mark" | grep -q 200 \
  && echo "✓ Message de test envoyé — il doit apparaître sur ton iPhone." || echo "✗ Envoi impossible (réseau ?)"
