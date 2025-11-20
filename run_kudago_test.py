#!/usr/bin/env python3
"""
Скрипт для ручного запуска парсера KudaGo для тестирования
"""

import asyncio
import logging
import sys

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


async def main():
    """Запуск парсера KudaGo"""
    try:
        from modern_scheduler import ModernEventScheduler

        logger.info("🎭 === РУЧНОЙ ЗАПУСК ПАРСЕРА KUDAGO ===")
        logger.info("📊 Проверяем работу с TODAY_MAX_EVENTS=400")
        logger.info("")

        scheduler = ModernEventScheduler()

        # Запускаем парсинг KudaGo
        await scheduler.ingest_kudago()

        logger.info("")
        logger.info("✅ === ПАРСИНГ KUDAGO ЗАВЕРШЕН ===")

    except Exception as e:
        logger.error(f"❌ Ошибка при запуске парсера KudaGo: {e}")
        import traceback

        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
