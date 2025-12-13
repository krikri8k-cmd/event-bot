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
    # Проверка категорий в tasks
    print("1. Checking categories in 'tasks' table:")
    result = conn.execute(
        text("""
        SELECT category, COUNT(*) as count
        FROM tasks
        GROUP BY category
        ORDER BY category
    """)
    )

    tasks_by_category = {}
    for row in result:
        tasks_by_category[row[0]] = row[1]
        print(f"   - {row[0]}: {row[1]} tasks")

    print()

    # Проверка категорий в task_places
    print("2. Checking categories in 'task_places' table:")
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
    print("3. Checking for old categories (should be 0):")
    result = conn.execute(
        text("""
        SELECT COUNT(*) FROM tasks WHERE category IN ('body', 'spirit')
        UNION ALL
        SELECT COUNT(*) FROM task_places WHERE category IN ('body', 'spirit')
    """)
    )

    old_tasks = result.fetchone()[0]
    old_places = result.fetchone()[0] if result.rowcount > 1 else 0

    print(f"   - Old 'body'/'spirit' in tasks: {old_tasks}")
    print(f"   - Old 'body'/'spirit' in task_places: {old_places}")

    print()
    print("=" * 70)

    # Итоговая проверка
    success = True
    issues = []

    if "body" in tasks_by_category or "spirit" in tasks_by_category:
        success = False
        issues.append("Old categories still exist in tasks")

    if "body" in places_by_category or "spirit" in places_by_category:
        success = False
        issues.append("Old categories still exist in task_places")

    if "food" not in tasks_by_category:
        success = False
        issues.append("Food category not found in tasks")
    elif tasks_by_category["food"] < 15:
        success = False
        issues.append(f"Food category has only {tasks_by_category['food']} tasks, expected 15")

    if "health" not in tasks_by_category:
        success = False
        issues.append("Health category not found in tasks")

    if "places" not in tasks_by_category:
        success = False
        issues.append("Places category not found in tasks")

    if success:
        print("SUCCESS: All migrations applied correctly!")
        print()
        print("Summary:")
        print(f"  - Health tasks: {tasks_by_category.get('health', 0)}")
        print(f"  - Places tasks: {tasks_by_category.get('places', 0)}")
        print(f"  - Food tasks: {tasks_by_category.get('food', 0)}")
    else:
        print("ERROR: Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)

    print("=" * 70)
