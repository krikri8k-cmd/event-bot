#!/usr/bin/env python3
"""Делаем organizer_id nullable"""

from sqlalchemy import create_engine, text

from api import config


def fix_organizer_nullable():
    engine = create_engine(config.DATABASE_URL)

    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE events ALTER COLUMN organizer_id DROP NOT NULL"))
        conn.commit()
        print("organizer_id made nullable")


if __name__ == "__main__":
    fix_organizer_nullable()
