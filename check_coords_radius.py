#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Проверяем координаты события
    result = conn.execute(
        text("""
        SELECT lat, lng, location_name
        FROM events 
        WHERE source = 'user' 
        AND starts_at >= '2025-10-01 16:00:00' 
        AND starts_at < '2025-10-02 16:00:00'
    """)
    )

    for row in result:
        print(f"Event coordinates: lat={row[0]}, lng={row[1]}, location={row[2]}")

        # Проверяем расстояние от INSTIKI INDONESIA
        # Координаты INSTIKI: -8.666609, 115.225588
        instiki_lat = -8.666609
        instiki_lng = 115.225588

        if row[0] and row[1]:
            # Простой расчет расстояния (приблизительный)
            import math

            lat_diff = abs(row[0] - instiki_lat)
            lng_diff = abs(row[1] - instiki_lng)
            distance_km = math.sqrt(lat_diff**2 + lng_diff**2) * 111  # Примерно

            print(f"Distance from INSTIKI: {distance_km:.2f} km")

            # Проверяем попадает ли в радиус 10км
            in_radius = distance_km <= 10
            print(f"In 10km radius: {in_radius}")
        else:
            print("No coordinates!")

    # Проверяем события с координатами в радиусе
    result = conn.execute(
        text("""
        SELECT COUNT(*) 
        FROM events 
        WHERE source = 'user' 
        AND starts_at >= '2025-10-01 16:00:00' 
        AND starts_at < '2025-10-02 16:00:00'
        AND lat IS NOT NULL 
        AND lng IS NOT NULL
        AND 6371 * acos(
            GREATEST(-1, LEAST(1,
                cos(radians(-8.666609)) * cos(radians(lat)) *
                cos(radians(lng) - radians(115.225588)) +
                sin(radians(-8.666609)) * sin(radians(lat))
            ))
        ) <= 10
    """)
    )

    print(f"Events in 10km radius: {result.fetchone()[0]}")
