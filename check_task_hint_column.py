#!/usr/bin/env python3
"""Проверка наличия столбца task_hint в таблице task_places"""

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

print("🔍 Проверка столбца task_hint в таблице task_places\n")

with engine.connect() as conn:
    # Проверяем наличие столбца
    result = conn.execute(
        text("""
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'task_places' AND column_name = 'task_hint'
    """)
    )

    row = result.fetchone()

    if row:
        print("✅ Столбец task_hint существует!")
        print(f"   Тип: {row[1]}")
        print(f"   Длина: {row[2] if row[2] else 'неограниченная'}")
        print(f"   Nullable: {row[3]}")
    else:
        print("❌ Столбец task_hint НЕ найден!")
        print("\n   Нужно применить миграцию:")
        print("   python scripts/apply_migration.py migrations/029_add_task_hint_to_task_places.sql")
        sys.exit(1)

    # Проверяем количество мест с подсказками и без
    result = conn.execute(
        text("""
        SELECT 
            COUNT(*) as total,
            COUNT(task_hint) as with_hint,
            COUNT(*) - COUNT(task_hint) as without_hint
        FROM task_places
    """)
    )

    row = result.fetchone()
    if row:
        print("\n📊 Статистика:")
        print(f"   Всего мест: {row[0]}")
        print(f"   С подсказками: {row[1]}")
        print(f"   Без подсказок: {row[2]}")
