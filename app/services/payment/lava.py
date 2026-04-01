"""Интеграция Lava.top (invoice API v3 + webhook).

Суммы: ручной LAVA_OFFER_AMOUNTS_MAP_JSON (копейки → UUID оффера),
динамический каталог GET /api/v2/products (LAVA_FETCH_PRODUCTS_FROM_API),
или одна пара LAVA_DEFAULT_OFFER_ID + LAVA_EXPECTED_AMOUNT_KOPEKS.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import PaymentMethod, TransactionType
from app.external.lava_client import LavaAPIError, create_invoice_v3, fetch_all_products_v2
from app.utils.payment_logger import payment_logger as logger
from app.utils.user_utils import format_referrer_info


def _parse_static_offer_map() -> dict[int, str]:
    raw = settings.LAVA_OFFER_AMOUNTS_MAP_JSON
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    out: dict[int, str] = {}
    for k, v in data.items():
        try:
            out[int(k)] = str(v).strip()
        except (TypeError, ValueError):
            continue
    return out


_lava_offer_map_cache: tuple[float, dict[int, str]] | None = None


def _product_type_filter() -> set[str] | None:
    raw = (settings.LAVA_API_PRODUCT_TYPES or '').strip()
    if not raw:
        return None
    return {x.strip().upper() for x in raw.split(',') if x.strip()}


def _build_amount_offer_map_from_products(products: list[dict[str, Any]]) -> dict[int, str]:
    """Сумма в копейках → offerId по ценам ONE_TIME в выбранной валюте."""
    currency = (settings.LAVA_CURRENCY or 'RUB').upper()
    type_filter = _product_type_filter()
    out: dict[int, str] = {}
    for prod in products:
        ptype = (prod.get('type') or '').strip().upper()
        if type_filter is not None and ptype not in type_filter:
            continue
        for offer in prod.get('offers') or []:
            oid = str(offer.get('id') or '').strip()
            if not oid:
                continue
            for price in offer.get('prices') or []:
                if (price.get('currency') or '').upper() != currency:
                    continue
                if price.get('periodicity') != 'ONE_TIME':
                    continue
                amt = price.get('amount')
                if amt is None:
                    continue
                try:
                    kopeks = int(round(float(amt) * 100))
                except (TypeError, ValueError):
                    continue
                if kopeks < settings.LAVA_MIN_AMOUNT_KOPEKS or kopeks > settings.LAVA_MAX_AMOUNT_KOPEKS:
                    continue
                if kopeks in out:
                    if out[kopeks] != oid:
                        logger.warning(
                            'Lava API: несколько офферов на одну сумму, оставляем первый',
                            amount_kopeks=kopeks,
                            kept_offer_id=out[kopeks],
                            skipped_offer_id=oid,
                        )
                    continue
                out[kopeks] = oid
    return out


def _default_pair_offer_map() -> dict[int, str]:
    if not settings.LAVA_DEFAULT_OFFER_ID or settings.LAVA_EXPECTED_AMOUNT_KOPEKS is None:
        return {}
    amount = int(settings.LAVA_EXPECTED_AMOUNT_KOPEKS)
    if amount < settings.LAVA_MIN_AMOUNT_KOPEKS or amount > settings.LAVA_MAX_AMOUNT_KOPEKS:
        return {}
    return {amount: str(settings.LAVA_DEFAULT_OFFER_ID).strip()}


async def get_lava_amount_to_offer_id_map() -> dict[int, str]:
    """Приоритет: ручной JSON → API (кэш) → одна пара default/expected."""
    static = _parse_static_offer_map()
    if static:
        return static

    global _lava_offer_map_cache
    ttl = max(5, int(settings.LAVA_API_PRODUCTS_CACHE_TTL_SECONDS))

    api_map: dict[int, str] = {}
    if settings.LAVA_FETCH_PRODUCTS_FROM_API:
        now = time.monotonic()
        if _lava_offer_map_cache is not None and (now - _lava_offer_map_cache[0]) < ttl:
            api_map = _lava_offer_map_cache[1]
        else:
            try:
                products = await fetch_all_products_v2()
                api_map = _build_amount_offer_map_from_products(products)
                _lava_offer_map_cache = (time.monotonic(), api_map)
            except LavaAPIError as e:
                logger.error('Lava: каталог API недоступен', status_code=e.status_code)
                if _lava_offer_map_cache is not None:
                    api_map = _lava_offer_map_cache[1]
            except Exception as e:
                logger.exception('Lava: ошибка загрузки каталога', e=e)
                if _lava_offer_map_cache is not None:
                    api_map = _lava_offer_map_cache[1]

    if api_map:
        return api_map
    return _default_pair_offer_map()


def _buyer_email(user_id: int | None, email: str | None) -> str:
    if email and '@' in email:
        return email.strip()
    tpl = settings.LAVA_PLACEHOLDER_EMAIL_TEMPLATE or 'tg_{user_id}@telegram.bot'
    uid = user_id if user_id is not None else 0
    return tpl.format(user_id=uid)


class LavaPaymentMixin:
    async def create_lava_payment(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        amount_kopeks: int,
        description: str = 'Пополнение баланса',
        email: str | None = None,
        language: str = 'ru',
        payment_method: str | None = None,
        lava_payment_method_type: str | None = None,
    ) -> dict[str, Any] | None:
        if not settings.is_lava_enabled():
            logger.error('Lava не настроена')
            return None

        if amount_kopeks < settings.LAVA_MIN_AMOUNT_KOPEKS:
            logger.warning('Lava: сумма меньше минимальной', amount_kopeks=amount_kopeks)
            return None

        if amount_kopeks > settings.LAVA_MAX_AMOUNT_KOPEKS:
            logger.warning('Lava: сумма больше максимальной', amount_kopeks=amount_kopeks)
            return None

        offer_map = await get_lava_amount_to_offer_id_map()
        offer_id = offer_map.get(amount_kopeks)
        if not offer_id:
            logger.warning(
                'Lava: нет оффера для суммы (LAVA_OFFER_AMOUNTS_MAP_JSON или LAVA_DEFAULT_OFFER_ID)',
                amount_kopeks=amount_kopeks,
            )
            return None

        currency = (settings.LAVA_CURRENCY or 'RUB').upper()
        buyer_email = _buyer_email(user_id, email)

        body: dict[str, Any] = {
            'email': buyer_email,
            'offerId': offer_id,
            'currency': currency,
        }
        if settings.LAVA_BUYER_LANGUAGE:
            body['buyerLanguage'] = settings.LAVA_BUYER_LANGUAGE
        if settings.LAVA_PAYMENT_PROVIDER:
            body['paymentProvider'] = settings.LAVA_PAYMENT_PROVIDER
        effective_method_type = (lava_payment_method_type or settings.LAVA_PAYMENT_METHOD_TYPE or '').strip().upper()
        if effective_method_type:
            body['paymentMethod'] = effective_method_type

        expires_at = datetime.now(UTC) + timedelta(seconds=settings.LAVA_PAYMENT_TIMEOUT_SECONDS)

        metadata = {
            'user_id': user_id,
            'amount_kopeks': amount_kopeks,
            'description': description,
            'language': language,
            'type': 'balance_topup',
            'payment_method': payment_method or 'lava',
        }

        try:
            resp = await create_invoice_v3(body)
        except LavaAPIError as e:
            logger.exception('Lava: ошибка API', e=e)
            return None

        contract_id = str(resp.get('id') or '').strip()
        payment_url = resp.get('paymentUrl')
        if not contract_id:
            logger.error('Lava: в ответе нет id контракта', resp=resp)
            return None

        lava_crud = import_module('app.database.crud.lava')
        local = await lava_crud.create_lava_payment(
            db=db,
            user_id=user_id,
            contract_id=contract_id,
            offer_id=offer_id,
            amount_kopeks=amount_kopeks,
            currency=currency,
            payment_url=payment_url,
            email=buyer_email,
            expires_at=expires_at,
            metadata_json=metadata,
        )

        logger.info(
            'Lava: создан платёж',
            contract_id=contract_id,
            user_id=user_id,
            amount_kopeks=amount_kopeks,
        )

        return {
            'contract_id': contract_id,
            'order_id': contract_id,
            'amount_kopeks': amount_kopeks,
            'currency': currency,
            'payment_url': payment_url,
            'expires_at': expires_at.isoformat(),
            'local_payment_id': local.id,
        }

    async def process_lava_webhook(self, db: AsyncSession, payload: dict[str, Any]) -> bool:
        try:
            event_type = payload.get('eventType')
            contract_id = str(payload.get('contractId') or '').strip()

            if not contract_id:
                logger.warning('Lava webhook: нет contractId')
                return False

            lava_crud = import_module('app.database.crud.lava')
            payment = await lava_crud.get_lava_payment_by_contract_id(db, contract_id)
            if not payment:
                logger.warning('Lava webhook: платёж не найден (ack)', contract_id=contract_id)
                return True

            locked = await lava_crud.get_lava_payment_by_id_for_update(db, payment.id)
            if not locked:
                logger.error('Lava webhook: lock не получен', payment_id=payment.id)
                return False
            payment = locked

            if event_type == 'payment.failed':
                payment.status = 'failed'
                payment.callback_payload = payload
                payment.updated_at = datetime.now(UTC)
                await db.commit()
                logger.info('Lava webhook: отказ оплаты', contract_id=contract_id)
                return True

            if event_type != 'payment.success':
                logger.info('Lava webhook: игнор события', event_type=event_type)
                return True

            if payment.is_paid:
                logger.info('Lava webhook: уже оплачен', contract_id=contract_id)
                return True

            amount = float(payload.get('amount') or 0)
            expected = payment.amount_kopeks / 100.0
            if abs(amount - expected) > 0.02:
                logger.warning(
                    'Lava webhook: сумма не совпадает',
                    expected=expected,
                    got=amount,
                    contract_id=contract_id,
                )
                return False

            payment.status = 'success'
            payment.is_paid = True
            payment.paid_at = datetime.now(UTC)
            payment.callback_payload = payload
            payment.updated_at = datetime.now(UTC)
            await db.flush()

            return await self._finalize_lava_payment(db, payment, trigger='webhook')
        except Exception as e:
            logger.exception('Lava webhook: ошибка', e=e)
            return False

    async def _finalize_lava_payment(
        self,
        db: AsyncSession,
        payment: Any,
        *,
        trigger: str,
    ) -> bool:
        payment_module = import_module('app.services.payment_service')

        if payment.transaction_id:
            logger.info('Lava: уже есть транзакция', contract_id=payment.contract_id, trigger=trigger)
            return True

        fk_metadata = dict(getattr(payment, 'metadata_json', {}) or {})
        from app.services.payment.common import try_fulfill_guest_purchase

        guest_result = await try_fulfill_guest_purchase(
            db,
            metadata=fk_metadata,
            payment_amount_kopeks=payment.amount_kopeks,
            provider_payment_id=str(payment.contract_id),
            provider_name='lava',
        )
        if guest_result is not None:
            return True

        user = await payment_module.get_user_by_id(db, payment.user_id)
        if not user:
            logger.error('Lava: пользователь не найден', user_id=payment.user_id)
            return False

        transaction = await payment_module.create_transaction(
            db,
            user_id=payment.user_id,
            type=TransactionType.DEPOSIT,
            amount_kopeks=payment.amount_kopeks,
            description=f'Пополнение через Lava (#{payment.contract_id})',
            payment_method=PaymentMethod.LAVA,
            external_id=str(payment.contract_id),
            is_completed=True,
            created_at=getattr(payment, 'created_at', None),
            commit=False,
        )

        payment.transaction_id = transaction.id
        payment.updated_at = datetime.now(UTC)
        await db.flush()

        from app.database.crud.user import lock_user_for_update

        user = await lock_user_for_update(db, user)

        old_balance = user.balance_kopeks
        was_first_topup = not user.has_made_first_topup

        user.balance_kopeks += payment.amount_kopeks
        user.updated_at = datetime.now(UTC)

        promo_group = user.get_primary_promo_group()
        subscription = getattr(user, 'subscription', None)
        referrer_info = format_referrer_info(user)
        topup_status = 'Первое пополнение' if was_first_topup else 'Пополнение'

        await db.commit()

        from app.database.crud.transaction import emit_transaction_side_effects

        await emit_transaction_side_effects(
            db,
            transaction,
            amount_kopeks=payment.amount_kopeks,
            user_id=payment.user_id,
            type=TransactionType.DEPOSIT,
            payment_method=PaymentMethod.LAVA,
            external_id=str(payment.contract_id),
        )

        try:
            from app.services.referral_service import process_referral_topup

            await process_referral_topup(db, user.id, payment.amount_kopeks, getattr(self, 'bot', None))
        except Exception as error:
            logger.error('Lava: реферальное пополнение', error=error)

        if was_first_topup and not user.has_made_first_topup and not user.referred_by_id:
            user.has_made_first_topup = True
            await db.commit()

        await db.refresh(user)
        await db.refresh(payment)

        if getattr(self, 'bot', None):
            try:
                from app.services.admin_notification_service import AdminNotificationService

                notification_service = AdminNotificationService(self.bot)
                await notification_service.send_balance_topup_notification(
                    user,
                    transaction,
                    old_balance,
                    topup_status=topup_status,
                    referrer_info=referrer_info,
                    subscription=subscription,
                    promo_group=promo_group,
                    db=db,
                )
            except Exception as error:
                logger.error('Lava: админ-уведомление', error=error)

        if getattr(self, 'bot', None) and user.telegram_id:
            try:
                keyboard = await self.build_topup_success_keyboard(user)
                display_name = settings.get_lava_display_name_html()
                await self.bot.send_message(
                    user.telegram_id,
                    (
                        '✅ <b>Пополнение успешно!</b>\n\n'
                        f'💰 Сумма: {settings.format_price(payment.amount_kopeks)}\n'
                        f'💳 Способ: {display_name}\n'
                        f'🆔 Транзакция: {transaction.id}\n\n'
                        'Баланс пополнен автоматически!'
                    ),
                    parse_mode='HTML',
                    reply_markup=keyboard,
                )
            except Exception as error:
                logger.error('Lava: уведомление пользователю', error=error)

        try:
            from app.services.payment.common import send_cart_notification_after_topup

            await send_cart_notification_after_topup(user, payment.amount_kopeks, db, getattr(self, 'bot', None))
        except Exception as error:
            logger.error('Lava: корзина после пополнения', error=error)

        logger.info('Lava: зачислено', contract_id=payment.contract_id, user_id=payment.user_id, trigger=trigger)
        return True
