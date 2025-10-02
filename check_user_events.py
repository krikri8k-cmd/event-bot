#!/usr/bin/env python3
"""
Проверка пользовательских событий
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")


def check_user_events():
    """Проверяет пользовательские события"""

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found")
        return

    engine = create_engine(db_url)

    try:
        with engine.connect() as conn:
            # Проверяем события в events_user
            result = conn.execute(
                text("""
                SELECT id, title, starts_at, location_name, organizer_id, status
                FROM events_user 
                ORDER BY id DESC 
                LIMIT 10
            """)
            )

            print("=== User events in events_user ===")
            for row in result:
                print(
                    f"ID: {row[0]}, Title: {row[1]}, Time: {row[2]}, Location: {row[3]}, Organizer: {row[4]}, Status: {row[5]}"
                )

            # Проверяем события в основной таблице events
            result = conn.execute(
                text("""
                SELECT id, title, starts_at, location_name, organizer_id, source
                FROM events 
                WHERE source = 'user'
                ORDER BY id DESC 
                LIMIT 10
            """)
            )

            print("\n=== User events in main events table ===")
            for row in result:
                print(
                    f"ID: {row[0]}, Title: {row[1]}, Time: {row[2]}, Location: {row[3]}, Organizer: {row[4]}, Source: {row[5]}"
                )

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    check_user_events()
