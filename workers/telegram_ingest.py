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

    text = _message_text(message)
    logger.info("TG ingest [%s:%s] len=%s preview=%r", chat_id, message_id, len(text), text[:80])
    service.log_reject(
        chat_id=chat_id,
        message_id=message_id,
        stage="filter",
        reason="logged_awaiting_llm_pr2",
        raw_snippet=text[:200],
    )
    service.update_last_processed_message_id(chat_id, message_id)


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

    from database import get_engine
    from utils.telegram_sources_service import TelegramSourcesService

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

    logger.info("Starting Telethon userbot worker (PR1: log-only, LLM in PR2)...")
    await client.start()
    asyncio.create_task(refresh_sources_loop())
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
