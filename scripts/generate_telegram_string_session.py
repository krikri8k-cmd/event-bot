#!/usr/bin/env python3
"""Одноразовая генерация TELEGRAM_STRING_SESSION для userbot worker.

Использование:
  export TELEGRAM_API_ID=12345
  export TELEGRAM_API_HASH=your_hash
  python scripts/generate_telegram_string_session.py

При первом запуске Telethon запросит телефон и код из Telegram.
Скопируй выведённую строку в Railway → TELEGRAM_STRING_SESSION.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    api_id_raw = (os.getenv("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()
    if not api_id_raw or not api_hash:
        print("Задай TELEGRAM_API_ID и TELEGRAM_API_HASH в окружении.", file=sys.stderr)
        return 1

    try:
        from telethon.sessions import StringSession
        from telethon.sync import TelegramClient
    except ImportError:
        print("Установи telethon: pip install telethon", file=sys.stderr)
        return 1

    api_id = int(api_id_raw)
    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session = client.session.save()
        print("\n=== TELEGRAM_STRING_SESSION (сохрани в Railway, не коммить в git) ===\n")
        print(session)
        print("\n====================================================================\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
