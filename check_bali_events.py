#!/usr/bin/env python3
"""
Проверка событий на Бали
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_bali_events():
    """Проверяем события на Бали"""
    print("🏝️ ПРОВЕРКА СОБЫТИЙ НА БАЛИ")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    # Координаты пользователя
    user_lat = -8.679649
    user_lon = 115.230388

    print(f"📍 Координаты пользователя: ({user_lat}, {user_lon})")
    print()

    with engine.connect() as conn:
        # 1. Проверяем события на Бали в events_parser
        print("1️⃣ СОБЫТИЯ НА БАЛИ В EVENTS_PARSER")
        print("-" * 30)

        try:
            # События на Бали
            bali_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, country, city
                FROM events_parser
                WHERE (country = 'ID' OR city = 'bali' OR city ILIKE '%bali%')
                ORDER BY starts_at DESC
                LIMIT 20
            """)
            ).fetchall()

            print(f"📊 Событий на Бали в events_parser: {len(bali_events)}")
            for event in bali_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")
                print(f"      Регион: {event[5]}, {event[6]}")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке Бали: {e}")
            print()

        # 2. Проверяем все события в events_parser
        print("2️⃣ ВСЕ СОБЫТИЯ В EVENTS_PARSER")
        print("-" * 30)

        try:
            # Все события
            all_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, country, city
                FROM events_parser
                ORDER BY starts_at DESC
                LIMIT 20
            """)
            ).fetchall()

            print(f"📊 Всего событий в events_parser: {len(all_events)}")
            for event in all_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")
                print(f"      Регион: {event[5]}, {event[6]}")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке всех событий: {e}")
            print()

        # 3. Проверяем события в events_user
        print("3️⃣ СОБЫТИЯ В EVENTS_USER")
        print("-" * 30)

        try:
            # События пользователей
            user_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, country, city
                FROM events_user
                ORDER BY starts_at DESC
                LIMIT 20
            """)
            ).fetchall()

            print(f"📊 Всего событий в events_user: {len(user_events)}")
            for event in user_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")
                print(f"      Регион: {event[5]}, {event[6]}")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке пользовательских событий: {e}")
            print()

        # 4. Проверяем события в events (объединенная)
        print("4️⃣ СОБЫТИЯ В EVENTS (ОБЪЕДИНЕННАЯ)")
        print("-" * 30)

        try:
            # События в объединенной таблице
            events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, country, city
                FROM events
                ORDER BY starts_at DESC
                LIMIT 20
            """)
            ).fetchall()

            print(f"📊 Всего событий в events: {len(events)}")
            for event in events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")
                print(f"      Регион: {event[5]}, {event[6]}")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке объединенной таблицы: {e}")
            print()

        # 5. Анализ проблемы
        print("5️⃣ АНАЛИЗ ПРОБЛЕМЫ")
        print("-" * 30)

        print("🔍 Возможные причины:")
        print("   1. События на Бали не парсятся")
        print("   2. События парсятся, но не сохраняются")
        print("   3. События сохраняются, но с неправильным регионом")
        print("   4. События в прошлом")
        print("   5. События без координат")
        print()

    print("=" * 50)
    print("🎯 РЕКОМЕНДАЦИИ:")
    print("1. Проверь парсинг событий на Бали")
    print("2. Проверь сохранение в БД")
    print("3. Проверь регион событий")
    print("4. Проверь координаты событий")
    print("5. Проверь временные зоны")


async def main():
    """Основная функция"""
    try:
        await check_bali_events()
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
