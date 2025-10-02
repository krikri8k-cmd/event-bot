#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Проверяем даты событий
    result = conn.execute(
        text("""
        SELECT starts_at, title
        FROM events 
        WHERE source = 'user' 
        ORDER BY id DESC 
        LIMIT 3
    """)
    )

    print("=== Recent user events ===")
    for row in result:
        print(f"Time: {row[0]}, Title: {row[1]}")

    # Проверяем события на 2 октября 2025
    result = conn.execute(
        text("""
        SELECT COUNT(*) 
        FROM events 
        WHERE source = 'user' 
        AND starts_at >= '2025-10-02 00:00:00' 
        AND starts_at < '2025-10-03 00:00:00'
    """)
    )

    print(f"\nEvents on 2025-10-02: {result.fetchone()[0]}")

    # Проверяем события на сегодня
    result = conn.execute(
        text("""
        SELECT COUNT(*) 
        FROM events 
        WHERE source = 'user' 
        AND starts_at >= CURRENT_DATE 
        AND starts_at < CURRENT_DATE + INTERVAL '1 day'
    """)
    )

    print(f"Events today: {result.fetchone()[0]}")
