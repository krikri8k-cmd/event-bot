#!/usr/bin/env python3
"""
Telegram Event Ingestion Worker (Telethon).
Отдельный процесс для Railway develop: слушает telegram_sources и логирует посты.

Запуск: python workers/telegram_ingest.py
Env: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_STRING_SESSION, DATABASE_URL
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("telegram_ingest")

# Дедуп альбомов: media_group_id -> message_id первого обработанного
_seen_media_groups: dict[int, int] = {}
_active_chat_ids: set[int] = set()


def _ingest_enabled() -> bool:
    return os.getenv("TELEGRAM_INGEST_ENABLED", "0").strip() == "1"


def _message_text(message) -> str:
    parts = [message.message or ""]
    if getattr(message, "caption", None):
        parts.append(message.caption)
    return "\n".join(p for p in parts if p).strip()


def _should_skip_before_llm(message) -> str | None:
    text = _message_text(message)
    if not text:
        return "no_text_or_caption"
    if getattr(message, "sticker", None):
        return "sticker"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "action", None):
        return "service"
    if getattr(message, "fwd_from", None) and not text:
        return "forward_without_text"
    return None


async def _reload_active_sources(service) -> set[int]:
    global _active_chat_ids
    try:
        sources = service.list_sources(active_only=True)
        _active_chat_ids = {s.chat_id for s in sources}
        logger.info("Active telegram sources: %s", len(_active_chat_ids))
    except Exception as e:
        logger.error("Failed to load telegram_sources (migration applied?): %s", e)
    return _active_chat_ids


async def _handle_message(event, service):
    message = event.message
    chat_id = event.chat_id
    message_id = message.id

    if chat_id not in _active_chat_ids:
        return

    media_group_id = getattr(message, "grouped_id", None)
    if media_group_id:
        if media_group_id in _seen_media_groups:
            service.log_reject(
                chat_id=chat_id,
                message_id=message_id,
                stage="filter",
                reason="media_group_duplicate",
            )
            service.update_last_processed_message_id(chat_id, message_id)
            return
        _seen_media_groups[media_group_id] = message_id

    skip_reason = _should_skip_before_llm(message)
    if skip_reason:
        service.log_reject(
            chat_id=chat_id,
            message_id=message_id,
            stage="filter",
            reason=skip_reason,
            raw_snippet=_message_text(message)[:200],
        )
        service.update_last_processed_message_id(chat_id, message_id)
        return

    from utils.telegram_telethon_helpers import extract_message_entity_links

    text = _message_text(message)
    entity_links = extract_message_entity_links(message)
    logger.info("TG ingest [%s:%s] len=%s preview=%r", chat_id, message_id, len(text), text[:80])
    if entity_links:
        logger.info("TG ingest [%s:%s] entity_links=%s", chat_id, message_id, len(entity_links))

    source = service.get_by_chat_id(chat_id)
    if not source or not source.is_active:
        return

    from utils.telegram_ingest_pipeline import process_telegram_post
    from utils.telegram_telethon_helpers import (
        export_message_link,
        resolve_message_poster,
    )

    post_date = getattr(message, "date", None)
    poster_id, poster_username = await resolve_message_poster(message)
    post_url = await export_message_link(
        event.client,
        chat_id,
        message_id,
        source_username=source.username,
    )
    if poster_username:
        logger.info("TG ingest poster @%s (id=%s)", poster_username, poster_id)
    if post_url:
        logger.info("TG ingest post_url=%s", post_url)

    await process_telegram_post(
        engine=service.engine,
        service=service,
        source=source,
        message_id=message_id,
        text=text,
        post_date=post_date,
        post_url=post_url,
        poster_id=poster_id,
        poster_username=poster_username,
        entity_links=entity_links,
    )


def _start_health_server() -> None:
    """Railway healthcheck: worker не uvicorn, но /health нужен для деплоя."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    port = int(os.getenv("PORT", "8080"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/health", "/"):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            return

    def serve():
        server = HTTPServer(("0.0.0.0", port), Handler)
        logger.info("Health server listening on 0.0.0.0:%s", port)
        server.serve_forever()

    threading.Thread(target=serve, daemon=True).start()


async def main():
    _start_health_server()
    if not _ingest_enabled():
        logger.error("TELEGRAM_INGEST_ENABLED is not 1 — exiting")
        sys.exit(1)

    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()
    if not api_id or not api_hash or not session:
        logger.error("Missing TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_STRING_SESSION")
        sys.exit(1)

    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    from config import load_settings
    from database import get_engine, init_engine
    from utils.telegram_sources_service import TelegramSourcesService

    settings = load_settings(require_bot=False)
    init_engine(settings.database_url)
    engine = get_engine()
    service = TelegramSourcesService(engine)
    await _reload_active_sources(service)

    client = TelegramClient(StringSession(session), int(api_id), api_hash)

    @client.on(events.NewMessage())
    async def handler(event):
        try:
            await _handle_message(event, service)
        except Exception:
            logger.exception("Error handling message chat=%s", event.chat_id)

    async def refresh_sources_loop():
        while True:
            await asyncio.sleep(120)
            await _reload_active_sources(service)

    logger.info("Starting Telethon userbot worker (PR2: LLM + geo + save)...")
    await client.start()
    asyncio.create_task(refresh_sources_loop())
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
