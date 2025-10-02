#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from utils.simple_timezone import get_today_start_utc, get_tomorrow_start_utc

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Параметры поиска (РЕАЛЬНЫЕ координаты из логов!)
    city = "bali"
    user_lat = -8.6747  # Из логов!
    user_lng = 115.2300  # Из логов!
    radius_km = 5

    # Временные границы
    start_utc = get_today_start_utc(city)
    end_utc = get_tomorrow_start_utc(city)

    print("=== DEBUG WITH REAL COORDS ===")
    print(f"User coords: {user_lat}, {user_lng}")
    print(f"Radius: {radius_km} km")

    # Проверяем событие
    result = conn.execute(
        text("""
        SELECT lat, lng
        FROM events
        WHERE source = 'user'
        AND starts_at >= :start_utc
        AND starts_at < :end_utc
    """),
        {"start_utc": start_utc, "end_utc": end_utc},
    )

    event_coords = result.fetchone()
    if event_coords:
        event_lat, event_lng = event_coords
        print(f"Event coords: {event_lat}, {event_lng}")

        # Проверяем расстояние
        import math

        lat_diff = abs(event_lat - user_lat)
        lng_diff = abs(event_lng - user_lng)
        distance_km = math.sqrt(lat_diff**2 + lng_diff**2) * 111
        print(f"Distance: {distance_km:.2f} km")
        print(f"In 5km radius: {distance_km <= 5}")

        # Проверяем точный SQL запрос
        result = conn.execute(
            text("""
            SELECT 6371 * acos(
                GREATEST(-1, LEAST(1,
                    cos(radians(:user_lat)) * cos(radians(:event_lat)) *
                    cos(radians(:event_lng) - radians(:user_lng)) +
                    sin(radians(:user_lat)) * sin(radians(:event_lat))
                ))
            ) as sql_distance
        """),
            {"user_lat": user_lat, "user_lng": user_lng, "event_lat": event_lat, "event_lng": event_lng},
        )

        sql_distance = result.fetchone()[0]
        print(f"SQL distance: {sql_distance:.2f} km")
        print(f"SQL in 5km radius: {sql_distance <= 5}")

        # Полный запрос поиска
        query = text("""
            SELECT COUNT(*)
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

        count = result.fetchone()[0]
        print(f"Found by search query: {count} events")
    else:
        print("No user events found!")
