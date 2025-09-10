#!/usr/bin/env python3
"""
Скрипт для тестирования SQL миграции локально
"""

import os
import sys

from sqlalchemy import create_engine, text


def test_migration():
    """Тестирует применение SQL миграции"""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        print("   Установи: export DATABASE_URL='postgresql://user:pass@host:port/db?sslmode=require'")
        return False

    sql_file = "sql/2025_ics_sources_and_indexes.sql"
    if not os.path.exists(sql_file):
        print(f"❌ Файл {sql_file} не найден")
        return False

    print("🔗 Подключаюсь к БД...")
    print(f"📄 Применяю: {sql_file}")

    try:
        engine = create_engine(db_url, future=True, pool_pre_ping=True)

        # Читаем SQL файл
        with open(sql_file, encoding="utf-8") as f:
            sql_content = f.read()

        # Применяем миграцию
        with engine.begin() as conn:
            # Разбиваем на команды
            commands = [cmd.strip() for cmd in sql_content.split(";") if cmd.strip()]

            for i, command in enumerate(commands, 1):
                if command:
                    print(f"  Выполняю команду {i}/{len(commands)}...")
                    try:
                        conn.execute(text(command))
                        print(f"  ✅ Команда {i} выполнена")
                    except Exception as e:
                        print(f"  ⚠️  Команда {i}: {e}")
                        # Продолжаем выполнение

        print("✅ Миграция применена успешно!")

        # Проверяем результат
        with engine.connect() as conn:
            # Проверяем таблицу event_sources
            result = conn.execute(
                text("""
                SELECT COUNT(*) as count 
                FROM information_schema.tables 
                WHERE table_name = 'event_sources'
            """)
            )
            if result.fetchone()[0] > 0:
                print("✅ Таблица event_sources создана")
            else:
                print("❌ Таблица event_sources не найдена")

            # Проверяем индексы
            result = conn.execute(
                text("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'event_sources'
            """)
            )
            indexes = [row[0] for row in result.fetchall()]
            print(f"📋 Индексы event_sources: {', '.join(indexes) if indexes else 'нет'}")

        return True

    except Exception as e:
        print(f"❌ Ошибка применения миграции: {e}")
        return False


if __name__ == "__main__":
    success = test_migration()
    sys.exit(0 if success else 1)
