"""Internal API для сигналов от Telegram ingest worker."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import load_settings

logger = logging.getLogger(__name__)

router = APIRouter()

_notified_event_ids: set[int] = set()


class IngestNotifyPayload(BaseModel):
    event_id: int
    source_chat_id: int
    message_id: int


@router.post("/telegram-ingest/notify")
async def telegram_ingest_notify(
    payload: IngestNotifyPayload,
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
):
    """
    Worker вызывает после сохранения draft-события.
    PR3: отправка карточки в MODERATION_CHAT_ID.
    """
    settings = load_settings()
    secret = settings.internal_ingest_secret
    if not secret or x_internal_secret != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if payload.event_id in _notified_event_ids:
        return {"ok": True, "duplicate": True}

    _notified_event_ids.add(payload.event_id)
    logger.info(
        "telegram ingest notify: event_id=%s chat_id=%s message_id=%s (moderation card — PR3)",
        payload.event_id,
        payload.source_chat_id,
        payload.message_id,
    )
    return {"ok": True, "queued": False, "note": "Moderation UI in PR3"}
