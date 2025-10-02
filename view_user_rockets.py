#!/usr/bin/env python3
"""
Просмотр ракет пользователей
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")


def view_user_rockets():
    """Показывает ракеты всех пользователей"""

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found")
        return

    engine = create_engine(db_url)

    try:
        with engine.connect() as conn:
            # Пользователи с ракетами
            result = conn.execute(
                text("""
                SELECT
                    id,
                    username,
                    full_name,
                    rockets_balance,
                    created_at_utc
                FROM users
                WHERE rockets_balance > 0
                ORDER BY rockets_balance DESC
            """)
            )

            print("=== Users with rockets ===")
            for row in result:
                print(f"ID: {row[0]}, Username: {row[1]}, Name: {row[2]}, Rockets: {row[3]}")

            # Статистика
            result = conn.execute(
                text("""
                SELECT
                    COUNT(*) as total_users,
                    SUM(rockets_balance) as total_rockets,
                    AVG(rockets_balance) as avg_rockets,
                    MAX(rockets_balance) as max_rockets
                FROM users
            """)
            )

            row = result.fetchone()
            print("\n=== Statistics ===")
            print(f"Total users: {row[0]}")
            print(f"Total rockets: {row[1]}")
            print(f"Average rockets: {row[2]:.1f}")
            print(f"Max rockets: {row[3]}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    view_user_rockets()
