#!/usr/bin/env python3
"""Тест подключения к БД"""

from config import load_settings
from database import User, get_session, init_engine


def test_db():
    try:
        # Загружаем настройки
        settings = load_settings(require_bot=True)
        print("✅ Настройки загружены")
        print(f"   DATABASE_URL: {settings.database_url[:50]}...")

        # Инициализируем engine
        init_engine(settings.database_url)
        print("✅ Engine инициализирован")

        # Получаем сессию
        with get_session() as session:
            print("✅ Сессия получена")

            # Пробуем простой запрос
            user_count = session.query(User).count()
            print(f"✅ Запрос выполнен: пользователей в БД: {user_count}")

        print("✅ Все тесты БД прошли успешно")

    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_db()
