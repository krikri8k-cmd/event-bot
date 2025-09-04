#!/usr/bin/env python3
"""Простой тест бота"""

import asyncio

from aiogram import Bot

from config import load_settings


async def test_bot():
    try:
        # Загружаем настройки
        settings = load_settings(require_bot=True)
        print("✅ Настройки загружены")
        print(f"   TELEGRAM_TOKEN: {settings.telegram_token[:20]}...")
        print(f"   DATABASE_URL: {bool(settings.database_url)}")

        # Создаём бота
        bot = Bot(token=settings.telegram_token)
        print("✅ Бот создан")

        # Получаем информацию о боте
        bot_info = await bot.get_me()
        print("✅ Информация о боте получена:")
        print(f"   ID: {bot_info.id}")
        print(f"   Username: @{bot_info.username}")
        print(f"   First Name: {bot_info.first_name}")

        # Закрываем соединение
        await bot.session.close()
        print("✅ Соединение закрыто")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_bot())
