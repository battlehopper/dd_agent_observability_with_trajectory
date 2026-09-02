#!/usr/bin/env bash
# Instala systemd timer (preferido) ou cron para gerar /chat a cada 5 minutos.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$ROOT/scripts/generate-trace.sh"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Rode como root (sudo) para instalar o timer." >&2
  exit 1
fi

if command -v systemctl >/dev/null 2>&1 && [[ -d /etc/systemd/system ]]; then
  unit_dir=/etc/systemd/system
  sed "s|/root/llmagent|${ROOT}|g" \
    "$ROOT/deploy/systemd/retail-trace-generator.service" > "${unit_dir}/retail-trace-generator.service"
  cp "$ROOT/deploy/systemd/retail-trace-generator.timer" "${unit_dir}/retail-trace-generator.timer"
  touch /var/log/retail-trace.log
  systemctl daemon-reload
  systemctl enable --now retail-trace-generator.timer
  echo "Aguardando gateway em http://127.0.0.1:8001/health..."
  GATEWAY_WAIT_SECS=90 systemctl start retail-trace-generator.service
  echo "Timer ativo: a cada 5 minutos chama ${ROOT}/scripts/generate-trace.sh"
  echo "  systemctl status retail-trace-generator.timer"
  echo "  journalctl -u retail-trace-generator.service -n 20"
  echo "  tail -f /var/log/retail-trace.log"
  systemctl list-timers retail-trace-generator.timer --no-pager
  exit 0
fi

cron_line="*/5 * * * * GATEWAY_URL=http://127.0.0.1:8001 TRACE_LOG=/var/log/retail-trace.log ${ROOT}/scripts/generate-trace.sh"
(crontab -l 2>/dev/null | grep -v generate-trace.sh; echo "$cron_line") | crontab -
echo "Cron instalado:"
echo "  $cron_line"
echo "  tail -f /var/log/retail-trace.log"
