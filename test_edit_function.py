#!/usr/bin/env python3
"""
Тест функции update_event_field для проверки редактирования событий
"""

import os
import sys

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot_enhanced_v3 import update_event_field
from config import load_settings
from database import Event, get_session, init_engine


def test_update_event_field():
    """Тестирует функцию обновления события"""
    print("🧪 Тестируем функцию update_event_field...")

    # Загружаем настройки
    settings = load_settings()
    init_engine(settings.database_url)

    # Находим тестовое событие
    with get_session() as session:
        # Ищем событие с названием "Пробежка"
        event = session.query(Event).filter(Event.title == "Пробежка").first()

        if not event:
            print("❌ Событие 'Пробежка' не найдено")
            return False

        print(f"✅ Найдено событие: ID={event.id}, Название='{event.title}', Организатор={event.organizer_id}")

        # Тестируем обновление названия
        print(f"📝 Тестируем обновление названия с '{event.title}' на 'Тестовое название'...")

        success = update_event_field(event.id, "title", "Тестовое название", event.organizer_id)

        if success:
            print("✅ Обновление названия успешно!")

            # Проверяем, что название действительно изменилось
            session.refresh(event)
            if event.title == "Тестовое название":
                print("✅ Название в БД обновлено корректно!")

                # Возвращаем обратно
                update_event_field(event.id, "title", "Пробежка", event.organizer_id)
                print("✅ Название возвращено обратно")
                return True
            else:
                print(f"❌ Название в БД не изменилось: '{event.title}'")
                return False
        else:
            print("❌ Обновление названия не удалось")
            return False


if __name__ == "__main__":
    try:
        result = test_update_event_field()
        if result:
            print("\n🎉 Тест прошел успешно! Функция update_event_field работает корректно.")
        else:
            print("\n💥 Тест не прошел. Есть проблемы с функцией update_event_field.")
    except Exception as e:
        print(f"\n💥 Ошибка при тестировании: {e}")
        import traceback

        traceback.print_exc()
