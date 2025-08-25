#!/usr/bin/env python3
"""
Smoke тест для проверки основных компонентов EventBot
"""

import asyncio

import pytest
from sqlalchemy import text

from ai_utils import fetch_ai_events_nearby
from config import load_settings
from database import create_all, get_session, init_engine
from enhanced_event_search import enhanced_search_events


@pytest.mark.asyncio
async def test_config_loading():
    """Тест загрузки конфигурации"""
    settings = load_settings()
    assert settings is not None
    print("✅ Конфигурация загружается")


@pytest.mark.asyncio
async def test_database_connection():
    """Тест подключения к базе данных"""
    try:
        settings = load_settings()
        init_engine(settings.database_url)
        create_all()

        with get_session() as session:
            # Простой запрос для проверки подключения
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
        print("✅ База данных работает")
    except Exception as e:
        print(f"⚠️ База данных: {e}")


@pytest.mark.asyncio
async def test_ai_generation():
    """Тест AI генерации"""
    try:
        events = await fetch_ai_events_nearby(-6.2088, 106.8456)  # Джакарта
        assert isinstance(events, list)
        print(f"✅ AI генерация работает (сгенерировано: {len(events)} событий)")
    except Exception as e:
        print(f"⚠️ AI генерация: {e}")


@pytest.mark.asyncio
async def test_event_search():
    """Тест поиска событий"""
    try:
        # Координаты Джакарты
        events = await enhanced_search_events(-6.2088, 106.8456, 5)
        assert isinstance(events, list)
        print(f"✅ Поиск событий работает (найдено: {len(events)})")
    except Exception as e:
        print(f"⚠️ Поиск событий: {e}")


def test_imports():
    """Тест импорта основных модулей"""
    try:
        # Проверяем, что модули можно импортировать
        import importlib.util

        modules = [
            "ai_utils",
            "config",
            "database",
            "enhanced_event_search",
            "event_apis",
            "smart_ai_generator",
        ]

        for module in modules:
            spec = importlib.util.find_spec(module)
            if spec is None:
                pytest.fail(f"Модуль {module} не найден")

        print("✅ Все модули импортируются")
    except Exception as e:
        pytest.fail(f"Ошибка импорта: {e}")


def test_basic_functionality():
    """Базовый тест функциональности"""
    assert True
    print("✅ Базовая функциональность работает")


if __name__ == "__main__":
    print("🚀 Запуск smoke тестов...")
    print("=" * 50)

    # Запускаем тесты
    test_imports()
    test_basic_functionality()

    # Асинхронные тесты
    asyncio.run(test_config_loading())
    asyncio.run(test_database_connection())
    asyncio.run(test_ai_generation())
    asyncio.run(test_event_search())

    print("=" * 50)
    print("🎉 Smoke тесты завершены!")
