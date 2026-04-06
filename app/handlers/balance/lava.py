"""Handler for Lava.top balance top-up."""

import html

import structlog
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.keyboards.inline import get_back_keyboard
from app.localization.texts import get_texts
from app.services.payment.lava import get_lava_amount_to_offer_id_map
from app.services.payment_service import PaymentService
from app.utils.decorators import error_handler


logger = structlog.get_logger(__name__)


def _check_topup_restriction(db_user: User, texts) -> InlineKeyboardMarkup | None:
    if not getattr(db_user, 'restriction_topup', False):
        return None

    keyboard = []
    support_url = settings.get_support_contact_url()
    if support_url:
        keyboard.append([InlineKeyboardButton(text='🆘 Обжаловать', url=support_url)])
    keyboard.append([InlineKeyboardButton(text=texts.BACK, callback_data='menu_balance')])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def _get_lava_offer_amounts_kopeks() -> list[int]:
    """Допустимые суммы: ручной JSON, каталог API или default/expected."""
    offer_map = await get_lava_amount_to_offer_id_map()
    return sorted(offer_map.keys())


async def _create_lava_payment_and_respond(
    message_or_callback,
    db_user: User,
    db: AsyncSession,
    amount_kopeks: int,
    edit_message: bool = False,
    lava_payment_method_type: str | None = None,
):
    texts = get_texts(db_user.language)
    amount_rub = amount_kopeks / 100

    payment_service = PaymentService()

    description = settings.PAYMENT_BALANCE_TEMPLATE.format(
        service_name=settings.PAYMENT_SERVICE_NAME,
        description='Пополнение баланса',
    )

    result = await payment_service.create_lava_payment(
        db=db,
        user_id=db_user.id,
        amount_kopeks=amount_kopeks,
        description=description,
        email=getattr(db_user, 'email', None),
        language=db_user.language or settings.DEFAULT_LANGUAGE,
        payment_method=(f'lava_{lava_payment_method_type.lower()}' if lava_payment_method_type else 'lava'),
        lava_payment_method_type=lava_payment_method_type,
    )

    if not result:
        error_text = texts.t(
            'PAYMENT_CREATE_ERROR',
            'Не удалось создать платёж. Попробуйте позже.',
        )
        if edit_message:
            await message_or_callback.edit_text(
                error_text,
                reply_markup=get_back_keyboard(db_user.language),
                parse_mode='HTML',
            )
        else:
            await message_or_callback.answer(
                error_text,
                parse_mode='HTML',
            )
        return

    payment_url = result.get('payment_url')
    display_name = settings.get_lava_display_name()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.t(
                        'PAY_BUTTON',
                        '💳 Оплатить {amount}₽',
                    ).format(amount=f'{amount_rub:.0f}'),
                    url=payment_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.t('BACK_BUTTON', '◀️ Назад'),
                    callback_data='menu_balance',
                )
            ],
        ]
    )

    response_text = texts.t(
        'LAVA_PAYMENT_CREATED',
        '💳 <b>Оплата через {name}</b>\n\n'
        'Сумма: <b>{amount}₽</b>\n\n'
        'Нажмите кнопку ниже для оплаты.\n'
        'После успешной оплаты баланс будет пополнен автоматически.',
    ).format(name=display_name, amount=f'{amount_rub:.2f}')

    if edit_message:
        await message_or_callback.edit_text(
            response_text,
            reply_markup=keyboard,
            parse_mode='HTML',
        )
    else:
        await message_or_callback.answer(
            response_text,
            reply_markup=keyboard,
            parse_mode='HTML',
        )

    logger.info('Lava payment created', telegram_id=db_user.telegram_id, amount_rub=amount_rub)


@error_handler
async def process_lava_payment_amount(
    message: types.Message,
    db_user: User,
    db: AsyncSession,
    amount_kopeks: int,
    state: FSMContext,
    lava_payment_method_type: str | None = None,
):
    texts = get_texts(db_user.language)

    restriction_kb = _check_topup_restriction(db_user, texts)
    if restriction_kb:
        reason = html.escape(getattr(db_user, 'restriction_reason', None) or 'Действие ограничено администратором')
        await message.answer(
            f'🚫 <b>Пополнение ограничено</b>\n\n{reason}',
            parse_mode='HTML',
            reply_markup=restriction_kb,
        )
        await state.clear()
        return

    min_amount = settings.LAVA_MIN_AMOUNT_KOPEKS
    max_amount = settings.LAVA_MAX_AMOUNT_KOPEKS

    if amount_kopeks < min_amount:
        await message.answer(
            texts.t(
                'PAYMENT_AMOUNT_TOO_LOW',
                'Минимальная сумма пополнения: {min_amount}₽',
            ).format(min_amount=min_amount // 100),
            reply_markup=get_back_keyboard(db_user.language),
            parse_mode='HTML',
        )
        return

    if amount_kopeks > max_amount:
        await message.answer(
            texts.t(
                'PAYMENT_AMOUNT_TOO_HIGH',
                'Максимальная сумма пополнения: {max_amount}₽',
            ).format(max_amount=max_amount // 100),
            reply_markup=get_back_keyboard(db_user.language),
            parse_mode='HTML',
        )
        return

    await state.clear()

    await _create_lava_payment_and_respond(
        message_or_callback=message,
        db_user=db_user,
        db=db,
        amount_kopeks=amount_kopeks,
        edit_message=False,
        lava_payment_method_type=lava_payment_method_type,
    )


@error_handler
async def start_lava_topup(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    texts = get_texts(db_user.language)

    restriction_kb = _check_topup_restriction(db_user, texts)
    if restriction_kb:
        reason = html.escape(getattr(db_user, 'restriction_reason', None) or 'Действие ограничено администратором')
        await callback.message.edit_text(
            f'🚫 <b>Пополнение ограничено</b>\n\n{reason}',
            parse_mode='HTML',
            reply_markup=restriction_kb,
        )
        return

    display_name = settings.get_lava_display_name()
    offer_amounts = await _get_lava_offer_amounts_kopeks()

    if not offer_amounts:
        await state.clear()
        await callback.message.edit_text(
            texts.t(
                'LAVA_OFFERS_NOT_CONFIGURED',
                '⚠️ <b>Оплата через {name} временно недоступна</b>\n\n'
                'Для этого способа должны быть настроены офферы сумм.\n'
                'Обратитесь в поддержку.',
            ).format(name=display_name),
            parse_mode='HTML',
            reply_markup=get_back_keyboard(db_user.language),
        )
        return

    await state.clear()
    await state.update_data(payment_method='lava')

    amount_buttons: list[list[InlineKeyboardButton]] = []
    for amount_kopeks in offer_amounts:
        amount_rub = amount_kopeks / 100
        amount_buttons.append(
            [
                InlineKeyboardButton(
                    text=f'💳 {amount_rub:,.0f} ₽'.replace(',', ' '),
                    callback_data=f'topup_amount|lava_card|{amount_kopeks}',
                ),
            ]
        )

    amount_buttons.append(
        [
            InlineKeyboardButton(
                text=texts.t('BACK_BUTTON', '◀️ Назад'),
                callback_data='balance_topup',
            )
        ]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=amount_buttons)

    await callback.message.edit_text(
        texts.t(
            'LAVA_SELECT_AMOUNT',
            '💳 <b>Пополнение через {name}</b>\n\n'
            'Выберите сумму пополнения (оплата банковской картой).\n'
            'Для каждой суммы используется отдельный оффер Lava.',
        ).format(
            name=display_name,
        ),
        parse_mode='HTML',
        reply_markup=keyboard,
    )
