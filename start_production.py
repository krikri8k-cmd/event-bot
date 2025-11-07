#!/usr/bin/env python3
"""
Скрипт запуска продакшн версии с автоматизацией
Запускает FastAPI сервер (с ботом) и планировщик автоматизации
"""

import logging
import os
import signal
import sys
from threading import Thread

import uvicorn

from modern_scheduler import start_modern_scheduler

# Настройка логирования для продакшна
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


def main():
    """Главная функция - запускает FastAPI сервер (с ботом) и автоматизацию"""
    logger.info("🎯 === ЗАПУСК ПРОДАКШН ВЕРСИИ ===")
    logger.info("🚀 FastAPI сервер (с Telegram ботом) + 🤖 Автоматизация парсинга")

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

        # Запускаем FastAPI сервер с ботом
        # FastAPI приложение уже включает webhook и health check через webhook_attach.py
        port = int(os.getenv("PORT", "8000"))
        host = os.getenv("HOST", "0.0.0.0")

        logger.info(f"🚀 Запуск FastAPI сервера на {host}:{port}...")
        logger.info("📡 Webhook: /webhook")
        logger.info("🏥 Health check: /health")

        # Запускаем uvicorn с нашим FastAPI приложением
        uvicorn.run(
            "api.app:app",
            host=host,
            port=port,
            proxy_headers=True,
            access_log=False,  # Отключаем access log для производительности
            log_level="info",
        )

    except KeyboardInterrupt:
        logger.info("⏹️ Остановка по Ctrl+C")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback

        logger.error(f"❌ Детали ошибки: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
