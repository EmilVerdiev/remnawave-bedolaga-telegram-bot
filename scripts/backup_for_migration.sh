#!/usr/bin/env bash
# Бэкап БД, Redis (опционально), каталогов приложения и .env для переноса на другой сервер.
# См. docs/MIGRATION_TO_NEW_SERVER.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PG_CONTAINER="${BACKUP_PG_CONTAINER:-remnawave_bot_db}"
REDIS_CONTAINER="${BACKUP_REDIS_CONTAINER:-remnawave_bot_redis}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${1:-${PROJECT_ROOT}/migration_bundle/${STAMP}}"

mkdir -p "${OUT}"

echo "==> Выходная папка: ${OUT}"

if ! docker ps --format '{{.Names}}' | grep -qx "${PG_CONTAINER}"; then
  echo "Ошибка: контейнер Postgres не запущен: ${PG_CONTAINER}" >&2
  echo "Задайте BACKUP_PG_CONTAINER=имя_контейнера при необходимости." >&2
  exit 1
fi

echo "==> PostgreSQL (custom format, pg_restore)..."
docker exec "${PG_CONTAINER}" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "${OUT}/postgres.dump"
ls -lh "${OUT}/postgres.dump"

if docker ps --format '{{.Names}}' | grep -qx "${REDIS_CONTAINER}"; then
  echo "==> Redis RDB..."
  docker exec "${REDIS_CONTAINER}" redis-cli SAVE >/dev/null || true
  if docker cp "${REDIS_CONTAINER}:/data/dump.rdb" "${OUT}/redis-dump.rdb" 2>/dev/null; then
    ls -lh "${OUT}/redis-dump.rdb"
  else
    echo "Предупреждение: не удалось скопировать dump.rdb (не критично для многих установок)."
  fi
else
  echo "Предупреждение: Redis-контейнер ${REDIS_CONTAINER} не найден — пропуск."
fi

echo "==> Файлы приложения (uploads, data, locales)..."
ARCHIVE_PATHS=()
for d in uploads data locales; do
  if [[ -d "${PROJECT_ROOT}/${d}" ]]; then
    ARCHIVE_PATHS+=("${d}")
  fi
done
if [[ ${#ARCHIVE_PATHS[@]} -gt 0 ]]; then
  tar -czf "${OUT}/app_files.tar.gz" -C "${PROJECT_ROOT}" "${ARCHIVE_PATHS[@]}"
  echo "В архиве: ${ARCHIVE_PATHS[*]}"
else
  echo "Предупреждение: нет каталогов uploads/data/locales — пустой app_files.tar.gz."
  TMP_EMPTY="$(mktemp -d)"
  tar -czf "${OUT}/app_files.tar.gz" -C "${TMP_EMPTY}" .
  rmdir "${TMP_EMPTY}"
fi

for logo in vpn_logo.PNG vpn_logo.png; do
  if [[ -f "${PROJECT_ROOT}/${logo}" ]]; then
    cp -a "${PROJECT_ROOT}/${logo}" "${OUT}/"
    echo "Скопирован ${logo}"
  fi
done

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  cp -a "${PROJECT_ROOT}/.env" "${OUT}/dotenv.migration_COPY_SECRET"
  chmod 600 "${OUT}/dotenv.migration_COPY_SECRET"
  echo "Скопирован .env -> dotenv.migration_COPY_SECRET (права 600). Не коммитьте и не шарьте публично."
else
  echo "Предупреждение: .env не найден в корне проекта — перенесите секреты вручную."
fi

docker exec "${PG_CONTAINER}" sh -c 'printf "%s\n" "POSTGRES_USER=$POSTGRES_USER" "POSTGRES_DB=$POSTGRES_DB"' > "${OUT}/postgres_container_env.txt"
echo "Записан postgres_container_env.txt (без пароля) для сверки с .env на новом сервере."

cat > "${OUT}/README_BUNDLE.txt" <<EOF
Содержимое бандла миграции (${STAMP})
- postgres.dump       — восстановление через scripts/restore_after_migration.sh
- redis-dump.rdb      — опционально, если был Redis бота
- app_files.tar.gz    — uploads, data, locales
- dotenv.migration_COPY_SECRET — копия .env (секреты)
- vpn_logo.*          — логотип, если был в корне

Дальше: docs/MIGRATION_TO_NEW_SERVER.md
EOF

echo ""
echo "Готово. Перенесите всю папку на новый сервер (scp/rsync):"
echo "  ${OUT}"
echo ""
ls -la "${OUT}"
