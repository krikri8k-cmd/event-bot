#!/usr/bin/env python3
"""
Проверка синхронизации событий
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")


def check_sync():
    """Проверяет синхронизацию событий"""

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found")
        return

    engine = create_engine(db_url)

    try:
        with engine.connect() as conn:
            # События в events_user
            result = conn.execute(text("SELECT COUNT(*) FROM events_user"))
            events_user_count = result.fetchone()[0]
            print(f"Events in events_user: {events_user_count}")

            # События в основной таблице events
            result = conn.execute(text("SELECT COUNT(*) FROM events WHERE source = 'user'"))
            events_main_count = result.fetchone()[0]
            print(f"Events in main table: {events_main_count}")

            # Последние события в events_user
            result = conn.execute(
                text("""
                SELECT id, title, starts_at, organizer_id 
                FROM events_user 
                ORDER BY id DESC 
                LIMIT 3
            """)
            )

            print("\nLast events in events_user:")
            for row in result:
                print(f"  ID: {row[0]}, Title: {row[1]}, Time: {row[2]}, Organizer: {row[3]}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    check_sync()
