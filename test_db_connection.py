#!/usr/bin/env python3
"""
Скрипт для тестирования подключения к базе данных
"""

import os
import sys

from sqlalchemy import create_engine, text


def test_connection():
    """Тестирует подключение к базе данных"""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        return False

    print("🔗 Подключаюсь к БД...")
    print(f"   URL: {db_url.split('@')[1] if '@' in db_url else '***'}")  # Показываем только хост

    try:
        engine = create_engine(db_url, future=True, pool_pre_ping=True)

        with engine.connect() as conn:
            # Проверяем подключение
            result = conn.execute(text("SELECT current_database(), current_user, version()"))
            row = result.fetchone()

            print("✅ Подключение успешно!")
            print(f"   База данных: {row[0]}")
            print(f"   Пользователь: {row[1]}")
            print(f"   PostgreSQL версия: {row[2].split(',')[0]}")

            # Проверяем существующие таблицы
            result = conn.execute(
                text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
            )
            tables = [row[0] for row in result.fetchall()]

            print(f"📋 Существующие таблицы: {', '.join(tables) if tables else 'нет'}")

            return True

    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
