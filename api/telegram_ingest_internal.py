"""Internal API для сигналов от Telegram ingest worker."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import load_settings
from database import get_engine, init_engine

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

    settings = load_settings(require_bot=False)
    init_engine(settings.database_url)
    engine = get_engine()

    from utils.telegram_moderation_service import send_moderation_card

    try:
        sent = await send_moderation_card(
            engine,
            event_id=payload.event_id,
            source_chat_id=payload.source_chat_id,
            message_id=payload.message_id,
        )
    except Exception:
        logger.exception(
            "telegram ingest notify failed event_id=%s chat_id=%s message_id=%s",
            payload.event_id,
            payload.source_chat_id,
            payload.message_id,
        )
        raise HTTPException(status_code=500, detail="Failed to send moderation card") from None

    return {"ok": True, "sent": sent}
