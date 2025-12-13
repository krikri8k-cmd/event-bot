#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Загружаем переменные окружения
env_path = Path(__file__).parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Загружен файл: {env_path}")
else:
    print(f"⚠️ Файл не найден: {env_path}")

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL не найден в переменных окружения")
    sys.exit(1)

print(f"🔗 Подключение к БД: {db_url[:50]}...")
engine = create_engine(db_url, future=True)

# Сначала проверяем, есть ли столбец
print("\n🔍 Проверка наличия столбца task_hint...")
with engine.connect() as conn:
    result = conn.execute(
        text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'task_places' AND column_name = 'task_hint'
    """)
    )
    exists = result.fetchone()

    if exists:
        print("✅ Столбец task_hint уже существует!")
    else:
        print("❌ Столбец task_hint НЕ найден. Применяю миграцию...")

        # Применяем миграцию
        with engine.begin() as conn:
            print("📝 Добавляю столбец task_hint...")
            conn.execute(
                text("""
                ALTER TABLE task_places
                ADD COLUMN IF NOT EXISTS task_hint VARCHAR(200)
            """)
            )

            print("📝 Добавляю комментарий...")
            conn.execute(
                text("""
                COMMENT ON COLUMN task_places.task_hint IS 'Короткое задание/подсказка для места (1 предложение)'
            """)
            )

            print("📝 Создаю индекс...")
            conn.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_task_places_task_hint_null
                ON task_places(category, place_type)
                WHERE task_hint IS NULL
            """)
            )

            print("✅ Миграция применена!")

        # Проверяем снова
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'task_places' AND column_name = 'task_hint'
            """)
            )
            row = result.fetchone()
            if row:
                print("\n✅ Столбец создан успешно:")
                print(f"   Имя: {row[0]}")
                print(f"   Тип: {row[1]}")
                print(f"   Длина: {row[2]}")
            else:
                print("\n❌ Столбец все еще не найден после миграции!")

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

print("\n✨ Готово!")
