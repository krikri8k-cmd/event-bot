#!/usr/bin/env python3
"""Проверка статуса подсказок"""

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
            COUNT(*) as total,
            COUNT(task_hint) as with_hint,
            COUNT(*) - COUNT(task_hint) as without_hint
        FROM task_places
    """)
    )

    row = result.fetchone()
    print("=" * 50)
    print("STATUS: Task hints")
    print("=" * 50)
    print(f"Total places: {row[0]}")
    print(f"With hints: {row[1]}")
    print(f"Without hints: {row[2]}")
    print("=" * 50)
