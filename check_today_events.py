#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Проверяем события на сегодня
    result = conn.execute(
        text("""
        SELECT id, title, starts_at, lat, lng, location_name, source, status
        FROM events 
        WHERE source = 'user' 
        AND starts_at >= CURRENT_DATE 
        AND starts_at < CURRENT_DATE + INTERVAL '1 day'
        ORDER BY id DESC
    """)
    )

    print("=== User events today ===")
    events = list(result)
    for row in events:
        print(
            f"ID: {row[0]}, Title: {row[1]}, Time: {row[2]}, Lat: {row[3]}, Lng: {row[4]}, Location: {row[5]}, Status: {row[7]}"
        )

    print(f"\nTotal user events today: {len(events)}")

    # Проверяем события с координатами на сегодня
    result = conn.execute(
        text("""
        SELECT COUNT(*) 
        FROM events 
        WHERE source = 'user' 
        AND lat IS NOT NULL 
        AND lng IS NOT NULL
        AND starts_at >= CURRENT_DATE 
        AND starts_at < CURRENT_DATE + INTERVAL '1 day'
    """)
    )

    print(f"User events today with coordinates: {result.fetchone()[0]}")
