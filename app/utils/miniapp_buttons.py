from aiogram import types
from aiogram.types import InlineKeyboardButton

from app.config import settings
from app.utils.button_styles_cache import CALLBACK_TO_SECTION, get_cached_button_styles


# Mapping from callback_data to cabinet frontend paths.
# Used for automatic deep-linking when explicit ``cabinet_path`` is not provided.
# If callback_data is NOT in this mapping, the button falls back to a regular callback.
CALLBACK_TO_CABINET_PATH: dict[str, str] = {
    'menu_balance': '/balance',
    'balance_topup': '/balance/top-up',
    'menu_subscription': '/subscription',
    'subscription': '/subscription',
    'subscription_extend': '/subscription',
    'subscription_upgrade': '/subscription',
    'subscription_connect': '/subscription',
    'subscription_resume_checkout': '/subscription',
    'return_to_saved_cart': '/subscription',
    'menu_buy': '/subscription',
    'buy_traffic': '/subscription',
    'menu_referrals': '/referral',
    'menu_referral': '/referral',
    'menu_promocode': '/balance',
    'menu_support': '/support',
    'menu_info': '/info',
    'menu_profile': '/profile',
    'back_to_menu': '/',
}

# Default button styles per callback_data for cabinet mode.
# Values: 'primary' (blue), 'success' (green), 'danger' (red), None (default).
CALLBACK_TO_CABINET_STYLE: dict[str, str] = {
    'menu_balance': 'primary',
    'balance_topup': 'primary',
    'menu_subscription': 'success',
    'subscription': 'success',
    'subscription_extend': 'success',
    'subscription_upgrade': 'success',
    'subscription_connect': 'success',
    'subscription_resume_checkout': 'success',
    'return_to_saved_cart': 'success',
    'menu_buy': 'success',
    'buy_traffic': 'success',
    'menu_referrals': 'success',
    'menu_referral': 'success',
    'menu_promocode': 'primary',
    'menu_support': 'primary',
    'menu_info': 'primary',
    'menu_profile': 'primary',
    'back_to_menu': 'primary',
}

# Mapping from broadcast button keys to cabinet paths.
BUTTON_KEY_TO_CABINET_PATH: dict[str, str] = {
    'balance': '/balance/top-up',
    'referrals': '/referral',
    'promocode': '/balance',
    'connect': '/subscription',
    'subscription': '/subscription',
    'support': '/support',
    'home': '/',
    'buy': '/subscription',
}

# Valid style values accepted by the Telegram Bot API.
_VALID_STYLES = frozenset({'primary', 'success', 'danger'})


def _resolve_style(style: str | None) -> str | None:
    """Return a validated style or ``None``."""
    if style and style in _VALID_STYLES:
        return style
    return None


def build_cabinet_url(path: str = '', *, query: dict[str, str | int] | None = None) -> str:
    """Join ``MINIAPP_CUSTOM_URL`` with an optional *path* segment.

    Handles trailing-slash normalization so that both
    ``https://example.com`` and ``https://example.com/`` produce
    correct URLs like ``https://example.com/balance``.

    *query*: optional dict encoded as GET parameters (SPA may read ``amount_kopeks``).

    Если в *query* есть ``amount_kopeks``, добавляется фрагмент
    ``#tgWebAppStartParam=<сумма_коп>`` — так Telegram пробрасывает значение в
    ``Telegram.WebApp.initDataUnsafe.start_param`` (рекомендованный способ для Mini App,
    когда клиентский роутер игнорирует query после открытия из бота).

    Returns an empty string when the base URL is not configured
    or when *path* is empty (no known section).
    """
    base = (settings.MINIAPP_CUSTOM_URL or '').strip().rstrip('/')
    if not base:
        return ''
    if not path:
        return ''
    if path == '/':
        href = base
    else:
        if not path.startswith('/'):
            path = f'/{path}'
        href = f'{base}{path}'
    if query:
        from urllib.parse import urlencode

        qs = urlencode([(k, str(v)) for k, v in query.items()])
        sep = '&' if '?' in href else '?'
        href = f'{href}{sep}{qs}'
    amount_for_start_param: str | None = None
    if query:
        ak = query.get('amount_kopeks')
        if ak is not None and str(ak).strip() != '':
            digits_only = ''.join(c for c in str(ak).strip() if c.isdigit())
            # Telegram допускает [A-Za-z0-9_-], длина до 64
            if digits_only and len(digits_only) <= 64:
                amount_for_start_param = digits_only
    if amount_for_start_param:
        href = href.split('#', maxsplit=1)[0]
        href = f'{href}#tgWebAppStartParam={amount_for_start_param}'
    return href


