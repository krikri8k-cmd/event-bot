#!/usr/bin/env python3
"""Обновляет task_type для health мест на Бали с urban на island"""

import os
import sys

# Устанавливаем UTF-8 для stdout
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")

from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv  # noqa: E402

env_path = project_root / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

from database import TaskPlace, get_session, init_engine  # noqa: E402

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL не найден")
    sys.exit(1)

init_engine(db_url)

with get_session() as session:
    # Находим health места на Бали с task_type='urban'
    places = (
        session.query(TaskPlace)
        .filter(
            TaskPlace.category == "health",
            TaskPlace.region == "bali",
            TaskPlace.task_type == "urban",
        )
        .all()
    )

    print(f"Найдено health мест на Бали с task_type='urban': {len(places)}")

    if not places:
        print("Нет мест для обновления")
        sys.exit(0)

    # Обновляем task_type на 'island'
    updated_count = 0
    for place in places:
        place.task_type = "island"
        updated_count += 1
        print(f"  Обновлено: {place.name} (ID: {place.id})")

    session.commit()

    print(f"\n✅ Обновлено мест: {updated_count}")
