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


async def export_message_link(
    client: TelegramClient,
    chat_id: int,
    message_id: int,
    *,
    source_username: str | None = None,
) -> str | None:
    """
    Рабочая ссылка от Telegram API (корректна для закрытых супергрупп).
    Fallback — эвристика t.me/c/… (может не работать для basic group).
    """
    try:
        from telethon.tl.functions.messages import ExportMessageLinkRequest

        result = await client(ExportMessageLinkRequest(peer=chat_id, id=message_id, grouped=False))
        link = (getattr(result, "link", None) or "").strip()
        if link.startswith("http"):
            return link
    except Exception as e:
        logger.warning("exportMessageLink failed chat=%s msg=%s: %s", chat_id, message_id, e)
    return build_telegram_post_url(chat_id, message_id, source_username)
