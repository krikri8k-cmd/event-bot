#!/usr/bin/env python3
"""
Скрипт для ручного запуска парсера событий
Работает в Windows без проблем с кодировкой
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Устанавливаем UTF-8 для Windows
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Добавляем текущую директорию в путь
sys.path.append(".")

from database import get_engine, init_engine
from sources.baliforum import fetch
from utils.structured_logging import StructuredLogger
from utils.unified_events_service import UnifiedEventsService


def run_ingest():
    """Запуск инжеста событий"""
    start_time = datetime.now()

    print(f"[*] Запуск парсера событий: {start_time}")

    # Инициализируем БД
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[!] Ошибка: DATABASE_URL не установлен")
        print("[!] Убедитесь, что файл app.local.env существует и содержит DATABASE_URL")
        return

    init_engine(database_url)
    engine = get_engine()
    service = UnifiedEventsService(engine)

    try:
        # Получаем события от BaliForum
        print("[*] Получаем события от BaliForum...")
        events = fetch(limit=100)
        print(f"[*] Найдено событий: {len(events)}")

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

                    # Сохраняем через UnifiedEventsService
                    event_id = service.save_parser_event(
                        source="baliforum",
                        external_id=event.external_id or event.url.split("/")[-1],
                        title=event.title,
                        description=event.description,
                        starts_at_utc=event.starts_at,
                        city="bali",
                        lat=event.lat,
                        lng=event.lng,
                        location_name=event.description or "",
                        location_url="",
                        url=event.url,
                    )

                    if event_id:
                        saved_count += 1
                        print(f"[+] Сохранено: {event.title[:50]}")

                except Exception as e:
                    print(f"[-] Ошибка сохранения события: {e}")
                    errors += 1

            print(f"[*] Сохранено событий: {saved_count}")
            print(f"[*] Пропущено без координат: {skipped_no_coords}")
            print(f"[*] Ошибок: {errors}")

            # Логируем результат
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            StructuredLogger.log_ingest(
                source="baliforum",
                region="bali",
                parsed=len(events),
                skipped_no_time=0,
                skipped_no_coords=skipped_no_coords,
                upserted=saved_count,
                updated=0,
                duration_ms=duration_ms,
                errors=errors,
            )

        else:
            print("[!] Нет событий для сохранения")

        print(f"[*] Парсинг завершен за {(datetime.now() - start_time).total_seconds():.1f}с")

    except Exception as e:
        print(f"[!] Ошибка: {e}")
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
    # Загружаем переменные окружения
    env_file = "app.local.env"
    if not os.path.exists(env_file):
        env_file = ".env"
    load_dotenv(env_file)

    run_ingest()
