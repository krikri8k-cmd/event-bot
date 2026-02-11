#!/usr/bin/env python3
"""
Скрипт для запуска миграции 040: добавление title_en, description_en, location_name_en в events.
"""

import sys

sys.path.insert(0, ".")

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

print("Migration 040: adding title_en, description_en, location_name_en to events...")

try:
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()
    with engine.begin() as conn:
        with open("migrations/040_add_events_title_description_location_en.sql", encoding="utf-8") as f:
            sql_script = f.read()
        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
        statements = [
            s
            for s in statements
            if s and not all(line.strip().startswith("--") for line in s.splitlines() if line.strip())
        ]
        for idx, stmt in enumerate(statements, 1):
            if stmt:
                print(f"  [{idx}/{len(statements)}] Executing...")
                conn.execute(text(stmt))
    print("OK Migration 040 done.")
except Exception as e:
    print("Error:", e)
    import traceback

    traceback.print_exc()
    sys.exit(1)
