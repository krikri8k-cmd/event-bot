"""LLM extraction for Telegram event ingest (PR2): one call, bilingual structured output."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7
DESCRIPTION_MAX_LEN = 220
PAST_EVENT_HOURS = 24

TELEGRAM_EVENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_event": {"type": "boolean"},
        "confidence": {"type": "number"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "title_en": {"type": "string"},
        "description_en": {"type": "string"},
        "starts_at": {"type": ["string", "null"]},
        "ends_at": {"type": ["string", "null"]},
        "location_name": {"type": ["string", "null"]},
        "categories": {"type": "array", "items": {"type": "string"}},
        "external_registration_url": {"type": ["string", "null"]},
        "extracted_contact": {"type": ["string", "null"]},
        "is_all_day": {"type": "boolean"},
    },
    "required": [
        "is_event",
        "confidence",
        "title",
        "description",
        "title_en",
        "description_en",
        "starts_at",
        "ends_at",
        "location_name",
        "categories",
        "external_registration_url",
        "extracted_contact",
        "is_all_day",
    ],
    "additionalProperties": False,
}


@dataclass
class TelegramExtractResult:
    ok: bool
    data: dict[str, Any] | None = None
    reject_reason: str | None = None


def _build_system_prompt(timezone: str) -> str:
    return (
        "You extract structured event data from Telegram channel posts for a Bali events guide (MyGuide). "
        f"Interpret all dates and times in timezone {timezone}. "
        "Return starts_at and ends_at as ISO8601 with numeric UTC offset (e.g. 2026-06-15T19:00:00+08:00). "
        "BILINGUAL OUTPUT (mandatory): "
        "title and description — Russian (Cyrillic). "
        "title_en and description_en — English (Latin). "
        "Even if the source post is in English, still write title/description in Russian "
        "(translate or transliterate the event name if needed). "
        "Never copy the same English text into both RU and EN description fields. "
        "description and description_en: exactly two short sentences each, max 220 characters, "
        "no links, hashtags, emojis, or promotional filler. "
        "location_name: venue as written in the post (may be Latin). "
        "extracted_contact: @username of organizer/contact from the post if present, else null. "
        "Set is_event=false for announcements, thank-you posts, memes, job ads, "
        "or generic chat without a dated gathering. "
        "Set is_all_day=true only when the post explicitly says all-day / весь день."
    )


def _build_user_prompt(text: str, post_date: datetime | None, timezone: str) -> str:
    posted = ""
    if post_date:
        if post_date.tzinfo is None:
            post_date = post_date.replace(tzinfo=ZoneInfo(timezone))
        posted = post_date.isoformat()
    return f"SOURCE_TIMEZONE: {timezone}\n" f"POST_DATE: {posted or 'unknown'}\n\n" f"POST_TEXT:\n{text}"


def _parse_iso_dt(value: str | None, tz: ZoneInfo) -> datetime | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def validate_extracted_event(
    payload: dict[str, Any],
    *,
    timezone: str,
    now: datetime | None = None,
    raw_text: str = "",
) -> TelegramExtractResult:
    """Validate LLM JSON without calling the API (also used after extraction)."""
    tz = ZoneInfo(timezone)
    now = now or datetime.now(tz)

    if not payload.get("is_event"):
        return TelegramExtractResult(ok=False, reject_reason="not_an_event")

    confidence = float(payload.get("confidence") or 0)
    if confidence < CONFIDENCE_THRESHOLD:
        return TelegramExtractResult(ok=False, reject_reason="low_confidence")

    starts_at = _parse_iso_dt(payload.get("starts_at"), tz)
    if not starts_at:
        return TelegramExtractResult(ok=False, reject_reason="missing_starts_at")

    if starts_at < now - timedelta(hours=PAST_EVENT_HOURS):
        return TelegramExtractResult(ok=False, reject_reason="starts_at_too_old")

    title = (payload.get("title") or "").strip()
    if not title:
        return TelegramExtractResult(ok=False, reject_reason="missing_title")

    for field in ("description", "description_en"):
        val = (payload.get(field) or "").strip()
        if not val:
            return TelegramExtractResult(ok=False, reject_reason=f"missing_{field}")
        if len(val) > DESCRIPTION_MAX_LEN:
            payload[field] = val[:DESCRIPTION_MAX_LEN].rstrip()

    ends_at = _parse_iso_dt(payload.get("ends_at"), tz)
    is_all_day = bool(payload.get("is_all_day")) or _text_suggests_all_day(raw_text)

    if is_all_day:
        day = starts_at.date()
        starts_at = datetime(day.year, day.month, day.day, 9, 0, tzinfo=tz)
        ends_at = datetime(day.year, day.month, day.day, 21, 0, tzinfo=tz)

    payload["starts_at_dt"] = starts_at
    payload["ends_at_dt"] = ends_at
    payload["is_all_day"] = is_all_day
    return TelegramExtractResult(ok=True, data=payload)


def _text_suggests_all_day(text: str) -> bool:
    low = (text or "").lower()
    return "весь день" in low or "all day" in low or "all-day" in low


def call_openai_telegram_extract(
    text: str,
    *,
    timezone: str = "Asia/Makassar",
    post_date: datetime | None = None,
    model: str | None = None,
) -> TelegramExtractResult:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.error("OPENAI_API_KEY is not set")
        return TelegramExtractResult(ok=False, reject_reason="openai_not_configured")

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        mdl = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=mdl,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "telegram_event",
                    "strict": True,
                    "schema": TELEGRAM_EVENT_JSON_SCHEMA,
                },
            },
            messages=[
                {"role": "system", "content": _build_system_prompt(timezone)},
                {"role": "user", "content": _build_user_prompt(text, post_date, timezone)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
    except Exception as e:
        logger.exception("Telegram LLM extract failed: %s", e)
        return TelegramExtractResult(ok=False, reject_reason="llm_error")

    return validate_extracted_event(payload, timezone=timezone, raw_text=text)


def compute_time_mode(starts_at: datetime, ends_at: datetime | None, is_all_day: bool) -> str:
    if is_all_day:
        return "all_day"
    if ends_at is not None:
        return "range"
    return "start"
