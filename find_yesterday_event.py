#!/usr/bin/env python3
"""Поиск события, созданного вчера"""

import os
from datetime import datetime, timedelta

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

print("🔍 Ищем событие, созданное вчера...")
print("=" * 60)

# Получаем вчерашнюю дату
yesterday = datetime.now() - timedelta(days=1)
yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

print(
    f"📅 Ищем события с {yesterday_start.strftime('%Y-%m-%d %H:%M:%S')} "
    f"по {yesterday_end.strftime('%Y-%m-%d %H:%M:%S')}"
)

# Запрос для поиска событий, созданных вчера
query = text("""
    SELECT
        id,
        title,
        description,
        starts_at,
        location_name,
        organizer_username,
        source,
        created_at_utc,
        status
    FROM events
    WHERE created_at_utc >= :start_date
      AND created_at_utc <= :end_date
    ORDER BY created_at_utc DESC
""")

with engine.begin() as con:
    result = con.execute(query, {"start_date": yesterday_start, "end_date": yesterday_end}).fetchall()

    if result:
        print(f"🎉 Найдено {len(result)} событий, созданных вчера:")
        print("-" * 60)

        for row in result:
            print(f"🆔 ID: {row[0]}")
            print(f"📝 Название: {row[1]}")
            if row[2]:  # description
                print(f"📄 Описание: {row[2][:100]}{'...' if len(row[2]) > 100 else ''}")
            print(f"⏰ Время начала: {row[3]}")
            print(f"📍 Место: {row[4] or 'Не указано'}")
            print(f"👤 Организатор: {row[5] or 'Не указан'}")
            print(f"🔗 Источник: {row[6] or 'Не указан'}")
            print(f"📅 Создано: {row[7]}")
            print(f"📊 Статус: {row[8]}")
            print("-" * 60)
    else:
        print("😔 События, созданные вчера, не найдены.")

        # Покажем последние 10 событий для справки
        print("\n🔍 Последние 10 событий в базе:")
        recent_query = text("""
            SELECT
                id,
                title,
                created_at_utc,
                organizer_username,
                source
            FROM events
            ORDER BY created_at_utc DESC
            LIMIT 10
        """)

        recent_result = con.execute(recent_query).fetchall()
        for row in recent_result:
            print(f"🆔 {row[0]} | 📝 {row[1][:50]}... | 📅 {row[2]} | 👤 {row[3] or 'N/A'} | 🔗 {row[4] or 'N/A'}")

print("\n💡 Совет: Если событие не найдено, проверь:")
print("   - Правильно ли настроена временная зона")
print("   - Возможно, событие было создано в другой день")
print("   - Проверь статус события (draft/published)")
