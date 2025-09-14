#!/usr/bin/env python3
"""
Миграция на упрощенную архитектуру без VIEW
"""

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def migrate_to_simple():
    """Мигрируем на упрощенную архитектуру без VIEW"""
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # 1. Удаляем VIEW events (он не нужен)
        conn.execute(text("DROP VIEW IF EXISTS events"))
        print("✅ Удален VIEW events")

        # 2. Удаляем старые таблицы которые не нужны
        conn.execute(text("DROP TABLE IF EXISTS moments"))
        print("✅ Удалена таблица moments")

        # 3. Удаляем старые VIEW для регионов
        conn.execute(text("DROP VIEW IF EXISTS events_all_bali"))
        conn.execute(text("DROP VIEW IF EXISTS events_all_moscow"))
        conn.execute(text("DROP VIEW IF EXISTS events_all_spb"))
        print("✅ Удалены старые VIEW для регионов")

        # 4. Проверяем что осталось
        result = conn.execute(
            text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'TABLE'
            ORDER BY table_name
        """)
        ).fetchall()

        print("📋 Оставшиеся таблицы:")
        for row in result:
            print(f"  - {row[0]}")

        conn.commit()
        print("✅ Миграция завершена!")


if __name__ == "__main__":
    migrate_to_simple()
