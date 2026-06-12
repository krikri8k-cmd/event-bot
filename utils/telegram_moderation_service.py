"""PR3: карточки модерации Telegram ingest и смена статуса draft → open/canceled."""

from __future__ import annotations

import html
import logging
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import text
from sqlalchemy.engine import Engine

from config import load_settings
from utils.telegram_sources_service import TelegramSourcesService

logger = logging.getLogger(__name__)


def _fetch_event(engine: Engine, event_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = (
            conn.execute(
                text("""
                SELECT id, title, title_en, description, description_en,
                       starts_at, ends_at, location_name, lat, lng, city,
                       community_name, community_link, status, url
                FROM events
                WHERE id = :id AND source = 'telegram'
            """),
                {"id": event_id},
            )
            .mappings()
            .fetchone()
        )
    return dict(row) if row else None


def _format_when(event: dict[str, Any]) -> str:
    starts = event.get("starts_at")
    ends = event.get("ends_at")
    if not starts:
        return "—"
    start_s = starts.strftime("%d.%m.%Y %H:%M")
    if ends:
        return f"{start_s} – {ends.strftime('%H:%M')}"
    return start_s


def build_moderation_card_text(
    event: dict[str, Any],
    *,
    source_chat_id: int,
    message_id: int,
    source_title: str | None = None,
) -> str:
    title = html.escape(event.get("title") or "—")
    title_en = html.escape((event.get("title_en") or "").strip() or "—")
    desc = html.escape((event.get("description") or "")[:220])
    desc_en = html.escape((event.get("description_en") or "")[:220])
    loc = html.escape(event.get("location_name") or "—")
    when = html.escape(_format_when(event))
    community = html.escape(event.get("community_name") or source_title or str(source_chat_id))
    lat = event.get("lat")
    lng = event.get("lng")
    coords = f"{lat:.5f}, {lng:.5f}" if lat is not None and lng is not None else "—"

    post_link = ""
    if event.get("url"):
        post_link = f'\n🔗 <a href="{html.escape(event["url"])}">Подробнее</a>'

    return (
        f"📋 <b>Telegram ingest — модерация</b>\n"
        f"ID <code>{event['id']}</code> · draft\n\n"
        f"🇷🇺 <b>{title}</b>\n"
        f"🇬🇧 {title_en}\n\n"
        f"🇷🇺 {desc}\n"
        f"🇬🇧 {desc_en}\n\n"
        f"📅 {when}\n"
        f"📍 {loc} ({html.escape(coords)})\n"
        f"📡 {community} · msg <code>{message_id}</code>"
        f"{post_link}"
    )


def moderation_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"tgingest:approve:{event_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"tgingest:reject:{event_id}"),
            ]
        ]
    )


async def send_moderation_card(
    engine: Engine,
    *,
    event_id: int,
    source_chat_id: int,
    message_id: int,
) -> bool:
    settings = load_settings()
    mod_chat_id = settings.moderation_chat_id
    if not mod_chat_id:
        logger.warning("MODERATION_CHAT_ID not set — skip moderation card")
        return False

    event = _fetch_event(engine, event_id)
    if not event:
        logger.error("Moderation card: event %s not found", event_id)
        return False
    if event.get("status") != "draft":
        logger.info("Moderation card: event %s status=%s, skip", event_id, event.get("status"))
        return False

    source = TelegramSourcesService(engine).get_by_chat_id(source_chat_id)
    card_text = build_moderation_card_text(
        event,
        source_chat_id=source_chat_id,
        message_id=message_id,
        source_title=source.title if source else None,
    )

    from bot_enhanced_v3 import bot

    await bot.send_message(
        mod_chat_id,
        card_text,
        parse_mode="HTML",
        reply_markup=moderation_keyboard(event_id),
        disable_web_page_preview=True,
    )
    logger.info("Moderation card sent event_id=%s chat=%s", event_id, mod_chat_id)
    return True


def set_telegram_event_status(engine: Engine, event_id: int, new_status: str) -> bool:
    if new_status not in {"open", "canceled"}:
        return False
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                UPDATE events
                SET status = :status, updated_at_utc = NOW()
                WHERE id = :id AND source = 'telegram' AND status = 'draft'
                RETURNING id
            """),
            {"id": event_id, "status": new_status},
        ).fetchone()
    return row is not None
