#!/usr/bin/env python3
"""Проверка структуры таблицы events"""

from sqlalchemy import create_engine, text

from config import load_settings


def check_schema():
    settings = load_settings()
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        # Получаем структуру таблицы
        result = conn.execute(
            text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'events'
            ORDER BY ordinal_position
        """)
        )

        print("Table events structure:")
        for row in result:
            print(f"- {row.column_name}: {row.data_type} (nullable: {row.is_nullable})")


if __name__ == "__main__":
    check_schema()
