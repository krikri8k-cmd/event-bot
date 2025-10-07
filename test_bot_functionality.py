#!/usr/bin/env python3
"""
Тест функциональности бота с обновленной структурой events
"""

import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text

from config import load_settings
from utils.unified_events_service import UnifiedEventsService


def test_bot_search():
    """Тест поиска событий как в боте"""
    print("🤖 Тест поиска событий как в боте")
    print("=" * 40)

    try:
        settings = load_settings()
        engine = create_engine(settings.database_url)
        service = UnifiedEventsService(engine)

        # Тест поиска для разных городов
        cities = ["bali", "moscow", "spb"]

        for city in cities:
            print(f"\n🏙️ Тест для города: {city}")

            # Поиск без координат
            events = service.search_events_today(city=city)
            print(f"  📊 События без координат: {len(events)}")

            # Поиск с координатами (центр города)
            if city == "bali":
                lat, lng = -8.6500, 115.2167
            elif city == "moscow":
                lat, lng = 55.7558, 37.6176
            else:  # spb
                lat, lng = 59.9311, 30.3609

            events_with_coords = service.search_events_today(city=city, user_lat=lat, user_lng=lng, radius_km=10)
            print(f"  📊 События с координатами: {len(events_with_coords)}")

            # Проверяем источники событий
            sources = {}
            for event in events_with_coords:
                source = event.get("source", "unknown")
                sources[source] = sources.get(source, 0) + 1

            if sources:
                print(f"  📋 Источники: {dict(sources)}")
            else:
                print("  ℹ️ События не найдены")

        return True

    except Exception as e:
        print(f"❌ Ошибка теста бота: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_database_queries():
    """Тест прямых запросов к базе данных"""
    print("\n🗄️ Тест прямых запросов к базе данных")
    print("=" * 40)

    try:
        settings = load_settings()
        engine = create_engine(settings.database_url)

        with engine.connect() as conn:
            # Проверяем общую статистику
            result = conn.execute(
                text("""
                SELECT
                    source,
                    COUNT(*) as count,
                    COUNT(geo_hash) as with_geo_hash,
                    COUNT(starts_at_normalized) as with_normalized_time
                FROM events
                WHERE source IS NOT NULL
                GROUP BY source
                ORDER BY count DESC
            """)
            )

            print("📊 Статистика по источникам:")
            for row in result.fetchall():
                source, count, with_geo, with_time = row
                print(f"  {source}: {count} событий")
                print(f"    С geo_hash: {with_geo} ({with_geo/count*100:.1f}%)")
                print(f"    С нормализованным временем: {with_time} ({with_time/count*100:.1f}%)")

            # Проверяем индексы
            result = conn.execute(
                text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'events'
                AND indexname LIKE 'idx_events_%'
                ORDER BY indexname
            """)
            )

            print("\n🔍 Индексы events:")
            index_count = 0
            for row in result.fetchall():
                indexname, indexdef = row
                print(f"  {indexname}")
                index_count += 1

            print(f"  Всего индексов: {index_count}")

            # Проверяем производительность запроса
            import time

            start_time = time.time()

            result = conn.execute(
                text("""
                SELECT COUNT(*) FROM events
                WHERE city = 'bali'
                AND starts_at >= NOW() - INTERVAL '1 day'
                AND starts_at < NOW() + INTERVAL '1 day'
                AND lat IS NOT NULL AND lng IS NOT NULL
            """)
            )

            query_time = time.time() - start_time
            count = result.fetchone()[0]

            print("\n⚡ Производительность запроса:")
            print(f"  Время выполнения: {query_time*1000:.2f}ms")
            print(f"  Найдено событий: {count}")

        return True

    except Exception as e:
        print(f"❌ Ошибка теста БД: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    print("🧪 Тест функциональности бота после миграции")
    print("=" * 60)

    success = True

    # Тест поиска событий
    if not test_bot_search():
        success = False

    # Тест базы данных
    if not test_database_queries():
        success = False

    if success:
        print("\n🎉 Все тесты функциональности пройдены успешно!")
        print("✅ Бот готов к работе с новой структурой")
    else:
        print("\n❌ Некоторые тесты не прошли")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
