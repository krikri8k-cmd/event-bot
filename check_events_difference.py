#!/usr/bin/env python3
"""
Проверка разницы между events и events_all
"""

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def check_events_difference():
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # Проверяем что у нас есть в БД
        result = conn.execute(
            text("""
            SELECT table_name, table_type 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'events%'
            ORDER BY table_name
        """)
        ).fetchall()

        print("📋 Таблицы и VIEW с events:")
        for row in result:
            print(f"  - {row[0]} ({row[1]})")

        print()

        # Проверяем VIEW
        result = conn.execute(
            text("""
            SELECT viewname 
            FROM pg_views 
            WHERE schemaname = 'public' 
            AND viewname LIKE 'events%'
            ORDER BY viewname
        """)
        ).fetchall()

        print("📋 VIEW с events:")
        for row in result:
            print(f"  - {row[0]}")

        print()

        # Проверяем есть ли таблица events
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM events")).fetchone()
            print(f"📊 Количество событий в таблице 'events': {result[0]}")
        except Exception as e:
            print(f"❌ Таблица 'events' не существует: {e}")

        # Проверяем есть ли VIEW events_all
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM events_all")).fetchone()
            print(f"📊 Количество событий в VIEW 'events_all': {result[0]}")

            # Показываем распределение по городам
            result = conn.execute(
                text("""
                SELECT city, COUNT(*) as count 
                FROM events_all 
                GROUP BY city 
                ORDER BY count DESC
            """)
            ).fetchall()

            print("🌍 Распределение по городам в events_all:")
            for row in result:
                print(f"  - {row[0]}: {row[1]} событий")

        except Exception as e:
            print(f"❌ VIEW 'events_all' не существует: {e}")


if __name__ == "__main__":
    check_events_difference()
