#!/usr/bin/env python3
"""Проверка новых событий после AI Ingest"""

import os

from dotenv import load_dotenv
from sqlalchemy import text

from database import get_engine, init_engine

# Загружаем переменные окружения
load_dotenv(".env.local")

# Инициализируем engine
database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("❌ DATABASE_URL не найден в .env.local")
    exit(1)

init_engine(database_url)
engine = get_engine()

print("=== ПОСЛЕДНИЕ СОБЫТИЯ (все источники) ===")
q1 = text("""
    select id, title, starts_at, city, country, source, created_at_utc
    from events 
    order by created_at_utc desc 
    limit 15
""")
with engine.begin() as con:
    result = con.execute(q1).fetchall()
    for row in result:
        print(
            f"ID: {row[0]}, Title: {row[1][:50]}..., Time: {row[2]}, City: {row[3]}, Country: {row[4]}, Source: {row[5]}, Created: {row[6]}"
        )

print("\n=== СОБЫТИЯ ПО ИСТОЧНИКАМ ===")
q2 = text("""
    select source, count(*) as count, 
           min(created_at_utc) as oldest, 
           max(created_at_utc) as newest
    from events 
    group by source 
    order by 2 desc
""")
with engine.begin() as con:
    result = con.execute(q2).fetchall()
    for row in result:
        print(f"Source: {row[0]}, Count: {row[1]}, Oldest: {row[2]}, Newest: {row[3]}")

print("\n=== СОБЫТИЯ С AI-ТЕГОМ ===")
q3 = text("""
    select count(*) as ai_events
    from events 
    where source = 'ai'
""")
with engine.begin() as con:
    result = con.execute(q3).fetchone()
    print(f"AI-событий: {result[0]}")

print("\n=== СОБЫТИЯ БЕЗ ГОРОДА/СТРАНЫ ===")
q4 = text("""
    select count(*) as events_without_location
    from events 
    where city is null or country is null
""")
with engine.begin() as con:
    result = con.execute(q4).fetchone()
    print(f"Событий без города/страны: {result[0]}")

print("\n=== ОБЩЕЕ КОЛИЧЕСТВО СОБЫТИЙ ===")
q5 = text("select count(*) as total_events from events")
with engine.begin() as con:
    result = con.execute(q5).fetchone()
    print(f"Всего событий: {result[0]}")
