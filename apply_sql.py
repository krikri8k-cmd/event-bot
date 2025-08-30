#!/usr/bin/env python3
"""
Простой скрипт для применения SQL-миграций
"""

import os
import sys

from sqlalchemy import create_engine, text

from config import load_settings


def apply_sql_file(engine, sql_file_path: str):
    """Применяет SQL-файл к базе данных"""
    print(f"Применяю {sql_file_path}...")

    with open(sql_file_path, encoding="utf-8") as f:
        sql_content = f.read()

    with engine.begin() as conn:
        # Разбиваем на отдельные команды по ;
        commands = [cmd.strip() for cmd in sql_content.split(";") if cmd.strip()]

        for i, command in enumerate(commands, 1):
            if command:
                print(f"  Выполняю команду {i}/{len(commands)}...")
                try:
                    conn.execute(text(command))
                except Exception as e:
                    print(f"  Ошибка в команде {i}: {e}")
                    # Продолжаем выполнение других команд
                    continue

    print(f"✅ {sql_file_path} применён")


def main():
    # Загружаем настройки
    settings = load_settings()
    if not settings.database_url:
        print("❌ DATABASE_URL не настроен")
        sys.exit(1)

    # Создаём engine
    engine = create_engine(settings.database_url, future=True)

    # Проверяем подключение
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Подключение к БД успешно")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        sys.exit(1)

    # Применяем SQL-файл
    sql_file = "sql/2025_ics_sources_and_indexes.sql"
    if os.path.exists(sql_file):
        apply_sql_file(engine, sql_file)
    else:
        print(f"❌ Файл {sql_file} не найден")
        sys.exit(1)

    print("✅ Все миграции применены успешно")


if __name__ == "__main__":
    main()
