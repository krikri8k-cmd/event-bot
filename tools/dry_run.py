#!/usr/bin/env python3
"""
Dry-run тестирование системы парсинга событий
Имитирует запрос пользователя без запуска Telegram бота
"""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_settings
from database import init_engine
from enhanced_event_search import enhanced_search_events
from utils.geo_utils import haversine_km

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def dry_run_search(lat: float, lng: float, radius_km: float, when: str = "today", verbose: bool = False):
    """Выполняет dry-run поиск событий"""

    print("🔍 Dry-run поиск событий")
    print(f"📍 Координаты: ({lat}, {lng})")
    print(f"📏 Радиус: {radius_km} км")
    print(f"📅 Время: {when}")
    print("-" * 50)

    # Инициализация базы данных
    settings = load_settings()
    init_engine(settings.database_url)

    # Определяем временной диапазон
    now = datetime.now(UTC)
    if when == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=1)
    elif when == "tomorrow":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        end_time = start_time + timedelta(days=1)
    elif when == "week":
        start_time = now
        end_time = now + timedelta(days=7)
    else:
        start_time = now
        end_time = now + timedelta(days=1)

    print(f"⏰ Временной диапазон: {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%Y-%m-%d %H:%M')}")

    try:
        # Выполняем поиск
        start_search = datetime.now()
        events, diag = await enhanced_search_events(
            lat=lat,
            lng=lng,
            radius_km=radius_km,
            start_time=start_time,
            end_time=end_time,
            verbose=verbose,
        )
        search_duration = (datetime.now() - start_search).total_seconds()

        print(f"⏱️ Время поиска: {search_duration:.2f} сек")
        print()

        # Выводим диагностику
        print("📊 Диагностика:")
        print(f"  • Найдено событий: {diag.get('in', 0)}")
        print(f"  • Отфильтровано: {diag.get('dropped', 0)}")
        print(f"  • Итоговых: {len(events)}")

        found_by_stream = diag.get("found_by_stream", {})
        print("  • По источникам:")
        print(f"    - ICS: {found_by_stream.get('ics', 0)}")
        print(f"    - Meetup: {found_by_stream.get('meetup', 0)}")
        print(f"    - AI: {found_by_stream.get('ai', 0)}")
        print(f"    - Моменты: {found_by_stream.get('moments', 0)}")

        kept_by_type = diag.get("kept_by_type", {})
        print("  • По типам:")
        print(f"    - Источники: {kept_by_type.get('source', 0)}")
        print(f"    - Пользовательские: {kept_by_type.get('user', 0)}")
        print(f"    - AI: {kept_by_type.get('ai_parsed', 0)}")

        print()

        # Выводим события
        if events:
            print(f"🎉 Найдено {len(events)} событий:")
            print()

            for i, event in enumerate(events[:10], 1):  # Показываем первые 10
                print(f"{i}. {event.get('title', 'Без названия')}")
                print(f"   📅 {event.get('time_local', 'Время не указано')}")
                print(f"   📍 {event.get('location_name', 'Место не указано')}")

                # Проверяем ссылки
                source_url = event.get("source_url") or event.get("url")
                if source_url:
                    print(f"   🔗 Источник: {source_url}")
                else:
                    print("   🔗 Источник: не указан")

                # Проверяем координаты
                event_lat = event.get("lat")
                event_lng = event.get("lng")
                if event_lat and event_lng:
                    distance = haversine_km(lat, lng, event_lat, event_lng)
                    print(f"   📏 Расстояние: {distance:.1f} км")

                print(f"   🏷️ Тип: {event.get('type', 'unknown')}")
                print()

            if len(events) > 10:
                print(f"... и еще {len(events) - 10} событий")
        else:
            print("😔 События не найдены")
            print()
            print("💡 Возможные причины:")
            print("  • Нет событий в указанном радиусе")
            print("  • Проблемы с источниками данных")
            print("  • Ошибки в парсинге")

        # Проверяем производительность
        if search_duration > 30:
            print(f"⚠️ ВНИМАНИЕ: Поиск занял {search_duration:.2f} сек (превышает 30 сек)")

        return len(events) > 0

    except Exception as e:
        logger.error(f"Ошибка при выполнении dry-run: {e}")
        print(f"❌ Ошибка: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Dry-run тестирование системы парсинга событий")
    parser.add_argument("--lat", type=float, default=-8.5069, help="Широта (по умолчанию: Бали)")
    parser.add_argument("--lng", type=float, default=115.2625, help="Долгота (по умолчанию: Бали)")
    parser.add_argument("--radius", type=float, default=10.0, help="Радиус поиска в км (по умолчанию: 10)")
    parser.add_argument("--when", choices=["today", "tomorrow", "week"], default="today", help="Временной диапазон")
    parser.add_argument("--verbose", action="store_true", help="Подробные логи")

    args = parser.parse_args()

    print("🚀 Запуск dry-run тестирования...")
    print()

    success = await dry_run_search(
        lat=args.lat, lng=args.lng, radius_km=args.radius, when=args.when, verbose=args.verbose
    )

    if success:
        print("✅ Dry-run завершен успешно!")
        sys.exit(0)
    else:
        print("❌ Dry-run завершен с ошибками!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
