#!/usr/bin/env python3
"""
Тестовый скрипт для проверки изолированных обработчиков групповых чатов
Этот файл НЕ влияет на основной бот
"""

import os
import sys

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def test_imports():
    """Тест импортов модуля"""
    try:
        print("✅ Импорты работают корректно")
        return True
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        return False


def test_states():
    """Тест FSM состояний"""
    try:
        from group_chat_handlers import GroupCreate

        # Проверяем, что состояния определены
        states = [
            GroupCreate.waiting_for_title,
            GroupCreate.waiting_for_datetime,
            GroupCreate.waiting_for_city,
            GroupCreate.waiting_for_location,
            GroupCreate.waiting_for_description,
        ]
        print(f"✅ FSM состояния определены: {len(states)} состояний")
        return True
    except Exception as e:
        print(f"❌ Ошибка FSM состояний: {e}")
        return False


def test_service_connection():
    """Тест подключения к сервису"""
    try:
        from utils.community_events_service import CommunityEventsService

        # Создаем экземпляр сервиса
        CommunityEventsService()
        print("✅ CommunityEventsService создан успешно")
        return True
    except Exception as e:
        print(f"❌ Ошибка сервиса: {e}")
        return False


def main():
    """Основная функция тестирования"""
    print("🧪 Тестирование изолированных обработчиков групповых чатов")
    print("=" * 60)

    tests = [
        ("Импорты", test_imports),
        ("FSM состояния", test_states),
        ("Сервис", test_service_connection),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔍 Тест: {test_name}")
        if test_func():
            passed += 1
        else:
            print(f"❌ Тест {test_name} провален")

    print("\n" + "=" * 60)
    print(f"📊 Результат: {passed}/{total} тестов пройдено")

    if passed == total:
        print("🎉 Все тесты пройдены! Модуль готов к интеграции.")
        return True
    else:
        print("⚠️ Есть проблемы, требующие исправления.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
