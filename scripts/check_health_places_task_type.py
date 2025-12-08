#!/usr/bin/env python3
"""Проверяет task_type для health мест на Бали"""

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
    # Проверяем health места на Бали
    places = (
        session.query(TaskPlace)
        .filter(
            TaskPlace.category == "health",
            TaskPlace.region == "bali",
        )
        .all()
    )

    print(f"Найдено health мест на Бали: {len(places)}")
    print("\nРаспределение по task_type:")

    urban_count = 0
    island_count = 0

    for place in places:
        if place.task_type == "urban":
            urban_count += 1
        elif place.task_type == "island":
            island_count += 1

    print(f"  urban: {urban_count}")
    print(f"  island: {island_count}")

    if urban_count > 0:
        print(f"\n⚠️  Найдено {urban_count} мест с task_type='urban' (должно быть 'island')")
        print("Примеры мест с urban:")
        for place in places[:5]:
            if place.task_type == "urban":
                print(f"  - {place.name} (ID: {place.id}, task_type: {place.task_type})")
