#!/usr/bin/env bash
# Запуск db_idle_tx_reset_and_restart_bot.sh не чаще чем раз в $1 секунд (по умолчанию 90).
# Для cron: две строки "* * * * *" и "* * * * * sleep 30; ..." — иначе раз в минуту
# границу в 90 с не попасть.
#
# Наследует окружение (SKIP_RESTART, DOCKER, …).

set -euo pipefail

INTERVAL_SEC="${1:-90}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN="${SCRIPT_DIR}/db_idle_tx_reset_and_restart_bot.sh"
STAMP_FILE="${STAMP_FILE:-${HOME}/.local/state/remnawave-bedolaga/last-idle-tx-run}"

mkdir -p "$(dirname "${STAMP_FILE}")"

now=$(date +%s)
last=0
if [[ -f "${STAMP_FILE}" ]]; then
  last=$(tr -dc '0-9' <"${STAMP_FILE}" 2>/dev/null | head -c 12)
  last="${last:-0}"
fi

if (( now - last < INTERVAL_SEC )); then
  exit 0
fi

printf '%s\n' "${now}" >"${STAMP_FILE}"
exec "${MAIN}"
