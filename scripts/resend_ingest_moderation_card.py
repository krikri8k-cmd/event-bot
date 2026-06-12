#!/usr/bin/env python3
"""Повторно отправить карточку модерации для draft telegram-события."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_settings  # noqa: E402
from database import get_engine, init_engine  # noqa: E402
from utils.telegram_moderation_service import send_moderation_card  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_id", type=int)
    parser.add_argument("source_chat_id", type=int)
    parser.add_argument("message_id", type=int)
    args = parser.parse_args()

    settings = load_settings()
    init_engine(settings.database_url)
    ok = await send_moderation_card(
        get_engine(),
        event_id=args.event_id,
        source_chat_id=args.source_chat_id,
        message_id=args.message_id,
    )
    print("sent:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
