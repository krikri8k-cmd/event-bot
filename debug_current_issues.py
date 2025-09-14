#!/usr/bin/env python3
"""
Диагностика текущих проблем с ботом
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def debug_current_issues():
    """Диагностика текущих проблем"""
    print("🔍 ДИАГНОСТИКА ТЕКУЩИХ ПРОБЛЕМ")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # 1. Проверяем пользовательские события в БД
        print("\n1️⃣ ПОЛЬЗОВАТЕЛЬСКИЕ СОБЫТИЯ В БД")
        print("-" * 40)

        # Считаем все пользовательские события
        total_user_events = conn.execute(text("SELECT COUNT(*) FROM events_user")).scalar()
        print(f"📊 Всего пользовательских событий: {total_user_events}")

        # Проверяем события по регионам
        user_regions = conn.execute(
            text("""
            SELECT country, city, COUNT(*)
            FROM events_user
            GROUP BY country, city
            ORDER BY COUNT(*) DESC
        """)
        ).fetchall()

        print("\n🌍 События по регионам:")
        for region in user_regions:
            print(f"   {region[0] or 'NULL'}/{region[1] or 'NULL'}: {region[2]} событий")

        # Проверяем последние события
        recent_events = conn.execute(
            text("""
            SELECT id, title, starts_at, lat, lng, country, city, organizer_id, created_at_utc
            FROM events_user
            ORDER BY created_at_utc DESC
            LIMIT 10
        """)
        ).fetchall()

        print("\n📋 Последние 10 пользовательских событий:")
        for event in recent_events:
            print(f"   ID {event[0]}: '{event[1][:30]}...'")
            print(f"      Время: {event[2]}")
            print(f"      Координаты: ({event[3] or 'NULL'}, {event[4] or 'NULL'})")
            print(f"      Регион: {event[5] or 'NULL'}/{event[6] or 'NULL'}")
            print(f"      Организатор: {event[7]}")
            print(f"      Создано: {event[8]}")
            print()

        # 2. Тестируем поиск событий для Бали (как в скриншоте)
        print("\n2️⃣ ТЕСТ ПОИСКА ДЛЯ БАЛИ")
        print("-" * 40)

        # Координаты Бали (как в скриншоте с событием "Дирка")
        bali_lat, bali_lng = -8.6500, 115.2167  # Denpasar, Bali
        test_radius = 5

        print(f"🔍 Ищем события в радиусе {test_radius} км от Бали ({bali_lat}, {bali_lng})")

        # Поиск в events_user для Бали
        bali_user_events = conn.execute(
            text("""
            SELECT id, title, lat, lng, country, city, starts_at
            FROM events_user
            WHERE lat IS NOT NULL AND lng IS NOT NULL
            AND (
                6371 * acos(
                    cos(radians(:lat)) * cos(radians(lat)) *
                    cos(radians(lng) - radians(:lng)) +
                    sin(radians(:lat)) * sin(radians(lat))
                )
            ) <= :radius
            AND starts_at > NOW()
            ORDER BY starts_at ASC
            LIMIT 10
        """),
            {"lat": bali_lat, "lng": bali_lng, "radius": test_radius},
        ).fetchall()

        print(f"👤 Найдено пользовательских событий в Бали: {len(bali_user_events)}")
        for event in bali_user_events:
            print(f"   - '{event[1]}' ({event[4]}/{event[5]}) - {event[6]}")

        # Поиск в events_parser для Бали
        bali_parser_events = conn.execute(
            text("""
            SELECT id, title, lat, lng, country, city, starts_at, source
            FROM events_parser
            WHERE lat IS NOT NULL AND lng IS NOT NULL
            AND (
                6371 * acos(
                    cos(radians(:lat)) * cos(radians(lat)) *
                    cos(radians(lng) - radians(:lng)) +
                    sin(radians(:lat)) * sin(radians(lat))
                )
            ) <= :radius
            AND starts_at > NOW()
            ORDER BY starts_at ASC
            LIMIT 10
        """),
            {"lat": bali_lat, "lng": bali_lng, "radius": test_radius},
        ).fetchall()

        print(f"📊 Найдено событий от парсеров в Бали: {len(bali_parser_events)}")
        for event in bali_parser_events:
            print(f"   - '{event[1]}' ({event[4]}/{event[5]}) - {event[7]}")

        # 3. Тестируем EventsService
        print("\n3️⃣ ТЕСТ EVENTSERVICE")
        print("-" * 40)

        try:
            from storage.events_service import EventsService
            from storage.region_router import Region

            events_service = EventsService(engine)

            # Тестируем поиск в Бали
            bali_events = await events_service.find_events_by_region(
                region=Region.BALI, center_lat=bali_lat, center_lng=bali_lng, radius_km=test_radius, days_ahead=7
            )

            print(f"🌍 EventsService для Бали: {len(bali_events)} событий")

            # Анализируем типы событий
            parser_count = sum(1 for e in bali_events if e.get("event_type") == "parser")
            user_count = sum(1 for e in bali_events if e.get("event_type") == "user")

            print(f"   📊 Парсер: {parser_count}, 👤 Пользователь: {user_count}")

            # Показываем примеры событий
            if bali_events:
                print("\n📋 Примеры событий из EventsService:")
                for event in bali_events[:5]:
                    print(f"   - '{event['title'][:30]}...' [{event.get('event_type', 'unknown')}]")

        except Exception as e:
            print(f"❌ Ошибка EventsService: {e}")

        # 4. Проверяем события с координатами NULL
        print("\n4️⃣ СОБЫТИЯ БЕЗ КООРДИНАТ")
        print("-" * 40)

        null_coords_events = conn.execute(
            text("""
            SELECT COUNT(*)
            FROM events_user
            WHERE lat IS NULL OR lng IS NULL
        """)
        ).scalar()

        print(f"⚠️ Пользовательских событий без координат: {null_coords_events}")

        if null_coords_events > 0:
            print("\n📋 Примеры событий без координат:")
            examples = conn.execute(
                text("""
                SELECT id, title, lat, lng, country, city
                FROM events_user
                WHERE lat IS NULL OR lng IS NULL
                LIMIT 5
            """)
            ).fetchall()

            for event in examples:
                print(f"   ID {event[0]}: '{event[1][:30]}...'")
                print(f"      Координаты: ({event[2]}, {event[3]})")
                print(f"      Регион: {event[4] or 'NULL'}/{event[5] or 'NULL'}")

        # 5. Проверяем события с неправильными регионами
        print("\n5️⃣ СОБЫТИЯ С НЕПРАВИЛЬНЫМИ РЕГИОНАМИ")
        print("-" * 40)

        wrong_region_events = conn.execute(
            text("""
            SELECT COUNT(*)
            FROM events_user
            WHERE country IS NULL OR city IS NULL
        """)
        ).scalar()

        print(f"⚠️ Пользовательских событий с NULL регионами: {wrong_region_events}")

        print("\n" + "=" * 50)
        print("🎯 ДИАГНОСТИКА ЗАВЕРШЕНА")

        # Итоговые выводы
        print("\n📋 ИТОГОВЫЕ ВЫВОДЫ:")

        if total_user_events == 0:
            print("❌ Проблема: Пользовательских событий нет в БД")
        elif len(bali_user_events) == 0:
            print("⚠️ Проблема: События есть в БД, но не находятся в поиске для Бали")
            if null_coords_events > 0:
                print("💡 Возможная причина: События без координат")
            if wrong_region_events > 0:
                print("💡 Возможная причина: События с неправильными регионами")
        else:
            print("✅ Пользовательские события найдены в поиске для Бали")

        if len(bali_events) == 0:
            print("❌ EventsService не находит события для Бали")
        else:
            print(f"✅ EventsService находит {len(bali_events)} событий для Бали")

        return True


async def main():
    """Основная функция"""
    try:
        await debug_current_issues()
        return True
    except Exception as e:
        logger.error(f"Ошибка диагностики: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
