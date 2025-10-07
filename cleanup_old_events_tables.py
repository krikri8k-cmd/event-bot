#!/usr/bin/env python3
"""
Скрипт для удаления старых таблиц events_parser и events_user
после успешной миграции в events
"""

import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text

from config import load_settings


def check_migration_success(engine) -> bool:
    """Проверяет успешность миграции"""
    with engine.connect() as conn:
        # Проверяем что в events есть данные из разных источников
        result = conn.execute(
            text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN source = 'user' THEN 1 END) as user_events,
                COUNT(CASE WHEN source != 'user' AND source IS NOT NULL THEN 1 END) as parser_events
            FROM events
        """)
        )

        row = result.fetchone()
        total, user_events, parser_events = row

        print(f"📊 События в events: всего={total}, пользовательские={user_events}, от парсеров={parser_events}")

        # Миграция считается успешной если есть события от парсеров или пользователей
        return parser_events > 0 or user_events > 0


def get_table_counts(engine) -> dict:
    """Получает количество записей в таблицах"""
    counts = {}
    tables = ["events", "events_parser", "events_user"]

    with engine.connect() as conn:
        for table in tables:
            try:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                counts[table] = result.fetchone()[0]
            except Exception:
                counts[table] = 0

    return counts


def create_backup_tables(engine) -> bool:
    """Создает резервные копии таблиц"""
    try:
        with engine.connect() as conn:
            # Создаем резервные копии
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS events_parser_backup AS
                SELECT * FROM events_parser
            """)
            )

            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS events_user_backup AS
                SELECT * FROM events_user
            """)
            )

            conn.commit()

        print("✅ Резервные копии созданы")
        return True
    except Exception as e:
        print(f"❌ Ошибка создания резервных копий: {e}")
        return False


def drop_old_tables(engine) -> bool:
    """Удаляет старые таблицы"""
    try:
        with engine.connect() as conn:
            # Удаляем таблицы в правильном порядке (сначала foreign keys)
            conn.execute(text("DROP TABLE IF EXISTS events_user CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS events_parser CASCADE"))
            conn.commit()

        print("✅ Старые таблицы удалены")
        return True
    except Exception as e:
        print(f"❌ Ошибка удаления таблиц: {e}")
        return False


def main():
    print("🗑️ Очистка: удаление старых таблиц events_parser и events_user")
    print("=" * 60)

    try:
        # Загружаем настройки
        settings = load_settings()
        engine = create_engine(settings.database_url)

        # Проверяем подключение
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Подключение к базе данных установлено")

        # Проверяем успешность миграции
        if not check_migration_success(engine):
            print("❌ Миграция не была выполнена или выполнена неуспешно!")
            print("Убедитесь что данные успешно перенесены в таблицу events")
            return 1

        # Получаем текущие количества записей
        counts = get_table_counts(engine)
        print(f"📊 Текущее состояние таблиц: {counts}")

        if counts["events_parser"] == 0 and counts["events_user"] == 0:
            print("ℹ️ Таблицы events_parser и events_user уже пусты")
            return 0

        # Создаем резервные копии
        print("\n💾 Создаем резервные копии...")
        if not create_backup_tables(engine):
            return 1

        # Спрашиваем подтверждение
        print("\n⚠️ ВНИМАНИЕ: Будут удалены таблицы events_parser и events_user!")
        print("Резервные копии созданы в events_parser_backup и events_user_backup")

        response = input("\nПродолжить удаление? (yes/no): ").strip().lower()
        if response not in ["yes", "y", "да", "д"]:
            print("❌ Удаление отменено пользователем")
            return 0

        # Удаляем старые таблицы
        print("\n🗑️ Удаляем старые таблицы...")
        if not drop_old_tables(engine):
            return 1

        # Проверяем результат
        counts_after = get_table_counts(engine)
        print(f"📊 Состояние после очистки: {counts_after}")

        if counts_after["events_parser"] == 0 and counts_after["events_user"] == 0:
            print("✅ Очистка выполнена успешно!")
            print("🎉 Теперь все события находятся в единой таблице events")
            return 0
        else:
            print("❌ Ошибка очистки!")
            return 1

    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
