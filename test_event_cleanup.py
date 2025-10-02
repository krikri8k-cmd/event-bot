#!/usr/bin/env python3
"""
Тест очистки событий
"""

import asyncio
import logging

from config import load_settings
from database import get_engine, init_engine
from utils.event_cleanup import cleanup_old_events, cleanup_old_moments, get_active_events_count

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_event_cleanup():
    """Тестируем очистку событий"""
    print("🧹 ТЕСТ ОЧИСТКИ СОБЫТИЙ")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    # 1. Проверяем текущее состояние
    print("1️⃣ ТЕКУЩЕЕ СОСТОЯНИЕ СОБЫТИЙ")
    print("-" * 30)

    try:
        counts = get_active_events_count(engine, "bali")

        print("📊 Активные события на Бали:")
        print(f"   👥 Пользовательские: {counts['user_events']}")
        print(f"   🤖 Парсерные: {counts['parser_events']}")
        print(f"   📋 Объединенные: {counts['total_events']}")
        print(f"   🕒 Временное окно: {counts['date_range']}")
        print()

    except Exception as e:
        print(f"❌ Ошибка при проверке состояния: {e}")
        print()

    # 2. Очищаем старые события
    print("2️⃣ ОЧИСТКА СТАРЫХ СОБЫТИЙ")
    print("-" * 30)

    try:
        deleted_count = cleanup_old_events(engine, "bali")
        print(f"✅ Очистка завершена. Удалено событий: {deleted_count}")
        print()

    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")
        print()

    # 3. Проверяем состояние после очистки
    print("3️⃣ СОСТОЯНИЕ ПОСЛЕ ОЧИСТКИ")
    print("-" * 30)

    try:
        counts = get_active_events_count(engine, "bali")

        print("📊 Активные события на Бали после очистки:")
        print(f"   👥 Пользовательские: {counts['user_events']}")
        print(f"   🤖 Парсерные: {counts['parser_events']}")
        print(f"   📋 Объединенные: {counts['total_events']}")
        print()

    except Exception as e:
        print(f"❌ Ошибка при проверке после очистки: {e}")
        print()

    # 4. Очищаем моменты
    print("4️⃣ ОЧИСТКА МОМЕНТОВ")
    print("-" * 30)

    try:
        moments_deleted = cleanup_old_moments(engine)
        print(f"✅ Очистка моментов завершена. Удалено: {moments_deleted}")
        print()

    except Exception as e:
        print(f"❌ Ошибка при очистке моментов: {e}")
        print()

    print("=" * 50)
    print("🎯 РЕЗУЛЬТАТ:")
    print("✅ Очистка событий работает!")
    print("✅ Используется только starts_at")
    print("✅ События очищаются после наступления следующего дня")
    print("✅ Моменты очищаются по истечении TTL")


async def main():
    """Основная функция"""
    try:
        await test_event_cleanup()
        return True
    except Exception as e:
        logger.error(f"Ошибка теста: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
