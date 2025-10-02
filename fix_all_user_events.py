#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))


def fix_all_user_events():
    """Исправляет координаты всех пользовательских событий с неправильными координатами"""

    with engine.connect() as conn:
        # Находим пользовательские события с неправильными координатами
        result = conn.execute(
            text("""
                SELECT id, lat, lng, location_name
                FROM events
                WHERE source = 'user'
                AND (lat > 40 OR lat < -10 OR lng > 120 OR lng < 110)
                ORDER BY id DESC
            """)
        )

        events = list(result)
        print(f"Found {len(events)} user events with wrong coordinates")

        for event in events:
            event_id, lat, lng, location_name = event
            print(f"\nEvent ID: {event_id}")
            print(f"Wrong coords: {lat}, {lng}")
            print(f"Location: {location_name}")

            # Используем центр Бали как fallback
            correct_lat = -8.67  # Центр Бали
            correct_lng = 115.21

            # Обновляем координаты
            conn.execute(
                text("""
                    UPDATE events
                    SET lat = :lat, lng = :lng
                    WHERE id = :event_id
                """),
                {"lat": correct_lat, "lng": correct_lng, "event_id": event_id},
            )

            print(f"Fixed to: {correct_lat}, {correct_lng}")

        conn.commit()
        print(f"\n✅ Fixed {len(events)} user events")


if __name__ == "__main__":
    fix_all_user_events()
