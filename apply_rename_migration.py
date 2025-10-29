#!/usr/bin/env python3
"""
Скрипт для переименования таблицы daily_views в daily_views_tasks
"""

import os
import sys
from sqlalchemy import create_engine, text


def apply_migration():
    """Применяет миграцию переименования таблицы"""

    # Получаем URL базы данных из переменной окружения
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        return False

    try:
        # Создаем подключение к базе данных
        engine = create_engine(database_url)

        with engine.connect() as conn:
            # Проверяем существует ли таблица daily_views
            result = conn.execute(
                text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'daily_views'
                );
            """)
            )

            table_exists = result.scalar()

            if not table_exists:
                print("❌ Таблица daily_views не существует")
                return False

            # Проверяем существует ли уже таблица daily_views_tasks
            result = conn.execute(
                text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'daily_views_tasks'
                );
            """)
            )

            new_table_exists = result.scalar()

            if new_table_exists:
                print("❌ Таблица daily_views_tasks уже существует")
                return False

            print("🔄 Переименовываем таблицу daily_views в daily_views_tasks...")

            # Переименовываем таблицу
            conn.execute(text("ALTER TABLE daily_views RENAME TO daily_views_tasks;"))

            # Добавляем комментарии
            conn.execute(
                text("""
                COMMENT ON TABLE daily_views_tasks IS 'Отслеживание просмотренных заданий и мест пользователями для предотвращения повторений в системе квестов';
            """)
            )

            conn.execute(
                text("""
                COMMENT ON COLUMN daily_views_tasks.user_id IS 'ID пользователя';
            """)
            )

            conn.execute(
                text("""
                COMMENT ON COLUMN daily_views_tasks.view_type IS 'Тип просмотра: template (шаблон задания) или place (место)';
            """)
            )

            conn.execute(
                text("""
                COMMENT ON COLUMN daily_views_tasks.view_key IS 'ID шаблона задания или места';
            """)
            )

            conn.execute(
                text("""
                COMMENT ON COLUMN daily_views_tasks.view_date IS 'Дата и время просмотра';
            """)
            )

            conn.commit()

            print("✅ Таблица успешно переименована в daily_views_tasks")
            print("✅ Добавлены комментарии к таблице и полям")
            return True

    except Exception as e:
        print(f"❌ Ошибка при применении миграции: {e}")
        return False


if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)
