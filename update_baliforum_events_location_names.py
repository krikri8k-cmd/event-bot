#!/usr/bin/env python3
"""
Скрипт для обновления названий мест у существующих событий от baliforum
Извлекает place_id из location_url и получает название через Places API
"""

import codecs
import sys
from datetime import datetime

# Устанавливаем UTF-8 для Windows
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Добавляем текущую директорию в путь
sys.path.append(".")

import asyncio
import logging

from dotenv import load_dotenv
from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine
from utils.geo_utils import reverse_geocode

load_dotenv("app.local.env")

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def extract_venue_from_title(title: str) -> str | None:
    """Извлекает название места из заголовка события"""
    import re

    # Паттерны для извлечения названия места из заголовка
    # "Событие в Название Места" или "Событие в Название Места на Бали"
    patterns = [
        r"в\s+([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z\s&]+?)" r"(?:\s+на\s+Бали|$|,|\.|\s*—|\s*\d{1,2}:\d{2})",
        r"в\s+([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z\s&]+?)(?:\s*—|\s*\d{1,2}:\d{2}|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            venue = match.group(1).strip()
            # Убираем лишние слова
            venue = re.sub(r"\s+(на|в|для|с|и|или)\s+.*$", "", venue, flags=re.IGNORECASE)
            if len(venue) > 3 and len(venue) < 50:  # Разумная длина
                return venue

    return None


async def get_place_name_from_coordinates(lat: float, lng: float) -> str | None:
    """Получает название места по координатам через reverse geocoding"""
    try:
        name = await reverse_geocode(lat, lng)
        if name:
            logger.info(f"Reverse geocoding для ({lat}, {lng}) вернул: '{name}'")
            return name
        else:
            logger.warning(f"Reverse geocoding для ({lat}, {lng}) вернул None")
    except Exception as e:
        logger.warning(f"Ошибка при reverse geocoding для координат ({lat}, {lng}): {e}")
    return None


async def update_event_location_name(
    event_id: int, title: str, location_url: str, lat: float, lng: float, engine
) -> bool:
    """Обновляет название места для события"""
    try:
        # Сначала пробуем извлечь название из заголовка
        place_name = extract_venue_from_title(title)
        if place_name:
            logger.info(f"Событие {event_id}: извлечено название из title: '{place_name}'")
        else:
            # Если не получилось из title, пробуем reverse geocoding
            place_name = await get_place_name_from_coordinates(lat, lng)
            if place_name:
                logger.info(f"Событие {event_id}: получено название через reverse geocoding: '{place_name}'")

        if not place_name:
            logger.warning(f"Событие {event_id}: не удалось получить название")
            return False

        # Обновляем в БД
        with engine.begin() as conn:
            update_query = text("""
                UPDATE events
                SET location_name = :location_name,
                    updated_at_utc = NOW()
                WHERE id = :event_id
            """)
            result = conn.execute(update_query, {"event_id": event_id, "location_name": place_name})
            logger.info(f"Событие {event_id}: обновлено строк в БД: {result.rowcount}")

        logger.info(f"✅ Обновлено событие {event_id}: '{place_name}'")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления события {event_id}: {e}", exc_info=True)
        return False


async def main():
    """Основная функция"""
    print("🔄 Обновление названий мест у событий от baliforum...")
    print(f"⏰ Время запуска: {datetime.now()}\n")

    # Инициализируем БД
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    # Получаем все события от baliforum с координатами, но без location_name или с некорректным
    with engine.connect() as conn:
        query = text("""
            SELECT id, title, location_url, location_name, lat, lng
            FROM events
            WHERE source = 'baliforum'
            AND lat IS NOT NULL
            AND lng IS NOT NULL
            AND (
                location_name IS NULL
                OR location_name = ''
                OR location_name IN ('Место не указано', 'Локация', 'Место по ссылке', 'Место проведения')
            )
            ORDER BY created_at_utc DESC
        """)
        result = conn.execute(query)
        events = result.fetchall()

    print(f"📊 Найдено событий для обновления: {len(events)}\n")

    if not events:
        print("✅ Все события уже имеют корректные названия мест")
        return

    updated_count = 0
    failed_count = 0

    for event_id, title, location_url, current_location_name, lat, lng in events:
        print(f"🔄 Обрабатываю событие {event_id}: {title[:50]}...")
        if await update_event_location_name(event_id, title, location_url, lat, lng, engine):
            updated_count += 1
        else:
            failed_count += 1

        # Небольшая задержка, чтобы не перегружать API
        await asyncio.sleep(0.1)

    print(f"\n✅ Обновлено: {updated_count}")
    print(f"❌ Не удалось обновить: {failed_count}")
    print(f"📊 Всего обработано: {len(events)}")


if __name__ == "__main__":
    asyncio.run(main())
