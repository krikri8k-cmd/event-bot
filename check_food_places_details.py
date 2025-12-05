#!/usr/bin/env python3
"""Проверка деталей food мест"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

env_path = Path(__file__).parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL not found")
    sys.exit(1)

engine = create_engine(db_url, future=True)

with engine.connect() as conn:
    # Все food места
    result = conn.execute(
        text("""
        SELECT region, task_type, COUNT(*) as count
        FROM task_places
        WHERE category = 'food' AND is_active = true
        GROUP BY region, task_type
        ORDER BY region, task_type
    """)
    )

    print("=" * 70)
    print("FOOD PLACES BY REGION AND TASK_TYPE")
    print("=" * 70)

    for row in result:
        print(f"Region: {row[0]}, Task Type: {row[1]}, Count: {row[2]}")

    print("=" * 70)

    # Проверка для Бали
    result = conn.execute(
        text("""
        SELECT COUNT(*) 
        FROM task_places
        WHERE category = 'food' 
          AND is_active = true
          AND region = 'bali'
          AND task_type = 'island'
    """)
    )

    bali_island_count = result.fetchone()[0]
    print(f"\nFood places для Бали с task_type='island': {bali_island_count}")

    # Проверка для Бали с task_type='urban'
    result = conn.execute(
        text("""
        SELECT COUNT(*) 
        FROM task_places
        WHERE category = 'food' 
          AND is_active = true
          AND region = 'bali'
          AND task_type = 'urban'
    """)
    )

    bali_urban_count = result.fetchone()[0]
    print(f"Food places для Бали с task_type='urban': {bali_urban_count}")
