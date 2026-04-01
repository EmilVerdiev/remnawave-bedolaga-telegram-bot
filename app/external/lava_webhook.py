"""Webhook Lava.top: whitelist IP (см. https://developers.lava.top/ru)."""

from __future__ import annotations

from ipaddress import ip_address

LAVA_WEBHOOK_IPS = frozenset({'158.160.60.174'})


def collect_lava_ip_candidates(
    x_forwarded_for: str | None,
    x_real_ip: str | None,
    cf_connecting_ip: str | None,
) -> list[str]:
    out: list[str] = []
    for raw in (x_forwarded_for, x_real_ip, cf_connecting_ip):
        if not raw:
            continue
        first = raw.split(',')[0].strip()
        if first:
            out.append(first)
    return out


def resolve_lava_ip(header_candidates: list[str], remote: str | None) -> str | None:
    for h in header_candidates:
        try:
            ip_address(h)
            return h
        except ValueError:
            continue
    if remote:
        try:
            ip_address(remote)
            return remote
        except ValueError:
            return None
    return None


def is_lava_webhook_ip_allowed(ip: str) -> bool:
    return ip in LAVA_WEBHOOK_IPS
