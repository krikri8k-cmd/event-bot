#!/usr/bin/env python3
"""Проверка типа колонки starts_at в events_community"""

from sqlalchemy import text

from database import get_engine

engine = get_engine()
with engine.connect() as conn:
    result = conn.execute(
        text(
            """
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name='events_community' AND column_name='starts_at'
        """
        )
    )
    row = result.fetchone()
    if row:
        print(f"Column: {row[0]}, Type: {row[1]}")
        if row[1] == "timestamp without time zone":
            print("✅ Миграция применена успешно! Тип колонки: TIMESTAMP WITHOUT TIME ZONE")
        else:
            print(f"⚠️ Тип колонки: {row[1]} (ожидался: timestamp without time zone)")
    else:
        print("❌ Колонка не найдена")
