#!/usr/bin/env python3
"""
Скрипт проверки подключения к базе данных.
Проверяет DATABASE_URL и делает тестовый запрос.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main():
    # Загружаем переменные из .env.local
    load_dotenv(".env.local")

    url = os.getenv("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL MISSING")
        sys.exit(1)

    # Подсказка: для Railway внешний URL должен содержать ?sslmode=require
    print("DATABASE_URL:", url[:80] + "..." if len(url) > 80 else url)

    try:
        # Создаем engine с правильными параметрами
        eng = create_engine(url, pool_pre_ping=True, future=True)

        # Проверяем подключение
        with eng.connect() as c:
            r = c.execute(text("SELECT 1")).scalar()

        print("✅ DB OK:", r == 1)
        sys.exit(0)

    except Exception as e:
        print(f"❌ DB ERROR: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
