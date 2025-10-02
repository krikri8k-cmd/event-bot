#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    result = conn.execute(
        text("""
        SELECT lat, lng, location_name, title
        FROM events 
        WHERE source = 'user' 
        ORDER BY id DESC 
        LIMIT 1
    """)
    )

    row = result.fetchone()
    if row:
        print(f"Event coords: {row[0]}, {row[1]}")
        print(f"Location: {row[2]}")
        print(f"Title: {row[3]}")

        # Проверяем где это координаты
        lat, lng = row[0], row[1]
        if lat and lng:
            if 47.0 <= lat <= 48.0 and 38.0 <= lng <= 39.0:
                print("📍 These coordinates are in UKRAINE/RUSSIA!")
            elif -9.0 <= lat <= -8.0 and 114.0 <= lng <= 116.0:
                print("📍 These coordinates are in BALI!")
            else:
                print("📍 These coordinates are somewhere else!")
    else:
        print("No user events found!")
