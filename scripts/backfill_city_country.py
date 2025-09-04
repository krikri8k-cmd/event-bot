#!/usr/bin/env python3
"""Backfill city и country для существующих событий"""

import os
import sys
import time

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

from api import config
from api.normalize import reverse_geocode


def backfill_city_country():
    engine = create_engine(config.DATABASE_URL)

    with engine.connect() as conn:
        # Получаем события без city/country
        result = conn.execute(
            text("""
            SELECT id, lat, lng FROM events
            WHERE city IS NULL AND country IS NULL AND lat IS NOT NULL AND lng IS NOT NULL
            LIMIT 500
        """)
        )

        rows = result.fetchall()
        print(f"Found {len(rows)} events to backfill")

        for _id, lat, lng in rows:
            try:
                geo = reverse_geocode(lat, lng)
                if geo.get("city") or geo.get("country"):
                    conn.execute(
                        text("UPDATE events SET city=%s, country=%s WHERE id=%s"),
                        (geo.get("city"), geo.get("country"), _id),
                    )
                    print(
                        f"Updated event {_id}: city={geo.get('city')}, country={geo.get('country')}"
                    )

                time.sleep(1.1)  # не спамить Nominatim

            except Exception as e:
                print(f"Error updating event {_id}: {e}")

        conn.commit()
        print("Backfill completed")


if __name__ == "__main__":
    backfill_city_country()
