#!/usr/bin/env python3
"""
Один раз вызвать deleteWebhook для СТАРОГО бота перед миграцией на новый токен.
Запуск: задайте старый токен в OLD_TELEGRAM_TOKEN и выполните скрипт.

  set OLD_TELEGRAM_TOKEN=7369401579:AAG...
  python scripts/delete_webhook_old_bot.py

Или передайте токен аргументом:
  python scripts/delete_webhook_old_bot.py 7369401579:AAG...
"""

import asyncio
import os
import sys

from aiogram import Bot


async def main():
    token = os.getenv("OLD_TELEGRAM_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not token:
        print("Set OLD_TELEGRAM_TOKEN or pass token as argument.")
        sys.exit(1)
    bot = Bot(token=token.strip())
    try:
        result = await bot.delete_webhook(drop_pending_updates=True)
        print("[OK] deleteWebhook result:", result)
        info = await bot.get_webhook_info()
        print("     Webhook info:", info.url or "(empty)")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
