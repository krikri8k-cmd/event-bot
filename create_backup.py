#!/usr/bin/env python3
"""Создание резервной копии проекта"""

import os
import zipfile
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent
backup_dir = project_root.parent
timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
archive_name = backup_dir / f"event-bot-backup-{timestamp}.zip"

print("📦 Создание архива проекта...")
print(f"📁 Исходная папка: {project_root}")

# Файлы и папки для исключения
exclude = {
    "__pycache__",
    ".git",
    "venv",
    "env",
    ".venv",
    "node_modules",
    ".pytest_cache",
    "*.pyc",
    "*.pyo",
    "*.db",
    "*.log",
    ".env",
    "event_bot.db",
}

exclude_patterns = {".git", "venv", "__pycache__", "node_modules", ".pytest_cache"}


def should_exclude(path: Path) -> bool:
    """Проверяет, нужно ли исключить путь"""
    parts = path.parts
    # Исключаем папки
    for part in parts:
        if part in exclude_patterns:
            return True
        if part.startswith("."):
            return True
    # Исключаем файлы
    if path.suffix in [".pyc", ".pyo", ".db", ".log"]:
        return True
    return False


files_count = 0
with zipfile.ZipFile(archive_name, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(project_root):
        # Фильтруем директории для исключения
        dirs[:] = [d for d in dirs if not should_exclude(Path(root) / d)]

        for file in files:
            file_path = Path(root) / file
            if should_exclude(file_path):
                continue

            # Относительный путь в архиве
            arcname = file_path.relative_to(project_root)
            zipf.write(file_path, arcname)
            files_count += 1

file_size_mb = archive_name.stat().st_size / (1024 * 1024)

print("\n✅ Архив успешно создан!")
print(f"📦 Имя файла: {archive_name.name}")
print(f"📁 Полный путь: {archive_name}")
print(f"📊 Размер: {file_size_mb:.2f} MB")
print(f"📄 Файлов в архиве: {files_count}")
print(f"\n💾 Архив находится в: {backup_dir}")
