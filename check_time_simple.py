#!/usr/bin/env python3
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Проверяем границы поиска
    from utils.simple_timezone import get_today_start_utc, get_tomorrow_start_utc

    start_utc = get_today_start_utc("bali")
    end_utc = get_tomorrow_start_utc("bali")

    print("Search boundaries:")
    print(f"Start UTC: {start_utc}")
    print(f"End UTC: {end_utc}")

    # Проверяем попадает ли событие в границы
    result = conn.execute(
        text("""
        SELECT COUNT(*) 
        FROM events 
        WHERE source = 'user' 
        AND starts_at >= :start_utc
        AND starts_at < :end_utc
    """),
        {"start_utc": start_utc, "end_utc": end_utc},
    )

    print(f"Events in search boundaries: {result.fetchone()[0]}")

    # Проверяем время события
    result = conn.execute(
        text("""
        SELECT starts_at
        FROM events 
        WHERE source = 'user' 
        AND starts_at >= '2025-10-02 00:00:00' 
        AND starts_at < '2025-10-03 00:00:00'
    """)
    )

    for row in result:
        utc_time = row[0]
        bali_tz = ZoneInfo("Asia/Makassar")
        local_time = utc_time.astimezone(bali_tz)
        print(f"Event UTC time: {utc_time}")
        print(f"Event Bali time: {local_time}")

        # Проверяем попадает ли в границы
        in_range = start_utc <= utc_time < end_utc
        print(f"In search range: {in_range}")
