#!/usr/bin/env bash
# Срочный обход: завершить в PostgreSQL сессии приложения в состоянии
# idle in transaction (освобождает пул) и при необходимости перезапустить бота.
#
# Запуск из cron (пример; DOCKER="sudo docker" если без группы docker; лог — в каталог,
# доступный пользователю cron, не в project/logs если он чужой — иначе задача не стартует):
#   * * * * * DOCKER="sudo docker" /path/to/scripts/db_idle_tx_reset_and_restart_bot.sh >> /home/you/.local/state/remnawave-bedolaga/db-idle-fix.log 2>&1
#
# Переменные окружения (опционально):
#   COMPOSE_DIR  — каталог с docker-compose.yml (по умолчанию: родитель scripts/)
#   DOCKER       — префикс docker (например DOCKER="sudo docker" если сокет только у root;
#                 удобно прописать в crontab: DOCKER=sudo\ docker перед путём к скрипту)
#   FORCE_RESTART=1 — всегда делать docker compose restart bot, даже если никого не убили
#   SKIP_RESTART=1 — только terminate, без рестарта (для проверки)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${COMPOSE_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
DOCKER="${DOCKER:-docker}"

DB_CONTAINER="${DB_CONTAINER:-remnawave_bot_db}"
BOT_SERVICE="${BOT_SERVICE:-bot}"

load_env_kv() {
  local key="$1"
  local f="${COMPOSE_DIR}/.env"
  [[ -f "$f" ]] || return 0
  grep -E "^${key}=" "$f" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r'
}

POSTGRES_USER="$(load_env_kv POSTGRES_USER)"
POSTGRES_DB="$(load_env_kv POSTGRES_DB)"
POSTGRES_USER="${POSTGRES_USER:-remnawave_user}"
POSTGRES_DB="${POSTGRES_DB:-remnawave_bot}"

log() {
  echo "[$(date -Iseconds)] $*"
}

if ! command -v "${DOCKER%% *}" &>/dev/null; then
  log "ERROR: docker not found (DOCKER=${DOCKER})"
  exit 1
fi

if [[ ! -f "${COMPOSE_DIR}/docker-compose.yml" ]]; then
  log "ERROR: docker-compose.yml not found in ${COMPOSE_DIR}"
  exit 1
fi

# Сколько «зависших» транзакций до действий
STUCK_BEFORE="$(${DOCKER} exec "${DB_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -A -c \
  "SELECT count(*)::text FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND application_name = 'remnawave_bot' AND state IN ('idle in transaction', 'idle in transaction (aborted)');" 2>/dev/null || echo -1)"

if [[ "${STUCK_BEFORE}" == "-1" ]]; then
  log "ERROR: cannot query PostgreSQL (container ${DB_CONTAINER} / DB ${POSTGRES_DB})"
  exit 1
fi

log "idle_in_transaction (remnawave_bot) before: ${STUCK_BEFORE}"

# MATERIALIZED CTE фиксирует список pid до любых terminate — иначе при сканировании
# pg_stat_activity в одном SELECT часть сессий не завершается и count(*) даёт 0.
KILLED="$(${DOCKER} exec "${DB_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -A -c \
  "WITH pids AS MATERIALIZED (
     SELECT pid FROM pg_stat_activity
     WHERE datname = '${POSTGRES_DB}'
       AND application_name = 'remnawave_bot'
       AND state IN ('idle in transaction', 'idle in transaction (aborted)')
       AND pid <> pg_backend_pid()
   )
   SELECT count(*)::text FROM pids, LATERAL (SELECT pg_terminate_backend(pids.pid) AS ok) t WHERE t.ok;" 2>/dev/null || echo 0)"

log "terminated backends: ${KILLED}"

if [[ "${SKIP_RESTART:-0}" == 1 ]]; then
  log "SKIP_RESTART=1 — контейнер бота не перезапускаю"
  exit 0
fi

# Рестарт нужен не только когда terminate что-то вернул: если на старте были
# idle in transaction, а KILLED=0 (гонка/снимок), без перезапуска пул так и остаётся мёртвым.
need_restart=0
if [[ "${KILLED}" =~ ^[0-9]+$ ]] && [[ "${KILLED}" -gt 0 ]]; then need_restart=1; fi
if [[ "${STUCK_BEFORE}" =~ ^[0-9]+$ ]] && [[ "${STUCK_BEFORE}" -gt 0 ]]; then need_restart=1; fi

if [[ "${need_restart}" -eq 1 ]]; then
  log "restarting bot service (${BOT_SERVICE}) (had idle-in-tx: ${STUCK_BEFORE}, terminated: ${KILLED})..."
  (cd "${COMPOSE_DIR}" && ${DOCKER} compose restart "${BOT_SERVICE}")
  log "done restart"
elif [[ "${FORCE_RESTART:-0}" == 1 ]]; then
  log "FORCE_RESTART=1 — restarting bot anyway..."
  (cd "${COMPOSE_DIR}" && ${DOCKER} compose restart "${BOT_SERVICE}")
  log "done restart"
else
  log "no idle-in-tx seen, skip restart (set FORCE_RESTART=1 to restart every run)"
fi

exit 0
