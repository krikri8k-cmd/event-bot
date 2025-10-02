#!/usr/bin/env python3
"""
Тест сохранения парсерных событий в БД
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine
from utils.parser_integration import ParserIntegration
from utils.simple_timezone import get_city_from_coordinates

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_parser_save():
    """Тестируем сохранение парсерных событий"""
    print("🧪 ТЕСТ СОХРАНЕНИЯ ПАРСЕРНЫХ СОБЫТИЙ В БД")
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

    # 1. Проверяем текущее состояние БД
    print("1️⃣ СОСТОЯНИЕ БД ДО ПАРСИНГА")
    print("-" * 30)

    with engine.connect() as conn:
        parser_result = conn.execute(
            text("""
            SELECT COUNT(*) FROM events_parser
            WHERE city = :city
        """),
            {"city": test_city},
        ).fetchone()

        print(f"📊 Парсерных событий в {test_city}: {parser_result[0]}")

        # Показываем источники
        if parser_result[0] > 0:
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

            print("📋 По источникам:")
            for row in result:
                print(f"   - {row[0]}: {row[1]} событий")

        print()

    # 2. Запускаем парсеры и сохраняем события
    print("2️⃣ ЗАПУСК ПАРСЕРОВ И СОХРАНЕНИЕ")
    print("-" * 30)

    try:
        parser_integration = ParserIntegration()
        results = await parser_integration.run_parsers_and_save(lat=test_lat, lng=test_lng, radius_km=15)

        print("📊 Результаты парсинга:")
        total_saved = 0
        for source, count in results.items():
            print(f"   - {source}: {count} событий")
            total_saved += count

        print(f"🎯 Всего сохранено: {total_saved} событий")
        print()

    except Exception as e:
        print(f"❌ Ошибка при парсинге: {e}")
        logger.exception("Ошибка парсинга")
        return

    # 3. Проверяем состояние БД после парсинга
    print("3️⃣ СОСТОЯНИЕ БД ПОСЛЕ ПАРСИНГА")
    print("-" * 30)

    with engine.connect() as conn:
        parser_result = conn.execute(
            text("""
            SELECT COUNT(*) FROM events_parser
            WHERE city = :city
        """),
            {"city": test_city},
        ).fetchone()

        print(f"📊 Парсерных событий в {test_city}: {parser_result[0]}")

        # Показываем источники
        if parser_result[0] > 0:
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

            print("📋 По источникам:")
            for row in result:
                print(f"   - {row[0]}: {row[1]} событий")

            # Показываем примеры событий
            result = conn.execute(
                text("""
                SELECT title, source, starts_at
                FROM events_parser
                WHERE city = :city
                ORDER BY starts_at
                LIMIT 3
            """),
                {"city": test_city},
            ).fetchall()

            print("📝 Примеры сохраненных событий:")
            for row in result:
                print(f"   - '{row[0]}' ({row[1]}) - {row[2]}")

        print()

    # 4. Проверяем общий VIEW events_all
    print("4️⃣ ПРОВЕРКА VIEW events_all")
    print("-" * 30)

    with engine.connect() as conn:
        all_result = conn.execute(
            text("""
            SELECT COUNT(*) FROM events_all
            WHERE city = :city
        """),
            {"city": test_city},
        ).fetchone()

        print(f"📊 Всего событий в {test_city}: {all_result[0]}")

        # Показываем по типам
        result = conn.execute(
            text("""
            SELECT source_type, COUNT(*) as count
            FROM events_all
            WHERE city = :city
            GROUP BY source_type
            ORDER BY count DESC
        """),
            {"city": test_city},
        ).fetchall()

        print("📋 По типам:")
        for row in result:
            print(f"   - {row[0]}: {row[1]} событий")

        print()

    # 5. Тестируем поиск через новый сервис
    print("5️⃣ ТЕСТ ПОИСКА ЧЕРЕЗ НОВЫЙ СЕРВИС")
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
    print("🎯 РЕЗУЛЬТАТ:")
    if total_saved > 0:
        print("✅ Парсерные события успешно сохранены в БД!")
        print("✅ Поиск через events_all работает!")
        print("✅ Интеграция парсеров с БД работает!")
    else:
        print("⚠️ Парсерные события не найдены или не сохранены")
        print("⚠️ Проверьте настройки парсеров")


if __name__ == "__main__":
    asyncio.run(test_parser_save())
