#!/usr/bin/env python3
"""Проверка конкретного события пользователя"""

import os

from dotenv import load_dotenv
from sqlalchemy import text

from database import get_engine, init_engine

# Загружаем переменные окружения
load_dotenv("app.local.env")

# Инициализируем engine
database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("❌ DATABASE_URL не найден в app.local.env")
    exit(1)

init_engine(database_url)
engine = get_engine()

print("🔍 Проверяем твое событие...")
print("=" * 60)

# Сначала проверим пользователя Fincontro
print("👤 Ищем пользователя Fincontro:")
user_query = text("""
    SELECT 
        id,
        username,
        full_name,
        events_created_ids,
        created_at_utc
    FROM users 
    WHERE username = 'Fincontro' OR full_name LIKE '%Fincontro%'
""")

with engine.begin() as con:
    user_result = con.execute(user_query).fetchall()

    if user_result:
        for user in user_result:
            print(f"🆔 ID пользователя: {user[0]}")
            print(f"👤 Username: {user[1]}")
            print(f"📝 Полное имя: {user[2]}")
            print(f"📋 Созданные события: {user[3]}")
            print(f"📅 Дата регистрации: {user[4]}")
            print("-" * 40)

            user_id = user[0]

            # Теперь ищем события этого пользователя
            print(f"\n🎯 Ищем события пользователя ID {user_id}:")
            events_query = text("""
                SELECT 
                    id,
                    title,
                    description,
                    starts_at,
                    location_name,
                    organizer_id,
                    organizer_username,
                    source,
                    created_at_utc,
                    updated_at_utc,
                    status,
                    is_generated_by_ai
                FROM events 
                WHERE organizer_id = :user_id
                ORDER BY created_at_utc DESC
            """)

            events_result = con.execute(events_query, {"user_id": user_id}).fetchall()

            if events_result:
                print(f"🎉 Найдено {len(events_result)} событий:")
                for event in events_result:
                    print(f"🆔 ID события: {event[0]}")
                    print(f"📝 Название: {event[1]}")
                    print(f"📄 Описание: {event[2] or 'Нет описания'}")
                    print(f"⏰ Время начала: {event[3] or 'Не указано'}")
                    print(f"📍 Место: {event[4] or 'Не указано'}")
                    print(f"👤 ID организатора: {event[5]}")
                    print(f"👤 Username организатора: {event[6]}")
                    print(f"🔗 Источник: {event[7] or 'Не указан'}")
                    print(f"📅 Создано: {event[8]}")
                    print(f"🔄 Обновлено: {event[9]}")
                    print(f"📊 Статус: {event[10]}")
                    print(f"🤖 AI-событие: {event[11]}")
                    print("-" * 40)
            else:
                print("😔 События этого пользователя не найдены.")

                # Проверим, есть ли события с username организатора
                print(f"\n🔍 Ищем события по username организатора '{user[1]}':")
                username_events_query = text("""
                    SELECT 
                        id,
                        title,
                        organizer_username,
                        created_at_utc,
                        status
                    FROM events 
                    WHERE organizer_username = :username
                    ORDER BY created_at_utc DESC
                """)

                username_events = con.execute(username_events_query, {"username": user[1]}).fetchall()
                if username_events:
                    print(f"🎉 Найдено {len(username_events)} событий по username:")
                    for event in username_events:
                        print(f"🆔 {event[0]} | 📝 {event[1]} | 👤 {event[2]} | 📅 {event[3]} | 📊 {event[4]}")
                else:
                    print("😔 События по username тоже не найдены.")
    else:
        print("😔 Пользователь Fincontro не найден.")

        # Покажем всех пользователей для справки
        print("\n👥 Все пользователи в системе:")
        all_users_query = text("""
            SELECT id, username, full_name, created_at_utc
            FROM users 
            ORDER BY created_at_utc DESC
            LIMIT 10
        """)

        all_users = con.execute(all_users_query).fetchall()
        for user in all_users:
            print(f"🆔 {user[0]} | 👤 {user[1]} | 📝 {user[2]} | 📅 {user[3]}")

# Теперь проверим событие ID 72 напрямую
print("\n🎯 Проверяем событие ID 72 напрямую:")
direct_query = text("""
    SELECT 
        id,
        title,
        description,
        organizer_id,
        organizer_username,
        created_at_utc,
        status,
        source
    FROM events 
    WHERE id = 72
""")

with engine.begin() as con:
    direct_result = con.execute(direct_query).fetchone()

    if direct_result:
        print("✅ Событие ID 72 существует:")
        print(f"🆔 ID: {direct_result[0]}")
        print(f"📝 Название: {direct_result[1]}")
        print(f"📄 Описание: {direct_result[2] or 'Нет описания'}")
        print(f"👤 ID организатора: {direct_result[3]}")
        print(f"👤 Username организатора: {direct_result[4]}")
        print(f"📅 Создано: {direct_result[5]}")
        print(f"📊 Статус: {direct_result[6]}")
        print(f"🔗 Источник: {direct_result[7] or 'Не указан'}")

        # Проверим, существует ли пользователь-организатор
        if direct_result[3]:
            org_query = text("SELECT id, username, full_name FROM users WHERE id = :org_id")
            org_result = con.execute(org_query, {"org_id": direct_result[3]}).fetchone()
            if org_result:
                print(f"👤 Организатор найден: ID {org_result[0]}, Username: {org_result[1]}, Имя: {org_result[2]}")
            else:
                print("❌ Организатор не найден в таблице users!")
    else:
        print("❌ Событие ID 72 не найдено!")

print("\n💡 Возможные причины, почему событие не видно в интерфейсе:")
print("   1. Интерфейс Railway может показывать не все записи")
print("   2. Возможна проблема с пагинацией")
print("   3. Событие может быть в статусе 'draft'")
print("   4. Возможны проблемы с отображением в веб-интерфейсе")
