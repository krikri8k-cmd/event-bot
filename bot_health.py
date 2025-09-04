#!/usr/bin/env python3
"""
Простой health check сервер для Telegram бота
Помогает Railway понять, что бот работает
"""

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        logger.info(f"Получен запрос: {self.path}")

        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            response = {
                "status": "healthy",
                "service": "EventBot Telegram Bot",
                "timestamp": time.time(),
                "uptime": "running",
            }

            self.wfile.write(json.dumps(response).encode())
            logger.info("Health check ответ отправлен")

        elif self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            response = {"pong": time.time()}
            self.wfile.write(json.dumps(response).encode())
            logger.info("Ping ответ отправлен")

        else:
            self.send_response(404)
            self.end_headers()
            logger.warning(f"Неизвестный путь: {self.path}")

    def log_message(self, format, *args):
        # Логируем все HTTP запросы
        logger.info(f"HTTP: {format % args}")


class BotHealthServer:
    def __init__(self, port=8000):
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        """Запускает health check сервер в отдельном потоке"""
        try:
            self.server = HTTPServer(("0.0.0.0", self.port), HealthCheckHandler)
            logger.info(f"Health check сервер запущен на порту {self.port}")

            # Запускаем сервер в отдельном потоке
            self.thread = threading.Thread(target=self._run_server, daemon=True)
            self.thread.start()
            logger.info("Health check сервер запущен в фоновом потоке")

            return True
        except Exception as e:
            logger.error(f"Ошибка запуска health check сервера: {e}")
            return False

    def _run_server(self):
        """Запускает сервер в бесконечном цикле"""
        try:
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"Ошибка в health check сервере: {e}")

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
            # Держим основной поток живым
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            health_server.stop()
            print("Health check сервер остановлен")
