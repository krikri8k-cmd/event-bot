#!/usr/bin/env python3
"""
Исправление пользовательских событий
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def fix_user_events():
    """Исправляет пользовательские события"""
    print("🔧 ИСПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЬСКИХ СОБЫТИЙ")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.begin() as conn:
        # 1. Исправляем события без координат
        print("\n1️⃣ ИСПРАВЛЕНИЕ СОБЫТИЙ БЕЗ КООРДИНАТ")
        print("-" * 40)

        # События без координат получаем координаты по умолчанию для Бали
        null_coords_count = conn.execute(
            text("""
            UPDATE events_user
            SET lat = -8.5069, lng = 115.2625, country = 'ID', city = 'bali'
            WHERE lat IS NULL OR lng IS NULL
        """)
        ).rowcount

        print(f"✅ Обновлено {null_coords_count} событий без координат (установлены координаты Бали)")

        # 2. Исправляем события с NULL регионами
        print("\n2️⃣ ИСПРАВЛЕНИЕ СОБЫТИЙ С NULL РЕГИОНАМИ")
        print("-" * 40)

        # События с координатами Бали
        bali_events_count = conn.execute(
            text("""
            UPDATE events_user
            SET country = 'ID', city = 'bali'
            WHERE (country IS NULL OR city IS NULL)
            AND lat BETWEEN -9.0 AND -8.0
            AND lng BETWEEN 114.0 AND 116.0
        """)
        ).rowcount

        print(f"✅ Обновлено {bali_events_count} событий в регионе Бали")

        # События с координатами Москвы
        moscow_events_count = conn.execute(
            text("""
            UPDATE events_user
            SET country = 'RU', city = 'moscow'
            WHERE (country IS NULL OR city IS NULL)
            AND lat BETWEEN 55.0 AND 60.0
            AND lng BETWEEN 35.0 AND 40.0
        """)
        ).rowcount

        print(f"✅ Обновлено {moscow_events_count} событий в регионе Москва")

        # События с координатами СПб
        spb_events_count = conn.execute(
            text("""
            UPDATE events_user
            SET country = 'RU', city = 'spb'
            WHERE (country IS NULL OR city IS NULL)
            AND lat BETWEEN 59.0 AND 60.5
            AND lng BETWEEN 29.0 AND 31.0
        """)
        ).rowcount

        print(f"✅ Обновлено {spb_events_count} событий в регионе СПб")

        # 3. Проверяем результаты
        print("\n3️⃣ ПРОВЕРКА РЕЗУЛЬТАТОВ")
        print("-" * 40)

        # Считаем события по регионам
        regions = conn.execute(
            text("""
            SELECT country, city, COUNT(*)
            FROM events_user
            GROUP BY country, city
            ORDER BY COUNT(*) DESC
        """)
        ).fetchall()

        print("🌍 События по регионам после исправления:")
        for region in regions:
            print(f"   {region[0] or 'NULL'}/{region[1] or 'NULL'}: {region[2]} событий")

        # Проверяем события без координат
        null_coords = conn.execute(
            text("""
            SELECT COUNT(*)
            FROM events_user
            WHERE lat IS NULL OR lng IS NULL
        """)
        ).scalar()

        print(f"\n⚠️ Событий без координат осталось: {null_coords}")

        # Проверяем события с NULL регионами
        null_regions = conn.execute(
            text("""
            SELECT COUNT(*)
            FROM events_user
            WHERE country IS NULL OR city IS NULL
        """)
        ).scalar()

        print(f"⚠️ Событий с NULL регионами осталось: {null_regions}")

    # 4. Тестируем поиск после исправления
    print("\n4️⃣ ТЕСТ ПОИСКА ПОСЛЕ ИСПРАВЛЕНИЯ")
    print("-" * 40)

    try:
        from storage.events_service import EventsService
        from storage.region_router import Region

        events_service = EventsService(engine)

        # Тестируем поиск в Бали с расширенным радиусом
        bali_lat, bali_lng = -8.65, 115.2167
        test_radius = 20  # Увеличиваем радиус

        print(f"🔍 Ищем события в радиусе {test_radius} км от Бали ({bali_lat}, {bali_lng})")

        bali_events = await events_service.find_events_by_region(
            region=Region.BALI, center_lat=bali_lat, center_lng=bali_lng, radius_km=test_radius, days_ahead=7
        )

        print(f"🌍 Найдено событий для Бали: {len(bali_events)}")

        # Анализируем типы событий
        parser_count = sum(1 for e in bali_events if e.get("event_type") == "parser")
        user_count = sum(1 for e in bali_events if e.get("event_type") == "user")

        print(f"   📊 Парсер: {parser_count}, 👤 Пользователь: {user_count}")

        # Показываем примеры событий
        if bali_events:
            print("\n📋 Примеры событий:")
            for event in bali_events:
                print(f"   - '{event['title'][:30]}...' [{event.get('event_type', 'unknown')}]")

    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")

    print("\n" + "=" * 50)
    print("🎯 ИСПРАВЛЕНИЕ ЗАВЕРШЕНО")

    return True


async def main():
    """Основная функция"""
    try:
        await fix_user_events()
        return True
    except Exception as e:
        logger.error(f"Ошибка исправления: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
