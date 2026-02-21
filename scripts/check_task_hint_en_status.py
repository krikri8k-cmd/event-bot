#!/usr/bin/env python3
"""Проверка: сколько записей task_places без перевода task_hint_en. Для ручной проверки и отчёта."""

import os
import sys

# корень проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.backfill_task_places_translation import _count_places_needing_hint_translation


def main():
    n = _count_places_needing_hint_translation()
    print(f"Мест без перевода (task_hint есть, task_hint_en пусто): {n}")
    if n == 0:
        print("В базе не осталось пустых task_hint_en.")
    sys.exit(0)


if __name__ == "__main__":
    main()
