"""PR2 pipeline: LLM → geo → save_parser_event → optional moderation notify."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Engine

from utils.event_category_manager import EventCategoryManager
from utils.telegram_event_extractor import call_openai_telegram_extract, compute_time_mode
from utils.telegram_geo_resolver import resolve_telegram_location
from utils.telegram_sources_service import TelegramSource, TelegramSourcesService
from utils.unified_events_service import UnifiedEventsService

logger = logging.getLogger(__name__)


def _strip_at(username: str | None) -> str | None:
    if not username:
        return None
    return username.lstrip("@").strip() or None


def _build_event_url(source: TelegramSource, message_id: int, external_registration_url: str | None) -> str | None:
    if external_registration_url and str(external_registration_url).startswith("http"):
        return str(external_registration_url).strip()
    uname = _strip_at(source.username)
    if uname:
        return f"https://t.me/{uname}/{message_id}"
    return None


def _community_link(source: TelegramSource) -> str | None:
    uname = _strip_at(source.username)
    if uname:
        return f"https://t.me/{uname}"
    return None


def _get_referral_code(engine: Engine, partner_id: int | None) -> str | None:
    if not partner_id:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT default_promo_code FROM partners WHERE id = :id"),
            {"id": partner_id},
        ).fetchone()
    if row and row[0]:
        return str(row[0]).strip()
    return None


async def _notify_moderation(
    *,
    event_id: int,
    source_chat_id: int,
    message_id: int,
) -> None:
    base = (os.getenv("API_BASE_URL") or "").strip().rstrip("/")
    secret = (os.getenv("INTERNAL_INGEST_SECRET") or "").strip()
    if not base or not secret:
        logger.warning("Skip moderation notify: API_BASE_URL or INTERNAL_INGEST_SECRET missing")
        return
    url = f"{base}/internal/telegram-ingest/notify"
    payload = {
        "event_id": event_id,
        "source_chat_id": source_chat_id,
        "message_id": message_id,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"X-Internal-Secret": secret},
            )
            resp.raise_for_status()
            logger.info("Moderation notify ok event_id=%s", event_id)
    except Exception as e:
        logger.error("Moderation notify failed event_id=%s: %s", event_id, e)


async def process_telegram_post(
    *,
    engine: Engine,
    service: TelegramSourcesService,
    source: TelegramSource,
    message_id: int,
    text: str,
    post_date: datetime | None = None,
) -> None:
    chat_id = source.chat_id

    extract = await asyncio.to_thread(
        call_openai_telegram_extract,
        text,
        timezone=source.timezone,
        post_date=post_date,
    )
    if not extract.ok:
        service.log_reject(
            chat_id=chat_id,
            message_id=message_id,
            stage="llm",
            reason=extract.reject_reason or "llm_rejected",
            raw_snippet=text[:200],
        )
        service.update_last_processed_message_id(chat_id, message_id)
        return

    data = extract.data or {}
    geo = await resolve_telegram_location(engine, source, data.get("location_name"), raw_text=text)
    if not geo.ok:
        service.log_reject(
            chat_id=chat_id,
            message_id=message_id,
            stage="geo",
            reason=geo.reject_reason or "no_coordinates",
            raw_snippet=(data.get("location_name") or "")[:200],
        )
        service.update_last_processed_message_id(chat_id, message_id)
        return

    starts_at = data["starts_at_dt"]
    ends_at = data.get("ends_at_dt")
    is_all_day = bool(data.get("is_all_day"))
    time_mode = compute_time_mode(starts_at, ends_at, is_all_day)
    logger.info(
        "TG ingest parsed chat=%s msg=%s title=%r geo=%s mode=%s",
        chat_id,
        message_id,
        (data.get("title") or "")[:60],
        geo.method,
        time_mode,
    )

    category_mgr = EventCategoryManager()
    categories = category_mgr.assign_categories(
        {"categories": data.get("categories") or [], "default_categories": source.default_categories},
        "telegram",
    )
    raw_category = category_mgr.resolve_raw_category(
        {"categories": categories or source.default_categories},
        "telegram",
    )

    organizer = _strip_at(data.get("extracted_contact")) or _strip_at(source.default_contact)
    status = "open" if source.trust_level == "trusted" else "draft"
    external_id = f"tg:{chat_id}:{message_id}"
    event_url = _build_event_url(source, message_id, data.get("external_registration_url"))

    events_service = UnifiedEventsService(engine)
    referral_code = _get_referral_code(engine, source.partner_id)

    def _save() -> int:
        return events_service.save_parser_event(
            source="telegram",
            external_id=external_id,
            title=data["title"],
            description=data["description"],
            title_en=data.get("title_en"),
            description_en=data.get("description_en"),
            starts_at_utc=starts_at,
            ends_at_utc=ends_at,
            city=source.default_city,
            lat=geo.lat,
            lng=geo.lng,
            location_name=geo.resolved_name or data.get("location_name"),
            location_url=geo.location_url,
            url=event_url,
            place_id=geo.place_id,
            status=status,
            community_name=source.title,
            community_link=_community_link(source),
            chat_id=chat_id,
            organizer_username=organizer,
            referral_code=referral_code,
        )

    try:
        event_id = await asyncio.to_thread(_save)
    except Exception as e:
        logger.exception("save_parser_event failed chat=%s msg=%s", chat_id, message_id)
        service.log_reject(
            chat_id=chat_id,
            message_id=message_id,
            stage="save",
            reason="save_error",
            raw_snippet=str(e)[:200],
        )
        service.update_last_processed_message_id(chat_id, message_id)
        return

    service.log_reject(
        chat_id=chat_id,
        message_id=message_id,
        stage="save",
        reason="ok",
        raw_snippet=f"event_id={event_id} status={status} cats={raw_category}",
    )
    service.update_last_processed_message_id(chat_id, message_id)

    if status == "draft":
        await _notify_moderation(
            event_id=event_id,
            source_chat_id=chat_id,
            message_id=message_id,
        )
