#!/usr/bin/env python3
"""
Диагностика проблемы с пользовательскими событиями
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def diagnose_user_events():
    """Полная диагностика пользовательских событий"""
    print("🔍 ДИАГНОСТИКА ПОЛЬЗОВАТЕЛЬСКИХ СОБЫТИЙ")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # 1. Проверяем структуру таблиц
        print("\n1️⃣ СТРУКТУРА ТАБЛИЦ")
        print("-" * 30)

        # Проверяем существование таблиц
        tables_result = conn.execute(
            text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'events%'
            ORDER BY table_name
        """)
        ).fetchall()

        existing_tables = [row[0] for row in tables_result]
        print(f"📋 Найденные таблицы: {existing_tables}")

        # Проверяем структуру events_user
        if "events_user" in existing_tables:
            print("\n📊 Структура таблицы events_user:")
            columns_result = conn.execute(
                text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'events_user'
                ORDER BY ordinal_position
            """)
            ).fetchall()

            for col in columns_result:
                nullable = "NULL" if col[2] == "YES" else "NOT NULL"
                default = f" DEFAULT {col[3]}" if col[3] else ""
                print(f"   - {col[0]}: {col[1]} {nullable}{default}")
        else:
            print("❌ Таблица events_user не найдена!")
            return False

        # 2. Проверяем данные в таблицах
        print("\n2️⃣ ДАННЫЕ В ТАБЛИЦАХ")
        print("-" * 30)

        # Считаем события в каждой таблице
        parser_count = conn.execute(text("SELECT COUNT(*) FROM events_parser")).scalar()
        user_count = conn.execute(text("SELECT COUNT(*) FROM events_user")).scalar()

        print(f"📊 events_parser: {parser_count} событий")
        print(f"👤 events_user: {user_count} событий")

        # 3. Анализируем пользовательские события
        if user_count > 0:
            print("\n📋 Последние пользовательские события:")
            recent_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, country, city, organizer_id, created_at_utc
                FROM events_user
                ORDER BY created_at_utc DESC
                LIMIT 5
            """)
            ).fetchall()

            for event in recent_events:
                print(f"   ID {event[0]}: '{event[1][:40]}...'")
                print(f"      Время: {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")
                print(f"      Регион: {event[5]}/{event[6]}")
                print(f"      Организатор: {event[7]}")
                print(f"      Создано: {event[8]}")
                print()
        else:
            print("⚠️ Пользовательских событий нет в БД")

        # 4. Проверяем события по регионам
        print("\n3️⃣ СОБЫТИЯ ПО РЕГИОНАМ")
        print("-" * 30)

        # Парсер события по регионам
        parser_regions = conn.execute(
            text("""
            SELECT country, city, COUNT(*)
            FROM events_parser
            GROUP BY country, city
            ORDER BY COUNT(*) DESC
        """)
        ).fetchall()

        print("📊 События от парсеров:")
        for region in parser_regions:
            print(f"   {region[0] or 'NULL'}/{region[1] or 'NULL'}: {region[2]} событий")

        # Пользовательские события по регионам
        user_regions = conn.execute(
            text("""
            SELECT country, city, COUNT(*)
            FROM events_user
            GROUP BY country, city
            ORDER BY COUNT(*) DESC
        """)
        ).fetchall()

        print("\n👤 Пользовательские события:")
        for region in user_regions:
            print(f"   {region[0] or 'NULL'}/{region[1] or 'NULL'}: {region[2]} событий")

        # 5. Проверяем события за последние 24 часа
        print("\n4️⃣ СОБЫТИЯ ЗА ПОСЛЕДНИЕ 24 ЧАСА")
        print("-" * 30)

        yesterday = datetime.utcnow() - timedelta(hours=24)

        recent_parser = conn.execute(
            text("""
            SELECT COUNT(*) FROM events_parser
            WHERE created_at_utc >= :yesterday
        """),
            {"yesterday": yesterday},
        ).scalar()

        recent_user = conn.execute(
            text("""
            SELECT COUNT(*) FROM events_user
            WHERE created_at_utc >= :yesterday
        """),
            {"yesterday": yesterday},
        ).scalar()

        print(f"📊 Новых событий от парсеров: {recent_parser}")
        print(f"👤 Новых пользовательских событий: {recent_user}")

        # 6. Тестируем поиск событий
        print("\n5️⃣ ТЕСТ ПОИСКА СОБЫТИЙ")
        print("-" * 30)

        # Тестовые координаты (Москва)
        test_lat, test_lng = 55.7558, 37.6173
        test_radius = 10

        print(f"🔍 Ищем события в радиусе {test_radius} км от ({test_lat}, {test_lng})")

        # Поиск в events_parser
        parser_events = conn.execute(
            text("""
            SELECT id, title, lat, lng, country, city
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
            LIMIT 5
        """),
            {"lat": test_lat, "lng": test_lng, "radius": test_radius},
        ).fetchall()

        print(f"📊 Найдено событий от парсеров: {len(parser_events)}")
        for event in parser_events:
            print(f"   - '{event[1][:30]}...' ({event[4]}/{event[5]})")

        # Поиск в events_user
        user_events = conn.execute(
            text("""
            SELECT id, title, lat, lng, country, city
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
            LIMIT 5
        """),
            {"lat": test_lat, "lng": test_lng, "radius": test_radius},
        ).fetchall()

        print(f"👤 Найдено пользовательских событий: {len(user_events)}")
        for event in user_events:
            print(f"   - '{event[1][:30]}...' ({event[4]}/{event[5]})")

        # 7. Проверяем EventsService
        print("\n6️⃣ ТЕСТ EVENTSERVICE")
        print("-" * 30)

        try:
            from storage.events_service import EventsService
            from storage.region_router import Region

            events_service = EventsService(engine)

            # Тестируем поиск в разных регионах
            for region in [Region.MOSCOW, Region.SPB, Region.BALI]:
                events = await events_service.find_events_by_region(
                    region=region,
                    center_lat=test_lat if region == Region.MOSCOW else (59.9343 if region == Region.SPB else -8.5069),
                    center_lng=test_lng if region == Region.MOSCOW else (30.3351 if region == Region.SPB else 115.2625),
                    radius_km=test_radius,
                    days_ahead=7,
                )
                print(f"🌍 {region.value}: {len(events)} событий")

                # Анализируем типы событий
                parser_count = sum(1 for e in events if e.get("event_type") == "parser")
                user_count = sum(1 for e in events if e.get("event_type") == "user")
                print(f"   📊 Парсер: {parser_count}, 👤 Пользователь: {user_count}")

        except Exception as e:
            print(f"❌ Ошибка EventsService: {e}")

        print("\n" + "=" * 50)
        print("🎯 ДИАГНОСТИКА ЗАВЕРШЕНА")

        # Итоговые выводы
        print("\n📋 ИТОГОВЫЕ ВЫВОДЫ:")
        if user_count == 0:
            print("❌ Проблема: Пользовательских событий нет в БД")
            print("💡 Возможные причины:")
            print("   - События не сохраняются при создании")
            print("   - Проблема с EventsService.upsert_user_event")
            print("   - Ошибка в региональной маршрутизации")
        elif len(user_events) == 0:
            print("⚠️ Проблема: События есть в БД, но не находятся в поиске")
            print("💡 Возможные причины:")
            print("   - Неправильные координаты")
            print("   - Проблема с геопоиском")
            print("   - Неправильная региональная маршрутизация")
        else:
            print("✅ Пользовательские события работают корректно")

        return True


async def main():
    """Основная функция"""
    try:
        await diagnose_user_events()
        return True
    except Exception as e:
        logger.error(f"Ошибка диагностики: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
