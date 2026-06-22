"""Защита task_places от случайной перезаливки из файлов (production — канон)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

EXAMPLE_MIRROR_FILES = frozenset(
    {
        "food_places_example.txt",
        "health_places_example.txt",
        "entertainment_places_example.txt",
        "interesting_places_example.txt",
    }
)

MIRROR_HEADER = """# ЗЕРКАЛО production task_places — НЕ импортировать в БД.
# Бот (@MyGuide) читает только Postgres. Направление: таблица → файлы.
# Обновить из БД: railway run -e production python scripts/export_task_places_to_example_files.py
# Проверка:       railway run -e production python scripts/compare_task_places_with_files.py
# Правки мест:    Railway UI или точечный SQL (не add_places_from_simple_file.py для этих файлов).
"""


def is_example_mirror_file(file_path: str | Path) -> bool:
    name = Path(file_path).name.lower()
    return name in EXAMPLE_MIRROR_FILES or name.endswith("_places_example.txt")


def is_production_database_context() -> bool:
    for key in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENV"):
        if (os.getenv(key) or "").strip().lower() == "production":
            return True
    return (os.getenv("TASK_PLACES_DB_TIER") or "").strip().lower() == "production"


def _exit(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def refuse_example_file_import(file_path: str | Path) -> None:
    if not is_example_mirror_file(file_path):
        return
    _exit(
        f"ERROR: {Path(file_path).name} — зеркало production task_places, не источник для импорта.\n"
        "  Экспорт из БД: scripts/export_task_places_to_example_files.py\n"
        "  Правки мест: Railway UI или точечный UPDATE.\n"
        "  Импорт из txt в prod намеренно заблокирован."
    )


def refuse_unsafe_task_places_import(
    file_path: str | Path,
    *,
    update_existing: bool = False,
) -> None:
    """Вызывать перед любой записью в task_places из txt/json."""
    refuse_example_file_import(file_path)

    if is_production_database_context() and os.getenv("TASK_PLACES_ALLOW_PRODUCTION_WRITE") != "1":
        _exit(
            "ERROR: запись в production task_places из файла заблокирована.\n"
            "  Канон — таблица в Railway (production). Меняйте места в UI или SQL.\n"
            "  Для осознанного импорта (только по явной просьбе):\n"
            "    TASK_PLACES_ALLOW_PRODUCTION_WRITE=1 railway run -e production python ..."
        )

    if update_existing and os.getenv("TASK_PLACES_ALLOW_UPDATE") != "1" and "--allow-update" not in sys.argv:
        _exit(
            "ERROR: режим --update заблокирован по умолчанию (защита проверенных данных).\n"
            "  Develop: TASK_PLACES_ALLOW_UPDATE=1 или флаг --allow-update\n"
            "  Production: правки только точечно в Railway."
        )


def refuse_destructive_task_places_reset(existing_count: int) -> None:
    if is_production_database_context():
        _exit("ERROR: полная перезаливка task_places в production запрещена.")

    if existing_count > 0 and os.getenv("TASK_PLACES_RESET") != "1":
        _exit(
            f"ERROR: в task_places уже {existing_count} строк — полная очистка заблокирована.\n"
            "  Для develop-сброса: TASK_PLACES_RESET=1 (осознанно)."
        )
