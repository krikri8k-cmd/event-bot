import os
import zipfile
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent
backup_dir = project_root.parent
timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
archive_name = backup_dir / f"event-bot-backup-{timestamp}.zip"

print("Создание архива...")
print(f"Исходная папка: {project_root}")

exclude_dirs = {".git", "venv", "__pycache__", "node_modules", ".pytest_cache"}
exclude_files = {".pyc", ".pyo", ".db", ".log"}

files_count = 0
total_size = 0

with zipfile.ZipFile(archive_name, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(project_root):
        # Исключаем директории
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".")]

        for file in files:
            file_path = Path(root) / file

            # Исключаем файлы
            if file_path.suffix in exclude_files:
                continue
            if file_path.name.startswith("."):
                continue

            # Исключаем сам скрипт бэкапа
            if file_path.name in ["backup.py", "create_backup.py", "make_backup.ps1"]:
                continue

            try:
                arcname = file_path.relative_to(project_root)
                zipf.write(file_path, arcname)
                files_count += 1
                total_size += file_path.stat().st_size
            except Exception as e:
                print(f"Пропущен файл {file_path}: {e}")

file_size_mb = archive_name.stat().st_size / (1024 * 1024)

print("\n✅ Архив успешно создан!")
print(f"📦 Имя файла: {archive_name.name}")
print(f"📁 Полный путь: {archive_name}")
print(f"📊 Размер: {file_size_mb:.2f} MB")
print(f"📄 Файлов в архиве: {files_count}")
print(f"\n💾 Архив находится в: {backup_dir}")

# Сохраняем информацию в файл
info_file = project_root / "BACKUP_INFO.txt"
with open(info_file, "w", encoding="utf-8") as f:
    f.write(f"Архив создан: {archive_name}\n")
    f.write(f"Размер: {file_size_mb:.2f} MB\n")
    f.write(f"Файлов: {files_count}\n")
    f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

print(f"\n📝 Информация сохранена в: {info_file}")
