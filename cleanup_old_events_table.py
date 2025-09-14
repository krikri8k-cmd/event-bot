#!/usr/bin/env python3
"""
Удаление старой неиспользуемой таблицы events
"""

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def cleanup_old_events_table():
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # Проверяем что в старой таблице events
        result = conn.execute(text("SELECT COUNT(*) FROM events")).fetchone()
        print(f"📊 Событий в старой таблице 'events': {result[0]}")

        if result[0] == 0:
            print("✅ Таблица 'events' пустая, можно безопасно удалить")

            # Удаляем старую таблицу
            conn.execute(text("DROP TABLE IF EXISTS events"))
            conn.commit()
            print("🗑️ Старая таблица 'events' удалена")
        else:
            print("⚠️ В таблице 'events' есть данные, не удаляем")

        print()

        # Проверяем что осталось
        result = conn.execute(
            text("""
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'events%'
            ORDER BY table_name
        """)
        ).fetchall()

        print("📋 Оставшиеся таблицы и VIEW:")
        for row in result:
            print(f"  - {row[0]} ({row[1]})")

        print()

        # Проверяем что events_all работает
        result = conn.execute(text("SELECT COUNT(*) FROM events_all")).fetchone()
        print(f"✅ VIEW 'events_all' содержит {result[0]} событий")


if __name__ == "__main__":
    cleanup_old_events_table()
