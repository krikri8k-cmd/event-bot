#!/usr/bin/env python3
"""
Скрипт для удаления таблицы moments из PostgreSQL базы данных
"""

import sys

from sqlalchemy import create_engine, text

from config import load_settings


def main():
    print("🗄️ Удаление таблицы moments из базы данных...")

    try:
        # Загружаем настройки
        settings = load_settings()

        # Создаем подключение к базе данных
        engine = create_engine(settings.database_url)

        with engine.connect() as conn:
            # Проверяем, существует ли таблица moments
            result = conn.execute(
                text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'moments'
                );
            """)
            )

            table_exists = result.scalar()

            if table_exists:
                print("✅ Таблица moments найдена, удаляем...")

                # Удаляем таблицу moments
                conn.execute(text("DROP TABLE moments CASCADE;"))
                conn.commit()

                print("✅ Таблица moments успешно удалена!")
            else:
                print("ℹ️ Таблица moments не существует")

    except Exception as e:
        print(f"❌ Ошибка при удалении таблицы moments: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
