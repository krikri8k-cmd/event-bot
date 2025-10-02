#!/usr/bin/env python3
"""
Миграция: обновить всех пользователей с радиусом 4 км на 5 км
"""

from sqlalchemy import text

from database import get_session


def migrate_radius_4_to_5():
    """Обновляет всех пользователей с радиусом 4 км на 5 км"""

    with get_session() as session:
        # Обновляем пользователей с радиусом 4 км на 5 км
        result = session.execute(text("UPDATE users SET default_radius_km = 5 WHERE default_radius_km = 4"))
        session.commit()

        # Проверяем результат
        count_result = session.execute(text("SELECT COUNT(*) FROM users WHERE default_radius_km = 5"))
        count = count_result.scalar()

        print(f"✅ Миграция выполнена: {result.rowcount} пользователей обновлено")
        print(f"📊 Всего пользователей с радиусом 5 км: {count}")

        return result.rowcount


if __name__ == "__main__":
    migrate_radius_4_to_5()
