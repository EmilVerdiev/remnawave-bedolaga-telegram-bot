"""HTTP-клиент Lava.top Public API (https://gate.lava.top/docs)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings
from app.utils.payment_logger import payment_logger as logger

LAVA_GATE_BASE = 'https://gate.lava.top'


class LavaAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _normalize_lava_product_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Лента может отдавать {type,data}; актуальный API — плоский объект продукта."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get('type')
    if kind in ('PRODUCT', 'POST') and isinstance(raw.get('data'), dict):
        if kind != 'PRODUCT':
            return None
        return raw['data']
    if raw.get('id'):
        return raw
    return None


async def fetch_all_products_v2() -> list[dict[str, Any]]:
    """GET /api/v2/products с пагинацией по nextPage (см. gate.lava.top/docs)."""
    api_key = settings.LAVA_API_KEY
    if not api_key:
        raise LavaAPIError('LAVA_API_KEY не задан')

    headers = {
        'Accept': 'application/json',
        'X-Api-Key': api_key,
    }
    timeout = httpx.Timeout(settings.LAVA_HTTP_TIMEOUT_SECONDS, connect=10.0)
    out: list[dict[str, Any]] = []
    url: str | None = f'{LAVA_GATE_BASE}/api/v2/products'

    async with httpx.AsyncClient(timeout=timeout) as client:
        while url:
            response = await client.get(url, headers=headers)
            text = response.text
            if response.status_code != 200:
                logger.error(
                    'Lava API: ошибка списка продуктов',
                    status_code=response.status_code,
                    body=text[:2000],
                )
                raise LavaAPIError('Lava API products error', status_code=response.status_code, body=text)
            try:
                body = json.loads(text)
            except json.JSONDecodeError as e:
                raise LavaAPIError('Invalid JSON from Lava API (products)') from e

            for raw in body.get('items') or []:
                prod = _normalize_lava_product_item(raw)
                if prod:
                    out.append(prod)

            next_url = body.get('nextPage')
            url = str(next_url).strip() if next_url else None

    return out


async def create_invoice_v3(body: dict[str, Any]) -> dict[str, Any]:
    """POST /api/v3/invoice — контракт оплаты, в ответе id (contractId) и paymentUrl."""
    api_key = settings.LAVA_API_KEY
    if not api_key:
        raise LavaAPIError('LAVA_API_KEY не задан')

    url = f'{LAVA_GATE_BASE}/api/v3/invoice'
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Api-Key': api_key,
    }
    timeout = httpx.Timeout(settings.LAVA_HTTP_TIMEOUT_SECONDS, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, content=json.dumps(body))

    text = response.text
    if response.status_code not in (200, 201):
        logger.error(
            'Lava API: ошибка создания инвойса',
            status_code=response.status_code,
            body=text[:2000],
        )
        raise LavaAPIError('Lava API error', status_code=response.status_code, body=text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LavaAPIError('Invalid JSON from Lava API') from e
