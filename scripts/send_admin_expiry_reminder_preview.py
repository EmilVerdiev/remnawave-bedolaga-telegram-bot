"""Превью уведомления об истекающей подписке (как в мониторинге).

Примеры:

  cd /app && .venv/bin/python scripts/send_admin_expiry_reminder_preview.py
      → одно сообщение (5 дн.), первый ID из ADMIN_IDS

  PREVIEW_TELEGRAM_ID=123456789 cd /app && .venv/bin/python scripts/send_admin_expiry_reminder_preview.py --all-obhodich
      → четыре сообщения Обходыч (5/3/2/1 дня) нужному telegram_id

  python scripts/send_admin_expiry_reminder_preview.py --telegram-id 123456 --days 2
"""

from __future__ import annotations

import argparse
import asyncio
import os

from aiogram import Bot

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.crud.saved_payment_method import get_user_ids_with_active_payment_methods
from app.database.crud.subscription import get_subscription_by_user_id
from app.database.crud.user import get_user_by_telegram_id
from app.services.monitoring_service import MonitoringService, _OBHODICH_EXPIRING_NOTICE_DAYS


def _resolve_telegram_id(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    env_id = os.environ.get('PREVIEW_TELEGRAM_ID', '').strip()
    if env_id:
        return int(env_id)
    raw = (settings.ADMIN_IDS or '').strip()
    if not raw:
        raise SystemExit('Укажите получателя: --telegram-id, PREVIEW_TELEGRAM_ID или заполните ADMIN_IDS')
    return int(raw.split(',')[0].strip())


async def _preview_for_days(bot: Bot, user, sub: object, *, days: int, has_card: bool) -> bool:
    svc = MonitoringService(bot=bot)
    return await svc._send_subscription_expiring_notification(user, sub, days=days, has_saved_card=has_card)


async def main() -> None:
    parser = argparse.ArgumentParser(description='Отправить тест истекающей подписки')
    parser.add_argument('--telegram-id', type=int, default=None, help='Telegram ID получателя')
    parser.add_argument('--days', type=int, default=None, metavar='N', help='Только один вариант (дней до конца)')
    parser.add_argument(
        '--all-obhodich',
        action='store_true',
        help='Отправить все варианты Обходыч (5/3/2/1 дня) по очереди',
    )
    args = parser.parse_args()

    tg_id = _resolve_telegram_id(args.telegram_id)
    delay_sec = float(os.environ.get('PREVIEW_MESSAGES_DELAY_SEC', '2'))

    async with AsyncSessionLocal() as db:
        user = await get_user_by_telegram_id(db, tg_id)
        if not user or not user.telegram_id:
            raise SystemExit(f'Пользователь с telegram_id={tg_id} не найден или без telegram_id')
        sub = await get_subscription_by_user_id(db, user.id)
        if not sub:
            raise SystemExit(f'У пользователя user_id={user.id} нет подписки в БД — нечего привязать к тексту')

        has_card = False
        if settings.ENABLE_AUTOPAY and getattr(settings, 'YOOKASSA_RECURRENT_ENABLED', False) and sub.autopay_enabled:
            with_cards = await get_user_ids_with_active_payment_methods(db, [user.id])
            has_card = user.id in with_cards

    if args.days is not None:
        day_list = [args.days]
    elif args.all_obhodich:
        day_list = sorted(_OBHODICH_EXPIRING_NOTICE_DAYS, reverse=True)
    else:
        day_list = [5]

    bot = Bot(token=settings.BOT_TOKEN)
    results: list[tuple[int, bool]] = []
    try:
        for i, d in enumerate(day_list):
            if i > 0 and delay_sec > 0:
                await asyncio.sleep(delay_sec)
            ok = await _preview_for_days(bot, user, sub, days=d, has_card=has_card)
            results.append((d, ok))
    finally:
        await bot.session.close()

    for d, ok in results:
        print(('OK' if ok else 'FAIL'), f'days={d}', f'telegram_id={tg_id}', f'subscription_id={sub.id}')


if __name__ == '__main__':
    asyncio.run(main())
