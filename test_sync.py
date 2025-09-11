#!/usr/bin/env python3
"""
Тестируем синхронизацию BaliForum
"""

import os

from database import get_engine, init_engine
from ingest import upsert_events
from sources.baliforum import fetch


def test_sync():
    """Тестируем синхронизацию"""
    print("🔍 Тестируем синхронизацию BaliForum...")

    # Инициализируем базу данных
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:GHeScaRnEXJEPRRXpFGJCdTPgcQOtzlw@interchange.proxy.rlwy.net:23764/railway?sslmode=require",
    )
    init_engine(database_url)
    engine = get_engine()

    # Получаем события
    events = fetch(limit=3)
    print(f"📊 Получено {len(events)} событий")

    for i, event in enumerate(events, 1):
        print(f"\n{i}. {event.title}")
        print(f"   starts_at: {event.starts_at}")
        print(f"   lat: {event.lat}, lng: {event.lng}")
        print(f"   source: {event.source}")
        print(f"   external_id: {event.external_id}")

    # Пытаемся вставить
    try:
        inserted_count = upsert_events(events, engine)
        print(f"\n✅ Вставлено {inserted_count} событий")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_sync()
