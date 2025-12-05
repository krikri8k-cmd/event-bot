#!/usr/bin/env python3
"""
Простой скрипт для добавления локаций из CSV файла

Использование:
    python scripts/add_places_simple.py places_template.csv

Формат CSV:
    category,place_type,region,name,google_maps_url,description

    category: body, spirit, career, social
    place_type: cafe, park, gym, temple, viewpoint, yoga_studio, beach, etc.
    region: moscow, spb, bali, jakarta, или auto (определится автоматически)
    name: Название места
    google_maps_url: Ссылка на Google Maps
    description: Описание (опционально)
"""

import csv
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


async def extract_coordinates_async(google_maps_url: str) -> tuple[float, float] | None:
    """Извлекает координаты из Google Maps ссылки (асинхронно)"""
    result = await parse_google_maps_link(google_maps_url)
    if result and result.get("lat") and result.get("lng"):
        return result["lat"], result["lng"]
    return None


def extract_coordinates(google_maps_url: str) -> tuple[float, float] | None:
    """Извлекает координаты из Google Maps ссылки"""
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(extract_coordinates_async(google_maps_url))
    finally:
        loop.close()


def add_place_from_row(row: dict) -> bool:
    """Добавляет место из строки CSV"""
    category = row["category"].strip()
    place_type = row["place_type"].strip()
    region = row.get("region", "auto").strip()
    name = row["name"].strip()
    google_maps_url = row["google_maps_url"].strip()
    description = row.get("description", "").strip() or None

    if not all([category, place_type, name, google_maps_url]):
        print("❌ Пропущена строка: не все поля заполнены")
        return False

    # Извлекаем координаты
    print(f"📍 Обрабатываю: {name}...")
    coords = extract_coordinates(google_maps_url)
    if not coords:
        print(f"❌ Не удалось извлечь координаты из: {google_maps_url}")
        return False

    lat, lng = coords

    # Определяем регион, если не указан
    if not region or region.lower() == "auto":
        region = get_user_region(lat, lng)
        print(f"   Регион определен автоматически: {region}")

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

        print(f"✅ Добавлено: {name} ({region}, {place_type}) - {lat:.6f}, {lng:.6f}")
        return True


def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование: python scripts/add_places_simple.py <csv_file>")
        print("\nПример:")
        print("  python scripts/add_places_simple.py places_template.csv")
        sys.exit(1)

    csv_file = sys.argv[1]

    if not os.path.exists(csv_file):
        print(f"❌ Файл не найден: {csv_file}")
        sys.exit(1)

    # Инициализируем БД
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        print("   Убедитесь, что файл app.local.env существует и содержит DATABASE_URL")
        sys.exit(1)

    init_engine(db_url)

    # Читаем CSV и добавляем места
    print(f"📄 Загружаю места из файла: {csv_file}\n")

    added_count = 0
    skipped_count = 0

    with open(csv_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):  # Начинаем с 2, т.к. первая строка - заголовок
            try:
                if add_place_from_row(row):
                    added_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                print(f"❌ Ошибка в строке {row_num}: {e}")
                skipped_count += 1

    print("\n✅ Готово!")
    print(f"   Добавлено: {added_count}")
    print(f"   Пропущено: {skipped_count}")


if __name__ == "__main__":
    main()
