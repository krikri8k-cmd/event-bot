#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Проверяем статус события
    result = conn.execute(
        text("""
        SELECT status, title
        FROM events 
        WHERE source = 'user' 
        AND starts_at >= '2025-10-01 16:00:00' 
        AND starts_at < '2025-10-02 16:00:00'
    """)
    )

    for row in result:
        print(f"Event status: {row[0]}")
        print(f"Event title: {row[1]}")

    # Проверяем все возможные статусы
    result = conn.execute(
        text("""
        SELECT DISTINCT status, COUNT(*)
        FROM events 
        WHERE source = 'user'
        GROUP BY status
    """)
    )

    print("\nAll user event statuses:")
    for row in result:
        print(f"Status: {row[0]}, Count: {row[1]}")
