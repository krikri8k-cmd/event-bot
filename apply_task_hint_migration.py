#!/usr/bin/env python3
"""Применение миграции для добавления столбца task_hint"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

env_path = Path(__file__).parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL не найден")
    sys.exit(1)

engine = create_engine(db_url, future=True)

print("🔧 Применение миграции: добавление столбца task_hint\n")

migration_sql = """
ALTER TABLE task_places
ADD COLUMN IF NOT EXISTS task_hint VARCHAR(200);

COMMENT ON COLUMN task_places.task_hint IS 'Короткое задание/подсказка для места (1 предложение)';
"""

try:
    with engine.begin() as conn:
        print("📝 Выполняю SQL...")
        conn.execute(text(migration_sql))
        print("✅ Миграция применена успешно!")

        # Проверяем результат
        result = conn.execute(
            text("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'task_places' AND column_name = 'task_hint'
        """)
        )

        row = result.fetchone()
        if row:
            print("\n✅ Столбец task_hint создан:")
            print(f"   Тип: {row[1]}")
            print(f"   Длина: {row[2]}")
        else:
            print("\n⚠️ Столбец не найден после миграции")

except Exception as e:
    print(f"❌ Ошибка при применении миграции: {e}")
    sys.exit(1)
