#!/usr/bin/env python3
"""
Скрипт для бекфилла chat_number для существующих чатов
"""

import os
import sys

from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def load_env():
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.local.env"))
    if load_dotenv and os.path.exists(env_path):
        load_dotenv(env_path)


def main():
    load_env()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL is not set. Ensure app.local.env is configured.")
        sys.exit(1)

    engine = create_engine(db_url, future=True)

    with engine.begin() as conn:
        # Сначала сбрасываем последовательность на 1
        print("1. Сбрасываем последовательность на 1...")
        conn.execute(text("SELECT setval('chat_number_seq', 1, false)"))

        # Получаем все чаты, которым нужно назначить номер
        print("2. Получаем список чатов без chat_number...")
        result = conn.execute(
            text("""
            SELECT chat_id
            FROM chat_settings
            WHERE chat_number IS NULL
            ORDER BY created_at, chat_id
        """)
        )
        chats = result.fetchall()
        print(f"   Найдено {len(chats)} чатов для бекфилла")

        # Назначаем номера
        if chats:
            print("3. Назначаем chat_number...")
            next_num = 1
            for chat in chats:
                chat_id = chat[0]
                conn.execute(
                    text("UPDATE chat_settings SET chat_number = :num WHERE chat_id = :id"),
                    {"num": next_num, "id": chat_id},
                )
                print(f"   Chat {chat_id} → #{next_num}")
                next_num += 1

        # Устанавливаем sequence на правильное значение после бекфилла
        print("4. Устанавливаем sequence на правильное значение...")
        result = conn.execute(
            text("""
            SELECT setval('chat_number_seq',
                COALESCE((SELECT MAX(chat_number) FROM chat_settings), 0) + 1,
                false
            )
        """)
        )
        max_num = result.scalar()
        print(f"   Sequence установлена на {max_num}")

    print("✅ Бекфилл chat_number завершен успешно!")


if __name__ == "__main__":
    main()
