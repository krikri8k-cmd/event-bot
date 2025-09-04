#!/usr/bin/env python3
"""
Простой health check сервер для Telegram бота
Помогает Railway понять, что бот работает
"""

import logging
import threading
import time

from aiohttp import web

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BotHealthServer:
    def __init__(self, port=8000):
        self.port = port
        self.app = web.Application()
        self.app.router.add_get("/", self.health_check)
        self.app.router.add_get("/health", self.health_check)
        self.app.router.add_get("/ping", self.ping)

    async def health_check(self, request):
        """Основной health check endpoint"""
        return web.json_response(
            {
                "status": "healthy",
                "service": "EventBot Telegram Bot",
                "timestamp": time.time(),
                "uptime": "running",
            }
        )

    async def ping(self, request):
        """Простой ping endpoint для keep-alive"""
        return web.json_response({"pong": time.time()})

    def start(self):
        """Запускает health check сервер в отдельном потоке"""

        def run_server():
            web.run_app(self.app, port=self.port, host="0.0.0.0")

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        logger.info(f"Health check сервер запущен на порту {self.port}")
        return thread


# Глобальный экземпляр для использования в основном боте
health_server = BotHealthServer()

if __name__ == "__main__":
    # Тестовый запуск
    health_server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Health check сервер остановлен")
