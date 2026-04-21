"""Одна миграция: пресеты платного триала и брендинга Mini App в system_settings.

Revision ID: 0056
Revises: 0055
Create Date: 2026-04-20

Один INSERT … ON CONFLICT (key) DO NOTHING. Тарифы в ``tariffs`` не создаются (нужны сквады/цены).
После деплоя задайте TRIAL_TARIFF_ID и is_trial_available у тарифа в админке.

Downgrade удаляет только строки с description LIKE ``seed:0056:%``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0056'
down_revision: Union[str, None] = '0055'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED_MARKER = 'seed:0056'

_SETTINGS_ROWS: tuple[tuple[str, str, str], ...] = (
    ('TRIAL_PAYMENT_ENABLED', 'true', 'Платная активация триала (включено)'),
    ('TRIAL_ACTIVATION_PRICE', '10000', 'Цена активации триала, коп. (100 ₽); измените под свой прайс'),
    ('MINIAPP_SERVICE_NAME_RU', 'VPN (второй бот)', 'Название сервиса в Mini App (RU)'),
    ('MINIAPP_SERVICE_NAME_EN', 'VPN (second bot)', 'Название сервиса в Mini App (EN)'),
    ('MINIAPP_SERVICE_DESCRIPTION_RU', 'Быстрое и безопасное подключение', 'Описание в Mini App (RU)'),
    ('MINIAPP_SERVICE_DESCRIPTION_EN', 'Fast and secure connection', 'Описание в Mini App (EN)'),
    ('PAYMENT_SERVICE_NAME', 'VPN — второй бот', 'Имя в чеках/описаниях платежей'),
)


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    values_sql = ', '.join(
        f'({_sql_str(key)}, {_sql_str(val)}, {_sql_str(f"{_SEED_MARKER}: {note}")})'
        for key, val, note in _SETTINGS_ROWS
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO system_settings (key, value, description)
            VALUES {values_sql}
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM system_settings
            WHERE description IS NOT NULL AND description LIKE :marker
            """
        ),
        {'marker': f'{_SEED_MARKER}:%'},
    )
