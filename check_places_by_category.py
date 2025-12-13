#!/usr/bin/env python3
"""Проверка мест по категориям"""

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
    result = conn.execute(
        text("""
        SELECT 
            category,
            COUNT(*) as total,
            COUNT(CASE WHEN task_hint IS NOT NULL THEN 1 END) as with_hint
        FROM task_places
        GROUP BY category
        ORDER BY category
    """)
    )

    print("=" * 70)
    print("PLACES BY CATEGORY")
    print("=" * 70)

    for row in result:
        print(f"{row[0]}: {row[1]} places ({row[2]} with hints)")

    print("=" * 70)

    # Проверка наличия food мест
    result = conn.execute(
        text("""
        SELECT COUNT(*) FROM task_places WHERE category = 'food'
    """)
    )

    food_count = result.fetchone()[0]
    print(f"\nFood places: {food_count}")
    if food_count == 0:
        print("WARNING: No food places found! Need to add food places.")

    print("=" * 70)
