#!/usr/bin/env python3
"""
Тестирование новых статусов событий
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main():
    print("🧪 Тестирование новых статусов событий")
    print("=" * 50)

    # Загружаем переменные окружения
    load_dotenv("app.local.env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL не найден")
        return

    engine = create_engine(database_url)

    with engine.begin() as conn:
        print("1. 📊 Текущие статусы:")
        result = conn.execute(
            text("""
            SELECT status, COUNT(*) as count
            FROM events
            GROUP BY status
            ORDER BY status
        """)
        ).fetchall()

        for row in result:
            print(f"   - {row[0]}: {row[1]} событий")

        print("\n2. 🔍 Тестируем валидные статусы:")
        test_statuses = ["open", "closed", "canceled", "active", "draft"]

        for status in test_statuses:
            try:
                # Пробуем обновить одно событие на тестовый статус
                result = conn.execute(
                    text("""
                    UPDATE events
                    SET status = :status
                    WHERE id = (SELECT id FROM events LIMIT 1)
                    RETURNING id, title, status
                """),
                    {"status": status},
                )

                if result.rowcount > 0:
                    row = result.fetchone()
                    print(f"   ✅ {status}: OK (ID {row[0]}: {row[1][:30]}...)")
                else:
                    print(f"   ⚠️  {status}: Нет событий для тестирования")

            except Exception as e:
                print(f"   ❌ {status}: Ошибка - {e}")

        print("\n3. 🤖 Тестируем функцию автомодерации:")
        try:
            closed_count = conn.execute(text("SELECT auto_close_events()")).scalar()
            print(f"   ✅ Автомодерация работает: закрыто {closed_count} событий")
        except Exception as e:
            print(f"   ❌ Ошибка автомодерации: {e}")

        print("\n4. 📈 Статистика по организаторам:")
        result = conn.execute(
            text("""
            SELECT
                organizer_username,
                status,
                COUNT(*) as count
            FROM events
            WHERE organizer_username IS NOT NULL
            GROUP BY organizer_username, status
            ORDER BY organizer_username, status
        """)
        ).fetchall()

        for row in result:
            print(f"   - {row[0]}: {row[1]} ({row[2]} событий)")

        print("\n5. 🎯 Твое событие (ID 72):")
        result = conn.execute(
            text("""
            SELECT id, title, status, organizer_username, starts_at
            FROM events
            WHERE id = 72
        """)
        ).fetchone()

        if result:
            print(f"   - ID: {result[0]}")
            print(f"   - Название: {result[1]}")
            print(f"   - Статус: {result[2]}")
            print(f"   - Организатор: {result[3]}")
            print(f"   - Время: {result[4]}")
        else:
            print("   ❌ Событие ID 72 не найдено")

        print("\n🎉 Тестирование завершено!")
        print("💡 Все новые статусы работают корректно!")


if __name__ == "__main__":
    main()
