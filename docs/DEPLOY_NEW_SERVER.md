# Развёртывание Bedolaga Bot на новом сервере (новый домен)

Руководство для стека **Docker Compose** из репозитория: `postgres` + `redis` + `bot` (в контейнере бота — Telegram, FastAPI и Cabinet API на порту **8080**). Предполагается **новый домен**, при необходимости **те же** Remnawave и Platega, что и на текущем проде.

См. также: [MIGRATION_TO_NEW_SERVER.md](./MIGRATION_TO_NEW_SERVER.md) (перенос БД со старого сервера), [miniapp-setup.md](./miniapp-setup.md) (мини-приложение).

---

## 1. Архитектура

| Компонент | Роль |
|-----------|------|
| `postgres` | База данных бота |
| `redis` | Кэш, корзина, сессии |
| `bot` | Telegram-бот + **Web API** + **Cabinet API** → `0.0.0.0:8080` внутри сети Docker |

Снаружи HTTPS обычно отдаёт **nginx** (или Caddy), проксируя на `127.0.0.1:8080`.

**Веб-кабинет** ([bedolaga-cabinet](https://github.com/BEDOLAGA-DEV/bedolaga-cabinet)) — отдельная сборка (React): статика на nginx, запросы к API — на тот же домен или отдельный API-поддомен, в зависимости от настроек фронта.

---

## 2. Важные ограничения

### Telegram

- **Один `BOT_TOKEN` = один активный процесс, получающий апдейты.** Два независимых прода с одним токеном параллельно не настраиваются.

### Platega

- У мерчанта задаётся **один публичный URL вебхука**. При **переносе** сервера — меняешь URL в кабинете Platega на новый HTTPS.  
- **Два одновременно работающих инстанса** с **одной** учёткой Platega и одним вебхуком — невозможны; нужен отдельный мерчант или один бэкенд.

### Remnawave

- Можно использовать **те же** `REMNAWAVE_API_URL` и ключ — пользователи будут общие для панели. Для изолированного «второго проекта» обычно поднимают отдельную панель.

---

## 3. Требования к серверу

- Linux с **Docker** и **Docker Compose v2**
- Открыты порты **80** и **443** (для Let’s Encrypt и HTTPS)
- DNS: **A** (и при необходимости **AAAA**) записи домена на IP сервера

Пример установки зависимостей (Debian/Ubuntu):

```bash
sudo apt update && sudo apt install -y git docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
sudo usermod -aG docker "$USER"
# перелогиниться, чтобы группа docker применилась
```

---

## 4. Клонирование и первый запуск

```bash
git clone git@github.com:YOUR_ACCOUNT/remnawave-bedolaga-telegram-bot.git
cd remnawave-bedolaga-telegram-bot
cp .env.example .env
```

Отредактируй `.env` (см. [раздел 5](#5-шаблон-переменных-окружения)). Убедись, что `POSTGRES_*` в `.env` совпадают с подстановками в `docker-compose.yml` (или задай явно в compose).

Сборка и старт:

```bash
docker compose build bot
docker compose up -d
```

Проверка health **на хосте** (подставь токен из `WEB_API_DEFAULT_TOKEN`):

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-API-Key: YOUR_WEB_API_DEFAULT_TOKEN" \
  "http://127.0.0.1:8080/health"
```

Ожидается `200`.

После любого изменения `.env`:

```bash
docker compose up -d --force-recreate bot
```

---

## 5. Шаблон переменных окружения

Подставь вместо `cabinet.NEWDOMAIN.ru` / `NEWDOMAIN.ru` свой домен. Секреты сгенерируй заново, если это новый прод.

```env
# ----- Уникальное для этого инстанса -----
BOT_TOKEN=
BOT_USERNAME=
ADMIN_IDS=

CABINET_URL=https://cabinet.NEWDOMAIN.ru
CABINET_ALLOWED_ORIGINS=https://cabinet.NEWDOMAIN.ru
CABINET_JWT_SECRET=

# UUID страницы подписки в Remnawave (GET /api/subscription-page-configs в панели)
CABINET_REMNA_SUB_CONFIG=

MAIN_MENU_MODE=cabinet
MINIAPP_CUSTOM_URL=https://cabinet.NEWDOMAIN.ru

WEB_API_ENABLED=true
WEB_API_HOST=0.0.0.0
WEB_API_PORT=8080
WEB_API_ALLOWED_ORIGINS=https://cabinet.NEWDOMAIN.ru
WEB_API_DEFAULT_TOKEN=
WEB_API_DOCS_ENABLED=false

BOT_RUN_MODE=polling

# ----- Remnawave (часто копия с текущего прода) -----
REMNAWAVE_API_URL=https://panel.example.com
REMNAWAVE_API_KEY=
REMNAWAVE_AUTH_TYPE=api_key
REMNAWAVE_USER_USERNAME_TEMPLATE=user_{telegram_id}
REMNAWAVE_USER_DESCRIPTION_TEMPLATE=Bot user: {full_name} {username}
REMNAWAVE_USER_DELETE_MODE=delete
REMNAWAVE_AUTO_SYNC_ENABLED=false

# ----- Platega (креды те же; URL — под новый домен) -----
PLATEGA_ENABLED=true
PLATEGA_MERCHANT_ID=
PLATEGA_SECRET=
PLATEGA_BASE_URL=https://app.platega.io
PLATEGA_MIN_AMOUNT_KOPEKS=100
PLATEGA_RETURN_URL=https://cabinet.NEWDOMAIN.ru/balance?paid=1
PLATEGA_FAILED_URL=https://cabinet.NEWDOMAIN.ru/balance?failed=1

# В кабинете Platega укажи Webhook URL, совпадающий с публичным маршрутом nginx → бот, например:
# https://cabinet.NEWDOMAIN.ru/platega-webhook

# ----- База и Redis (docker-compose) -----
DATABASE_MODE=auto
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=remnawave_bedolaga_bot
POSTGRES_USER=remnawave_bedolaga
POSTGRES_PASSWORD=
REDIS_URL=redis://redis:6379/0

TZ=Europe/Moscow
```

Полный перечень ключей — в `.env.example` в корне репозитория.

---

## 6. Nginx и TLS

### Сертификат (Let’s Encrypt)

```bash
sudo certbot certonly --nginx -d cabinet.NEWDOMAIN.ru
# или: sudo certbot --nginx -d cabinet.NEWDOMAIN.ru
```

### Пример `server` для кабинета + прокси API

Статика фронта — из каталога сборки `bedolaga-cabinet` (`npm run build`). Пути `/api/` и вебхуков приведи к соответствию с тем, как настроен фронт (`VITE_*` / base URL).

```nginx
server {
    listen 80;
    server_name cabinet.NEWDOMAIN.ru;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name cabinet.NEWDOMAIN.ru;

    ssl_certificate     /etc/letsencrypt/live/cabinet.NEWDOMAIN.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cabinet.NEWDOMAIN.ru/privkey.pem;

    root /var/www/cabinet-dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /platega-webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Убедись, что в `docker-compose.yml` порт `8080` проброшен на хост **только на localhost**, если API не должен быть доступен извне напрямую:

```yaml
ports:
  - '127.0.0.1:8080:8080'
```

(При необходимости измени и пересоздай контейнер.)

---

## 7. Кабинет (bedolaga-cabinet)

1. Собери фронт с переменными окружения, указывающими на **HTTPS API** нового домена (см. README кабинета).
2. Выложи артефакты в каталог, указанный в `root` nginx.
3. `CABINET_URL` и `CABINET_ALLOWED_ORIGINS` в `.env` бота должны совпадать с origin фронта.

---

## 8. Мини-приложение Telegram

- `MINIAPP_CUSTOM_URL` и `MAIN_MENU_MODE=cabinet` — как в `.env`.
- В @BotFather для бота задай **Web App URL** = тот же HTTPS, что и миниапп.
- Детали статики и прокси — [miniapp-setup.md](./miniapp-setup.md).

---

## 9. Чеклист после деплоя

| Шаг | Действие |
|-----|----------|
| 1 | `/start` в Telegram — бот отвечает |
| 2 | `GET /health` с заголовком `X-API-Key` — 200 |
| 3 | Вход в кабинет в браузере |
| 4 | Тест оплаты Platega + запись в логах бота по вебхуку |
| 5 | Выдача подписки / пользователь в Remnawave |

---

## 10. Перенос данных со старого сервера

Если нужна **копия БД и файлов**, используй скрипты и инструкцию в [MIGRATION_TO_NEW_SERVER.md](./MIGRATION_TO_NEW_SERVER.md). После восстановления обязательно обнови домены и URL вебхуков в `.env` и в кабинетах платёжных систем.
