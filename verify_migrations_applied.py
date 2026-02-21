#!/usr/bin/env python3
"""Проверка применения миграций 030 и 031"""

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

print("=" * 70)
print("VERIFICATION: Migrations 030 and 031")
print("=" * 70)
print()

with engine.connect() as conn:
    # Проверка категорий в task_places (таблица tasks удалена)
    print("1. Checking categories in 'task_places' table:")
    result = conn.execute(
        text("""
        SELECT category, COUNT(*) as count
        FROM task_places
        GROUP BY category
        ORDER BY category
    """)
    )

    places_by_category = {}
    for row in result:
        places_by_category[row[0]] = row[1]
        print(f"   - {row[0]}: {row[1]} places")

    print()

    # Проверка старых категорий (не должно быть)
    print("2. Checking for old categories in task_places (should be 0):")
    result = conn.execute(text("SELECT COUNT(*) FROM task_places WHERE category IN ('body', 'spirit')"))
    old_places = result.scalar()

    print(f"   - Old 'body'/'spirit' in task_places: {old_places}")

    print()
    print("=" * 70)

    success = True
    issues = []

    if "body" in places_by_category or "spirit" in places_by_category:
        success = False
        issues.append("Old categories still exist in task_places")

    if "food" not in places_by_category:
        success = False
        issues.append("Food category not found in task_places")

    if "health" not in places_by_category:
        success = False
        issues.append("Health category not found in task_places")

    if "places" not in places_by_category:
        success = False
        issues.append("Places category not found in task_places")

    if success:
        print("SUCCESS: All migrations applied correctly!")
        print()
        print("Summary (task_places):")
        print(f"  - Food: {places_by_category.get('food', 0)}")
        print(f"  - Health: {places_by_category.get('health', 0)}")
        print(f"  - Places: {places_by_category.get('places', 0)}")
    else:
        print("ERROR: Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)

    print("=" * 70)
