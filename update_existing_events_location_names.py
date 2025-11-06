#!/usr/bin/env python3
"""
Скрипт для обновления location_name для существующих событий через reverse geocoding
"""

import asyncio
import logging

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine
from utils.geo_utils import reverse_geocode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def update_events_location_names():
    """Обновляет location_name для событий с пустым location_name, но с координатами"""
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        # Находим события с пустым location_name, но с координатами
        query = text("""
            SELECT id, lat, lng, title, source, location_name
            FROM events
            WHERE (
                location_name IS NULL
                OR location_name = ''
                OR location_name = 'Место не указано'
                OR location_name = 'Локация уточняется'
            )
            AND lat IS NOT NULL AND lng IS NOT NULL
            AND status NOT IN ('closed', 'canceled')
            ORDER BY created_at_utc DESC
            LIMIT 100
        """)

        result = conn.execute(query)
        events = result.fetchall()

        logger.info(f"Найдено {len(events)} событий для обновления")

        updated_count = 0
        failed_count = 0

        for event in events:
            event_id, lat, lng, title, source, current_location = event

            try:
                logger.info(f"Обрабатываем событие {event_id}: {title[:50]}... (source: {source})")

                # Выполняем reverse geocoding
                location_name = await reverse_geocode(lat, lng)

                if location_name:
                    # Обновляем location_name в БД
                    update_query = text("""
                        UPDATE events
                        SET location_name = :location_name,
                            updated_at_utc = NOW()
                        WHERE id = :event_id
                    """)

                    conn.execute(
                        update_query,
                        {"location_name": location_name, "event_id": event_id},
                    )
                    conn.commit()

                    logger.info(f"✅ Обновлено событие {event_id}: '{current_location}' → '{location_name}'")
                    updated_count += 1
                else:
                    logger.warning(f"⚠️ Не удалось получить название места для события {event_id}")
                    failed_count += 1

                # Небольшая задержка, чтобы не перегружать API
                await asyncio.sleep(0.2)

            except Exception as e:
                logger.error(f"❌ Ошибка при обновлении события {event_id}: {e}")
                failed_count += 1
                continue

        logger.info(f"\n{'='*60}")
        logger.info("ИТОГИ:")
        logger.info(f"  ✅ Обновлено: {updated_count}")
        logger.info(f"  ❌ Ошибок: {failed_count}")
        logger.info(f"  📊 Всего обработано: {len(events)}")
        logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(update_events_location_names())
