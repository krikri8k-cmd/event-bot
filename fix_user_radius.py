#!/usr/bin/env python3
"""
Скрипт для обновления радиуса пользователя с 4 км на 5 км
"""

from sqlalchemy import text

from database import get_session


def fix_user_radius():
    """Обновляет всех пользователей с радиусом 4 км на 5 км"""

    try:
        with get_session() as session:
            # Проверяем, сколько пользователей с радиусом 4 км
            count_4km = session.execute(text("SELECT COUNT(*) FROM users WHERE default_radius_km = 4")).scalar()
            print(f"Users with 4km radius: {count_4km}")

            if count_4km == 0:
                print("All users already have correct radius")
                return

            # Обновляем пользователей с радиусом 4 км на 5 км
            result = session.execute(text("UPDATE users SET default_radius_km = 5 WHERE default_radius_km = 4"))
            session.commit()

            # Проверяем результат
            count_5km = session.execute(text("SELECT COUNT(*) FROM users WHERE default_radius_km = 5")).scalar()

            print(f"Updated users: {result.rowcount}")
            print(f"Total users with 5km radius: {count_5km}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    fix_user_radius()
