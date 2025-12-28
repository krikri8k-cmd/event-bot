#!/usr/bin/env python3
"""
Универсальный скрипт для поиска и исправления всех проблемных task_hint
"""

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import TaskPlace, get_session, init_engine
from tasks.ai_hints_generator import generate_hint_for_place

env_path = Path(__file__).parent.parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("[ERROR] DATABASE_URL not found")
    sys.exit(1)

init_engine(db_url)

print("=" * 60)
print("FIXING ALL WRONG task_hint")
print("=" * 60)
print()

with get_session() as session:
    # Получаем все места с task_hint
    places = session.query(TaskPlace).filter(TaskPlace.task_hint.isnot(None)).all()

    print(f"Total places with task_hint: {len(places)}")
    print()

    issues = []

    for place in places:
        place_name_lower = place.name.lower()
        task_hint_lower = place.task_hint.lower()

        # Получаем все другие места
        other_places = session.query(TaskPlace).filter(TaskPlace.id != place.id, TaskPlace.name.isnot(None)).all()

        found_issue = False

        for other_place in other_places:
            other_name = other_place.name.lower()

            # Пропускаем короткие названия
            if len(other_name) < 5:
                continue

            # Проверяем полное название
            if other_name in task_hint_lower and other_name != place_name_lower:
                if other_name not in place_name_lower:
                    issues.append(place)
                    found_issue = True
                    break

            # Проверяем отдельные слова
            other_words = [w for w in other_name.split() if len(w) >= 5]
            place_words = [w for w in place_name_lower.split() if len(w) >= 5]

            for word in other_words:
                if word in task_hint_lower and word not in place_words:
                    # Проверяем контекст
                    word_index = task_hint_lower.find(word)
                    if word_index >= 0:
                        context_start = max(0, word_index - 30)
                        context_end = min(len(task_hint_lower), word_index + len(word) + 30)
                        context = task_hint_lower[context_start:context_end]

                        other_words_in_context = [w for w in other_words if w in context]
                        if len(other_words_in_context) >= 1:
                            issues.append(place)
                            found_issue = True
                            break

            if found_issue:
                break

    if issues:
        print(f"[WARN] Found {len(issues)} places with problematic task_hint:")
        print()

        fixed_count = 0
        failed_count = 0

        for place in issues:
            place_name_safe = place.name.encode("ascii", "replace").decode("ascii")
            print(f"Fixing place ID {place.id}: {place_name_safe}")

            # Очищаем task_hint
            old_hint = place.task_hint
            place.task_hint = None
            session.commit()

            # Генерируем новую подсказку
            if generate_hint_for_place(place):
                session.commit()
                print(f"  [OK] Regenerated (old length: {len(old_hint)}, new length: {len(place.task_hint)})")
                fixed_count += 1
            else:
                print("  [ERROR] Failed to generate new task_hint")
                failed_count += 1
            print()

        print("=" * 60)
        print(f"SUMMARY: Fixed {fixed_count}, Failed {failed_count}")
        print("=" * 60)
    else:
        print("[OK] No problematic task_hint found!")
        print()
