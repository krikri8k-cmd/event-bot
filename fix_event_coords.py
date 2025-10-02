#!/usr/bin/env python3
"""
Исправление координат события в базе данных
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))


def fix_event_coordinates():
    """Исправляет координаты события на правильные (Бали)"""

    with engine.connect() as conn:
        # Находим событие с неправильными координатами
        result = conn.execute(
            text("""
            SELECT id, title, lat, lng, location_name
            FROM events
            WHERE source = 'user'
            AND lat > 40  -- Координаты России/Украины
            ORDER BY id DESC
            LIMIT 1
        """)
        )

        event = result.fetchone()
        if event:
            event_id, title, lat, lng, location_name = event
            print(f"Found event with wrong coords: {title}")
            print(f"Current coords: {lat}, {lng}")
            print(f"Location: {location_name}")

            # Правильные координаты для INSTIKI INDONESIA
            correct_lat = -8.6666093
            correct_lng = 115.225588

            # Обновляем координаты
            conn.execute(
                text("""
                UPDATE events
                SET lat = :lat, lng = :lng
                WHERE id = :event_id
            """),
                {"lat": correct_lat, "lng": correct_lng, "event_id": event_id},
            )

            conn.commit()
            print(f"✅ Fixed coordinates to: {correct_lat}, {correct_lng}")
        else:
            print("No events with wrong coordinates found")


if __name__ == "__main__":
    fix_event_coordinates()
