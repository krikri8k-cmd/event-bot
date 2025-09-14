#!/usr/bin/env python3
"""
Проверка старых VIEW в БД
"""

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def check_old_views():
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # Проверяем какие VIEW у нас есть
        result = conn.execute(
            text("""
            SELECT schemaname, viewname 
            FROM pg_views 
            WHERE schemaname = 'public' 
            ORDER BY viewname
        """)
        ).fetchall()

        print("📋 VIEW в БД:")
        for row in result:
            print(f"  - {row[1]}")

        print()

        # Проверяем структуру events_all_msk если он есть
        try:
            result = conn.execute(
                text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'events_all_msk' 
                ORDER BY ordinal_position
            """)
            ).fetchall()
            print("📋 Структура events_all_msk:")
            for row in result:
                print(f"  - {row[0]}")
        except Exception as e:
            print(f"❌ events_all_msk не найден: {e}")

        print()

        # Проверяем что в events_all_msk
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM events_all_msk")).fetchone()
            print(f"📊 Количество событий в events_all_msk: {result[0]}")

            # Показываем примеры
            result = conn.execute(text("SELECT title, city FROM events_all_msk LIMIT 3")).fetchall()
            print("📝 Примеры событий:")
            for row in result:
                print(f"  - '{row[0]}' в городе '{row[1]}'")

        except Exception as e:
            print(f"❌ Не удалось прочитать events_all_msk: {e}")


if __name__ == "__main__":
    check_old_views()
