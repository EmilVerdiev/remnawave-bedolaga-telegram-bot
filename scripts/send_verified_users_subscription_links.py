"""One-shot: email all email_verified users their active subscription import link."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.cabinet.services.email_service import email_service
from app.cabinet.services.email_templates import EmailNotificationTemplates
from app.config import settings
from app.database.database import AsyncSessionLocal
from app.services.notification_delivery_service import NotificationType

QUERY = """
SELECT DISTINCT ON (u.id)
    u.email,
    COALESCE(NULLIF(trim(u.language), ''), 'ru') AS lang,
    COALESCE(NULLIF(trim(t.name), ''), 'VPN') AS tariff_name,
    s.start_date,
    s.end_date,
    s.subscription_url
FROM users u
JOIN subscriptions s ON s.user_id = u.id
LEFT JOIN tariffs t ON t.id = s.tariff_id
WHERE u.email_verified = true
  AND u.email IS NOT NULL
  AND trim(u.email) <> ''
  AND s.status IN ('active', 'trial')
  AND s.subscription_url IS NOT NULL
  AND trim(s.subscription_url) <> ''
ORDER BY u.id, s.end_date DESC NULLS LAST
"""

ALLOWED_LANGS = frozenset({'ru', 'en', 'zh', 'ua', 'fa'})


def norm_lang(code: str | None) -> str:
    c = (code or 'ru').lower().strip()[:2]
    return c if c in ALLOWED_LANGS else 'ru'


async def main() -> None:
    from zoneinfo import ZoneInfo

    templates = EmailNotificationTemplates()
    cabinet = (settings.CABINET_URL or '').rstrip('/')

    async with AsyncSessionLocal() as session:
        result = await session.execute(text(QUERY))
        rows = result.mappings().all()

    sent = failed = 0
    for i, row in enumerate(rows):
        email_addr = row['email'].strip()
        lang = norm_lang(row['lang'])
        start = row['start_date']
        end = row['end_date']
        if start is not None and end is not None:
            period_days = max(1, (end - start).days)
        else:
            period_days = 30

        subj_suffix = ''
        if end is not None:
            end_aware = end if end.tzinfo else end.replace(tzinfo=ZoneInfo('UTC'))
            end_msk = end_aware.astimezone(ZoneInfo('Europe/Moscow'))
            subj_suffix = f' · {end_msk.strftime("%d.%m.%Y")}'

        tpl = templates.get_template(
            NotificationType.GUEST_SUBSCRIPTION_DELIVERED,
            lang,
            {
                'tariff_name': row['tariff_name'] or 'VPN',
                'period_days': period_days,
                'cabinet_url': cabinet,
                'cabinet_email': email_addr,
                'cabinet_password': '',
                'subscription_url': row['subscription_url'].strip(),
            },
        )
        if not tpl:
            failed += 1
            continue

        subject = tpl['subject'] + subj_suffix
        ok = await asyncio.to_thread(
            email_service.send_email,
            email_addr,
            subject,
            tpl['body_html'],
        )
        if ok:
            sent += 1
        else:
            failed += 1

        if i + 1 < len(rows):
            await asyncio.sleep(1.5)

    print(f'done: recipients={len(rows)} sent={sent} failed={failed}')


if __name__ == '__main__':
    asyncio.run(main())
