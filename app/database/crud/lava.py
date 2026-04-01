"""CRUD для платежей Lava.top."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LavaPayment


logger = structlog.get_logger(__name__)


async def create_lava_payment(
    db: AsyncSession,
    *,
    user_id: int | None,
    contract_id: str,
    offer_id: str,
    amount_kopeks: int,
    currency: str,
    payment_url: str | None,
    email: str | None,
    expires_at: datetime | None,
    metadata_json: dict[str, Any] | None,
) -> LavaPayment:
    payment = LavaPayment(
        user_id=user_id,
        contract_id=contract_id,
        offer_id=offer_id,
        amount_kopeks=amount_kopeks,
        currency=currency,
        payment_url=payment_url,
        email=email,
        status='pending',
        is_paid=False,
        metadata_json=metadata_json,
        expires_at=expires_at,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    logger.info('Создан платеж Lava', contract_id=contract_id, user_id=user_id)
    return payment


async def get_lava_payment_by_contract_id(db: AsyncSession, contract_id: str) -> LavaPayment | None:
    result = await db.execute(select(LavaPayment).where(LavaPayment.contract_id == contract_id))
    return result.scalar_one_or_none()


async def get_lava_payment_by_id(db: AsyncSession, payment_id: int) -> LavaPayment | None:
    result = await db.execute(select(LavaPayment).where(LavaPayment.id == payment_id))
    return result.scalar_one_or_none()


async def get_lava_payment_by_id_for_update(db: AsyncSession, payment_id: int) -> LavaPayment | None:
    result = await db.execute(
        select(LavaPayment)
        .where(LavaPayment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()
