#!/usr/bin/env python3
"""
Скрипт для отладки FSM в групповых чатах
"""

import os
import sys
from datetime import datetime

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def test_fsm_states():
    """Тест FSM состояний"""
    try:
        from group_chat_handlers import GroupCreate

        print("🔍 Проверка FSM состояний:")
        states = [
            ("waiting_for_title", GroupCreate.waiting_for_title),
            ("waiting_for_datetime", GroupCreate.waiting_for_datetime),
            ("waiting_for_city", GroupCreate.waiting_for_city),
            ("waiting_for_location", GroupCreate.waiting_for_location),
            ("waiting_for_description", GroupCreate.waiting_for_description),
        ]

        for name, state in states:
            print(f"  ✅ {name}: {state}")

        return True
    except Exception as e:
        print(f"❌ Ошибка FSM состояний: {e}")
        return False


def test_service_methods():
    """Тест методов сервиса"""
    try:
        from utils.community_events_service import CommunityEventsService

        print("\n🔍 Проверка методов сервиса:")
        service = CommunityEventsService()

        # Тестируем создание события
        test_event_id = service.create_community_event(
            group_id=-1002933948882,  # ID вашей тестовой группы
            creator_id=456065084,  # Ваш ID
            title="Тестовое событие",
            date=datetime(2025, 10, 10, 18, 0),
            description="Тестовое описание",
            city="Москва",
            location_name="Тестовое место",
        )

        print(f"  ✅ Событие создано с ID: {test_event_id}")

        # Тестируем получение событий
        events = service.get_community_events(-1002933948882)
        print(f"  ✅ Получено событий: {len(events)}")

        for event in events:
            print(f"    - {event['title']} ({event['starts_at']})")

        return True
    except Exception as e:
        print(f"❌ Ошибка сервиса: {e}")
        return False


def main():
    """Основная функция"""
    print("🧪 Отладка FSM и сервиса для групповых чатов")
    print("=" * 50)

    tests = [
        ("FSM состояния", test_fsm_states),
        ("Сервис", test_service_methods),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔍 Тест: {test_name}")
        if test_func():
            passed += 1
        else:
            print(f"❌ Тест {test_name} провален")

    print("\n" + "=" * 50)
    print(f"📊 Результат: {passed}/{total} тестов пройдено")

    if passed == total:
        print("🎉 Все тесты пройдены!")
        return True
    else:
        print("⚠️ Есть проблемы, требующие исправления.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
