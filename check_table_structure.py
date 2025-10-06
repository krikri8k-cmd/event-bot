#!/usr/bin/env python3
"""
Скрипт для проверки структуры таблицы events_community
"""

import sys

from sqlalchemy import create_engine, text

from config import load_settings


def main():
    """Основная функция"""
    print("🔍 Проверка структуры таблицы events_community...")

    try:
        settings = load_settings()
        engine = create_engine(settings.database_url)

        with engine.connect() as conn:
            # Получаем структуру таблицы
            result = conn.execute(
                text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'events_community'
                ORDER BY ordinal_position;
            """)
            )

            columns = result.fetchall()

            if columns:
                print("📋 Структура таблицы events_community:")
                for col in columns:
                    print(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
            else:
                print("❌ Таблица events_community не найдена")
                return False

    except Exception as e:
        print(f"💥 Ошибка: {e}")
        return False

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
