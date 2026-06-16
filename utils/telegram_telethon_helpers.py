"""Метаданные поста из Telethon: автор и рабочая ссылка на сообщение."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from utils.telegram_post_links import build_telegram_post_url

if TYPE_CHECKING:
    from telethon import TelegramClient

logger = logging.getLogger(__name__)


async def resolve_message_poster(message) -> tuple[int | None, str | None]:
    """user_id и @username автора поста (канал/аноним — None)."""
    try:
        sender = await message.get_sender()
    except Exception as e:
        logger.warning("get_sender failed: %s", e)
        return None, None
    if not sender:
        return None, None
    user_id = getattr(sender, "id", None)
    username = getattr(sender, "username", None)
    if username:
        return user_id, username.lstrip("@").strip() or None
    return user_id, None


def extract_message_entity_links(message) -> list[tuple[str, str]]:
    """
    URL из Telegram entities: text_link (вшитая ссылка) и plain url.
    Returns: [(url, anchor_text), ...] в порядке появления в сообщении.
    """
    text = (getattr(message, "message", None) or getattr(message, "caption", None) or "").strip()
    entities = getattr(message, "entities", None) or getattr(message, "caption_entities", None) or []
    if not text or not entities:
        return []

    try:
        from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
    except ImportError:
        logger.warning("telethon types unavailable — skip entity URL extraction")
        return []

    links: list[tuple[str, str]] = []
    for entity in entities:
        start = entity.offset
        end = entity.offset + entity.length
        anchor = text[start:end].strip()
        if isinstance(entity, MessageEntityTextUrl):
            url = (getattr(entity, "url", None) or "").strip()
            if url:
                links.append((url, anchor or url))
        elif isinstance(entity, MessageEntityUrl):
            url = text[start:end].strip()
            if url:
                links.append((url, anchor or url))
    return links


async def export_message_link(
    client: TelegramClient,
    chat_id: int,
    message_id: int,
    *,
    source_username: str | None = None,
) -> str | None:
    """
    Рабочая ссылка от Telegram API (супергруппы/каналы).
    Для basic group API недоступен — fallback t.me/c/… без warning.
    """
    fallback = build_telegram_post_url(chat_id, message_id, source_username)
    try:
        from telethon.tl.functions.channels import ExportMessageLinkRequest
        from telethon.tl.types import InputPeerChannel

        peer = await client.get_input_entity(chat_id)
        if not isinstance(peer, InputPeerChannel):
            return fallback

        result = await client(ExportMessageLinkRequest(channel=peer, id=message_id, grouped=False))
        link = (getattr(result, "link", None) or "").strip()
        if link.startswith("http"):
            return link
    except Exception as e:
        logger.debug(
            "exportMessageLink API unavailable chat=%s msg=%s: %s",
            chat_id,
            message_id,
            e,
        )
    return fallback
