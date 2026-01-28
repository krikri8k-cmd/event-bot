#!/usr/bin/env python3
"""
Скрипт для запуска миграции 039: добавление поля language_code в таблицу users
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

print("🚀 Запуск миграции 039: добавление language_code в users...")

try:
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.begin() as conn:
        migration_script_path = "migrations/039_add_language_code_to_users.sql"
        with open(migration_script_path, encoding="utf-8") as f:
            sql_script = f.read()

        # Разбиваем на отдельные команды
        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
        # Фильтруем комментарии
        statements = [
            s
            for s in statements
            if s and not all(line.strip().startswith("--") for line in s.splitlines() if line.strip())
        ]

        for idx, stmt in enumerate(statements, 1):
            if stmt:
                print(f"  [{idx}/{len(statements)}] Выполняю...")
                conn.execute(text(stmt))

    print("✅ Миграция 039 выполнена успешно!")
    print("   Поле language_code добавлено в таблицу users")
except Exception as e:
    print(f"❌ Ошибка при выполнении миграции 039: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
