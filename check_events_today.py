#!/usr/bin/env python3
"""
Проверка событий сегодня
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_events_today():
    """Проверяем события сегодня"""
    print("📅 ПРОВЕРКА СОБЫТИЙ СЕГОДНЯ")
    print("=" * 50)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # A. События парсера сегодня
        print("🔍 A. События парсера сегодня:")
        print("-" * 30)

        try:
            events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng
                FROM events_parser
                WHERE starts_at::date = CURRENT_DATE
                ORDER BY starts_at
            """)
            ).fetchall()

            for event in events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")

            print(f"\n📊 Всего событий парсера сегодня: {len(events)}")
            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке событий парсера: {e}")
            print()

        # B. События пользователей сегодня
        print("🔍 B. События пользователей сегодня:")
        print("-" * 30)

        try:
            user_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng
                FROM events_user
                WHERE starts_at::date = CURRENT_DATE
                ORDER BY starts_at
            """)
            ).fetchall()

            for event in user_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]}")
                print(f"      Координаты: ({event[3]}, {event[4]})")

            print(f"\n📊 Всего событий пользователей сегодня: {len(user_events)}")
            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке событий пользователей: {e}")
            print()

        # C. Все события сегодня (объединенные)
        print("🔍 C. Все события сегодня (объединенные):")
        print("-" * 30)

        try:
            all_events = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, 'parser' as source
                FROM events_parser
                WHERE starts_at::date = CURRENT_DATE
                UNION ALL
                SELECT id, title, starts_at, lat, lng, 'user' as source
                FROM events_user
                WHERE starts_at::date = CURRENT_DATE
                ORDER BY starts_at
            """)
            ).fetchall()

            for event in all_events:
                print(f"   ID {event[0]}: '{event[1]}' - {event[2]} ({event[5]})")
                print(f"      Координаты: ({event[3]}, {event[4]})")

            print(f"\n📊 Всего событий сегодня: {len(all_events)}")
            print()

        except Exception as e:
            print(f"❌ Ошибка при проверке всех событий: {e}")
            print()

        # D. Анализ проблемы
        print("🔍 D. АНАЛИЗ ПРОБЛЕМЫ:")
        print("-" * 30)

        print("🎯 Возможные причины почему события не видны:")
        print("   1. События в прошлом (время уже прошло)")
        print("   2. События слишком далеко (радиус фильтр)")
        print("   3. Два хэндлера работают подряд и перебивают друг друга")
        print("   4. Кэш перекрывает свежую выдачу")
        print("   5. Проблема с временными зонами")
        print()

        print("💡 Рекомендации:")
        print("   1. Парсер должен отправлять результат в НОВОЕ сообщение")
        print("   2. Не редактировать то же сообщение для разных сцен")
        print("   3. Логировать message_id отправленных сообщений")
        print("   4. Отключить кэш для отладки: CACHE_TTL_S=0")
        print()


async def main():
    """Основная функция"""
    try:
        await check_events_today()
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
