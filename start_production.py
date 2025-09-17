#!/usr/bin/env python3
"""
Скрипт запуска продакшн версии с автоматизацией
Запускает бота и планировщик автоматизации
"""

import asyncio
import logging
import signal
import sys
from threading import Thread

from modern_scheduler import start_modern_scheduler

# Настройка логирования для продакшена
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("automation.log", encoding="utf-8")],
)

logger = logging.getLogger(__name__)


def start_automation():
    """Запуск автоматизации в отдельном потоке"""
    try:
        logger.info("🚀 Запуск автоматизации парсинга...")
        start_modern_scheduler()

        # Держим поток живым
        import time

        while True:
            time.sleep(60)

    except Exception as e:
        logger.error(f"❌ Ошибка автоматизации: {e}")
        raise


def start_bot():
    """Запуск телеграм бота"""
    try:
        logger.info("🤖 Запуск Telegram бота...")

        # Импортируем и запускаем бота
        from bot_enhanced_v3 import main as bot_main

        asyncio.run(bot_main())

    except Exception as e:
        logger.error(f"❌ Ошибка бота: {e}")
        raise


def main():
    """Главная функция - запускает и бота и автоматизацию"""
    logger.info("🎯 === ЗАПУСК ПРОДАКШН ВЕРСИИ ===")
    logger.info("🤖 Telegram бот + 🚀 Автоматизация парсинга")

    # Graceful shutdown handler
    def signal_handler(sig, frame):
        logger.info("⏹️ Получен сигнал остановки...")
        logger.info("✅ Завершение работы")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Запускаем автоматизацию в отдельном потоке
        automation_thread = Thread(target=start_automation, daemon=True)
        automation_thread.start()
        logger.info("✅ Автоматизация запущена в фоне")

        # Запускаем бота в основном потоке
        start_bot()

    except KeyboardInterrupt:
        logger.info("⏹️ Остановка по Ctrl+C")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
