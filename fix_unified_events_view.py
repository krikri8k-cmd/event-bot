#!/usr/bin/env python3
"""
Исправление VIEW для единой таблицы всех событий
"""

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def fix_unified_events_view():
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # 1. Удаляем старые региональные VIEW
        conn.execute(text("DROP VIEW IF EXISTS events_all_msk"))
        print("✅ Удален старый VIEW events_all_msk")

        # 2. Создаем единый VIEW для ВСЕХ событий ВСЕХ городов
        conn.execute(
            text("""
            CREATE VIEW events_all AS
            SELECT
                'parser' as source_type,
                id,
                title,
                description,
                starts_at,
                city,
                lat,
                lng,
                location_name,
                location_url,
                url as event_url,
                NULL as organizer_id,
                NULL as max_participants,
                NULL as current_participants,
                'open' as status,
                created_at_utc
            FROM events_parser

            UNION ALL

            SELECT
                'user' as source_type,
                id,
                title,
                description,
                starts_at,
                city,
                lat,
                lng,
                location_name,
                location_url,
                NULL as event_url,
                organizer_id,
                max_participants,
                current_participants,
                status,
                created_at_utc
            FROM events_user
        """)
        )

        conn.commit()
        print("✅ Создан единый VIEW events_all для всех городов")

        # 3. Проверяем результат
        result = conn.execute(text("SELECT COUNT(*) FROM events_all")).fetchone()
        print(f"📊 Всего событий в events_all: {result[0]}")

        # 4. Показываем распределение по городам
        result = conn.execute(
            text("""
            SELECT city, COUNT(*) as count
            FROM events_all
            GROUP BY city
            ORDER BY count DESC
        """)
        ).fetchall()

        print("🌍 Распределение событий по городам:")
        for row in result:
            print(f"  - {row[0]}: {row[1]} событий")

        # 5. Показываем примеры событий из разных городов
        result = conn.execute(
            text("""
            SELECT city, title, source_type
            FROM events_all
            ORDER BY city, title
            LIMIT 5
        """)
        ).fetchall()

        print("📝 Примеры событий:")
        for row in result:
            print(f"  - {row[0]}: '{row[1]}' ({row[2]})")


if __name__ == "__main__":
    fix_unified_events_view()
