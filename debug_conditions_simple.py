#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from utils.simple_timezone import get_today_start_utc, get_tomorrow_start_utc

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Параметры поиска
    city = "bali"
    user_lat = -8.666609
    user_lng = 115.225588
    radius_km = 5

    # Временные границы
    start_utc = get_today_start_utc(city)
    end_utc = get_tomorrow_start_utc(city)

    print("=== DEBUG SEARCH CONDITIONS ===")
    print(f"City: {city}")
    print(f"Time range: {start_utc} to {end_utc}")

    # Проверяем каждое условие отдельно
    result = conn.execute(
        text("""
        SELECT id, starts_at, lat, lng, source, city, status
        FROM events
        WHERE source = 'user'
        ORDER BY id DESC
        LIMIT 1
    """)
    )

    event = result.fetchone()
    if event:
        event_id, starts_at, lat, lng, source, event_city, status = event
        print(f"\nLatest user event {event_id}:")
        print(f"  starts_at: {starts_at}")
        print(f"  city: {event_city}")
        print(f"  coords: {lat}, {lng}")
        print(f"  status: {status}")

        # Проверяем каждое условие
        print("  Conditions:")
        print(f"    city = '{city}': {event_city == city}")
        print(f"    starts_at >= {start_utc}: {starts_at >= start_utc if starts_at else 'None'}")
        print(f"    starts_at < {end_utc}: {starts_at < end_utc if starts_at else 'None'}")
        print(f"    lat IS NOT NULL: {lat is not None}")
        print(f"    lng IS NOT NULL: {lng is not None}")

        if lat and lng:
            import math

            lat_diff = abs(lat - user_lat)
            lng_diff = abs(lng - user_lng)
            distance_km = math.sqrt(lat_diff**2 + lng_diff**2) * 111
            print(f"    distance <= {radius_km}km: {distance_km <= radius_km} (distance: {distance_km:.2f}km)")

        # Проверяем все условия вместе
        all_conditions = (
            event_city == city
            and starts_at
            and starts_at >= start_utc
            and starts_at < end_utc
            and lat is not None
            and lng is not None
        )
        print(f"    ALL CONDITIONS: {all_conditions}")
    else:
        print("No user events found!")
