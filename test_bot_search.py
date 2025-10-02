#!/usr/bin/env python3
"""
Тест поиска событий в боте
"""

import asyncio
import logging

from enhanced_event_search import enhanced_search_events

from config import load_settings
from database import init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_bot_search():
    """Тестируем поиск событий в боте"""
    print("🤖 ТЕСТ ПОИСКА СОБЫТИЙ В БОТЕ")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)

    # Координаты пользователя
    user_lat = -8.679649
    user_lon = 115.230388

    print(f"📍 Координаты пользователя: ({user_lat}, {user_lon})")
    print()

    # 1. Тест с радиусом 15км (как в боте)
    print("1️⃣ ТЕСТ С РАДИУСОМ 15КМ")
    print("-" * 30)

    try:
        events = await enhanced_search_events(lat=user_lat, lng=user_lon, radius_km=15)

        print(f"📊 Найдено событий с радиусом 15км: {len(events)}")
        for event in events:
            print(f"   ID {event.get('id', 'N/A')}: '{event.get('title', 'N/A')}'")
            print(f"      Время: {event.get('time_local', 'N/A')}")
            print(f"      Координаты: ({event.get('lat', 'N/A')}, {event.get('lng', 'N/A')})")
            print(f"      Источник: {event.get('source', 'N/A')}")

        print()

    except Exception as e:
        print(f"❌ Ошибка с радиусом 15км: {e}")
        print()

    # 2. Тест с радиусом 50км
    print("2️⃣ ТЕСТ С РАДИУСОМ 50КМ")
    print("-" * 30)

    try:
        events = await enhanced_search_events(lat=user_lat, lng=user_lon, radius_km=50)

        print(f"📊 Найдено событий с радиусом 50км: {len(events)}")
        for event in events:
            print(f"   ID {event.get('id', 'N/A')}: '{event.get('title', 'N/A')}'")
            print(f"      Время: {event.get('time_local', 'N/A')}")
            print(f"      Координаты: ({event.get('lat', 'N/A')}, {event.get('lng', 'N/A')})")
            print(f"      Источник: {event.get('source', 'N/A')}")

        print()

    except Exception as e:
        print(f"❌ Ошибка с радиусом 50км: {e}")
        print()

    # 3. Тест без координат (все события)
    print("3️⃣ ТЕСТ БЕЗ КООРДИНАТ")
    print("-" * 30)

    try:
        events = await enhanced_search_events(lat=None, lng=None, radius_km=15)

        print(f"📊 Найдено событий без координат: {len(events)}")
        for event in events:
            print(f"   ID {event.get('id', 'N/A')}: '{event.get('title', 'N/A')}'")
            print(f"      Время: {event.get('time_local', 'N/A')}")
            print(f"      Координаты: ({event.get('lat', 'N/A')}, {event.get('lng', 'N/A')})")
            print(f"      Источник: {event.get('source', 'N/A')}")

        print()

    except Exception as e:
        print(f"❌ Ошибка без координат: {e}")
        print()

    # 4. Анализ результатов
    print("4️⃣ АНАЛИЗ РЕЗУЛЬТАТОВ")
    print("-" * 30)

    print("🔍 Возможные причины:")
    print("   1. События в прошлом")
    print("   2. События слишком далеко")
    print("   3. Проблема с координатами")
    print("   4. Проблема с временными зонами")
    print("   5. Проблема с фильтрацией")
    print()

    print("=" * 50)
    print("🎯 РЕКОМЕНДАЦИИ:")
    print("1. Проверь что события в будущем")
    print("2. Проверь координаты событий")
    print("3. Проверь радиус поиска")
    print("4. Проверь временные зоны")
    print("5. Проверь фильтрацию событий")


async def main():
    """Основная функция"""
    try:
        await test_bot_search()
        return True
    except Exception as e:
        logger.error(f"Ошибка теста: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
