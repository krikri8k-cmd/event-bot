#!/usr/bin/env python3
"""Скрипт запуска сервера для Railway с подробными логами"""

import logging
import os
import sys

import uvicorn

from api.app import create_app

# Настройка логирования: INFO/DEBUG в stdout, ERROR+ в stderr (важно для Railway)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Чистим существующие хендлеры, чтобы не дублировать вывод
if root_logger.handlers:
    root_logger.handlers.clear()

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)

stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.ERROR)

root_logger.addHandler(stdout_handler)
root_logger.addHandler(stderr_handler)

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
