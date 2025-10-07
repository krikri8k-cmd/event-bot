#!/usr/bin/env python3
"""
Тест обновленного UnifiedEventsService
"""

import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine

from config import load_settings
from utils.unified_events_service import UnifiedEventsService


def main():
    print("🧪 Тест обновленного UnifiedEventsService")
    print("=" * 50)

    try:
        # Загружаем настройки
        settings = load_settings()
        engine = create_engine(settings.database_url)

        # Создаем сервис
        service = UnifiedEventsService(engine)

        # Тест 1: Поиск событий сегодня
        print("\n🔍 Тест 1: Поиск событий сегодня в Bali")
        events = service.search_events_today(city="bali", user_lat=-8.6500, user_lng=115.2167, radius_km=15)

        print(f"📊 Найдено событий: {len(events)}")

        if events:
            print("\n📋 Примеры событий:")
            for i, event in enumerate(events[:3]):  # Показываем первые 3
                print(f"  {i+1}. {event.get('title', 'Без названия')} ({event.get('source', 'unknown')})")
                print(f"     Время: {event.get('starts_at')}")
                print(f"     Место: {event.get('location_name', 'Не указано')}")
                if event.get("venue_name"):
                    print(f"     Venue: {event['venue_name']}")
                if event.get("address"):
                    print(f"     Адрес: {event['address']}")
                print()

        # Тест 2: Статистика
        print("\n📊 Тест 2: Статистика событий")
        stats = service.get_events_stats(city="bali")

        print("📈 Статистика для Bali:")
        print(f"  Всего событий: {stats.get('total', 0)}")
        print(f"  Парсерных событий: {stats.get('parser_events', 0)}")
        print(f"  Пользовательских событий: {stats.get('user_events', 0)}")

        # Тест 3: Сохранение нового события (тест)
        print("\n💾 Тест 3: Сохранение тестового события")

        # Создаем тестовое событие
        test_event_id = service.save_parser_event(
            source="test",
            external_id="test_001",
            title="Тестовое событие после миграции",
            description="Это тестовое событие для проверки работы после миграции",
            starts_at_utc="2025-01-15 10:00:00+00",
            city="bali",
            lat=-8.6500,
            lng=115.2167,
            location_name="Тестовое место",
            location_url="https://example.com",
            url="https://example.com/event",
        )

        print(f"✅ Тестовое событие создано с ID: {test_event_id}")

        # Проверяем, что событие появилось в поиске
        test_events = service.search_events_today(city="bali", user_lat=-8.6500, user_lng=115.2167, radius_km=15)

        test_found = any(event.get("id") == test_event_id for event in test_events)
        if test_found:
            print("✅ Тестовое событие найдено в поиске")
        else:
            print("⚠️ Тестовое событие не найдено в поиске")

        # Удаляем тестовое событие
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(text("DELETE FROM events WHERE id = :event_id"), {"event_id": test_event_id})
            print("🧹 Тестовое событие удалено")

        print("\n🎉 Все тесты пройдены успешно!")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
