#!/usr/bin/env python3
"""
Безопасное применение миграции для управления статусами событий
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main():
    print("🚀 Применение миграции управления статусами событий")
    print("=" * 60)

    # Загружаем переменные окружения
    load_dotenv("app.local.env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL не найден в app.local.env")
        sys.exit(1)

    # Создаем подключение
    engine = create_engine(database_url)

    try:
        with engine.begin() as conn:
            print("📊 Проверяем текущее состояние...")

            # Проверяем текущие статусы
            result = conn.execute(
                text("""
                SELECT status, COUNT(*) as count
                FROM events 
                GROUP BY status 
                ORDER BY status
            """)
            ).fetchall()

            print("Текущие статусы:")
            for row in result:
                print(f"  - {row[0]}: {row[1]} событий")

            # Проверяем записи без organizer_id
            null_organizer = conn.execute(
                text("""
                SELECT COUNT(*) FROM events WHERE organizer_id IS NULL
            """)
            ).scalar()

            if null_organizer > 0:
                print(f"⚠️  Найдено {null_organizer} событий без organizer_id")
                print("   Эти записи нужно будет обработать отдельно")

            # Проверяем записи без starts_at
            null_starts = conn.execute(
                text("""
                SELECT COUNT(*) FROM events WHERE starts_at IS NULL
            """)
            ).scalar()

            if null_starts > 0:
                print(f"⚠️  Найдено {null_starts} событий без starts_at")
                print("   Эти записи нужно будет обработать отдельно")

            print("\n🔧 Применяем миграцию...")

            # 1. Обновляем пустые статусы
            updated_status = conn.execute(
                text("""
                UPDATE events 
                SET status = 'open' 
                WHERE status IS NULL OR status = ''
            """)
            ).rowcount

            print(f"✅ Обновлено {updated_status} записей со статусом")

            # 2. Устанавливаем default для status
            conn.execute(
                text("""
                ALTER TABLE events 
                ALTER COLUMN status SET DEFAULT 'open'
            """)
            )
            print("✅ Установлен default статус 'open'")

            # 3. Добавляем CHECK ограничение
            try:
                conn.execute(
                    text("""
                    ALTER TABLE events 
                    ADD CONSTRAINT events_status_check 
                    CHECK (status IN ('open', 'closed', 'canceled', 'active', 'draft'))
                """)
                )
                print("✅ Добавлено ограничение для статусов")
            except Exception as e:
                if "already exists" in str(e):
                    print("ℹ️  Ограничение статусов уже существует")
                else:
                    raise

            # 4. Создаем индексы
            try:
                conn.execute(
                    text("""
                    CREATE INDEX IF NOT EXISTS idx_events_status_starts_at 
                    ON events (status, starts_at)
                """)
                )
                print("✅ Создан индекс по статусу и дате")
            except Exception as e:
                print(f"⚠️  Ошибка создания индекса: {e}")

            try:
                conn.execute(
                    text("""
                    CREATE INDEX IF NOT EXISTS idx_events_organizer_status 
                    ON events (organizer_id, status)
                """)
                )
                print("✅ Создан индекс по организатору и статусу")
            except Exception as e:
                print(f"⚠️  Ошибка создания индекса: {e}")

            # 5. Создаем функцию автомодерации
            conn.execute(
                text("""
                CREATE OR REPLACE FUNCTION auto_close_events()
                RETURNS INTEGER AS $$
                DECLARE
                    closed_count INTEGER;
                BEGIN
                    UPDATE events
                    SET status = 'closed', 
                        updated_at_utc = NOW()
                    WHERE status = 'open'
                      AND starts_at::date < CURRENT_DATE;

                    GET DIAGNOSTICS closed_count = ROW_COUNT;

                    RETURN closed_count;
                END;
                $$ LANGUAGE plpgsql
            """)
            )
            print("✅ Создана функция автомодерации")

            # 6. Тестируем функцию
            closed_count = conn.execute(text("SELECT auto_close_events()")).scalar()
            print(f"✅ Автомодерация: закрыто {closed_count} событий")

            print("\n📊 Финальное состояние:")
            result = conn.execute(
                text("""
                SELECT status, COUNT(*) as count
                FROM events 
                GROUP BY status 
                ORDER BY status
            """)
            ).fetchall()

            for row in result:
                print(f"  - {row[0]}: {row[1]} событий")

            print("\n🎉 Миграция успешно применена!")
            print("💡 Теперь можно использовать новые статусы: open, closed, canceled")

    except Exception as e:
        print(f"❌ Ошибка при применении миграции: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
