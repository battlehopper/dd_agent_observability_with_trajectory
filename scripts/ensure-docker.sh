#!/usr/bin/env bash
# Instala e inicia o daemon Docker (Amazon Linux 2/2023 ou Ubuntu).
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  if command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y docker git
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y docker git
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y docker.io git ca-certificates curl
  else
    echo "Gerenciador de pacotes não suportado. Instale Docker manualmente." >&2
    exit 1
  fi
fi

if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl enable --now docker
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker instalado, mas o daemon não responde. Rode: sudo systemctl status docker" >&2
  exit 1
fi

echo "Docker OK: $(docker --version)"
