#!/usr/bin/env python3
"""Скрипт запуска сервера для Railway с подробными логами"""

import logging
import os

import uvicorn

from api.app import create_app

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Главная функция запуска сервера"""
    # Получаем порт из переменной окружения
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"

    logger.info("🚀 Starting EventBot API server...")
    logger.info(f"📡 Server will listen on {host}:{port}")
    logger.info(f"🏥 Health check available at http://{host}:{port}/health")

    # Создаем приложение
    app = create_app()

    # Запускаем сервер
    logger.info("🌐 Starting HTTP server...")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)


if __name__ == "__main__":
    main()
