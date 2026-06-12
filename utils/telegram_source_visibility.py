"""Публичный vs закрытый Telegram-источник (2 категории)."""

from __future__ import annotations


def is_public_telegram_source(username: str | None) -> bool:
    """Публичный канал/группа — есть @username."""
    return bool((username or "").lstrip("@").strip())


def is_public_telegram_event(event: dict) -> bool:
    """
    Публичное telegram-событие в ленте.
    community_link заполняется только если у источника есть @username.
    """
    if event.get("source") != "telegram":
        return False
    return bool((event.get("community_link") or "").strip())
