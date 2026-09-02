#!/usr/bin/env bash
# Bootstrap EC2: Docker + Compose v2 + grupo docker.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

chmod +x "$ROOT/scripts/"*.sh

echo "==> Docker"
sudo "$ROOT/scripts/ensure-docker.sh"

echo "==> Compose v2"
if docker compose version >/dev/null 2>&1; then
  docker compose version
else
  sudo "$ROOT/scripts/install-compose.sh"
fi

TARGET_USER="${SUDO_USER:-$USER}"
if [[ "$TARGET_USER" != "root" ]]; then
  echo "==> Adicionando $TARGET_USER ao grupo docker"
  sudo usermod -aG docker "$TARGET_USER" || true
  echo "Reconecte o SSH para o grupo docker valer (newgrp docker ou logout/login)."
fi

echo
echo "Próximo passo:"
echo "  cp deploy/.env.ec2.example .env"
echo "  nano .env    # DD_API_KEY, DD_SITE"
echo "  ./scripts/start-prod.sh"
