import os
import zipfile
from datetime import datetime
from pathlib import Path

root = Path(r"c:\Dev\event-bot")
backup_dir = Path(r"c:\Dev")
timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
archive = backup_dir / f"event-bot-backup-{timestamp}.zip"

z = zipfile.ZipFile(archive, "w")

count = 0
for root_dir, dirs, files in os.walk(root):
    # Пропускаем служебные папки
    dirs[:] = [d for d in dirs if d not in [".git", "venv", "__pycache__", "node_modules"]]

    for file in files:
        if file.endswith((".pyc", ".db", ".log")):
            continue
        if file.startswith("."):
            continue

        file_path = Path(root_dir) / file
        try:
            arcname = file_path.relative_to(root)
            z.write(file_path, arcname)
            count += 1
        except Exception:
            pass

z.close()
size_mb = archive.stat().st_size / (1024 * 1024)

# Сохраняем информацию
info = root / "ARCHIVE_INFO.txt"
with open(info, "w", encoding="utf-8") as f:
    f.write(f"Архив создан: {archive}\n")
    f.write(f"Размер: {size_mb:.2f} MB\n")
    f.write(f"Файлов: {count}\n")

print(f"ГОТОВО! Архив: {archive}")
