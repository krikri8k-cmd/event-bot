#!/usr/bin/env python3
"""Прямое применение миграции 029"""

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

print("=" * 60)
print("ПРИМЕНЕНИЕ МИГРАЦИИ 029: Добавление task_hint")
print("=" * 60)

# Загружаем переменные окружения
env_path = Path(__file__).parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Загружен файл: {env_path}")
else:
    print(f"❌ Файл не найден: {env_path}")
    sys.exit(1)

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL не найден")
    sys.exit(1)

print(f"🔗 Подключение к БД: {db_url[:50]}...")

try:
    engine = create_engine(db_url, future=True, echo=False)

    # Проверяем наличие столбца ДО миграции
    print("\n🔍 Проверка ДО миграции...")
    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'task_places' AND column_name = 'task_hint'
        """)
        )
        exists_before = result.fetchone()
        if exists_before:
            print("⚠️ Столбец task_hint УЖЕ существует!")
        else:
            print("✅ Столбец task_hint НЕ найден - применяю миграцию...")

    # Применяем миграцию
    if not exists_before:
        print("\n📝 Применение миграции...")
        with engine.begin() as conn:
            # 1. Добавляем столбец
            print("   [1/3] Добавляю столбец task_hint...")
            conn.execute(
                text("""
                ALTER TABLE task_places
                ADD COLUMN IF NOT EXISTS task_hint VARCHAR(200)
            """)
            )

            # 2. Добавляем комментарий
            print("   [2/3] Добавляю комментарий...")
            conn.execute(
                text("""
                COMMENT ON COLUMN task_places.task_hint IS 'Короткое задание/подсказка для места (1 предложение)'
            """)
            )

            # 3. Создаем индекс
            print("   [3/3] Создаю индекс...")
            conn.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_task_places_task_hint_null
                ON task_places(category, place_type)
                WHERE task_hint IS NULL
            """)
            )

        print("✅ Миграция применена!")

    # Проверяем наличие столбца ПОСЛЕ миграции
    print("\n🔍 Проверка ПОСЛЕ миграции...")
    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT column_name, data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'task_places' AND column_name = 'task_hint'
        """)
        )
        row = result.fetchone()
        if row:
            print("✅ Столбец создан успешно:")
            print(f"   Имя: {row[0]}")
            print(f"   Тип: {row[1]}")
            print(f"   Длина: {row[2]}")
            print(f"   Nullable: {row[3]}")
        else:
            print("❌ Столбец все еще не найден!")
            sys.exit(1)

    # Показываем статистику
    print("\n📊 Статистика по местам:")
    with engine.connect() as conn:
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
            print(f"   Всего мест: {row[0]}")
            print(f"   С подсказками: {row[1]}")
            print(f"   Без подсказок: {row[2]}")

    print("\n" + "=" * 60)
    print("✨ ГОТОВО! Столбец task_hint добавлен в таблицу task_places")
    print("=" * 60)

except Exception as e:
    print(f"\n❌ ОШИБКА: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
