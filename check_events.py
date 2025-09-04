#!/usr/bin/env python3
"""Проверка событий в базе данных"""

from sqlalchemy import create_engine, text

from api import config


def check_events():
    engine = create_engine(config.DATABASE_URL)

    with engine.connect() as conn:
        # Общее количество событий
        result = conn.execute(text("SELECT count(*) FROM events"))
        total = result.scalar()
        print(f"Total events: {total}")

        # Последние 10 событий
        if total > 0:
            result = conn.execute(
                text("""
                SELECT title, starts_at, lat, lng, source 
                FROM events 
                ORDER BY created_at DESC 
                LIMIT 10
            """)
            )

            print("\nLast 10 events:")
            for row in result:
                print(f"- {row.title} ({row.source}) at {row.starts_at}")


if __name__ == "__main__":
    check_events()
