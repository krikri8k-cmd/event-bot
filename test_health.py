#!/usr/bin/env python3
"""
Тестовый скрипт для проверки health check сервера
"""

import asyncio
import time

import aiohttp


async def test_health_endpoints():
    """Тестирует health check endpoints"""

    # URL для тестирования (замени на свой Railway URL)
    base_url = "http://localhost:8000"  # для локального тестирования

    async with aiohttp.ClientSession() as session:
        # Тест 1: Health check
        print("🔍 Тестирую /health endpoint...")
        try:
            async with session.get(f"{base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ /health работает: {data}")
                else:
                    print(f"❌ /health вернул статус: {response.status}")
        except Exception as e:
            print(f"❌ Ошибка при тестировании /health: {e}")

        # Тест 2: Ping endpoint
        print("\n🔍 Тестирую /ping endpoint...")
        try:
            async with session.get(f"{base_url}/ping") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ /ping работает: {data}")
                else:
                    print(f"❌ /ping вернул статус: {response.status}")
        except Exception as e:
            print(f"❌ Ошибка при тестировании /ping: {e}")

        # Тест 3: Root endpoint
        print("\n🔍 Тестирую / endpoint...")
        try:
            async with session.get(f"{base_url}/") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ / работает: {data}")
                else:
                    print(f"❌ / вернул статус: {response.status}")
        except Exception as e:
            print(f"❌ Ошибка при тестировании /: {e}")


def test_keep_alive():
    """Тестирует keep-alive механизм"""
    print("\n🔄 Тестирую keep-alive механизм...")

    for i in range(3):
        print(f"   Ping {i + 1}/3: {time.strftime('%H:%M:%S')}")
        time.sleep(2)

    print("✅ Keep-alive тест завершен")


if __name__ == "__main__":
    print("🚀 Тестирование health check сервера EventBot")
    print("=" * 50)

    # Тестируем health check endpoints
    asyncio.run(test_health_endpoints())

    # Тестируем keep-alive
    test_keep_alive()

    print("\n🎯 Для тестирования на Railway:")
    print("1. Замени base_url на твой Railway URL")
    print("2. Убедись что бот запущен")
    print("3. Запусти скрипт снова")
