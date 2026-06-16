"""Жёсткое удаление события из events (только для админ-команд бота)."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from utils.sync_community_world_events import _parse_community_external_id

logger = logging.getLogger(__name__)

_COMMUNITY_ARCHIVE_SQL = """
INSERT INTO events_community_archive (
    id, chat_id, organizer_id, organizer_username,
    admin_id, admin_ids, admin_count,
    title, title_en, description, description_en, starts_at, city,
    location_name, location_url, created_at,
    status, archived_at_utc
)
SELECT id, chat_id, organizer_id, organizer_username,
       admin_id, admin_ids, admin_count,
       title, title_en, description, description_en, starts_at, city,
       location_name, location_url, created_at,
       status, NOW()
FROM events_community
WHERE id = :community_event_id AND chat_id = :chat_id
ON CONFLICT (id) DO NOTHING
"""


def admin_delete_event(engine: Engine, event_id: int) -> dict:
    """
    Удаляет событие из таблицы events и связанные записи.
    Для source=community также архивирует и удаляет строку в events_community.
    """
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    """
                    SELECT id, title, source, external_id, status
                    FROM events
                    WHERE id = :event_id
                    """
                ),
                {"event_id": event_id},
            )
            .mappings()
            .first()
        )
        if not row:
            return {"ok": False, "reason": "not_found"}

        participations_removed = conn.execute(
            text("DELETE FROM user_participation WHERE event_id = :event_id"),
            {"event_id": event_id},
        ).rowcount

        community_deleted = False
        if row["source"] == "community" and row["external_id"]:
            parsed = _parse_community_external_id(str(row["external_id"]))
            if parsed:
                chat_id, community_event_id = parsed
                conn.execute(
                    text(_COMMUNITY_ARCHIVE_SQL),
                    {"community_event_id": community_event_id, "chat_id": chat_id},
                )
                community_deleted = (
                    conn.execute(
                        text(
                            """
                            DELETE FROM events_community
                            WHERE id = :community_event_id AND chat_id = :chat_id
                            """
                        ),
                        {"community_event_id": community_event_id, "chat_id": chat_id},
                    ).rowcount
                    > 0
                )

        events_removed = conn.execute(
            text("DELETE FROM events WHERE id = :event_id"),
            {"event_id": event_id},
        ).rowcount

        if events_removed <= 0:
            return {"ok": False, "reason": "delete_failed"}

        logger.info(
            "admin_delete_event: id=%s source=%s participations=%s community=%s",
            event_id,
            row["source"],
            participations_removed,
            community_deleted,
        )
        return {
            "ok": True,
            "event_id": event_id,
            "title": row["title"],
            "source": row["source"],
            "status": row["status"],
            "participations_removed": participations_removed,
            "community_deleted": community_deleted,
        }
