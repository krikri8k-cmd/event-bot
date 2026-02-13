#!/usr/bin/env python3
"""
Минимальный бот-редирект для СТАРОГО токена.
Если старый бот временно остаётся в работе — запустите этот скрипт с OLD_TELEGRAM_TOKEN.
Он будет отвечать на любое сообщение ссылкой на нового бота.

Переменные окружения:
  OLD_TELEGRAM_TOKEN — токен старого бота
  NEW_BOT_USERNAME  — username нового бота (без @), например MyNewEventBot
"""

import asyncio
import os
import sys

from aiogram import Bot, Dispatcher, types


async def redirect_handler(message: types.Message):
    new_username = (os.getenv("NEW_BOT_USERNAME") or "MyGuide_EventBot").strip()
    await message.answer("🚀 Мы переехали!\n" f"Новый бот: https://t.me/{new_username}")


async def main():
    token = os.getenv("OLD_TELEGRAM_TOKEN")
    if not token:
        print("Задайте OLD_TELEGRAM_TOKEN в окружении.")
        sys.exit(1)
    dp = Dispatcher()
    dp.message.register(redirect_handler)
    bot = Bot(token=token.strip())
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
