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

db_url = os.getenv("DATABASE_URL")
if not db_url:
    with open("migration_result.txt", "w", encoding="utf-8") as f:
        f.write("❌ DATABASE_URL не найден\n")
    sys.exit(1)

result_lines = []
result_lines.append("=" * 60)
result_lines.append("ПРИМЕНЕНИЕ МИГРАЦИИ 029: Добавление task_hint")
result_lines.append("=" * 60)
result_lines.append(f"🔗 Подключение к БД: {db_url[:50]}...")

try:
    engine = create_engine(db_url, future=True, echo=False)

    # Проверяем наличие столбца ДО миграции
    result_lines.append("\n🔍 Проверка ДО миграции...")
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
            result_lines.append("⚠️ Столбец task_hint УЖЕ существует!")
        else:
            result_lines.append("✅ Столбец task_hint НЕ найден - применяю миграцию...")

    # Применяем миграцию
    if not exists_before:
        result_lines.append("\n📝 Применение миграции...")
        with engine.begin() as conn:
            result_lines.append("   [1/3] Добавляю столбец task_hint...")
            conn.execute(
                text("""
                ALTER TABLE task_places
                ADD COLUMN IF NOT EXISTS task_hint VARCHAR(200)
            """)
            )

            result_lines.append("   [2/3] Добавляю комментарий...")
            conn.execute(
                text("""
                COMMENT ON COLUMN task_places.task_hint IS 'Короткое задание/подсказка для места (1 предложение)'
            """)
            )

            result_lines.append("   [3/3] Создаю индекс...")
            conn.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_task_places_task_hint_null
                ON task_places(category, place_type)
                WHERE task_hint IS NULL
            """)
            )

        result_lines.append("✅ Миграция применена!")

    # Проверяем наличие столбца ПОСЛЕ миграции
    result_lines.append("\n🔍 Проверка ПОСЛЕ миграции...")
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
            result_lines.append("✅ Столбец создан успешно:")
            result_lines.append(f"   Имя: {row[0]}")
            result_lines.append(f"   Тип: {row[1]}")
            result_lines.append(f"   Длина: {row[2]}")
            result_lines.append(f"   Nullable: {row[3]}")
        else:
            result_lines.append("❌ Столбец все еще не найден!")

    # Показываем статистику
    result_lines.append("\n📊 Статистика по местам:")
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
            result_lines.append(f"   Всего мест: {row[0]}")
            result_lines.append(f"   С подсказками: {row[1]}")
            result_lines.append(f"   Без подсказок: {row[2]}")

    result_lines.append("\n" + "=" * 60)
    result_lines.append("✨ ГОТОВО! Столбец task_hint добавлен в таблицу task_places")
    result_lines.append("=" * 60)

except Exception as e:
    result_lines.append(f"\n❌ ОШИБКА: {e}")
    import traceback

    result_lines.append(traceback.format_exc())

# Сохраняем результат в файл
with open("migration_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(result_lines))

# Также выводим в консоль
print("\n".join(result_lines))
