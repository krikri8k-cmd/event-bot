#!/usr/bin/env python3
"""
Быстрый запуск EventBot без проблем с портами
"""

import os
import socket
import subprocess
import sys


def find_free_port(start_port=8000):
    """Находит свободный порт"""
    for port in range(start_port, start_port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            continue
    return start_port + 1000


def kill_python_processes():
    """Убивает зависшие Python процессы"""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "python.exe"], capture_output=True, check=False)
        print("✅ Очищены зависшие процессы")
    except Exception:
        print("ℹ️  Процессы не найдены")


def main():
    print("🚀 Запуск EventBot...")

    # 1. Очищаем процессы
    kill_python_processes()

    # 2. Находим свободный порт
    port = find_free_port()
    print(f"🔍 Порт: {port}")

    # 3. Устанавливаем переменные
    os.environ["PORT"] = str(port)
    os.environ["WEBHOOK_URL"] = f"http://127.0.0.1:{port}/webhook"
    os.environ["TELEGRAM_TOKEN"] = "dummy"
    os.environ["ENABLE_BALIFORUM"] = "1"

    print(f"📡 Webhook: {os.environ['WEBHOOK_URL']}")
    print("🌴 Baliforum: включен")
    print("🤖 Запускаем бота...")
    print("   Ctrl+C для остановки")
    print()

    # 4. Запускаем бота
    try:
        subprocess.run([sys.executable, "bot_enhanced_v3.py"])
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
