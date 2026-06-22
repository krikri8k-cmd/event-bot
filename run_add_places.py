#!/usr/bin/env python3
"""DEPRECATED: food_places_example.txt — зеркало production task_places, не для импорта."""

import sys

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")

print("DEPRECATED: run_add_places.py больше не импортирует места из food_places_example.txt.")
print("  Канон — production task_places в Postgres (@MyGuide).")
print("  Обновить файлы из БД:")
print("    railway run -e production python scripts/export_task_places_to_example_files.py")
print("  Правки мест — Railway UI или scripts/deactivate_task_place.py")
sys.exit(1)
