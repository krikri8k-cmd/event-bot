#!/usr/bin/env python3
"""
Проверка индексов таблицы events
"""

import os

from sqlalchemy import text

from database import get_session, init_engine


def main():
    # Инициализируем подключение
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:GHeScaRnEXJEPRRXpFGJCdTPgcQOtzlw@interchange.proxy.rlwy.net:23764/railway?sslmode=require",
    )
    init_engine(database_url)

    # Проверяем индексы
    with get_session() as session:
        result = session.execute(
            text("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'events' 
            ORDER BY indexname
        """)
        )

        print("=== ИНДЕКСЫ ТАБЛИЦЫ events ===")
        for row in result:
            print(f"{row[0]}: {row[1]}")

        # Проверяем ограничения
        result2 = session.execute(
            text("""
            SELECT conname, contype, pg_get_constraintdef(oid) 
            FROM pg_constraint 
            WHERE conrelid = 'events'::regclass
            ORDER BY conname
        """)
        )

        print("\n=== ОГРАНИЧЕНИЯ ТАБЛИЦЫ events ===")
        for row in result2:
            print(f"{row[0]} ({row[1]}): {row[2]}")


if __name__ == "__main__":
    main()
