#!/usr/bin/env python3
"""
Проверка подключения к базе и подсчет записей
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Добавляем корень проекта в путь для импортов
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text  # noqa: E402

from database import TaskPlace, get_session, init_engine  # noqa: E402

# Загружаем переменные окружения
env_path = project_root / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)


def check_db():
    """Проверяет подключение и показывает статистику"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        sys.exit(1)

    print(f"🔗 Подключение к базе: {db_url[:50]}...")
    init_engine(db_url)

    with get_session() as session:
        # Проверяем количество записей через SQL
        result = session.execute(text("SELECT COUNT(*) FROM task_places"))
        count = result.scalar()
        print(f"\n📊 Количество записей в task_places: {count}")

        # Проверяем через ORM
        places = session.query(TaskPlace).all()
        print(f"📊 Количество через ORM: {len(places)}")

        if count > 0:
            print("\n✅ Таблица НЕ пустая!")
            print("\nПервые 5 записей:")
            for i, place in enumerate(places[:5], 1):
                print(
                    f"  {i}. ID={place.id}, name={place.name}, "
                    f"region={place.region}, category={place.category}, "
                    f"place_type={place.place_type}, task_type={place.task_type}"
                )
        else:
            print("\n⚠️ Таблица ПУСТАЯ!")

        # Проверяем структуру таблицы
        print("\n📋 Структура таблицы task_places:")
        result = session.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'task_places'
                ORDER BY ordinal_position
                """
            )
        )
        for row in result:
            default = f" DEFAULT {row[3]}" if row[3] else ""
            nullable = "NULL" if row[2] == "YES" else "NOT NULL"
            print(f"  - {row[0]}: {row[1]} {nullable}{default}")


if __name__ == "__main__":
    check_db()
