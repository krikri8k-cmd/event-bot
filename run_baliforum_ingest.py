#!/usr/bin/env python3
"""
Скрипт для запуска BaliForum парсера
Запускается по расписанию для инжеста событий
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Добавляем текущую директорию в путь
sys.path.append(".")

from database import get_engine, init_engine
from ingest.upsert import upsert_event
from sources.baliforum import fetch
from utils.structured_logging import StructuredLogger


def run_baliforum_ingest():
    """Запуск инжеста BaliForum событий"""
    start_time = datetime.now()

    print(f"🚀 Запуск BaliForum инжеста: {start_time}")

    # Инициализируем БД
    database_url = os.getenv("DATABASE_URL")
    init_engine(database_url)
    engine = get_engine()

    try:
        # Получаем события
        print("📊 Получаем события от BaliForum...")
        events = fetch(limit=100)
        print(f"  Найдено событий: {len(events)}")

        if events:
            # Сохраняем каждое событие
            saved_count = 0
            skipped_no_coords = 0
            errors = 0

            for event in events:
                try:
                    # Проверяем координаты
                    if not event.lat or not event.lng:
                        skipped_no_coords += 1
                        continue

                    row = {
                        "source": "baliforum",
                        "external_id": event.external_id or event.url.split("/")[-1],
                        "url": event.url,
                        "title": event.title,
                        "starts_at": event.starts_at,
                        "ends_at": None,
                        "lat": event.lat,
                        "lng": event.lng,
                        "location_name": "",
                        "location_url": "",
                        "city": "bali",
                        "country": "ID",
                    }

                    upsert_event(engine, row)
                    saved_count += 1

                except Exception as e:
                    print(f"    ❌ Ошибка сохранения события: {e}")
                    errors += 1

            print(f"  Сохранено событий: {saved_count}")
            print(f"  Пропущено без координат: {skipped_no_coords}")
            print(f"  Ошибок: {errors}")

            # Логируем результат
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            StructuredLogger.log_ingest(
                source="baliforum",
                region="bali",
                parsed=len(events),
                skipped_no_time=0,  # BaliForum парсер уже фильтрует
                skipped_no_coords=skipped_no_coords,
                upserted=saved_count,
                updated=0,
                duration_ms=duration_ms,
                errors=errors,
            )

        else:
            print("  ❌ Нет событий для сохранения")

    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()

        # Логируем ошибку
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        StructuredLogger.log_ingest(
            source="baliforum",
            region="bali",
            parsed=0,
            skipped_no_time=0,
            skipped_no_coords=0,
            upserted=0,
            updated=0,
            duration_ms=duration_ms,
            errors=1,
        )


if __name__ == "__main__":
    load_dotenv("app.local.env")
    run_baliforum_ingest()
