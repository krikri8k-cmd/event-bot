#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from utils.simple_timezone import get_today_start_utc, get_tomorrow_start_utc

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Параметры поиска (как в боте)
    city = "bali"
    user_lat = -8.666609
    user_lng = 115.225588
    radius_km = 10

    # Временные границы
    start_utc = get_today_start_utc(city)
    end_utc = get_tomorrow_start_utc(city)

    print("Search parameters:")
    print(f"City: {city}")
    print(f"User coords: {user_lat}, {user_lng}")
    print(f"Radius: {radius_km} km")
    print(f"Time range: {start_utc} to {end_utc}")

    # Полный запрос поиска (как в UnifiedEventsService)
    query = text("""
        SELECT source, id, title, description, starts_at,
               city, lat, lng, location_name, location_url, url as event_url,
               organizer_id, organizer_username, max_participants,
               current_participants, status, created_at_utc
        FROM events
        WHERE city = :city
        AND starts_at >= :start_utc
        AND starts_at < :end_utc
        AND lat IS NOT NULL AND lng IS NOT NULL
        AND 6371 * acos(
            GREATEST(-1, LEAST(1,
                cos(radians(:user_lat)) * cos(radians(lat)) *
                cos(radians(lng) - radians(:user_lng)) +
                sin(radians(:user_lat)) * sin(radians(lat))
            ))
        ) <= :radius_km
        ORDER BY starts_at
    """)

    result = conn.execute(
        query,
        {
            "city": city,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "user_lat": user_lat,
            "user_lng": user_lng,
            "radius_km": radius_km,
        },
    )

    events = list(result)
    print(f"\nFound {len(events)} events")

    for event in events:
        print(f"Event: {event[2]} at {event[4]} from {event[0]}")
