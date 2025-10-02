#!/usr/bin/env python3
"""
Тест EventsService с координатами
"""

import asyncio
import logging

from config import load_settings
from database import get_engine, init_engine
from storage.events_service import EventsService

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_eventsservice_coordinates():
    """Тестируем EventsService с координатами"""
    print("🔍 ТЕСТ EVENTSERVICE С КООРДИНАТАМИ")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)

    # Координаты пользователя
    user_lat = -8.679649
    user_lon = 115.230388

    print(f"📍 Координаты пользователя: ({user_lat}, {user_lon})")
    print()

    # Создаем EventsService
    engine = get_engine()
    events_service = EventsService(engine)

    # 1. Тест без координат (все события)
    print("1️⃣ ТЕСТ БЕЗ КООРДИНАТ")
    print("-" * 30)

    try:
        events = await events_service.search_events(region="bali", days_ahead=7)

        print(f"📊 Найдено событий без координат: {len(events)}")
        for event in events:
            print(f"   ID {event.id}: '{event.title}' - {event.starts_at}")
            print(f"      Координаты: ({event.lat}, {event.lng})")
            print(f"      Тип: {event.event_type}")

        print()

    except Exception as e:
        print(f"❌ Ошибка без координат: {e}")
        print()

    # 2. Тест с координатами (поиск в радиусе)
    print("2️⃣ ТЕСТ С КООРДИНАТАМИ")
    print("-" * 30)

    try:
        events = await events_service.search_events(
            region="bali", center_lat=user_lat, center_lng=user_lon, radius_km=15, days_ahead=7
        )

        print(f"📊 Найдено событий с координатами: {len(events)}")
        for event in events:
            print(f"   ID {event.id}: '{event.title}' - {event.starts_at}")
            print(f"      Координаты: ({event.lat}, {event.lng})")
            print(f"      Тип: {event.event_type}")

        print()

    except Exception as e:
        print(f"❌ Ошибка с координатами: {e}")
        print()

    # 3. Тест с большим радиусом
    print("3️⃣ ТЕСТ С БОЛЬШИМ РАДИУСОМ (50км)")
    print("-" * 30)

    try:
        events = await events_service.search_events(
            region="bali", center_lat=user_lat, center_lng=user_lon, radius_km=50, days_ahead=7
        )

        print(f"📊 Найдено событий с радиусом 50км: {len(events)}")
        for event in events:
            print(f"   ID {event.id}: '{event.title}' - {event.starts_at}")
            print(f"      Координаты: ({event.lat}, {event.lng})")
            print(f"      Тип: {event.event_type}")

        print()

    except Exception as e:
        print(f"❌ Ошибка с большим радиусом: {e}")
        print()

    # 4. Проверяем события в БД напрямую
    print("4️⃣ ПРОВЕРКА СОБЫТИЙ В БД")
    print("-" * 30)

    try:
        from sqlalchemy import text

        engine = get_engine()

        with engine.connect() as conn:
            # События в events_parser с координатами
            parser_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, country, city
                FROM events_parser
                WHERE lat IS NOT NULL AND lng IS NOT NULL
                AND starts_at > NOW()
                ORDER BY starts_at
                LIMIT 10
            """)
            ).fetchall()

            print(f"📊 Событий в events_parser с координатами: {len(parser_events)}")
            for event in parser_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")
                print(f"      Регион: {event[5]}, {event[6]}")

            print()

    except Exception as e:
        print(f"❌ Ошибка при проверке БД: {e}")
        print()

    print("=" * 50)
    print("🎯 АНАЛИЗ:")
    print("1. Проверь что EventsService находит события")
    print("2. Проверь что координаты правильно передаются")
    print("3. Проверь что радиус работает")
    print("4. Проверь что события в БД имеют координаты")


async def main():
    """Основная функция"""
    try:
        await test_eventsservice_coordinates()
        return True
    except Exception as e:
        logger.error(f"Ошибка теста: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
