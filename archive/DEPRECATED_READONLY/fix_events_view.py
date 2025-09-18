#!/usr/bin/env python3
"""
Исправление VIEW events для упрощенной архитектуры
"""

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def fix_events_view():
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # Удаляем старую таблицу events (она не нужна в упрощенной архитектуре)
        conn.execute(text("DROP TABLE IF EXISTS events"))
        print("✅ Удалена старая таблица events")

        # Создаем новый упрощенный VIEW
        conn.execute(
            text("""
            CREATE VIEW events AS
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
        print("✅ Создан новый упрощенный VIEW events")

        # Проверяем структуру нового VIEW
        result = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'events' ORDER BY ordinal_position"
            )
        ).fetchall()
        print("📋 Новый VIEW events columns:")
        for row in result:
            print(f"  {row[0]}")


if __name__ == "__main__":
    fix_events_view()
