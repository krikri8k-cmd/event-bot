#!/usr/bin/env python3
"""
Тест обновления события в реальном времени
"""

import os
import sys
from datetime import datetime

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot_enhanced_v3 import update_event_field
from config import load_settings
from database import Event, get_session, init_engine
from simple_status_manager import get_user_events


def test_live_update():
    """Тестирует обновление события и проверку через get_user_events"""
    print("🧪 Тестируем обновление события в реальном времени...")

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

        # Проверяем через get_user_events ДО обновления
        print("📋 Проверяем события через get_user_events ДО обновления...")
        events_before = get_user_events(event.organizer_id)
        event_before = next((e for e in events_before if e["id"] == event.id), None)
        if event_before:
            print(f"   Название ДО: '{event_before['title']}'")
        else:
            print("   Событие не найдено через get_user_events")
            return False

        # Тестируем обновление названия
        new_title = f"Тестовое название {datetime.now().strftime('%H:%M:%S')}"
        print(f"📝 Обновляем название на: '{new_title}'...")

        success = update_event_field(event.id, "title", new_title, event.organizer_id)

        if success:
            print("✅ Обновление названия успешно!")

            # Проверяем через SQLAlchemy напрямую
            session.refresh(event)
            print(f"   Название в SQLAlchemy: '{event.title}'")

            # Проверяем через get_user_events ПОСЛЕ обновления
            print("📋 Проверяем события через get_user_events ПОСЛЕ обновления...")
            events_after = get_user_events(event.organizer_id)
            event_after = next((e for e in events_after if e["id"] == event.id), None)
            if event_after:
                print(f"   Название ПОСЛЕ: '{event_after['title']}'")

                if event_after["title"] == new_title:
                    print("✅ get_user_events показывает обновленное название!")

                    # Возвращаем обратно
                    update_event_field(event.id, "title", "Пробежка", event.organizer_id)
                    print("✅ Название возвращено обратно")
                    return True
                else:
                    print("❌ get_user_events НЕ показывает обновленное название!")
                    print(f"   Ожидалось: '{new_title}'")
                    print(f"   Получено: '{event_after['title']}'")
                    return False
            else:
                print("❌ Событие не найдено через get_user_events после обновления")
                return False
        else:
            print("❌ Обновление названия не удалось")
            return False


if __name__ == "__main__":
    try:
        result = test_live_update()
        if result:
            print("\n🎉 Тест прошел успешно! Обновление работает корректно.")
        else:
            print("\n💥 Тест не прошел. Есть проблемы с обновлением.")
    except Exception as e:
        print(f"\n💥 Ошибка при тестировании: {e}")
        import traceback

        traceback.print_exc()
