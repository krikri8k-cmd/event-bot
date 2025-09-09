#!/usr/bin/env python3
"""Применение миграции БД"""

from sqlalchemy import create_engine, text

from api import config


def apply_migration():
    engine = create_engine(config.DATABASE_URL)

    # Читаем SQL файл
    with open("migrations/002_event_city_country_organizer.sql", encoding="utf-8") as f:
        sql = f.read()

    # Разбиваем на отдельные команды
    commands = [cmd.strip() for cmd in sql.split(";") if cmd.strip() and not cmd.strip().startswith("--")]

    with engine.connect() as conn:
        for command in commands:
            if command and command not in ["BEGIN", "COMMIT"]:
                try:
                    conn.execute(text(command))
                    print(f"Executed: {command[:50]}...")
                except Exception as e:
                    print(f"Error executing: {command[:50]}... - {e}")

        conn.commit()
        print("Migration completed")


if __name__ == "__main__":
    apply_migration()
