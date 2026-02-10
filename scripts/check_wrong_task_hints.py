#!/usr/bin/env python3
"""
Скрипт для проверки task_hint на упоминание других мест
Находит места, где task_hint содержит названия других заведений
"""

import os
import sys
from pathlib import Path

# Устанавливаем UTF-8 для вывода в Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import TaskPlace, get_session, init_engine

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

# Инициализируем базу данных
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("[ERROR] DATABASE_URL not found")
    sys.exit(1)

init_engine(db_url)

print("=" * 60)
print("CHECKING task_hint FOR MENTIONS OF OTHER PLACES")
print("=" * 60)
print()

with get_session() as session:
    # Получаем все места с task_hint
    places = session.query(TaskPlace).filter(TaskPlace.task_hint.isnot(None)).all()

    print(f"Total places with task_hint: {len(places)}")
    print()

    issues = []

    for place in places:
        place_name = place.name.lower()
        task_hint = place.task_hint.lower()

        # Получаем все другие места для сравнения
        other_places = session.query(TaskPlace).filter(TaskPlace.id != place.id, TaskPlace.name.isnot(None)).all()

        # Проверяем, упоминает ли task_hint другие места
        for other_place in other_places:
            other_name = other_place.name.lower()

            # Пропускаем слишком короткие названия (могут быть общими словами)
            if len(other_name) < 5:
                continue

            # Проверяем, есть ли название другого места в task_hint
            # Но не текущего места
            if other_name in task_hint and other_name != place_name:
                # Дополнительная проверка: не является ли это частью текущего названия
                if other_name not in place_name:
                    issues.append(
                        {
                            "place_id": place.id,
                            "place_name": place.name,
                            "task_hint": place.task_hint,
                            "mentioned_place": other_place.name,
                            "mentioned_place_id": other_place.id,
                        }
                    )
                    break  # Нашли проблему, переходим к следующему месту

    if issues:
        print(f"[WARN] Found {len(issues)} places with problematic task_hint:")
        print()

        for issue in issues:
            print(f"Place ID {issue['place_id']}: {issue['place_name']}")
            print(f"   task_hint: {issue['task_hint']}")
            print(f"   [WARN] Mentions other place: {issue['mentioned_place']} (ID {issue['mentioned_place_id']})")
            print()

        print("=" * 60)
        print("RECOMMENDATIONS:")
        print("=" * 60)
        print("1. Regenerate task_hint for these places")
        print("2. Check manually and fix")
        print("3. Improve GPT prompt (already done in code)")
        print()

        # SQL для исправления (очистить task_hint для проблемных мест)
        print("SQL to clear task_hint for problematic places:")
        print()
        place_ids = [str(issue["place_id"]) for issue in issues]
        print(f"UPDATE task_places SET task_hint = NULL WHERE id IN ({', '.join(place_ids)});")
        print()
    else:
        print("[OK] No problematic task_hint found!")
        print()
