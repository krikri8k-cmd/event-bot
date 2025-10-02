#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Ищем ВСЕ события с координатами России
    result = conn.execute(
        text("""
        SELECT id, source, lat, lng, location_name
        FROM events 
        WHERE lat > 40 AND lng > 30
        ORDER BY id DESC
        LIMIT 10
    """)
    )

    events = list(result)
    print(f"Events with Russia/Ukraine coords: {len(events)}")

    for event in events:
        print(f"ID: {event[0]}, Source: {event[1]}, Coords: {event[2]}, {event[3]}, Location: {event[4]}")

    # Проверяем есть ли событие "Игра в прядки" с такими координатами
    result = conn.execute(
        text("""
        SELECT id, source, lat, lng, location_name
        FROM events 
        WHERE title LIKE '%Игра%' OR title LIKE '%прядки%'
        ORDER BY id DESC
    """)
    )

    game_events = list(result)
    print(f"\nGame events: {len(game_events)}")

    for event in game_events:
        print(f"ID: {event[0]}, Source: {event[1]}, Coords: {event[2]}, {event[3]}, Location: {event[4]}")
