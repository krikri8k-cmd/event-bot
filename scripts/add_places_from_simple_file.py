#!/usr/bin/env python3
"""
Упрощенный скрипт для добавления локаций из простого текстового файла

Формат файла:
    # Комментарии начинаются с #
    category:place_type:region
    https://maps.google.com/ссылка1
    https://maps.google.com/ссылка2
    https://maps.google.com/ссылка3

    category:place_type:region
    https://maps.google.com/ссылка4
    ...

Использование:
    python scripts/add_places_from_simple_file.py places_simple.txt
"""

import os
import re
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


def extract_place_name_from_url(url: str) -> str:
    """Пытается извлечь название места из URL"""
    # Пробуем найти название в URL
    # Например: /place/Название+Места/...
    match = re.search(r"/place/([^/@]+)", url)
    if match:
        name = match.group(1).replace("+", " ").replace("%20", " ")
        # Декодируем URL-кодированные символы
        try:
            from urllib.parse import unquote

            name = unquote(name)
        except Exception:
            pass
        return name

    # Если не нашли, возвращаем общее название
    return "Место на карте"


def add_place_from_url(
    category: str,
    place_type: str,
    region: str,
    google_maps_url: str,
) -> bool:
    """Добавляет место из Google Maps ссылки"""
    google_maps_url = google_maps_url.strip()

    if not google_maps_url or not google_maps_url.startswith(("http", "https")):
        return False

    # Извлекаем координаты
    coords = extract_coordinates(google_maps_url)
    if not coords:
        print(f"❌ Не удалось извлечь координаты из: {google_maps_url[:50]}...")
        return False

    lat, lng = coords

    # Определяем регион, если не указан
    if not region or region.lower() == "auto":
        region = get_user_region(lat, lng)

    # Пытаемся извлечь название из URL
    name = extract_place_name_from_url(google_maps_url)

    with get_session() as session:
        # Проверяем, не существует ли уже такое место (по координатам)
        existing = (
            session.query(TaskPlace)
            .filter(
                TaskPlace.category == category,
                TaskPlace.place_type == place_type,
                TaskPlace.region == region,
                # Проверяем близость координат (в радиусе 100м)
                TaskPlace.lat.between(lat - 0.001, lat + 0.001),
                TaskPlace.lng.between(lng - 0.001, lng + 0.001),
            )
            .first()
        )

        if existing:
            print(f"⚠️ Место уже существует: {existing.name} (ID: {existing.id})")
            return False

        # Создаем новое место
        place = TaskPlace(
            category=category,
            place_type=place_type,
            region=region,
            name=name,
            description=None,
            lat=lat,
            lng=lng,
            google_maps_url=google_maps_url,
            is_active=True,
        )

        session.add(place)
        session.commit()

        print(f"✅ Добавлено: {name} ({region}, {place_type}) - {lat:.6f}, {lng:.6f}")
        return True


def parse_simple_file(file_path: str) -> list[dict]:
    """
    Парсит упрощенный файл формата:
    category:place_type:region
    url1
    url2
    url3
    """
    result = []
    current_category = None
    current_place_type = None
    current_region = None

    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()

            # Пропускаем пустые строки и комментарии
            if not line or line.startswith("#"):
                continue

            # Проверяем, является ли строка заголовком категории
            if ":" in line and not line.startswith("http"):
                # Формат: category:place_type:region
                parts = line.split(":")
                if len(parts) >= 2:
                    current_category = parts[0].strip()
                    current_place_type = parts[1].strip()
                    current_region = parts[2].strip() if len(parts) > 2 else "auto"
                    print(f"\n📋 Категория: {current_category}, Тип: {current_place_type}, Регион: {current_region}")
                continue

            # Если это ссылка
            if line.startswith(("http://", "https://")):
                if not current_category or not current_place_type:
                    print(f"⚠️ Строка {line_num}: пропущена (нет категории/типа)")
                    continue

                result.append(
                    {
                        "category": current_category,
                        "place_type": current_place_type,
                        "region": current_region,
                        "url": line,
                    }
                )

    return result


def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование: python scripts/add_places_from_simple_file.py <txt_file>")
        print("\nПример:")
        print("  python scripts/add_places_from_simple_file.py places_simple.txt")
        print("\nФормат файла:")
        print("  category:place_type:region")
        print("  https://maps.google.com/ссылка1")
        print("  https://maps.google.com/ссылка2")
        sys.exit(1)

    txt_file = sys.argv[1]

    if not os.path.exists(txt_file):
        print(f"❌ Файл не найден: {txt_file}")
        sys.exit(1)

    # Инициализируем БД
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        print("   Убедитесь, что файл app.local.env существует и содержит DATABASE_URL")
        sys.exit(1)

    init_engine(db_url)

    # Парсим файл
    print(f"📄 Загружаю места из файла: {txt_file}\n")
    places = parse_simple_file(txt_file)

    if not places:
        print("❌ Не найдено мест для добавления")
        sys.exit(1)

    # Добавляем места
    added_count = 0
    skipped_count = 0

    for place_info in places:
        try:
            if add_place_from_url(
                category=place_info["category"],
                place_type=place_info["place_type"],
                region=place_info["region"],
                google_maps_url=place_info["url"],
            ):
                added_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            skipped_count += 1

    print("\n✅ Готово!")
    print(f"   Добавлено: {added_count}")
    print(f"   Пропущено: {skipped_count}")


if __name__ == "__main__":
    main()
