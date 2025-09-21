#!/usr/bin/env python3
"""
Поиск события с organizer_username = "Fincontro"
"""

import os

from sqlalchemy import text

from database import get_session, init_engine


def find_fincontro_event():
    # Инициализируем базу данных
    db_url = os.getenv("DATABASE_URL", "sqlite:///event_bot.db")
    init_engine(db_url)

    session = get_session()
    try:
        # Ищем событие с username "Fincontro"
        result = session.execute(
            text("""
            SELECT id, title, organizer_id, organizer_username, status, created_at_utc
            FROM events
            WHERE organizer_username LIKE '%Fincontro%'
            OR organizer_username LIKE '%fincontro%'
            OR organizer_username LIKE '%Fin%'
        """)
        )

        fincontro_events = result.fetchall()

        print('🔍 Поиск события с username "Fincontro":')
        print("=" * 60)

        if fincontro_events:
            for event in fincontro_events:
                print("✅ Найдено событие:")
                print(f"  ID: {event[0]}")
                print(f"  Название: {event[1]}")
                print(f"  Organizer ID: {event[2]}")
                print(f'  Organizer Username: "{event[3]}"')
                print(f"  Статус: {event[4]}")
                print(f"  Создано: {event[5]}")

                # Тестируем нашу логику
                print("\n  🎯 Как будет отображаться автор:")
                organizer_id = event[2]
                organizer_username = event[3]

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
            print('❌ Событие с username "Fincontro" не найдено')

            # Проверим все уникальные username в базе
            result = session.execute(
                text("""
                SELECT DISTINCT organizer_username
                FROM events
                WHERE organizer_username IS NOT NULL
                AND organizer_username != "None"
                ORDER BY organizer_username
            """)
            )

            unique_usernames = result.fetchall()
            if unique_usernames:
                print("\n📋 Все уникальные username в базе:")
                for username in unique_usernames:
                    print(f'  "{username[0]}"')
            else:
                print("\n❌ В базе нет событий с реальными username")

        # Проверим общее количество событий
        result = session.execute(text("SELECT COUNT(*) FROM events"))
        total_events = result.fetchone()[0]
        print(f"\n📊 Всего событий в базе: {total_events}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    print("🔍 Поиск события с username 'Fincontro'...")
    print()
    find_fincontro_event()
