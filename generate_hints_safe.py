#!/usr/bin/env python3
"""Безопасная генерация подсказок (без эмодзи в выводе)"""

import os
import sys
from pathlib import Path

# Устанавливаем UTF-8 для stdout
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        # Для старых версий Python
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")

from dotenv import load_dotenv

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import TaskPlace, get_session, init_engine  # noqa: E402
from tasks.ai_hints_generator import generate_hint_for_place  # noqa: E402

env_path = project_root / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL not found")
    sys.exit(1)

init_engine(db_url)

print("=" * 70)
print("AI: Generating hints for places without task_hint")
print("=" * 70)
print()

with get_session() as session:
    places_without_hints = session.query(TaskPlace).filter(TaskPlace.task_hint.is_(None)).all()

    if not places_without_hints:
        print("OK: All places already have hints!")
        sys.exit(0)

    print(f"Found: {len(places_without_hints)} places without hints\n")

    success_count = 0
    error_count = 0

    for i, place in enumerate(places_without_hints, 1):
        print(f"[{i}/{len(places_without_hints)}] {place.name} ({place.category}/{place.place_type})...", end=" ")

        try:
            if generate_hint_for_place(place):
                session.commit()
                hint_preview = place.task_hint[:50] if place.task_hint else "N/A"
                print(f"OK: {hint_preview}...")
                success_count += 1
            else:
                print("WARN: Failed to generate")
                error_count += 1
        except Exception as e:
            print(f"ERROR: {e}")
            error_count += 1
            session.rollback()

    print()
    print("=" * 70)
    print("Results:")
    print(f"   OK: {success_count}")
    print(f"   ERROR: {error_count}")
    print(f"   Total: {len(places_without_hints)}")
    print("=" * 70)
