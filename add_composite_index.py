#!/usr/bin/env python3
"""Добавление составного индекса по city и country"""

from sqlalchemy import create_engine, text

from api import config


def add_composite_index():
    engine = create_engine(config.DATABASE_URL)

    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_events_city_country ON events (LOWER(city), country)"
            )
        )
        conn.commit()
        print("Composite index created successfully")


if __name__ == "__main__":
    add_composite_index()
