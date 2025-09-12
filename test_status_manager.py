#!/usr/bin/env python3
"""
Тестирование менеджера статусов событий
"""

from dotenv import load_dotenv

from event_status_manager import (
    auto_close_events,
    change_event_status,
    format_event_for_display,
    get_event_by_id,
    get_events_statistics,
    get_status_change_buttons,
    get_status_description,
    get_status_emoji,
    get_user_events,
    is_valid_status,
)


def main():
    print("🧪 Тестирование менеджера статусов событий")
    print("=" * 50)

    # Загружаем переменные окружения
    load_dotenv("app.local.env")

    # ID пользователя Fincontro
    user_id = 456065084

    print(f"👤 Тестируем для пользователя ID: {user_id}")

    print("\n1. 📊 Статистика событий:")
    stats = get_events_statistics(user_id)
    for status, count in stats.items():
        emoji = get_status_emoji(status)
        desc = get_status_description(status)
        print(f"   {emoji} {desc}: {count} событий")

    print("\n2. 📋 События пользователя:")
    events = get_user_events(user_id)
    for event in events:
        print(f"   - ID {event['id']}: {event['title']} ({event['status_emoji']} {event['status']})")

    print("\n3. 🎯 Конкретное событие (ID 72):")
    event = get_event_by_id(72, user_id)
    if event:
        print("   Событие найдено:")
        print(f"   - Название: {event['title']}")
        print(f"   - Статус: {event['status_emoji']} {event['status_description']}")
        print(f"   - Место: {event['location_name'] or 'Не указано'}")

        print("\n   📱 Форматированное отображение:")
        formatted = format_event_for_display(event)
        print("   " + "\n   ".join(formatted.split("\n")))

        print("\n   🔘 Кнопки управления:")
        buttons = get_status_change_buttons(event["id"], event["status"])
        for button in buttons:
            print(f"   - {button['text']} ({button['callback_data']})")
    else:
        print("   ❌ Событие не найдено")

    print("\n4. 🔄 Тестируем изменение статуса:")
    if event:
        print(f"   Текущий статус: {event['status']}")

        # Тестируем валидные статусы
        test_statuses = ["closed", "open", "canceled"]
        for new_status in test_statuses:
            if new_status != event["status"]:
                print(f"   Пробуем изменить на: {new_status}")
                success = change_event_status(event["id"], new_status, user_id)
                if success:
                    print(f"   ✅ Статус изменен на {new_status}")
                    # Возвращаем обратно
                    change_event_status(event["id"], "open", user_id)
                    print("   🔄 Возвращен статус 'open'")
                else:
                    print("   ❌ Ошибка изменения статуса")
                break

    print("\n5. 🤖 Тестируем автомодерацию:")
    closed_count = auto_close_events()
    print(f"   Закрыто событий: {closed_count}")

    print("\n6. ✅ Тестируем валидацию статусов:")
    test_statuses = ["open", "closed", "canceled", "active", "draft", "invalid"]
    for status in test_statuses:
        valid = is_valid_status(status)
        emoji = get_status_emoji(status)
        desc = get_status_description(status)
        print(f"   {emoji} '{status}': {'✅' if valid else '❌'} - {desc}")

    print("\n🎉 Тестирование завершено!")
    print("💡 Менеджер статусов работает корректно!")


if __name__ == "__main__":
    main()
