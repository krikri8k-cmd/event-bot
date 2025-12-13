#!/usr/bin/env python3
"""
Скрипт для массовой генерации подсказок (task_hint) для мест без подсказок
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import TaskPlace, get_session, init_engine  # noqa: E402
from tasks.ai_hints_generator import generate_hint_for_place  # noqa: E402

# Загружаем переменные окружения
env_path = project_root / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL не найден в переменных окружения")
    sys.exit(1)

init_engine(db_url)

print("AI: Генерация подсказок для мест без task_hint\n")

with get_session() as session:
    # Получаем все места без подсказок
    places_without_hints = session.query(TaskPlace).filter(TaskPlace.task_hint.is_(None)).all()

    if not places_without_hints:
        print("OK: Все места уже имеют подсказки!")
        sys.exit(0)

    print(f"Found: Найдено мест без подсказок: {len(places_without_hints)}\n")

    success_count = 0
    error_count = 0

    for i, place in enumerate(places_without_hints, 1):
        print(f"[{i}/{len(places_without_hints)}] {place.name} ({place.category}/{place.place_type})...", end=" ")

        try:
            if generate_hint_for_place(place):
                session.commit()
                print(f"OK: {place.task_hint[:50]}...")
                success_count += 1
            else:
                print("WARN: Не удалось сгенерировать")
                error_count += 1
        except Exception as e:
            print(f"ERROR: Ошибка: {e}")
            error_count += 1
            session.rollback()

    print("\nResults:")
    print(f"   OK: Успешно: {success_count}")
    print(f"   ERROR: Ошибок: {error_count}")
    print(f"   Total: Всего обработано: {len(places_without_hints)}")
