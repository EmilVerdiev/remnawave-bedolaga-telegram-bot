#!/usr/bin/env bash
# Восстановление из бандла на НОВОМ сервере (после git clone).
# Использование: ./scripts/restore_after_migration.sh /path/to/migration_bundle/20260101_120000
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

BUNDLE="${1:-}"
if [[ -z "${BUNDLE}" || ! -d "${BUNDLE}" ]]; then
  echo "Использование: $0 <путь_к_папке_бандла>" >&2
  exit 1
fi

PG_CONTAINER="${RESTORE_PG_CONTAINER:-remnawave_bot_db}"

if [[ ! -f "${BUNDLE}/postgres.dump" ]]; then
  echo "Ошибка: нет ${BUNDLE}/postgres.dump" >&2
  exit 1
fi

echo "==> Поднимаем Postgres и Redis..."
docker compose up -d postgres redis

echo "Ждём готовности Postgres..."
for _ in $(seq 1 45); do
  if docker exec "${PG_CONTAINER}" sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' &>/dev/null; then
    break
  fi
  sleep 2
done

echo "==> Восстановление БД (pg_restore)..."
docker cp "${BUNDLE}/postgres.dump" "${PG_CONTAINER}:/tmp/postgres.dump"
set +e
docker exec "${PG_CONTAINER}" sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner /tmp/postgres.dump'
PR=$?
set -e
if [[ ${PR} -ne 0 ]]; then
  echo "Примечание: pg_restore завершился с кодом ${PR} (часто из‑за предупреждений). Проверьте данные в БД."
fi

if [[ -f "${BUNDLE}/app_files.tar.gz" ]]; then
  echo "==> Распаковка app_files.tar.gz в корень проекта..."
  tar -xzf "${BUNDLE}/app_files.tar.gz" -C "${PROJECT_ROOT}"
fi

if [[ -f "${BUNDLE}/dotenv.migration_COPY_SECRET" ]]; then
  echo "==> Копирование секретов в .env..."
  cp -a "${BUNDLE}/dotenv.migration_COPY_SECRET" "${PROJECT_ROOT}/.env"
  chmod 600 "${PROJECT_ROOT}/.env"
  echo "Отредактируйте .env при необходимости: домены CABINET_URL, вебхуки, POSTGRES_* если пароль на новом сервере другой."
fi

for logo in "${BUNDLE}/vpn_logo.PNG" "${BUNDLE}/vpn_logo.png"; do
  if [[ -f "${logo}" ]]; then
    cp -a "${logo}" "${PROJECT_ROOT}/"
    echo "Скопирован $(basename "${logo}") в корень проекта."
  fi
done

echo "==> Запуск бота..."
docker compose up -d bot

echo ""
echo "Готово. Redis RDB при необходимости восстанавливайте вручную (см. docs/MIGRATION_TO_NEW_SERVER.md)."
echo "Проверка: curl -H \"X-API-Key: <WEB_API_DEFAULT_TOKEN>\" http://127.0.0.1:\${WEB_API_PORT:-8080}/health"
