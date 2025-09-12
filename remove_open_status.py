#!/usr/bin/env python3
"""
Удаление статуса open из системы (оставляем active)
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main():
    print("🔧 Удаление статуса 'open' из системы (оставляем 'active')")
    print("=" * 60)

    # Загружаем переменные окружения
    load_dotenv("app.local.env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL не найден")
        return

    engine = create_engine(database_url)

    try:
        with engine.begin() as conn:
            print("1. 📊 Проверяем текущие статусы:")
            result = conn.execute(
                text("""
                SELECT status, COUNT(*) as count
                FROM events
                GROUP BY status
                ORDER BY count DESC
            """)
            ).fetchall()

            for row in result:
                print(f"   - {row[0]}: {row[1]} событий")

            # Проверяем, есть ли события со статусом open
            open_count = conn.execute(
                text("""
                SELECT COUNT(*) FROM events WHERE status = 'open'
            """)
            ).scalar()

            if open_count > 0:
                print(f"\n2. 🔄 Обновляем {open_count} событий со статусом 'open' на 'active':")
                conn.execute(
                    text("""
                    UPDATE events
                    SET status = 'active', updated_at_utc = NOW()
                    WHERE status = 'open'
                """)
                )
                print("   ✅ События обновлены")
            else:
                print("\n2. ℹ️  Событий со статусом 'open' не найдено")

            print("\n3. 🗑️  Удаляем старое ограничение:")
            try:
                conn.execute(text("ALTER TABLE events DROP CONSTRAINT events_status_check"))
                print("   ✅ Старое ограничение удалено")
            except Exception as e:
                print(f"   ℹ️  Ограничение уже удалено или не существует: {e}")

            print("\n4. ✅ Добавляем новое ограничение (только active, closed, canceled):")
            conn.execute(
                text("""
                ALTER TABLE events
                ADD CONSTRAINT events_status_check
                CHECK (status IN ('active', 'closed', 'canceled'))
            """)
            )
            print("   ✅ Новое ограничение добавлено")

            print("\n5. 🔄 Обновляем default значение статуса:")
            conn.execute(
                text("""
                ALTER TABLE events
                ALTER COLUMN status SET DEFAULT 'active'
            """)
            )
            print("   ✅ Default статус изменен на 'active'")

            print("\n6. 📊 Финальные статусы:")
            result = conn.execute(
                text("""
                SELECT status, COUNT(*) as count
                FROM events
                GROUP BY status
                ORDER BY count DESC
            """)
            ).fetchall()

            for row in result:
                print(f"   - {row[0]}: {row[1]} событий")

            print("\n🎉 Статус 'open' успешно удален из системы!")
            print("💡 Теперь доступны только статусы: active, closed, canceled")
            print("📝 Default статус: active")

    except Exception as e:
        print(f"❌ Ошибка при обновлении: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
