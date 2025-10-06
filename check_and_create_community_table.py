#!/usr/bin/env python3
"""
Скрипт для проверки и создания таблицы events_community
"""

import sys

from sqlalchemy import create_engine, inspect, text

from config import load_settings


def check_table_exists(engine, table_name):
    """Проверяет существование таблицы"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def create_community_table(engine):
    """Создает таблицу events_community"""
    with engine.connect() as conn:
        # Создаем таблицу
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS events_community (
            id SERIAL PRIMARY KEY,
            group_id BIGINT NOT NULL,
            creator_id BIGINT NOT NULL,
            title TEXT NOT NULL,
            date TIMESTAMP NOT NULL,
            description TEXT,
            city TEXT,
            location_name TEXT,
            created_at TIMESTAMP DEFAULT now()
        );
        """

        # Создаем индексы
        create_indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_events_community_group_id ON events_community(group_id);",
            "CREATE INDEX IF NOT EXISTS idx_events_community_date ON events_community(date);",
            "CREATE INDEX IF NOT EXISTS idx_events_community_creator_id ON events_community(creator_id);",
        ]

        try:
            conn.execute(text(create_table_sql))
            conn.commit()
            print("✅ Таблица events_community создана")

            for index_sql in create_indexes_sql:
                conn.execute(text(index_sql))
                conn.commit()
            print("✅ Индексы созданы")

            return True
        except Exception as e:
            print(f"❌ Ошибка создания таблицы: {e}")
            return False


def main():
    """Основная функция"""
    print("🔍 Проверка таблицы events_community...")

    try:
        settings = load_settings()
        engine = create_engine(settings.database_url)

        # Проверяем существование таблицы
        if check_table_exists(engine, "events_community"):
            print("✅ Таблица events_community существует")

            # Проверяем структуру
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM events_community"))
                count = result.fetchone()[0]
                print(f"📊 Количество записей в таблице: {count}")
        else:
            print("❌ Таблица events_community НЕ существует")
            print("🔧 Создаем таблицу...")

            if create_community_table(engine):
                print("🎉 Таблица успешно создана!")
            else:
                print("💥 Не удалось создать таблицу")
                return False

    except Exception as e:
        print(f"💥 Ошибка: {e}")
        return False

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
