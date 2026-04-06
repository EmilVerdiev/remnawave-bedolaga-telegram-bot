"""seed FAQ page: paid traffic / mobile whitelist (ru)

Revision ID: 0054
Revises: 0053
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0054'
down_revision: Union[str, None] = '0053'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FAQ_TITLE = 'А почему есть платный трафик?'

_FAQ_CONTENT = (
    'Есть 2 вида обхода блокировок: когда вы включаете «Обход» для домашнего или офисного интернета, '
    'и когда включают глушилки мобильного интернета и начинают работать «белые списки», '
    'по которым обычно глушится вообще все 🙂\n\n'
    'Так вот, трафик по обходу блокировок по Wi-Fi — полностью безлимитный! Ютуб в 4К, 1 Тб трафика '
    'на рилсах в Инсте, вообще без проблем.\n\n'
    'А вот если нужно сделать обход «белых списков» на мобильном интернете, там всё сложнее и дороже. '
    'И как раз поэтому трафик уже не безлимитный на базовом тарифе. По умолчанию мы добавляем 100 Гб трафика, '
    'но при необходимости его можно докупить. Либо и вовсе взять сразу безлимитный ВИП-тариф 😎'
)


def upgrade() -> None:
    conn = op.get_bind()
    # Два разных bind-параметра для одного заголовка: иначе asyncpg смешивает text/varchar для одного $N.
    stmt = (
        sa.text(
            """
            INSERT INTO faq_pages (language, title, content, display_order, is_active, created_at, updated_at)
            SELECT
                'ru',
                :title_insert,
                :content,
                COALESCE((SELECT MAX(display_order) FROM faq_pages fp WHERE fp.language = 'ru'), 0) + 1,
                true,
                NOW(),
                NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM faq_pages fp
                WHERE fp.language = 'ru' AND fp.title = :title_check
            )
            """
        )
        .bindparams(
            sa.bindparam('title_insert', type_=sa.String(255)),
            sa.bindparam('title_check', type_=sa.String(255)),
            sa.bindparam('content', type_=sa.Text()),
        )
    )
    conn.execute(
        stmt,
        {
            'title_insert': _FAQ_TITLE,
            'title_check': _FAQ_TITLE,
            'content': _FAQ_CONTENT,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM faq_pages WHERE language = 'ru' AND title = :title"),
        {'title': _FAQ_TITLE},
    )
