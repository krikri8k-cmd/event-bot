#!/usr/bin/env python3
"""Проверка структуры таблицы events"""

from sqlalchemy import create_engine, text

from api import config


def check_structure():
    engine = create_engine(config.DATABASE_URL)

    with engine.connect() as conn:
        # Структура таблицы
        result = conn.execute(
            text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'events'
            ORDER BY ordinal_position
        """)
        )

        print("Table events structure:")
        for row in result:
            print(f"- {row.column_name}: {row.data_type} (nullable: {row.is_nullable})")

        print("\n" + "=" * 50)

        # Последние записи с новыми полями
        result = conn.execute(
            text("""
            SELECT id, title, city, country, organizer_id, organizer_url
            FROM events ORDER BY updated_at_utc DESC LIMIT 10
        """)
        )

        print("\nLast 10 events with new fields:")
        for row in result:
            print(f"- ID {row.id}: {row.title}")
            print(f"  City: {row.city}, Country: {row.country}")
            print(f"  Organizer ID: {row.organizer_id}, URL: {row.organizer_url}")

        print("\n" + "=" * 50)

        # Статистика по новым полям
        result = conn.execute(
            text("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN city IS NOT NULL THEN 1 END) as with_city,
                   COUNT(CASE WHEN country IS NOT NULL THEN 1 END) as with_country,
                   COUNT(CASE WHEN organizer_url IS NOT NULL THEN 1 END) as with_organizer_url
            FROM events
        """)
        )

        row = result.fetchone()
        print("\nStatistics:")
        print(f"- Total events: {row.total}")
        print(f"- With city: {row.with_city}")
        print(f"- With country: {row.with_country}")
        print(f"- With organizer_url: {row.with_organizer_url}")


if __name__ == "__main__":
    check_structure()
