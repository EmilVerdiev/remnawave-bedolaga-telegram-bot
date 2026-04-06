# Перенос бота и личного кабинета на другой сервер

Инструкция для стека **Docker Compose** из этого репозитория: `postgres` + `redis` + `bot` (в одном контейнере бота — API и кабинет на порту **8080** внутри сети контейнеров).

## Что переносится

| Компонент | Файл / действие |
|-----------|------------------|
| PostgreSQL | `postgres.dump` (формат `-Fc`, восстановление через `pg_restore`) |
| Файлы | `uploads/`, `data/`, `locales/` → архив `app_files.tar.gz` |
| Секреты и настройки | копия `.env` в бандле как `dotenv.migration_COPY_SECRET` |
| Redis (опционально) | `redis-dump.rdb` — не обязателен для многих установок |
| Логотип | `vpn_logo.PNG` / `vpn_logo.png` при наличии в корне проекта |

Папка `migration_bundle/<дата_время>/` **не попадает в git** (корень репозитория по умолчанию не в whitelist). Всё равно **не загружайте бандл в публичные места**: внутри секреты.

---

## Часть A — старый сервер

### 1. Остановить бота (короткая пауза записи)

Из корня проекта:

```bash
cd /path/to/remnawave-bedolaga-telegram-bot
docker compose stop bot
```

Postgres и Redis можно оставить запущенными на время дампа.

### 2. Создать бэкап одной командой

```bash
chmod +x scripts/backup_for_migration.sh
./scripts/backup_for_migration.sh
```

Скрипт создаст каталог вида `migration_bundle/20260101_143022/` с содержимым из таблицы выше.

Если контейнер БД называется иначе:

```bash
BACKUP_PG_CONTAINER=имя_контейнера_postgres ./scripts/backup_for_migration.sh
BACKUP_REDIS_CONTAINER=имя_redis ./scripts/backup_for_migration.sh
```

### 3. Перенести папку бандла на новый сервер

Пример:

```bash
scp -r ./migration_bundle/20260101_143022 user@NEW_SERVER:/home/user/
```

Или `rsync -avz`.

---

## Часть B — новый сервер (Cursor / SSH)

### 1. Зависимости

- Docker и Docker Compose v2 (`docker compose`).
- Git.

### 2. Клонировать репозиторий

Рекомендуется **тот же коммит/ветка**, что и на старом проде (или не ниже по миграциям Alembic).

```bash
git clone https://github.com/ВАШ_АККАУНТ/remnawave-bedolaga-telegram-bot.git
cd remnawave-bedolaga-telegram-bot
```

### 3. Положить бандл

Скопируйте каталог бандла в любое место, например `~/migration_incoming/20260101_143022/`.

### 4. Восстановление

**Важно:** до запуска скрипта в корне проекта должен быть рабочий `docker-compose.yml` и при необходимости **черновой** `.env` с теми же `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, что будут у нового Postgres (как в compose). Скрипт восстановления **перезапишет** `.env` из бандла, если есть `dotenv.migration_COPY_SECRET`.

```bash
chmod +x scripts/restore_after_migration.sh
./scripts/restore_after_migration.sh ~/migration_incoming/20260101_143022
```

Если имя контейнера Postgres другое:

```bash
RESTORE_PG_CONTAINER=имя_контейнера ./scripts/restore_after_migration.sh ~/migration_incoming/20260101_143022
```

### 5. Правки `.env` после переноса

Обязательно проверьте:

- `CABINET_URL`, `CABINET_ALLOWED_ORIGINS` — новый домен **https://…**
- URL вебхуков платёжных систем (Lava, YooKassa и т.д.)
- `POSTGRES_PASSWORD` — если на новом сервере задали другой пароль в `docker-compose.yml` / `.env`, всё должно совпадать
- `WEB_API_DEFAULT_TOKEN`, `BOT_TOKEN` — при переносе копии из старого `.env` уже будут в `.env`

Перезапуск после правок:

```bash
docker compose up -d --force-recreate bot
```

### 6. HTTPS и домен

Снаружи кабинет и API открываются через **reverse proxy** (nginx, Caddy) на `127.0.0.1:${WEB_API_PORT:-8080}`. Настройте TLS (Let’s Encrypt).

### 7. Проверка

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-API-Key: ВАШ_WEB_API_DEFAULT_TOKEN" \
  "http://127.0.0.1:${WEB_API_PORT:-8080}/health"
```

Ожидается `200`. В Telegram — базовые сценарии бота и вход в кабинет.

---

## Redis (опционально)

Часто сессии и кэш можно **сбросить**: поднять пустой Redis. Если нужен тот же RDB:

1. Остановите `redis` в compose.
2. Подставьте `redis-dump.rdb` в том данных Redis (зависит от имени volume; проще скопировать через временный контейнер с тем же volume).
3. Запустите `redis` снова.

Детали зависят от имени volume (`docker volume ls`). При сомнениях оставьте пустой Redis.

---

## Откат

На старом сервере не удаляйте данные, пока не убедитесь, что новый прод стабилен. Держите бандл в зашифрованном архиве или на защищённом носителе.

---

## Скрипты

- `scripts/backup_for_migration.sh` — формирование бандла на старом сервере.
- `scripts/restore_after_migration.sh` — восстановление на новом сервере.
