#!/usr/bin/env python3
"""
Утилита для автоматического управления портами
"""

import os
import socket
import subprocess
import sys


def find_free_port(start_port: int = 8000, max_attempts: int = 100) -> int:
    """
    Находит свободный порт начиная с start_port

    Args:
        start_port: Начальный порт для поиска
        max_attempts: Максимальное количество попыток

    Returns:
        Номер свободного порта
    """
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            continue

    # Если не нашли свободный порт, возвращаем случайный
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


def kill_processes_on_port(port: int) -> bool:
    """
    Убивает процессы, занимающие указанный порт (Windows)

    Args:
        port: Номер порта

    Returns:
        True если процессы были убиты, False если не найдены
    """
    try:
        # Находим PID процесса на порту
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, check=True)

        for line in result.stdout.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    try:
                        subprocess.run(["taskkill", "/PID", pid, "/F"], check=True)
                        print(f"✅ Убит процесс {pid} на порту {port}")
                        return True
                    except subprocess.CalledProcessError:
                        continue

        return False
    except Exception as e:
        print(f"⚠️ Ошибка при поиске процессов на порту {port}: {e}")
        return False


def setup_environment(port: int, mode: str = "bot") -> None:
    """
    Настраивает переменные окружения для запуска

    Args:
        port: Номер порта
        mode: Режим запуска ("bot" или "api")
    """
    os.environ["PORT"] = str(port)

    if mode == "bot":
        os.environ["WEBHOOK_URL"] = f"http://127.0.0.1:{port}/webhook"
        os.environ["TELEGRAM_TOKEN"] = "dummy"  # Для локальной разработки
        os.environ["ENABLE_BALIFORUM"] = "1"
        print(f"🤖 Bot mode: PORT={port}, WEBHOOK_URL={os.environ['WEBHOOK_URL']}")
    elif mode == "api":
        os.environ["DATABASE_URL"] = (
            "postgresql://postgres:GHeScaRnEXJEPRRXpFGJCdTPgcQOtzlw@interchange.proxy.rlwy.net:23764/railway?sslmode=require"
        )
        os.environ["ENABLE_BALIFORUM"] = "1"
        print(f"🌐 API mode: PORT={port}, API_URL=http://127.0.0.1:{port}")


def main():
    """Главная функция для запуска из командной строки"""
    if len(sys.argv) < 2:
        print("Использование: python port_manager.py <bot|api> [start_port]")
        sys.exit(1)

    mode = sys.argv[1]
    start_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000

    print(f"🚀 Запуск в режиме {mode}...")

    # Убиваем процессы на стартовом порту
    if kill_processes_on_port(start_port):
        print(f"🧹 Очищен порт {start_port}")

    # Находим свободный порт
    free_port = find_free_port(start_port)
    print(f"🔍 Найден свободный порт: {free_port}")

    # Настраиваем окружение
    setup_environment(free_port, mode)

    print("✅ Готово! Переменные окружения установлены.")


if __name__ == "__main__":
    main()
