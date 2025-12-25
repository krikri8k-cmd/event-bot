#!/usr/bin/env python3
"""
Скрипт для запуска миграции 034: добавление полей места в user_tasks
"""

import sys

# Устанавливаем UTF-8 для вывода
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.append(".")

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

print("🚀 Запуск миграции 034...")

try:
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.begin() as conn:
        migration_script_path = "migrations/034_add_place_fields_to_user_tasks.sql"
        with open(migration_script_path, encoding="utf-8") as f:
            sql_script = f.read()
        conn.execute(text(sql_script))
    print("✅ Миграция 034 выполнена успешно!")
except Exception as e:
    print(f"❌ Ошибка при выполнении миграции 034: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
