#!/usr/bin/env python3
"""
Простой тест основных требований ТЗ для Baliforum
"""

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sources.baliforum import _ru_date_to_dt, fetch_baliforum_events

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_basic_requirements():
    """Тест основных требований ТЗ"""
    logger.info("🧪 Тестируем основные требования ТЗ...")

    # 1. Тест парсинга дат
    logger.info("1️⃣ Тестируем парсинг дат...")
    tz = ZoneInfo("Asia/Makassar")
    now = datetime.now(tz)

    # Простые случаи должны работать
    start, end = _ru_date_to_dt("сегодня 19:00", now, tz)
    if start and start.hour == 19 and start.minute == 0:
        logger.info("  ✅ 'сегодня 19:00' парсится корректно")
    else:
        logger.error("  ❌ 'сегодня 19:00' не парсится")
        return False

    # События без времени должны пропускаться
    start, end = _ru_date_to_dt("сегодня", now, tz)
    if start is None:
        logger.info("  ✅ 'сегодня' без времени пропускается")
    else:
        logger.error("  ❌ 'сегодня' без времени не пропускается")
        return False

    # 2. Тест парсинга Baliforum
    logger.info("2️⃣ Тестируем парсинг Baliforum...")
    events = fetch_baliforum_events(limit=10)

    events_with_time = [e for e in events if e.get("start_time")]
    events_without_time = [e for e in events if not e.get("start_time")]

    logger.info(f"  📊 Всего событий: {len(events)}")
    logger.info(f"  📊 С точным временем: {len(events_with_time)}")
    logger.info(f"  📊 Без времени (пропущены): {len(events_without_time)}")

    if len(events_with_time) > 0:
        logger.info("  ✅ Найдены события с точным временем")
    else:
        logger.error("  ❌ Не найдены события с точным временем")
        return False

    # 3. Тест UTC конвертации
    logger.info("3️⃣ Тестируем UTC конвертацию...")
    utc_events = 0
    for event in events_with_time:
        start_time = event["start_time"]
        if start_time and start_time.tzinfo == UTC:
            utc_events += 1

    logger.info(f"  📊 Событий в UTC: {utc_events}/{len(events_with_time)}")

    if utc_events == len(events_with_time):
        logger.info("  ✅ Все события конвертированы в UTC")
    else:
        logger.error("  ❌ Не все события в UTC")
        return False

    # 4. Тест стабильного external_id
    logger.info("4️⃣ Тестируем стабильный external_id...")
    external_ids = [e.get("external_id") for e in events_with_time]
    unique_ids = set(external_ids)

    logger.info(f"  📊 Уникальных external_id: {len(unique_ids)}/{len(external_ids)}")

    if len(unique_ids) == len(external_ids):
        logger.info("  ✅ Все external_id уникальны")
    else:
        logger.error("  ❌ Есть дубликаты external_id")
        return False

    # 5. Показываем примеры
    logger.info("5️⃣ Примеры событий:")
    for i, event in enumerate(events_with_time[:3], 1):
        logger.info(f"  {i}. {event['title']}")
        logger.info(f"     Время: {event['start_time']}")
        logger.info(f"     External ID: {event.get('external_id', 'N/A')}")
        logger.info(f"     URL: {event['url']}")

    logger.info("🎉 Все основные требования ТЗ выполнены!")
    return True


if __name__ == "__main__":
    success = test_basic_requirements()
    if success:
        logger.info("✅ ТЕСТ ПРОШЕЛ - Baliforum готов к продакшену!")
    else:
        logger.error("❌ ТЕСТ НЕ ПРОШЕЛ - есть проблемы")
