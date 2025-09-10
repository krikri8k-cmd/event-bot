#!/usr/bin/env python3
"""Добавление тестовых событий в базу данных"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text

from api import config


def add_test_events():
    engine = create_engine(config.DATABASE_URL)

    # Тестовые события в Бали
    test_events = [
        {
            "title": "Тестовое событие в Убуде",
            "description": "Описание тестового события",
            "lat": -8.5069,
            "lng": 115.2625,
            "location_name": "Убуд, Бали",
            "source": "test",
            "url": "https://example.com/test1",
            "starts_at": datetime.now(UTC) + timedelta(hours=2),
            "city": "Ubud",
            "country": "ID",
            "organizer_url": "https://example.com/test1",
        },
        {
            "title": "Тестовое событие в Чангу",
            "description": "Ещё одно тестовое событие",
            "lat": -8.6500,
            "lng": 115.2160,
            "location_name": "Чангу, Бали",
            "source": "test",
            "url": "https://example.com/test2",
            "starts_at": datetime.now(UTC) + timedelta(hours=4),
            "city": "Canggu",
            "country": "ID",
            "organizer_url": "https://example.com/test2",
        },
    ]

    with engine.connect() as conn:
        for event in test_events:
            conn.execute(
                text("""
                INSERT INTO events (title, description, lat, lng, location_name, 
                                   source, url, starts_at, organizer_id, current_participants, 
                                   status, is_generated_by_ai, city, country, organizer_url,
                                   created_at, updated_at_utc)
                VALUES (:title, :description, :lat, :lng, :location_name,
                        :source, :url, :starts_at, NULL, 0, 'active', false, :city, :country, :organizer_url,
                        NOW(), NOW())
            """),
                event,
            )

        conn.commit()
        print(f"Added {len(test_events)} test events")


if __name__ == "__main__":
    add_test_events()
