#!/usr/bin/env python3
"""
Простой health check сервер для Telegram бота
Помогает Railway понять, что бот работает
"""

import json
import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            response = {
                "status": "healthy",
                "service": "EventBot Telegram Bot",
                "timestamp": time.time(),
                "uptime": "running",
            }

            self.wfile.write(json.dumps(response).encode())

        elif self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            response = {"pong": time.time()}
            self.wfile.write(json.dumps(response).encode())

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Отключаем логирование HTTP запросов
        pass


class BotHealthServer:
    def __init__(self, port=8000):
        self.port = port
        self.server = None

    def start(self):
        """Запускает health check сервер"""
        try:
            self.server = HTTPServer(("0.0.0.0", self.port), HealthCheckHandler)
            logger.info(f"Health check сервер запущен на порту {self.port}")
            return True
        except Exception as e:
            logger.error(f"Ошибка запуска health check сервера: {e}")
            return False

    def stop(self):
        """Останавливает health check сервер"""
        if self.server:
            self.server.shutdown()
            logger.info("Health check сервер остановлен")


# Глобальный экземпляр для использования в основном боте
health_server = BotHealthServer()

if __name__ == "__main__":
    # Тестовый запуск
    if health_server.start():
        try:
            health_server.server.serve_forever()
        except KeyboardInterrupt:
            health_server.stop()
            print("Health check сервер остановлен")
