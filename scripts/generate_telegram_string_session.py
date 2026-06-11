#!/usr/bin/env python3
"""Одноразовая генерация TELEGRAM_STRING_SESSION для userbot worker.

Использование:
  Добавь TELEGRAM_API_ID и TELEGRAM_API_HASH в .env.local, затем:
  python scripts/generate_telegram_string_session.py

При первом запуске Telethon запросит телефон и код из Telegram.
Скопируй выведённую строку в Railway → TELEGRAM_STRING_SESSION.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_local_env() -> None:
    """Подхватить .env.local / app.local.env как в config.py."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    for name in (".env.local", "app.local.env", ".env"):
        path = ROOT / name
        if path.exists():
            load_dotenv(dotenv_path=path, encoding="utf-8-sig", override=True)


def main() -> int:
    _load_local_env()
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
