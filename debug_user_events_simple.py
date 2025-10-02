#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))


def debug_user_events():
    """Проверяем пользовательские события и их координаты"""

    with engine.connect() as conn:
        # Находим последние пользовательские события
        result = conn.execute(
            text("""
                SELECT id, lat, lng, created_at_utc
                FROM events
                WHERE source = 'user'
                ORDER BY id DESC
                LIMIT 5
            """)
        )

        events = list(result)
        print(f"Found {len(events)} user events:")

        for event in events:
            event_id, lat, lng, created_at = event
            print(f"\nEvent ID: {event_id}")
            print(f"Coords: {lat}, {lng}")
            print(f"Created: {created_at}")

            # Проверяем, что координаты в разумных пределах для Бали
            if lat and lng:
                if -11 <= lat <= -6 and 110 <= lng <= 120:
                    print("✅ Coords look like Bali")
                else:
                    print("❌ Coords look wrong (not Bali)")


if __name__ == "__main__":
    debug_user_events()
