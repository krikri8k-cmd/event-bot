#!/usr/bin/env python3
"""
Проверка координат событий
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")


def check_coords():
    """Проверяет координаты событий"""

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found")
        return

    engine = create_engine(db_url)

    try:
        with engine.connect() as conn:
            # События без координат
            result = conn.execute(
                text("""
                SELECT id, title, starts_at, lat, lng, location_name, source
                FROM events 
                WHERE source = 'user'
                ORDER BY id DESC 
                LIMIT 5
            """)
            )

            print("=== User events with coordinates ===")
            for row in result:
                print(
                    f"ID: {row[0]}, Title: {row[1]}, Time: {row[2]}, Lat: {row[3]}, Lng: {row[4]}, Location: {row[5]}, Source: {row[6]}"
                )

            # События без координат
            result = conn.execute(
                text("""
                SELECT COUNT(*) 
                FROM events 
                WHERE source = 'user' AND (lat IS NULL OR lng IS NULL)
            """)
            )

            no_coords_count = result.fetchone()[0]
            print(f"\nUser events without coordinates: {no_coords_count}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    check_coords()
