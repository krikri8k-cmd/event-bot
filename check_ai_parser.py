#!/usr/bin/env python3
"""
Проверка AI парсера событий
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_ai_parser():
    """Проверяем AI парсер событий"""
    print("🤖 ПРОВЕРКА AI ПАРСЕРА СОБЫТИЙ")
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
        # 1. Проверяем настройки AI парсера
        print("1️⃣ НАСТРОЙКИ AI ПАРСЕРА")
        print("-" * 30)

        print(f"📊 AI_PARSE_ENABLE: {settings.ai_parse_enable}")
        print(f"📊 STRICT_SOURCE_ONLY: {settings.strict_source_only}")
        print()

        # 2. Проверяем события в events_parser (основная таблица парсера)
        print("2️⃣ СОБЫТИЯ В EVENTS_PARSER")
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

            print()

            # События в радиусе
            nearby_parser_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng,
                       earth_distance(ll_to_earth(:user_lat, :user_lon), ll_to_earth(lat, lng)) / 1000 as distance_km
                FROM events_parser
                WHERE earth_distance(ll_to_earth(:user_lat, :user_lon), ll_to_earth(lat, lng)) <= :radius_meters
                AND starts_at > NOW()
                ORDER BY distance_km
                LIMIT 10
            """),
                {
                    "user_lat": user_lat,
                    "user_lon": user_lon,
                    "radius_meters": 15000,  # 15 км
                },
            ).fetchall()

            print(f"📊 Событий в радиусе 15км: {len(nearby_parser_events)}")
            for event in nearby_parser_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]} - {event[5]:.1f}км")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке events_parser: {e}")
            print()

        # 3. Проверяем события в events (объединенная таблица)
        print("3️⃣ СОБЫТИЯ В EVENTS (ОБЪЕДИНЕННАЯ)")
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

            print()

            # События в радиусе
            nearby_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng,
                       earth_distance(ll_to_earth(:user_lat, :user_lon), ll_to_earth(lat, lng)) / 1000 as distance_km
                FROM events
                WHERE earth_distance(ll_to_earth(:user_lat, :user_lon), ll_to_earth(lat, lng)) <= :radius_meters
                AND starts_at > NOW()
                ORDER BY distance_km
                LIMIT 10
            """),
                {
                    "user_lat": user_lat,
                    "user_lon": user_lon,
                    "radius_meters": 15000,  # 15 км
                },
            ).fetchall()

            print(f"📊 Событий в радиусе 15км: {len(nearby_events)}")
            for event in nearby_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]} - {event[5]:.1f}км")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке events: {e}")
            print()

        # 4. Тестируем AI парсер напрямую
        print("4️⃣ ТЕСТ AI ПАРСЕРА")
        print("-" * 30)

        try:
            from enhanced_event_search import fetch_ai_events_nearby

            print("🤖 Запускаем AI парсер...")
            ai_events = await fetch_ai_events_nearby(user_lat, user_lon)

            print(f"📊 AI парсер нашел {len(ai_events)} событий")

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

        # 5. Проверяем источники событий
        print("5️⃣ ПРОВЕРКА ИСТОЧНИКОВ")
        print("-" * 30)

        print(f"📊 ENABLE_BALIFORUM: {settings.enable_baliforum}")
        print(f"📊 ENABLE_KUDAGO: {settings.enable_kudago}")
        print(f"📊 ENABLE_MEETUP: {settings.enable_meetup}")
        print()

        # 6. Анализ проблемы
        print("6️⃣ АНАЛИЗ ПРОБЛЕМЫ")
        print("-" * 30)

        print("🔍 Возможные причины:")
        print("   1. AI парсер не находит события в интернете")
        print("   2. События найдены, но не сохраняются в БД")
        print("   3. События в БД, но не попадают в результаты поиска")
        print("   4. Проблема с координатами событий")
        print("   5. События слишком далеко от пользователя")
        print("   6. Проблема с временными зонами")
        print()

    print("=" * 50)
    print("🎯 РЕКОМЕНДАЦИИ:")
    print("1. Проверь что AI парсер находит события")
    print("2. Проверь сохранение в БД")
    print("3. Проверь координаты событий")
    print("4. Проверь радиус поиска")
    print("5. Проверь временные зоны")


async def main():
    """Основная функция"""
    try:
        await check_ai_parser()
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
