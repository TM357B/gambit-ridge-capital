#!/bin/bash
# Le fonds tourne sur le serveur depuis le 2026-10-04 : le déploiement passe par
# deploy/server/deploy.sh. L'ancienne installation locale (~/gambit-ridge-capital)
# n'est plus exploitée (services Mac désactivés, voir deploy/server/README.md).
exec bash "$(cd "$(dirname "$0")/.." && pwd)/deploy/server/deploy.sh" "$@"
