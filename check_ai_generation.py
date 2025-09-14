#!/usr/bin/env python3
"""
Проверка AI генерации событий
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_ai_generation():
    """Проверяем AI генерацию событий"""
    print("🤖 ПРОВЕРКА AI ГЕНЕРАЦИИ СОБЫТИЙ")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    # Координаты пользователя
    user_lat = -8.679649
    user_lon = 115.230388

    print(f"📍 Координаты пользователя: ({user_lat}, {user_lon})")
    print()

    with engine.connect() as conn:
        # 1. Проверяем настройки AI
        print("1️⃣ НАСТРОЙКИ AI")
        print("-" * 30)

        print(f"📊 AI_PARSE_ENABLE: {settings.ai_parse_enable}")
        print(f"📊 AI_GENERATE_SYNTHETIC: {settings.ai_generate_synthetic}")
        print(f"📊 STRICT_SOURCE_ONLY: {settings.strict_source_only}")
        print()

        # 2. Проверяем есть ли AI события в БД
        print("2️⃣ AI СОБЫТИЯ В БД")
        print("-" * 30)

        try:
            ai_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, source, created_at_utc
                FROM events_user
                WHERE source = 'ai_generated' OR title ILIKE '%ai%' OR title ILIKE '%сгенерир%'
                ORDER BY created_at_utc DESC
                LIMIT 10
            """)
            ).fetchall()

            print(f"📊 AI событий в events_user: {len(ai_events)}")
            for event in ai_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]} - {event[5]}")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке AI событий: {e}")
            print()

        # 3. Проверяем events_parser
        try:
            parser_ai_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, source, created_at_utc
                FROM events_parser
                WHERE source = 'ai_generated' OR title ILIKE '%ai%' OR title ILIKE '%сгенерир%'
                ORDER BY created_at_utc DESC
                LIMIT 10
            """)
            ).fetchall()

            print(f"📊 AI событий в events_parser: {len(parser_ai_events)}")
            for event in parser_ai_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]} - {event[5]}")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке AI событий в parser: {e}")
            print()

        # 4. Проверяем events
        try:
            events_ai = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, source, created_at_utc
                FROM events
                WHERE source = 'ai_generated' OR title ILIKE '%ai%' OR title ILIKE '%сгенерир%'
                ORDER BY created_at_utc DESC
                LIMIT 10
            """)
            ).fetchall()

            print(f"📊 AI событий в events: {len(events_ai)}")
            for event in events_ai:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]} - {event[5]}")

            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке AI событий в events: {e}")
            print()

        # 5. Тестируем AI генерацию напрямую
        print("3️⃣ ТЕСТ AI ГЕНЕРАЦИИ")
        print("-" * 30)

        try:
            from enhanced_event_search import fetch_ai_events_nearby

            print("🤖 Запускаем AI генерацию...")
            ai_events = await fetch_ai_events_nearby(user_lat, user_lon)

            print(f"📊 AI сгенерировал {len(ai_events)} событий")

            for i, event in enumerate(ai_events, 1):
                print(f"   {i}. '{event.get('title', 'N/A')}'")
                print(f"      Описание: {event.get('description', 'N/A')[:50]}...")
                print(f"      Время: {event.get('time_local', 'N/A')}")
                print(f"      Локация: {event.get('location_name', 'N/A')}")
                print(f"      Координаты: ({event.get('lat', 'N/A')}, {event.get('lng', 'N/A')})")
                print()

        except Exception as e:
            print(f"❌ Ошибка при AI генерации: {e}")
            logger.exception("Полная ошибка:")
            print()

        # 6. Проверяем почему AI не показывается в поиске
        print("4️⃣ АНАЛИЗ ПОЧЕМУ AI НЕ ПОКАЗЫВАЕТСЯ")
        print("-" * 40)

        print("🔍 Возможные причины:")
        print("   1. AI_GENERATE_SYNTHETIC = 0 (отключено)")
        print("   2. AI события не сохраняются в БД")
        print("   3. AI события генерируются, но не попадают в результаты")
        print("   4. Проблема с координатами AI событий")
        print("   5. AI события слишком далеко от пользователя")
        print()

        # 7. Проверяем настройки в app.local.env
        print("5️⃣ НАСТРОЙКИ В APP.LOCAL.ENV")
        print("-" * 30)

        try:
            with open("app.local.env", encoding="utf-8") as f:
                content = f.read()

            ai_settings = []
            for line in content.split("\n"):
                if "AI_" in line or "ai_" in line:
                    ai_settings.append(line.strip())

            print("📊 AI настройки в .env:")
            for setting in ai_settings:
                print(f"   {setting}")

            print()

        except Exception as e:
            print(f"❌ Ошибка при чтении .env: {e}")
            print()

    print("=" * 50)
    print("🎯 РЕКОМЕНДАЦИИ:")
    print("1. Проверь AI_GENERATE_SYNTHETIC=1 в .env")
    print("2. Проверь что AI события генерируются")
    print("3. Проверь координаты AI событий")
    print("4. Проверь радиус поиска AI событий")


async def main():
    """Основная функция"""
    try:
        await check_ai_generation()
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
