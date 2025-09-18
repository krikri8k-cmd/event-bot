#!/usr/bin/env python3
"""Скрипт для проверки времени событий в базе данных"""

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def main():
    # Загружаем настройки и инициализируем движок
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()
    with engine.connect() as conn:
        # Проверяем события с BaliForum
        result = conn.execute(
            text("""
            SELECT title, starts_at, time_local, event_tz, source 
            FROM events 
            WHERE source LIKE '%bali%' OR source LIKE '%forum%'
            LIMIT 5
        """)
        )

        print("=== СОБЫТИЯ ИЗ БАЗЫ ДАННЫХ (BaliForum) ===")
        for row in result:
            print(f"Название: {row[0]}")
            print(f"starts_at: {row[1]} (тип: {type(row[1])})")
            print(f"time_local: {row[2]}")
            print(f"event_tz: {row[3]}")
            print(f"source: {row[4]}")
            print("---")

        # Проверяем вообще любые события
        result2 = conn.execute(
            text("""
            SELECT title, starts_at, time_local, event_tz, source 
            FROM events 
            WHERE starts_at IS NOT NULL
            LIMIT 3
        """)
        )

        print("\n=== СОБЫТИЯ С ЗАПОЛНЕННЫМ starts_at ===")
        for row in result2:
            print(f"Название: {row[0]}")
            print(f"starts_at: {row[1]} (тип: {type(row[1])})")
            print(f"time_local: {row[2]}")
            print(f"event_tz: {row[3]}")
            print(f"source: {row[4]}")
            print("---")


if __name__ == "__main__":
    main()
