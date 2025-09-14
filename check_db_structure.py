#!/usr/bin/env python3
"""
Проверка структуры БД
"""

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def check_db_structure():
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # Проверяем структуру events_user
        result = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'events_user' ORDER BY ordinal_position"
            )
        ).fetchall()
        print("events_user columns:")
        for row in result:
            print(f"  {row[0]}")

        print()

        # Проверяем структуру events_parser
        result = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'events_parser' ORDER BY ordinal_position"
            )
        ).fetchall()
        print("events_parser columns:")
        for row in result:
            print(f"  {row[0]}")

        print()

        # Проверяем VIEW events
        result = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'events' ORDER BY ordinal_position"
            )
        ).fetchall()
        print("events VIEW columns:")
        for row in result:
            print(f"  {row[0]}")


if __name__ == "__main__":
    check_db_structure()
