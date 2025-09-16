#!/usr/bin/env python3
"""
Простая проверка AI парсера
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_ai_parser_simple():
    """Простая проверка AI парсера"""
    print("🤖 ПРОСТАЯ ПРОВЕРКА AI ПАРСЕРА")
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
        # 1. Проверяем события в events_parser без сложных функций
        print("1️⃣ СОБЫТИЯ В EVENTS_PARSER")
        print("-" * 30)

        try:
            # Все события в events_parser
            all_parser_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, created_at_utc
                FROM events_parser
                ORDER BY created_at_utc DESC
                LIMIT 10
            """)
            ).fetchall()

            print(f"📊 Всего событий в events_parser: {len(all_parser_events)}")
            for event in all_parser_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")

            print()

            # События в будущем (простая проверка)
            future_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng
                FROM events_parser
                WHERE starts_at > NOW()
                ORDER BY starts_at
                LIMIT 10
            """)
            ).fetchall()

            print(f"📊 Событий в будущем: {len(future_events)}")
            for event in future_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке events_parser: {e}")
            print()

        # 2. Проверяем события в events
        print("2️⃣ СОБЫТИЯ В EVENTS")
        print("-" * 30)

        try:
            # Все события в events
            all_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, created_at_utc
                FROM events
                ORDER BY created_at_utc DESC
                LIMIT 10
            """)
            ).fetchall()

            print(f"📊 Всего событий в events: {len(all_events)}")
            for event in all_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")

            print()

            # События в будущем
            future_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng
                FROM events
                WHERE starts_at > NOW()
                ORDER BY starts_at
                LIMIT 10
            """)
            ).fetchall()

            print(f"📊 Событий в будущем: {len(future_events)}")
            for event in future_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке events: {e}")
            print()

        # 3. Тестируем AI парсер напрямую
        print("3️⃣ ТЕСТ AI ПАРСЕРА")
        print("-" * 30)

        try:
            from ai_utils import fetch_ai_events_nearby

            print("🤖 Запускаем AI парсер...")
            ai_events = await fetch_ai_events_nearby(user_lat, user_lon)

            print(f"📊 AI парсер нашел {len(ai_events)} событий")

            if len(ai_events) == 0:
                print("❌ AI парсер не находит события!")
                print("🔍 Возможные причины:")
                print("   1. AI не находит события в интернете")
                print("   2. AI находит события, но они не подходят по критериям")
                print("   3. Проблема с координатами или радиусом")
                print("   4. Проблема с временными зонами")
            else:
                for i, event in enumerate(ai_events, 1):
                    print(f"   {i}. '{event.get('title', 'N/A')}'")
                    print(f"      Описание: {event.get('description', 'N/A')[:50]}...")
                    print(f"      Время: {event.get('time_local', 'N/A')}")
                    print(f"      Локация: {event.get('location_name', 'N/A')}")
                    print(f"      Координаты: ({event.get('lat', 'N/A')}, {event.get('lng', 'N/A')})")
                    print()

        except Exception as e:
            print(f"❌ Ошибка при AI парсинге: {e}")
            logger.exception("Полная ошибка:")
            print()

        # 4. Проверяем настройки
        print("4️⃣ НАСТРОЙКИ")
        print("-" * 30)

        print(f"📊 AI_PARSE_ENABLE: {settings.ai_parse_enable}")
        print(f"📊 STRICT_SOURCE_ONLY: {settings.strict_source_only}")
        print(f"📊 ENABLE_BALIFORUM: {settings.enable_baliforum}")
        print()

    print("=" * 50)
    print("🎯 РЕКОМЕНДАЦИИ:")
    print("1. Проверь почему AI парсер не находит события")
    print("2. Проверь настройки AI")
    print("3. Проверь логи AI парсера")
    print("4. Проверь доступность интернета для AI")


async def main():
    """Основная функция"""
    try:
        await check_ai_parser_simple()
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
