#!/usr/bin/env python3
"""Проверка наличия столбца task_hint в таблице task_places"""

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

print("Checking task_hint column in task_places table...")
print()

with engine.connect() as conn:
    # Проверяем наличие столбца
    result = conn.execute(
        text("""
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'task_places' AND column_name = 'task_hint'
    """)
    )

    row = result.fetchone()

    if row:
        print("SUCCESS: Column task_hint exists!")
        print(f"   Type: {row[1]}")
        print(f"   Length: {row[2] if row[2] else 'unlimited'}")
        print(f"   Nullable: {row[3]}")
    else:
        print("ERROR: Column task_hint NOT found!")
        print()
        print("Need to apply migration:")
        print("   migrations/029_add_task_hint_to_task_places.sql")
        sys.exit(1)

    # Проверяем все столбцы таблицы
    print()
    print("All columns in task_places table:")
    result = conn.execute(
        text("""
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'task_places'
        ORDER BY ordinal_position
    """)
    )

    for row in result:
        length = f"({row[2]})" if row[2] else ""
        nullable = "NULL" if row[3] == "YES" else "NOT NULL"
        print(f"   - {row[0]}: {row[1]}{length} {nullable}")

    # Проверяем количество мест с подсказками и без
    result = conn.execute(
        text("""
        SELECT 
            COUNT(*) as total,
            COUNT(task_hint) as with_hint,
            COUNT(*) - COUNT(task_hint) as without_hint
        FROM task_places
    """)
    )

    row = result.fetchone()
    if row:
        print()
        print("Statistics:")
        print(f"   Total places: {row[0]}")
        print(f"   With hints: {row[1]}")
        print(f"   Without hints: {row[2]}")
