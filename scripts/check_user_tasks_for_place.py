#!/usr/bin/env python3
"""
Проверка UserTask для конкретного места
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
    # Ищем UserTask для места "Monsieur Spoon" (ID 24)
    result = conn.execute(
        text("""
            SELECT ut.id, ut.user_id, ut.place_id, ut.place_name, 
                   ut.frozen_title, ut.frozen_description, ut.frozen_task_hint,
                   tp.name as place_name_in_db, tp.task_hint as place_task_hint
            FROM user_tasks ut
            LEFT JOIN task_places tp ON ut.place_id = tp.id
            WHERE ut.place_id = 24 OR ut.place_name ILIKE '%Monsieur Spoon%'
            AND ut.status = 'active'
        """)
    )
    rows = result.fetchall()

    if rows:
        print(f"Found {len(rows)} active UserTask(s) for Monsieur Spoon:")
        print()

        for row in rows:
            print(f"UserTask ID: {row[0]}")
            print(f"User ID: {row[1]}")
            print(f"place_id: {row[2]}")
            print(f"place_name in UserTask: {row[3]}")
            print(f"frozen_title: {row[4]}")
            print(f"frozen_description: {row[5]}")
            print(f"frozen_task_hint: {row[6]}")
            print(f"Place name in DB: {row[7]}")
            print(f"Place task_hint in DB: {row[8]}")
            print()

            # Проверяем на "Margaret"
            frozen_text = (row[4] or "") + " " + (row[5] or "") + " " + (row[6] or "")
            if "Margaret" in frozen_text or "margaret" in frozen_text.lower() or "bistro" in frozen_text.lower():
                print("[WARN] Frozen data contains 'Margaret' or 'bistro'!")
                print("This is the problem - frozen data has wrong text.")
                print()
                print("SQL to fix (clear frozen data to use current place.task_hint):")
                print(
                    f"UPDATE user_tasks SET frozen_title = NULL, frozen_description = NULL, frozen_task_hint = NULL WHERE id = {row[0]};"
                )
                print()
    else:
        print("No active UserTask found for Monsieur Spoon")
