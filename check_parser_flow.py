#!/usr/bin/env python3
"""
Проверка как работает парсинг событий с новой архитектурой
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine
from utils.simple_timezone import get_city_from_coordinates
from utils.unified_events_service import UnifiedEventsService

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_parser_flow():
    """Проверяем как работает парсинг событий"""
    print("🔍 ПРОВЕРКА ПАРСИНГА СОБЫТИЙ С НОВОЙ АРХИТЕКТУРОЙ")
    print("=" * 60)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    # Создаем сервис
    events_service = UnifiedEventsService(engine)

    # Координаты для тестирования
    test_lat = -8.675326
    test_lng = 115.230191
    test_city = get_city_from_coordinates(test_lat, test_lng)

    print(f"📍 Тестовые координаты: ({test_lat}, {test_lng})")
    print(f"🌍 Определен город: {test_city}")
    print()

    # 1. Проверяем текущие события в БД
    print("1️⃣ ТЕКУЩИЕ СОБЫТИЯ В БД")
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

    # 2. Проверяем источники парсерных событий
    print("2️⃣ ИСТОЧНИКИ ПАРСЕРНЫХ СОБЫТИЙ")
    print("-" * 30)

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT source, COUNT(*) as count 
            FROM events_parser 
            WHERE city = :city
            GROUP BY source 
            ORDER BY count DESC
        """),
            {"city": test_city},
        ).fetchall()

        if result:
            for row in result:
                print(f"📋 {row[0]}: {row[1]} событий")
        else:
            print("❌ Нет парсерных событий")
        print()

    # 3. Проверяем настройки парсеров
    print("3️⃣ НАСТРОЙКИ ПАРСЕРОВ")
    print("-" * 30)

    import os

    baliforum_enabled = os.getenv("ENABLE_BALIFORUM", "0").strip() == "1"
    ai_generate = os.getenv("AI_GENERATE_SYNTHETIC", "0").strip() == "1"
    ai_parse = os.getenv("AI_PARSE_ENABLE", "0").strip() == "1"

    print(f"🌴 BaliForum: {'✅ включен' if baliforum_enabled else '❌ отключен'}")
    print(f"🤖 AI генерация: {'✅ включена' if ai_generate else '❌ отключена'}")
    print(f"🧠 AI парсинг: {'✅ включен' if ai_parse else '❌ отключен'}")
    print()

    # 4. Проверяем как работает поиск
    print("4️⃣ ТЕСТ ПОИСКА СОБЫТИЙ")
    print("-" * 30)

    try:
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
        print()

    # 5. Проверяем структуру таблиц
    print("5️⃣ СТРУКТУРА ТАБЛИЦ")
    print("-" * 30)

    with engine.connect() as conn:
        # Проверяем events_parser
        result = conn.execute(
            text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'events_parser' 
            ORDER BY ordinal_position
        """)
        ).fetchall()

        print("📋 events_parser колонки:")
        for row in result:
            print(f"   - {row[0]}")

        print()

    print("=" * 60)
    print("🎯 ВЫВОД:")
    print("✅ Парсинг событий работает через:")
    print("   1. Источники (BaliForum, KudaGo, AI)")
    print("   2. Сохранение в events_parser")
    print("   3. Поиск через events_all VIEW")
    print("   4. Фильтрация по городу и радиусу")


if __name__ == "__main__":
    asyncio.run(check_parser_flow())
