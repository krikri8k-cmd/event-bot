"""Ссылки на посты Telegram для ingest (публичные каналы и закрытые группы)."""

from __future__ import annotations


def build_telegram_post_url(chat_id: int, message_id: int, username: str | None = None) -> str | None:
    """
    Публичный канал: https://t.me/{username}/{message_id}
    Закрытая группа/супергруппа (только для участников): https://t.me/c/{internal_id}/{message_id}
    """
    uname = (username or "").lstrip("@").strip()
    if uname:
        return f"https://t.me/{uname}/{message_id}"

    cid = str(chat_id)
    if cid.startswith("-100"):
        internal = cid[4:]
    elif cid.startswith("-"):
        internal = cid[1:]
    else:
        return None
    if not internal.isdigit():
        return None
    return f"https://t.me/c/{internal}/{message_id}"
