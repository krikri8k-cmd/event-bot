#!/usr/bin/env python3
"""
Рассылка от СТАРОГО бота всем пользователям из БД: «Мы переехали» → новый @MyGuide_EventBot.

Переменные окружения (.env / app.local.env / export):
  OLD_TELEGRAM_TOKEN — токен старого бота (не путать с TELEGRAM_TOKEN нового)
  DATABASE_URL       — PostgreSQL (полный URL, обычно …/railway в конце)
  NEW_BOT_USERNAME   — опционально, например MyGuide_EventBot или @MyGuide_EventBot

Запуск (Windows cmd):
  set OLD_TELEGRAM_TOKEN=...
  python scripts/broadcast_old_bot_moved.py --dry-run
  python scripts/broadcast_old_bot_moved.py

Bash:
  export OLD_TELEGRAM_TOKEN=...
  python scripts/broadcast_old_bot_moved.py --dry-run
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Запуск: python scripts/broadcast_old_bot_moved.py из корня репозитория
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from aiogram import Bot  # noqa: E402
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import select  # noqa: E402

from database import User, get_engine, init_engine  # noqa: E402


def _load_env():
    """Подгружаем все найденные файлы; последний перекрывает ключи.
    Порядок: сначала общие, потом .env, в конце .env.local (локальные секреты всегда побеждают)."""
    root = Path(__file__).resolve().parent.parent
    for name in ("app.local.env", ".env", ".env.local"):
        path = root / name
        if path.exists():
            load_dotenv(path, override=True)


def _normalize_username(raw: str) -> str:
    """Без @ для ссылок t.me/username."""
    s = (raw or "").strip()
    if s.startswith("@"):
        s = s[1:]
    return s


def _message_ru(display_at: str, link: str) -> str:
    return (
        "Привет! Мы обновили бота и переехали.\n\n"
        f"Новый бот: {display_at}\n"
        f"{link}\n\n"
        "Открой его и нажми /start — там актуальные события и места.\n\n"
        "Спасибо, что были с нами!"
    )


async def main():
    _load_env()
    parser = argparse.ArgumentParser(description="Broadcast 'we moved' from OLD bot to all DB users.")
    parser.add_argument("--dry-run", action="store_true", help="Only print user count, do not send.")
    parser.add_argument("--delay", type=float, default=0.08, help="Seconds between messages (default 0.08).")
    args = parser.parse_args()

    old_token = os.getenv("OLD_TELEGRAM_TOKEN")
    new_username = _normalize_username(os.getenv("NEW_BOT_USERNAME") or "MyGuide_EventBot")
    db_url = os.getenv("DATABASE_URL")

    if not old_token:
        root = Path(__file__).resolve().parent.parent
        env_files = [root / n for n in ("app.local.env", ".env", ".env.local")]
        found = [p for p in env_files if p.exists()]
        # ASCII-only: avoids UnicodeEncodeError on Windows cp1252 consoles
        print("OLD_TELEGRAM_TOKEN is not set.")
        if found:
            print("  Env files loaded:", ", ".join(p.name for p in found))
            print("  Add OLD_TELEGRAM_TOKEN=... to one of them (no spaces around =).")
        else:
            print("  No env files in project root:", ", ".join(p.name for p in env_files))
            print("  Create .env or .env.local next to requirements.txt, or export vars in shell.")
            print("  Tip: Save the file in the editor (Ctrl+S) — dotenv reads from disk, not unsaved buffers.")
        sys.exit(1)
    if not new_username:
        print("Set NEW_BOT_USERNAME (e.g. MyGuide_EventBot or @MyGuide_EventBot).")
        sys.exit(1)
    if not db_url:
        print("Set DATABASE_URL (e.g. in app.local.env).")
        sys.exit(1)

    init_engine(db_url)
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(select(User.id))
        user_ids = sorted({int(row[0]) for row in result})

    print(f"Users in DB (unique): {len(user_ids)}")
    if not user_ids:
        print("No users to notify.")
        return

    if args.dry_run:
        print("DRY-RUN: would send to:", user_ids[:10], "..." if len(user_ids) > 10 else "")
        return

    bot = Bot(token=old_token.strip())
    display_at = f"@{new_username}"
    link = f"https://t.me/{new_username}"
    text = _message_ru(display_at, link)
    sent = 0
    forbidden = 0
    other_errors = 0

    try:
        for i, user_id in enumerate(user_ids):
            try:
                await bot.send_message(chat_id=user_id, text=text)
                sent += 1
                if (i + 1) % 50 == 0:
                    print(f"  sent {i + 1}/{len(user_ids)} ...")
            except TelegramForbiddenError:
                forbidden += 1
            except TelegramBadRequest as e:
                if "blocked" in str(e).lower() or "forbidden" in str(e).lower() or "deactivated" in str(e).lower():
                    forbidden += 1
                else:
                    other_errors += 1
                    print(f"  skip {user_id}: {e}")
            except Exception as e:
                other_errors += 1
                print(f"  skip {user_id}: {e}")

            await asyncio.sleep(args.delay)

    finally:
        await bot.session.close()

    print(f"Done. Sent: {sent}, forbidden/blocked: {forbidden}, other errors: {other_errors}")


if __name__ == "__main__":
    asyncio.run(main())
