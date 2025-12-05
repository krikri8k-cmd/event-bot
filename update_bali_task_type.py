#!/usr/bin/env python3
"""Обновление task_type для мест Бали с urban на island"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from config import load_settings
from database import TaskPlace, get_session, init_engine

env_path = Path(__file__).parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

settings = load_settings()
init_engine(settings.database_url)

with get_session() as session:
    # Находим все места Бали с task_type='urban'
    places = session.query(TaskPlace).filter(TaskPlace.region == "bali", TaskPlace.task_type == "urban").all()

    print(f"Found {len(places)} places to update")

    # Обновляем task_type на 'island'
    for place in places:
        place.task_type = "island"

    session.commit()
    print(f"Updated {len(places)} places from urban to island")
