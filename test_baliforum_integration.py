#!/usr/bin/env python3
"""
Тест интеграции Baliforum в enhanced_event_search
"""

import asyncio
import logging

from enhanced_event_search import enhanced_search_events

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def test_baliforum_integration():
    """Тестируем интеграцию Baliforum"""
    logger.info("🧪 Тестируем интеграцию Baliforum...")

    # Координаты Бали
    lat = -8.6500
    lng = 115.2167
    radius_km = 15

    try:
        # Запускаем поиск
        events = await enhanced_search_events(lat, lng, radius_km)

        logger.info(f"📊 Всего найдено событий: {len(events)}")

        # Фильтруем события из Baliforum
        baliforum_events = [e for e in events if e.get("source") == "baliforum"]

        logger.info(f"🌴 Событий из Baliforum: {len(baliforum_events)}")

        # Показываем первые 3 события из Baliforum
        for i, event in enumerate(baliforum_events[:3], 1):
            logger.info(f"  {i}. {event.get('title', 'Без названия')}")
            logger.info(f"     Время: {event.get('time_local', 'Не указано')}")
            logger.info(f"     URL: {event.get('source_url', 'Не указан')}")
            logger.info(f"     Координаты: {event.get('lat', 'N/A')}, {event.get('lng', 'N/A')}")
            logger.info("")

        if baliforum_events:
            logger.info("✅ Интеграция Baliforum работает!")
        else:
            logger.warning("⚠️ События из Baliforum не найдены")

    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_baliforum_integration())
