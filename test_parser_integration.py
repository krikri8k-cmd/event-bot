#!/usr/bin/env python3
"""
Тест интеграции парсинга событий с новой архитектурой
"""

import asyncio
import logging
import os

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine
from utils.simple_timezone import get_city_from_coordinates

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_parser_integration():
    """Тестируем интеграцию парсинга с новой архитектурой"""
    print("🧪 ТЕСТ ИНТЕГРАЦИИ ПАРСИНГА С НОВОЙ АРХИТЕКТУРОЙ")
    print("=" * 60)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    # Координаты для тестирования
    test_lat = -8.675326
    test_lng = 115.230191
    test_city = get_city_from_coordinates(test_lat, test_lng)

    print(f"📍 Тестовые координаты: ({test_lat}, {test_lng})")
    print(f"🌍 Определен город: {test_city}")
    print()

    # 1. Проверяем настройки
    print("1️⃣ НАСТРОЙКИ ПАРСЕРОВ")
    print("-" * 30)

    baliforum_enabled = os.getenv("ENABLE_BALIFORUM", "0").strip() == "1"
    ai_generate = os.getenv("AI_GENERATE_SYNTHETIC", "0").strip() == "1"
    ai_parse = os.getenv("AI_PARSE_ENABLE", "0").strip() == "1"

    print(f"🌴 BaliForum: {'✅ включен' if baliforum_enabled else '❌ отключен'}")
    print(f"🤖 AI генерация: {'✅ включена' if ai_generate else '❌ отключена'}")
    print(f"🧠 AI парсинг: {'✅ включен' if ai_parse else '❌ отключен'}")
    print()

    # 2. Тестируем BaliForum парсер
    if baliforum_enabled:
        print("2️⃣ ТЕСТ BALIFORUM ПАРСЕРА")
        print("-" * 30)

        try:
            from sources.baliforum_source import BaliForumSource

            source = BaliForumSource()
            print(f"📋 Источник: {source.display_name}")
            print(f"🌍 Страна: {source.country_code}")

            # Тестируем получение событий
            events = await source.fetch_events(test_lat, test_lng, radius_km=15)
            print(f"📊 Найдено событий: {len(events)}")

            if events:
                print("📝 Примеры событий:")
                for i, event in enumerate(events[:3], 1):
                    print(f"   {i}. {event['title']}")
                    print(f"      Время: {event.get('time_local', 'Не указано')}")
                    print(f"      Место: {event.get('venue', {}).get('name', 'Не указано')}")
                    print(f"      Координаты: ({event['lat']}, {event['lng']})")
                    print(f"      Источник: {event['source']}")
                    print()
            else:
                print("⚠️ События не найдены")

        except Exception as e:
            print(f"❌ Ошибка при тестировании BaliForum: {e}")
            logger.exception("Ошибка BaliForum")

        print()

    # 3. Проверяем текущее состояние БД
    print("3️⃣ ТЕКУЩЕЕ СОСТОЯНИЕ БД")
    print("-" * 30)

    with engine.connect() as conn:
        # Парсерные события
        parser_result = conn.execute(
            text("""
            SELECT COUNT(*) FROM events_parser
            WHERE city = :city
        """),
            {"city": test_city},
        ).fetchone()

        print(f"📊 Парсерных событий в {test_city}: {parser_result[0]}")

        # Пользовательские события
        user_result = conn.execute(
            text("""
            SELECT COUNT(*) FROM events_user
            WHERE city = :city
        """),
            {"city": test_city},
        ).fetchone()

        print(f"📊 Пользовательских событий в {test_city}: {user_result[0]}")

        # Всего через VIEW
        all_result = conn.execute(
            text("""
            SELECT COUNT(*) FROM events_all
            WHERE city = :city
        """),
            {"city": test_city},
        ).fetchone()

        print(f"📊 Всего событий в {test_city}: {all_result[0]}")
        print()

    # 4. Проверяем как работает поиск
    print("4️⃣ ТЕСТ ПОИСКА СОБЫТИЙ")
    print("-" * 30)

    try:
        from utils.ultra_simple_events import UltraSimpleEventsService

        events_service = UltraSimpleEventsService(engine)
        events = events_service.search_events_today(city=test_city, user_lat=test_lat, user_lng=test_lng, radius_km=15)

        print(f"📊 Найдено событий: {len(events)}")

        # Группируем по источникам
        sources = {}
        for event in events:
            source = event["source_type"]
            if source not in sources:
                sources[source] = 0
            sources[source] += 1

        print("📋 По источникам:")
        for source, count in sources.items():
            print(f"   - {source}: {count} событий")

        print()

    except Exception as e:
        print(f"❌ Ошибка при поиске: {e}")
        logger.exception("Ошибка поиска")
        print()

    print("=" * 60)
    print("🎯 ВЫВОД:")
    print("✅ Парсинг событий работает через:")
    print("   1. Источники (BaliForum, KudaGo, AI)")
    print("   2. Получение событий через fetch_events()")
    print("   3. Сохранение в events_parser (если реализовано)")
    print("   4. Поиск через events_all VIEW")
    print("   5. Фильтрация по городу и радиусу")
    print()
    print("⚠️ ВАЖНО:")
    print("   - Парсерные события пока не сохраняются в БД")
    print("   - Нужно добавить сохранение в events_parser")
    print("   - Сейчас работают только пользовательские события")


if __name__ == "__main__":
    asyncio.run(test_parser_integration())
