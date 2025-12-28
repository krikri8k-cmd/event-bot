#!/usr/bin/env python3
"""
Скрипт для проверки и исправления task_hint для конкретного места
"""

import os
import sys
from pathlib import Path

# Устанавливаем UTF-8 для вывода в Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # Перенаправляем stdout с правильной кодировкой
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import TaskPlace, get_session, init_engine
from tasks.ai_hints_generator import generate_hint_for_place

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
print("CHECKING AND FIXING task_hint FOR SPECIFIC PLACES")
print("=" * 60)
print()

with get_session() as session:
    # Ищем место "Monsieur Spoon"
    place = session.query(TaskPlace).filter(TaskPlace.name.ilike("%Monsieur Spoon%")).first()

    if not place:
        print("[ERROR] Place 'Monsieur Spoon' not found")
        sys.exit(1)

    place_name_safe = place.name.encode("ascii", "replace").decode("ascii")
    print(f"Found place: {place_name_safe} (ID: {place.id})")
    if place.task_hint:
        # Проверяем содержимое
        task_hint_has_margaret = "margaret" in place.task_hint.lower() or "bistro" in place.task_hint.lower()
        if task_hint_has_margaret:
            print("[WARN] task_hint contains 'margaret' or 'bistro' - likely wrong place mentioned")
        print(f"Current task_hint length: {len(place.task_hint)} chars")
    else:
        print("Current task_hint: None")
    print()

    # Проверяем, упоминает ли task_hint другие места
    if place.task_hint:
        # Ищем все места, которые могут быть упомянуты
        all_places = session.query(TaskPlace).filter(TaskPlace.id != place.id, TaskPlace.name.isnot(None)).all()

        place_name_lower = place.name.lower()
        task_hint_lower = place.task_hint.lower()

        found_issues = []
        task_hint_has_margaret = False

        # Специальная проверка для "margaret" и "bistro"
        if "margaret" in task_hint_lower or "bistro" in task_hint_lower:
            # Ищем место "Margaret Bistro"
            margaret_place = session.query(TaskPlace).filter(TaskPlace.name.ilike("%Margaret%")).first()
            if margaret_place:
                found_issues.append(margaret_place.name)
                task_hint_has_margaret = True

        for other_place in all_places:
            other_name = other_place.name.lower()

            # Проверяем полное название
            if other_name in task_hint_lower and other_name != place_name_lower:
                if other_place.name not in found_issues:
                    found_issues.append(other_place.name)

            # Проверяем отдельные слова (длиннее 4 символов)
            other_words = [w for w in other_name.split() if len(w) >= 5]
            place_words = [w for w in place_name_lower.split() if len(w) >= 5]

            for word in other_words:
                if word in task_hint_lower and word not in place_words:
                    # Проверяем контекст
                    word_index = task_hint_lower.find(word)
                    if word_index >= 0:
                        # Берем больше контекста
                        context_start = max(0, word_index - 30)
                        context_end = min(len(task_hint_lower), word_index + len(word) + 30)
                        context = task_hint_lower[context_start:context_end]

                        # Если в контексте есть другие слова из названия
                        other_words_in_context = [w for w in other_words if w in context]
                        if len(other_words_in_context) >= 1 and other_place.name not in found_issues:
                            found_issues.append(other_place.name)

        if found_issues or task_hint_has_margaret:
            issues_list = ", ".join([name.encode("ascii", "replace").decode("ascii") for name in found_issues])
            if issues_list:
                print(f"[WARN] task_hint mentions other places: {issues_list}")
            if task_hint_has_margaret:
                print("[WARN] task_hint contains 'margaret' or 'bistro' - fixing...")
            print()
            print("Fixing by clearing task_hint and regenerating...")
            print()

            # Очищаем task_hint
            place.task_hint = None
            session.commit()

            # Генерируем новую подсказку
            if generate_hint_for_place(place):
                session.commit()
                print(f"[OK] New task_hint generated (length: {len(place.task_hint)} chars)")
            else:
                print("[ERROR] Failed to generate new task_hint")
        else:
            print("[OK] No issues found in task_hint")
    else:
        print("[INFO] No task_hint, generating new one...")
        if generate_hint_for_place(place):
            session.commit()
            print(f"[OK] New task_hint generated (length: {len(place.task_hint)} chars)")
        else:
            print("[ERROR] Failed to generate task_hint")

print()
print("=" * 60)
print("DONE")
print("=" * 60)
