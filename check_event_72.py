#!/usr/bin/env python3
"""
Проверка события ID 72
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main():
    load_dotenv("app.local.env")
    engine = create_engine(os.getenv("DATABASE_URL"))

    with engine.connect() as conn:
        print("Проверяем событие ID 72:")
        result = conn.execute(text("SELECT id, title, organizer_id, status FROM events WHERE id = 72"))
        row = result.fetchone()

        if row:
            print(f"ID: {row[0]}")
            print(f"Title: {row[1]}")
            print(f"Organizer ID: {row[2]}")
            print(f"Status: {row[3]}")
        else:
            print("Событие ID 72 не найдено")

        print("\nВсе события пользователя 456065084:")
        result = conn.execute(text("SELECT id, title, organizer_id, status FROM events WHERE organizer_id = 456065084"))
        rows = result.fetchall()

        if rows:
            for row in rows:
                print(f"ID: {row[0]}, Title: {row[1]}, Organizer: {row[2]}, Status: {row[3]}")
        else:
            print("События пользователя 456065084 не найдены")


if __name__ == "__main__":
    main()
