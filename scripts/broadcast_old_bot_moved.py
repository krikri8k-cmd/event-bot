#!/usr/bin/env python3
"""
Рассылка от СТАРОГО бота всем пользователям из БД: "Мы переехали, новый бот: ..."

Запуск:
  set OLD_TELEGRAM_TOKEN=<старый_токен>
  set NEW_BOT_USERNAME=<username_нового_бота_без_@>
  python scripts/broadcast_old_bot_moved.py

Сначала проверка без отправки:
  python scripts/broadcast_old_bot_moved.py --dry-run

Требуется DATABASE_URL (из .env / app.local.env / railway.env).
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from dotenv import load_dotenv
from sqlalchemy import select

from database import User, get_engine, init_engine


def _load_env():
    root = Path(__file__).resolve().parent.parent
    for name in ("app.local.env", ".env.local", ".env"):
        path = root / name
        if path.exists():
            load_dotenv(path, override=False)
            break


MESSAGE_RU = (
    "🚀 Мы переехали!\n\n"
    "Теперь мы здесь — нажмите ссылку и начните с /start:\n"
    "{link}\n\n"
    "Спасибо, что были с нами!"
)
MESSAGE_EN = (
    "🚀 We've moved!\n\n" "Find us here — tap the link and send /start:\n" "{link}\n\n" "Thanks for staying with us!"
)


async def main():
    _load_env()
    parser = argparse.ArgumentParser(description="Broadcast 'we moved' from OLD bot to all DB users.")
    parser.add_argument("--dry-run", action="store_true", help="Only print user count, do not send.")
    parser.add_argument("--delay", type=float, default=0.08, help="Seconds between messages (default 0.08).")
    args = parser.parse_args()

    old_token = os.getenv("OLD_TELEGRAM_TOKEN")
    new_username = (os.getenv("NEW_BOT_USERNAME") or "MyGuide_EventBot").strip()
    db_url = os.getenv("DATABASE_URL")

    if not old_token:
        print("Set OLD_TELEGRAM_TOKEN.")
        sys.exit(1)
    if not new_username:
        print("Set NEW_BOT_USERNAME (new bot username without @).")
        sys.exit(1)
    if not db_url:
        print("Set DATABASE_URL (e.g. in app.local.env).")
        sys.exit(1)

    init_engine(db_url)
    engine = get_engine()
    link = f"https://t.me/{new_username}"

    with engine.connect() as conn:
        result = conn.execute(select(User.id))
        user_ids = [row[0] for row in result]

    print(f"Users in DB: {len(user_ids)}")
    if not user_ids:
        print("No users to notify.")
        return

    if args.dry_run:
        print("DRY-RUN: would send to:", user_ids[:10], "..." if len(user_ids) > 10 else "")
        return

    bot = Bot(token=old_token.strip())
    sent = 0
    forbidden = 0
    other_errors = 0

    try:
        for i, user_id in enumerate(user_ids):
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=MESSAGE_RU.format(link=link) + "\n\n---\n\n" + MESSAGE_EN.format(link=link),
                )
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
