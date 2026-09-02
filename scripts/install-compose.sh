#!/usr/bin/env bash
# Instala o plugin Compose v2 em /usr/local/lib/docker/cli-plugins/
# Útil no Amazon Linux 2, onde docker-compose-plugin pode não existir no yum.
set -euo pipefail

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) COMPOSE_ARCH=x86_64 ;;
  aarch64|arm64) COMPOSE_ARCH=aarch64 ;;
  *)
    echo "Arquitetura não suportada: $ARCH" >&2
    exit 1
    ;;
esac

VERSION="${COMPOSE_VERSION:-v2.29.7}"
PLUGIN_DIR=/usr/local/lib/docker/cli-plugins
URL="https://github.com/docker/compose/releases/download/${VERSION}/docker-compose-linux-${COMPOSE_ARCH}"

sudo mkdir -p "$PLUGIN_DIR"
sudo curl -fsSL "$URL" -o "$PLUGIN_DIR/docker-compose"
sudo chmod +x "$PLUGIN_DIR/docker-compose"

# Fallback no PATH para quem chama docker-compose.
if [[ ! -x /usr/local/bin/docker-compose ]]; then
  sudo ln -sf "$PLUGIN_DIR/docker-compose" /usr/local/bin/docker-compose
fi

docker compose version
