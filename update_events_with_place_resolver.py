#!/usr/bin/env python3
"""
Скрипт для ретро-обновления старых событий через PlaceResolver

Обновляет location_name для событий, у которых:
- Есть place_id, но нет location_name
- ИЛИ есть координаты, но нет location_name
"""

import asyncio
import logging
import sys
from datetime import datetime

from sqlalchemy import text

# Устанавливаем UTF-8 для вывода
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Добавляем текущую директорию в путь
sys.path.append(".")

from config import load_settings
from database import get_engine, init_engine
from utils.place_resolver import PlaceResolver

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def update_event_location_name(event_id: int, place_id: str, lat: float, lng: float, engine, resolver):
    """
    Обновляет location_name для одного события через PlaceResolver
    """
    try:
        # Пробуем получить название через PlaceResolver
        place_data = await resolver.resolve(place_id=place_id, lat=lat, lng=lng)

        if place_data and place_data.get("name"):
            new_location_name = place_data["name"]
            new_place_id = place_data.get("place_id") or place_id

            with engine.begin() as conn:
                update_query = text(
                    """
                    UPDATE events
                    SET location_name = :location_name, place_id = :place_id, updated_at_utc = NOW()
                    WHERE id = :event_id
                    """
                )
                conn.execute(
                    update_query,
                    {
                        "location_name": new_location_name,
                        "place_id": new_place_id,
                        "event_id": event_id,
                    },
                )
            logger.info(f"  ✅ Событие {event_id}: обновлено '{new_location_name}' " f"(place_id: {new_place_id})")
            return True
        else:
            logger.warning(f"  ⚠️ Событие {event_id}: PlaceResolver не вернул название")
            return False
    except Exception as e:
        logger.error(f"  ❌ Событие {event_id}: ошибка: {e}")
        return False


async def main():
    print("🔄 Обновление названий мест у событий через PlaceResolver...")
    print(f"⏰ Время запуска: {datetime.now()}\n")

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()
    resolver = PlaceResolver(engine=engine)

    updated_count = 0
    failed_count = 0

    with engine.connect() as conn:
        # Выбираем события, у которых:
        # 1. Есть place_id, но нет location_name или location_name слишком короткое
        # 2. ИЛИ есть координаты, но нет location_name
        select_query = text(
            """
            SELECT id, place_id, lat, lng, location_name, title
            FROM events
            WHERE source = 'baliforum'
            AND (
                (place_id IS NOT NULL AND (
                    location_name IS NULL OR
                    TRIM(location_name) = '' OR
                    LENGTH(TRIM(location_name)) < 5
                ))
                OR
                (place_id IS NULL AND lat IS NOT NULL AND lng IS NOT NULL AND (
                    location_name IS NULL OR
                    TRIM(location_name) = '' OR
                    LENGTH(TRIM(location_name)) < 5
                ))
            )
            AND lat IS NOT NULL AND lng IS NOT NULL
            ORDER BY id DESC
            LIMIT 100
            """
        )
        events_to_update = conn.execute(select_query).fetchall()

    print(f"📊 Найдено событий для обновления: {len(events_to_update)}\n")

    for event in events_to_update:
        event_id, place_id, lat, lng, location_name, title = event
        logger.info(f"🔄 Обрабатываю событие {event_id}: {title}...")
        if await update_event_location_name(event_id, place_id, lat, lng, engine, resolver):
            updated_count += 1
        else:
            failed_count += 1

        # Небольшая задержка, чтобы не перегружать API
        await asyncio.sleep(0.5)

    print(f"\n✅ Обновлено: {updated_count}")
    print(f"❌ Не удалось обновить: {failed_count}")
    print(f"📊 Всего обработано: {len(events_to_update)}")


if __name__ == "__main__":
    asyncio.run(main())
