"""CRUD и диагностика для telegram_sources / telegram_ingest_log."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

TRUST_LEVELS = frozenset({"trusted", "moderated"})


@dataclass
class TelegramSource:
    id: int
    chat_id: int
    username: str | None
    title: str
    is_active: bool
    trust_level: str
    default_city: str
    default_country: str
    timezone: str
    allow_default_coords: bool
    default_lat: float | None
    default_lng: float | None
    default_contact: str | None
    default_categories: list[str]
    partner_id: int | None
    last_processed_message_id: int | None


def _row_to_source(row) -> TelegramSource:
    raw_cats = row.default_categories
    if isinstance(raw_cats, str):
        try:
            raw_cats = json.loads(raw_cats)
        except json.JSONDecodeError:
            raw_cats = []
    if not isinstance(raw_cats, list):
        raw_cats = []
    return TelegramSource(
        id=row.id,
        chat_id=row.chat_id,
        username=row.username,
        title=row.title,
        is_active=bool(row.is_active),
        trust_level=row.trust_level,
        default_city=row.default_city or "bali",
        default_country=row.default_country or "ID",
        timezone=row.timezone or "Asia/Makassar",
        allow_default_coords=bool(row.allow_default_coords),
        default_lat=row.default_lat,
        default_lng=row.default_lng,
        default_contact=row.default_contact,
        default_categories=[str(c) for c in raw_cats],
        partner_id=row.partner_id,
        last_processed_message_id=row.last_processed_message_id,
    )


class TelegramSourcesService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def list_sources(self, active_only: bool = False) -> list[TelegramSource]:
        clause = "WHERE is_active = TRUE" if active_only else ""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT id, chat_id, username, title, is_active, trust_level,
                           default_city, default_country, timezone, allow_default_coords,
                           default_lat, default_lng, default_contact, default_categories,
                           partner_id, last_processed_message_id
                    FROM telegram_sources
                    {clause}
                    ORDER BY title
                """)
            ).fetchall()
        return [_row_to_source(r) for r in rows]

    def get_by_chat_id(self, chat_id: int) -> TelegramSource | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT id, chat_id, username, title, is_active, trust_level,
                           default_city, default_country, timezone, allow_default_coords,
                           default_lat, default_lng, default_contact, default_categories,
                           partner_id, last_processed_message_id
                    FROM telegram_sources
                    WHERE chat_id = :chat_id
                """),
                {"chat_id": chat_id},
            ).fetchone()
        return _row_to_source(row) if row else None

    def upsert_source(
        self,
        *,
        chat_id: int,
        title: str,
        username: str | None = None,
        trust_level: str = "moderated",
        partner_id: int | None = None,
    ) -> TelegramSource:
        if trust_level not in TRUST_LEVELS:
            raise ValueError(f"trust_level must be one of {sorted(TRUST_LEVELS)}")

        with self.engine.begin() as conn:
            row = conn.execute(
                text("""
                    INSERT INTO telegram_sources (chat_id, username, title, trust_level, partner_id)
                    VALUES (:chat_id, :username, :title, :trust_level, :partner_id)
                    ON CONFLICT (chat_id) DO UPDATE SET
                        username = COALESCE(EXCLUDED.username, telegram_sources.username),
                        title = EXCLUDED.title,
                        trust_level = EXCLUDED.trust_level,
                        partner_id = COALESCE(EXCLUDED.partner_id, telegram_sources.partner_id),
                        updated_at = NOW()
                    RETURNING id, chat_id, username, title, is_active, trust_level,
                              default_city, default_country, timezone, allow_default_coords,
                              default_lat, default_lng, default_contact, default_categories,
                              partner_id, last_processed_message_id
                """),
                {
                    "chat_id": chat_id,
                    "username": username,
                    "title": title,
                    "trust_level": trust_level,
                    "partner_id": partner_id,
                },
            ).fetchone()
        return _row_to_source(row)

    def set_active(self, source_id: int, is_active: bool) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE telegram_sources
                    SET is_active = :is_active, updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": source_id, "is_active": is_active},
            )
        return result.rowcount > 0

    def update_last_processed_message_id(self, chat_id: int, message_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE telegram_sources
                    SET last_processed_message_id = :message_id, updated_at = NOW()
                    WHERE chat_id = :chat_id
                """),
                {"chat_id": chat_id, "message_id": message_id},
            )

    def log_reject(
        self,
        *,
        chat_id: int,
        message_id: int,
        stage: str,
        reason: str,
        raw_snippet: str | None = None,
    ) -> None:
        snippet = (raw_snippet or "")[:500] or None
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO telegram_ingest_log (chat_id, message_id, stage, reason, raw_snippet)
                    VALUES (:chat_id, :message_id, :stage, :reason, :raw_snippet)
                """),
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "stage": stage,
                    "reason": reason,
                    "raw_snippet": snippet,
                },
            )

    def ingest_stats(self, days: int = 7) -> dict[str, Any]:
        with self.engine.connect() as conn:
            by_stage = conn.execute(
                text("""
                    SELECT stage, reason, COUNT(*) AS cnt
                    FROM telegram_ingest_log
                    WHERE created_at >= NOW() - (:days || ' days')::interval
                    GROUP BY stage, reason
                    ORDER BY cnt DESC
                """),
                {"days": days},
            ).fetchall()
            by_chat = conn.execute(
                text("""
                    SELECT l.chat_id, COALESCE(s.title, CAST(l.chat_id AS TEXT)) AS title, COUNT(*) AS cnt
                    FROM telegram_ingest_log l
                    LEFT JOIN telegram_sources s ON s.chat_id = l.chat_id
                    WHERE l.created_at >= NOW() - (:days || ' days')::interval
                    GROUP BY l.chat_id, s.title
                    ORDER BY cnt DESC
                    LIMIT 10
                """),
                {"days": days},
            ).fetchall()
        return {
            "days": days,
            "by_stage": [{"stage": r[0], "reason": r[1], "count": r[2]} for r in by_stage],
            "top_chats": [{"chat_id": r[0], "title": r[1], "count": r[2]} for r in by_chat],
        }
