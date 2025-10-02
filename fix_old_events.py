#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))


def fix_old_user_events():
    """Исправляет координаты старых пользовательских событий"""

    with engine.connect() as conn:
        # Находим пользовательские события с неправильными координатами
        result = conn.execute(
            text("""
                SELECT id, title, lat, lng, location_name
                FROM events
                WHERE source = 'user'
                AND (lat > 40 OR lat < -10 OR lng > 120 OR lng < 110)
                ORDER BY id DESC
            """)
        )

        events = list(result)
        print(f"Found {len(events)} user events with wrong coordinates")

        for event in events:
            event_id, title, lat, lng, location_name = event
            print(f"Event: {title}")
            print(f"Current coords: {lat}, {lng}")
            print(f"Location: {location_name}")

            # Запрашиваем правильные координаты для Бали
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
            print("---")

        conn.commit()
        print(f"✅ Fixed {len(events)} events")


if __name__ == "__main__":
    fix_old_user_events()
