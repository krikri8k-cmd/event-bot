#!/usr/bin/env python3
"""
Скрипт для добавления локаций в таблицу task_places из Google Maps ссылок

Использование:
    python scripts/add_places_from_google_links.py

Формат входных данных (можно ввести интерактивно или через файл):
    category,place_type,region,name,google_maps_url,description

Пример:
    body,cafe,moscow,Кофейня на Арбате,https://maps.google.com/...,Уютная кофейня
    body,park,spb,Парк Победы,https://maps.google.com/...,Красивый парк
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from database import TaskPlace, get_session, init_engine
from tasks_location_service import get_user_region
from utils.geo_utils import parse_google_maps_link

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)


def extract_coordinates_from_url(google_maps_url: str) -> tuple[float, float] | None:
    """
    Извлекает координаты из Google Maps ссылки

    Args:
        google_maps_url: Ссылка на Google Maps

    Returns:
        Кортеж (lat, lng) или None
    """
    import asyncio

    # Создаем event loop для асинхронной функции
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(parse_google_maps_link(google_maps_url))
        if result and result.get("lat") and result.get("lng"):
            return result["lat"], result["lng"]
    finally:
        loop.close()

    return None


def add_place(
    category: str,
    place_type: str,
    region: str,
    name: str,
    google_maps_url: str,
    description: str | None = None,
) -> bool:
    """
    Добавляет место в базу данных

    Args:
        category: Категория ('body', 'spirit', etc.)
        place_type: Тип места ('cafe', 'park', 'gym', etc.)
        region: Регион ('moscow', 'spb', 'bali', etc.)
        name: Название места
        google_maps_url: Ссылка на Google Maps
        description: Описание места (опционально)

    Returns:
        True если место добавлено успешно
    """
    # Извлекаем координаты из ссылки
    coords = extract_coordinates_from_url(google_maps_url)
    if not coords:
        print(f"❌ Не удалось извлечь координаты из ссылки: {google_maps_url}")
        return False

    lat, lng = coords

    # Если регион не указан, определяем по координатам
    if not region or region == "auto":
        region = get_user_region(lat, lng)

    with get_session() as session:
        # Проверяем, не существует ли уже такое место
        existing = (
            session.query(TaskPlace)
            .filter(
                TaskPlace.name == name,
                TaskPlace.category == category,
                TaskPlace.place_type == place_type,
                TaskPlace.region == region,
            )
            .first()
        )

        if existing:
            print(f"⚠️ Место уже существует: {name} (ID: {existing.id})")
            return False

        # Создаем новое место
        place = TaskPlace(
            category=category,
            place_type=place_type,
            region=region,
            name=name,
            description=description,
            lat=lat,
            lng=lng,
            google_maps_url=google_maps_url,
            is_active=True,
        )

        session.add(place)
        session.flush()  # Получаем ID места для генерации подсказки

        # Генерируем подсказку с помощью AI
        try:
            from tasks.ai_hints_generator import generate_hint_for_place

            if generate_hint_for_place(place):
                print(f"   🤖 Сгенерирована подсказка: {place.task_hint[:50]}...")
        except Exception as e:
            print(f"   ⚠️ Не удалось сгенерировать подсказку: {e}")

        session.commit()

        print(f"✅ Добавлено место: {name} ({region}, {place_type}) - {lat}, {lng}")
        return True


def add_places_from_file(file_path: str) -> None:
    """
    Добавляет места из CSV файла

    Формат файла (CSV):
    category,place_type,region,name,google_maps_url,description
    """
    import csv

    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            add_place(
                category=row["category"],
                place_type=row["place_type"],
                region=row.get("region", "auto"),
                name=row["name"],
                google_maps_url=row["google_maps_url"],
                description=row.get("description"),
            )


def interactive_add() -> None:
    """Интерактивное добавление мест"""
    print("📍 Добавление локаций в базу данных")
    print("=" * 50)

    while True:
        print("\nВведите данные места (или 'q' для выхода):")

        category = input("Категория (body/spirit/career/social): ").strip()
        if category.lower() == "q":
            break

        place_type = input("Тип места (cafe/park/gym/temple/etc): ").strip()
        if place_type.lower() == "q":
            break

        region = input("Регион (moscow/spb/bali/jakarta/auto): ").strip() or "auto"
        if region.lower() == "q":
            break

        name = input("Название места: ").strip()
        if name.lower() == "q":
            break

        google_maps_url = input("Google Maps ссылка: ").strip()
        if google_maps_url.lower() == "q":
            break

        description = input("Описание (опционально): ").strip() or None

        if add_place(category, place_type, region, name, google_maps_url, description):
            print("✅ Место добавлено!")
        else:
            print("❌ Ошибка при добавлении места")


def main():
    """Основная функция"""
    # Инициализируем БД
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        print("   Убедитесь, что файл app.local.env существует и содержит DATABASE_URL")
        sys.exit(1)

    init_engine(db_url)

    # Если передан файл как аргумент
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if os.path.exists(file_path):
            print(f"📄 Загружаю места из файла: {file_path}")
            add_places_from_file(file_path)
        else:
            print(f"❌ Файл не найден: {file_path}")
            sys.exit(1)
    else:
        # Интерактивный режим
        interactive_add()


if __name__ == "__main__":
    main()
