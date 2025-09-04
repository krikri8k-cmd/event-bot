#!/usr/bin/env python3
"""Проверка новых полей в событиях"""

from sqlalchemy import create_engine, text

from api import config


def check_new_fields():
    engine = create_engine(config.DATABASE_URL)

    with engine.connect() as conn:
        # Проверяем события с новыми полями
        result = conn.execute(
            text("""
            SELECT title, city, country, organizer_id, organizer_url, source
            FROM events 
            ORDER BY created_at DESC
        """)
        )

        print("Events with new fields:")
        for row in result:
            print(f"- {row.title}")
            print(f"  City: {row.city}, Country: {row.country}")
            print(f"  Organizer ID: {row.organizer_id}, URL: {row.organizer_url}")
            print(f"  Source: {row.source}")
            print()


if __name__ == "__main__":
    check_new_fields()
