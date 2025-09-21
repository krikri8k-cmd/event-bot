#!/usr/bin/env python3
"""
Проверка реальных событий из базы данных
"""

import os

from sqlalchemy import text

from database import get_session, init_engine


def check_real_events():
    # Инициализируем базу данных
    db_url = os.getenv("DATABASE_URL", "sqlite:///event_bot.db")
    init_engine(db_url)

    session = get_session()
    try:
        # Ищем события с реальными username (не "None")
        result = session.execute(
            text("""
            SELECT id, title, organizer_id, organizer_username, status, created_at_utc
            FROM events 
            WHERE organizer_username IS NOT NULL 
            AND organizer_username != "None"
            AND organizer_username != ""
            ORDER BY created_at_utc DESC
            LIMIT 10
        """)
        )

        events_with_username = result.fetchall()

        print("🔍 События с реальными username:")
        print("=" * 70)

        if events_with_username:
            for i, event in enumerate(events_with_username, 1):
                print(f"Событие {i}:")
                print(f"  ID: {event[0]}")
                print(f"  Название: {event[1]}")
                print(f"  Organizer ID: {event[2]}")
                print(f'  Organizer Username: "{event[3]}"')
                print(f"  Статус: {event[4]}")
                print(f"  Создано: {event[5]}")

                # Тестируем нашу логику отображения
                organizer_id = event[2]
                organizer_username = event[3]

                print("\n  🎯 Как будет отображаться автор:")
                if organizer_id and organizer_username and organizer_username != "None":
                    display = f"👤 @{organizer_username}"
                    print(f"    {display}")
                    print("    ✅ Показываем username!")
                else:
                    display = "👤 Автор"
                    print(f"    {display}")
                    print('    ⚠️  Показываем "Автор"')

                print("-" * 50)
        else:
            print("❌ События с реальными username не найдены")

        # Также проверим все события для сравнения
        print("\n📋 Все события (для сравнения):")
        result = session.execute(
            text("""
            SELECT id, title, organizer_id, organizer_username, status
            FROM events 
            WHERE organizer_id IS NOT NULL
            ORDER BY created_at_utc DESC 
            LIMIT 5
        """)
        )

        all_events = result.fetchall()
        for event in all_events:
            print(f"ID {event[0]}: {event[1]}")
            print(f'  Organizer ID: {event[2]}, Username: "{event[3]}"')
            print("-" * 30)

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    print("🔍 Проверка реальных событий с username...")
    print()
    check_real_events()
