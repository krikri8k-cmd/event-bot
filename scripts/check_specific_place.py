#!/usr/bin/env python3
"""
Проверка конкретного места через SQL
"""

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

env_path = Path(__file__).parent.parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("[ERROR] DATABASE_URL not found")
    sys.exit(1)

engine = create_engine(db_url, future=True)

with engine.connect() as conn:
    result = conn.execute(text("SELECT id, name, task_hint FROM task_places WHERE name ILIKE '%Monsieur Spoon%'"))
    row = result.fetchone()

    if row:
        print(f"ID: {row[0]}")
        print(f"Name: {row[1]}")
        print(f"task_hint: {row[2]}")

        # Проверяем на "Margaret"
        if row[2] and ("Margaret" in row[2] or "margaret" in row[2] or "bistro" in row[2].lower()):
            print("\n[WARN] task_hint contains 'Margaret' or 'bistro'!")
            print("This is a problem - fixing...")

            # Очищаем task_hint
            conn.execute(text("UPDATE task_places SET task_hint = NULL WHERE id = :id"), {"id": row[0]})
            conn.commit()
            print("[OK] task_hint cleared. Please regenerate it.")
    else:
        print("Place not found")