def build_miniapp_or_callback_button(
    text: str,
    *,
    callback_data: str,
    cabinet_path: str | None = None,
    cabinet_query: dict[str, str | int] | None = None,
    style: str | None = None,
    icon_custom_emoji_id: str | None = None,
) -> InlineKeyboardButton:
    """Create a button that opens the cabinet miniapp or falls back to a callback.

    In cabinet menu mode, if ``MINIAPP_CUSTOM_URL`` is configured the button
    opens the relevant section of the cabinet.  The target section is determined
    by ``cabinet_path`` (explicit) or inferred from ``callback_data`` via
    ``CALLBACK_TO_CABINET_PATH``.

    Button styling (Bot API 9.4):
    - ``style`` overrides the button color: ``'primary'`` (blue),
      ``'success'`` (green), ``'danger'`` (red).  When omitted the style is
      resolved from ``CABINET_BUTTON_STYLE`` config or per-section defaults.
    - ``icon_custom_emoji_id`` shows a custom emoji before the button text
      (requires bot owner to have Telegram Premium).

    When ``callback_data`` is not found in the mapping and no explicit
    ``cabinet_path`` is given, the button falls back to a regular Telegram
    callback — this keeps actions like ``claim_discount_*`` working correctly.

    Only ``MINIAPP_CUSTOM_URL`` is considered here — the purchase-only URL
    (``MINIAPP_PURCHASE_URL``) is intentionally excluded because it cannot
    display subscription details and would load indefinitely.
    """

    if settings.is_cabinet_mode():
        path = cabinet_path or CALLBACK_TO_CABINET_PATH.get(callback_data)
        if path:
            url = build_cabinet_url(path, query=cabinet_query)
            if url:
                # Resolve per-section config from cache
                section_key = CALLBACK_TO_SECTION.get(callback_data)
                if section_key is None and callback_data.startswith('balance_topup_prefill|'):
                    section_key = CALLBACK_TO_SECTION.get('balance_topup')
                section_cfg = get_cached_button_styles().get(section_key or '', {}) if section_key else {}

                # Style chain: explicit param > per-section DB > global config > hardcoded default
                # 'default' in per-section config means "no color" — do not fall through.
                if style:
                    resolved_style = _resolve_style(style)
                elif section_cfg.get('style'):
                    resolved_style = _resolve_style(section_cfg['style'])
                else:
                    cabinet_style_key = callback_data
                    if cabinet_style_key not in CALLBACK_TO_CABINET_STYLE and callback_data.startswith(
                        'balance_topup_prefill|'
                    ):
                        cabinet_style_key = 'balance_topup'
                    resolved_style = _resolve_style((settings.CABINET_BUTTON_STYLE or '').strip()) or _resolve_style(
                        CALLBACK_TO_CABINET_STYLE.get(cabinet_style_key)
                    )

                # Emoji chain: explicit param > per-section DB
                resolved_emoji = icon_custom_emoji_id or section_cfg.get('icon_custom_emoji_id') or None

                return InlineKeyboardButton(
                    text=text,
                    web_app=types.WebAppInfo(url=url),
                    style=resolved_style,
                    icon_custom_emoji_id=resolved_emoji or None,
                )

    return InlineKeyboardButton(text=text, callback_data=callback_data)
