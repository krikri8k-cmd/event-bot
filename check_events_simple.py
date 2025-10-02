#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Ищем события с координатами России
    result = conn.execute(
        text("""
        SELECT id, source, lat, lng
        FROM events 
        WHERE lat > 40 AND lng > 30
        ORDER BY id DESC
        LIMIT 5
    """)
    )

    events = list(result)
    print(f"Events with Russia coords: {len(events)}")

    for event in events:
        print(f"ID: {event[0]}, Source: {event[1]}, Coords: {event[2]}, {event[3]}")

    # Проверяем есть ли событие с координатами (47.4177853, 38.7884107)
    result = conn.execute(
        text("""
        SELECT id, source, lat, lng
        FROM events 
        WHERE lat = 47.4177853 AND lng = 38.7884107
    """)
    )

    exact_event = result.fetchone()
    if exact_event:
        print(f"\nFound exact event: ID: {exact_event[0]}, Source: {exact_event[1]}")
    else:
        print("\nNo event with exact coordinates (47.4177853, 38.7884107)")
