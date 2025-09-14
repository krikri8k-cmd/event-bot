#!/usr/bin/env python3
"""
Проверка использования поля ends_at
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_ends_at_usage():
    """Проверяем как используется поле ends_at"""
    print("🕒 ПРОВЕРКА ПОЛЯ ENDS_AT")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # 1. Проверяем events_user
        print("1️⃣ EVENTS_USER - Поле ends_at")
        print("-" * 30)

        try:
            result = conn.execute(
                text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(ends_at) as with_ends_at,
                    COUNT(*) - COUNT(ends_at) as without_ends_at
                FROM events_user
            """)
            ).fetchone()

            print(f"📊 Всего событий: {result[0]}")
            print(f"📊 С ends_at: {result[1]}")
            print(f"📊 Без ends_at: {result[2]}")

            # Показываем примеры
            examples = conn.execute(
                text("""
                SELECT id, title, starts_at, ends_at
                FROM events_user
                ORDER BY id
                LIMIT 5
            """)
            ).fetchall()

            print("\n📝 Примеры событий:")
            for event in examples:
                ends_at_str = str(event[3]) if event[3] else "NULL"
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]} → {ends_at_str}")

            print()

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print()

        # 2. Проверяем events_parser
        print("2️⃣ EVENTS_PARSER - Поле ends_at")
        print("-" * 30)

        try:
            result = conn.execute(
                text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(ends_at) as with_ends_at,
                    COUNT(*) - COUNT(ends_at) as without_ends_at
                FROM events_parser
            """)
            ).fetchone()

            print(f"📊 Всего событий: {result[0]}")
            print(f"📊 С ends_at: {result[1]}")
            print(f"📊 Без ends_at: {result[2]}")

            # Показываем примеры
            examples = conn.execute(
                text("""
                SELECT id, title, starts_at, ends_at
                FROM events_parser
                ORDER BY id
                LIMIT 5
            """)
            ).fetchall()

            print("\n📝 Примеры событий:")
            for event in examples:
                ends_at_str = str(event[3]) if event[3] else "NULL"
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]} → {ends_at_str}")

            print()

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print()

        # 3. Проверяем events
        print("3️⃣ EVENTS - Поле ends_at")
        print("-" * 30)

        try:
            result = conn.execute(
                text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(ends_at) as with_ends_at,
                    COUNT(*) - COUNT(ends_at) as without_ends_at
                FROM events
            """)
            ).fetchone()

            print(f"📊 Всего событий: {result[0]}")
            print(f"📊 С ends_at: {result[1]}")
            print(f"📊 Без ends_at: {result[2]}")

            print()

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print()

        # 4. Анализ проблемы
        print("4️⃣ АНАЛИЗ ПРОБЛЕМЫ")
        print("-" * 30)

        print("🎯 Проблемы с ends_at:")
        print("   1. Многие события не имеют времени окончания")
        print("   2. Сложно определить когда событие заканчивается")
        print("   3. Фильтрация по времени становится сложной")
        print()

        print("💡 Предлагаемое решение:")
        print("   1. Использовать только starts_at для фильтрации")
        print("   2. События очищаются после наступления следующего дня")
        print("   3. ends_at оставить как NULL или не использовать")
        print()

        print("🔧 Рекомендации:")
        print("   1. В запросах использовать только starts_at")
        print("   2. Фильтровать события по дате начала")
        print("   3. Очищать события после midnight следующего дня")
        print()


async def main():
    """Основная функция"""
    try:
        await check_ends_at_usage()
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
