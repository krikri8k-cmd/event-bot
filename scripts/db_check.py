#!/usr/bin/env python3
"""
Скрипт проверки подключения к базе данных.
Загружает .env.local, выводит урезанный DSN и делает SELECT 1.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main():
    # Загружаем переменные окружения из .env.local
    load_dotenv(".env.local", override=True)

    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")

    # Выводим урезанный DSN для безопасности
    print("DATABASE_URL:", (url[:80] + " ...") if len(url) > 80 else url)

    try:
        # Создаем engine с правильными параметрами
        engine = create_engine(url, pool_pre_ping=True, future=True)

        # Проверяем подключение
        with engine.begin() as conn:
            val = conn.execute(text("SELECT 1")).scalar()
            print("✅ DB OK:", val == 1)

        print("🎉 Подключение к базе данных успешно!")

    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
