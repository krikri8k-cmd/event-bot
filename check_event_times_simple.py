#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))


def check_event_times():
    """Проверяем время событий в базе данных"""

    with engine.connect() as conn:
        # Находим последние пользовательские события
        result = conn.execute(
            text("""
                SELECT id, starts_at, created_at_utc
                FROM events 
                WHERE source = 'user'
                ORDER BY id DESC
                LIMIT 10
            """)
        )

        events = list(result)
        print(f"Found {len(events)} user events:")

        for event in events:
            event_id, starts_at, created_at = event
            print(f"\nEvent ID: {event_id}")
            print(f"starts_at: {starts_at} (type: {type(starts_at)})")
            print(f"created_at: {created_at}")


if __name__ == "__main__":
    check_event_times()
