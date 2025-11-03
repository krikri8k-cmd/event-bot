#!/usr/bin/env python3
"""
Скрипт для применения миграции добавления колонки total_events в chat_settings
"""

import os
import sys

from sqlalchemy import create_engine, text

# Добавляем корневую директорию в путь для импорта
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import load_settings


def apply_migration():
    """Применяет миграцию добавления total_events"""
    print("🚀 Применение миграции: добавление total_events в chat_settings")

    # Загружаем настройки
    settings = load_settings()
    if not settings.database_url:
        print("❌ DATABASE_URL не настроен")
        sys.exit(1)

    # Создаём engine
    print("📡 Подключение к базе данных...")
    try:
        engine = create_engine(settings.database_url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Подключение к БД успешно")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        sys.exit(1)

    # SQL команды миграции
    migration_sql = """
    -- Добавляем колонку total_events
    ALTER TABLE chat_settings
    ADD COLUMN IF NOT EXISTS total_events INTEGER DEFAULT 0 NOT NULL;

    -- Создаем индекс для быстрого поиска
    CREATE INDEX IF NOT EXISTS idx_chat_settings_total_events ON chat_settings(total_events);

    -- Комментарий к колонке
    COMMENT ON COLUMN chat_settings.total_events IS 'Общее количество событий, созданных в этом чате через бота';

    -- Backfill: подсчитываем существующие события для каждого чата
    UPDATE chat_settings cs
    SET total_events = (
        SELECT COUNT(*)
        FROM events_community ec
        WHERE ec.chat_id = cs.chat_id
    )
    WHERE EXISTS (
        SELECT 1
        FROM events_community ec
        WHERE ec.chat_id = cs.chat_id
    );
    """

    print("\n📝 Выполнение SQL команд...")
    try:
        with engine.begin() as conn:
            # Разбиваем на отдельные команды, убирая комментарии
            raw_commands = [cmd.strip() for cmd in migration_sql.split(";") if cmd.strip()]
            commands = []
            for cmd in raw_commands:
                # Убираем строки комментариев
                lines = [line for line in cmd.split("\n") if line.strip() and not line.strip().startswith("--")]
                clean_cmd = "\n".join(lines).strip()
                if clean_cmd:
                    commands.append(clean_cmd)

            for i, command in enumerate(commands, 1):
                if command:
                    print(f"  [{i}/{len(commands)}] Выполняю команду...")
                    try:
                        result = conn.execute(text(command))
                        print("     ✅ Команда выполнена успешно")
                        # Если это UPDATE, показываем количество обновленных строк
                        if command.strip().upper().startswith("UPDATE"):
                            print(f"     📊 Обновлено строк: {result.rowcount}")
                    except Exception as e:
                        error_msg = str(e)
                        # Игнорируем ошибку "column already exists"
                        if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                            print("     ℹ️ Колонка уже существует, пропускаем")
                        else:
                            print(f"     ⚠️ Предупреждение: {e}")
                            # Для некритичных ошибок продолжаем
                            if "IF NOT EXISTS" not in command.upper():
                                raise  # Поднимаем исключение для критичных ошибок

        print("\n✅ Миграция применена успешно!")
        print("📊 Проверка результата...")

        # Проверяем, что колонка добавлена
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT column_name, data_type, column_default
                FROM information_schema.columns
                WHERE table_name = 'chat_settings' AND column_name = 'total_events'
            """)
            )
            row = result.fetchone()
            if row:
                print(f"✅ Колонка total_events найдена: {row[0]} ({row[1]}, default={row[2]})")
            else:
                print("❌ Колонка total_events не найдена!")
                sys.exit(1)

            # Показываем статистику
            result = conn.execute(
                text("""
                SELECT 
                    COUNT(*) as total_chats,
                    SUM(total_events) as total_events_sum,
                    AVG(total_events) as avg_events_per_chat
                FROM chat_settings
            """)
            )
            stats = result.fetchone()
            if stats:
                avg_events = float(stats[2]) if stats[2] else 0.0
                print("\n📈 Статистика:")
                print(f"   Всего чатов: {stats[0]}")
                print(f"   Всего событий: {stats[1] or 0}")
                print(f"   В среднем событий на чат: {avg_events:.2f}")

    except Exception as e:
        print(f"\n❌ Ошибка при применении миграции: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    apply_migration()
