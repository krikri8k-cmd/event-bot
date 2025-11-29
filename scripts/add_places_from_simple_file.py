#!/usr/bin/env python3
"""
Упрощенный скрипт для добавления и обновления локаций из простого текстового файла

Формат файла:
    # Комментарии начинаются с #
    category:place_type:region:promo_code (промокод опционален)
    https://maps.google.com/ссылка1|ПРОМОКОД (промокод после ссылки, приоритетнее)
    https://maps.google.com/ссылка2
    https://maps.google.com/ссылка3

    category:place_type:region
    https://maps.google.com/ссылка4
    ...

Использование:
    # Добавить новые места (существующие пропускаются)
    python scripts/add_places_from_simple_file.py places_simple.txt

    # Добавить и обновить существующие места
    python scripts/add_places_from_simple_file.py places_simple.txt --update

Особенности:
    - Если место с такой ссылкой уже есть - обновляет координаты и другие поля
    - Если место с такими координатами уже есть - обновляет ссылку
    - Если места нет - создает новое
    - Автоматически извлекает координаты из любых Google Maps ссылок (включая короткие)
"""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Добавляем корень проекта в путь для импортов
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import TaskPlace, get_session, init_engine  # noqa: E402
from tasks_location_service import get_user_region  # noqa: E402
from utils.geo_utils import parse_google_maps_link  # noqa: E402

# Загружаем переменные окружения
env_path = project_root / "app.local.env"
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
    promo_code: str | None = None,
    update_existing: bool = True,
) -> tuple[bool, str]:
    """
    Добавляет или обновляет место из Google Maps ссылки

    Args:
        category: Категория места
        place_type: Тип места
        region: Регион
        google_maps_url: Ссылка на Google Maps
        promo_code: Промокод (опционально)
        update_existing: Обновлять ли существующие места (по умолчанию True)

    Returns:
        Кортеж (успех, тип_операции) где:
        - успех: True если успешно, False если ошибка
        - тип_операции: "added", "updated", "skipped"
    """
    google_maps_url = google_maps_url.strip()

    if not google_maps_url or not google_maps_url.startswith(("http", "https")):
        return False, "skipped"

    # Извлекаем координаты
    coords = extract_coordinates(google_maps_url)
    if not coords:
        print(f"❌ Не удалось извлечь координаты из: {google_maps_url[:50]}...")
        return False, "skipped"

    lat, lng = coords

    # Определяем регион, если не указан
    if not region or region.lower() == "auto":
        region = get_user_region(lat, lng)

    # Пытаемся извлечь название из URL
    name = extract_place_name_from_url(google_maps_url)

    with get_session() as session:
        # Сначала проверяем, есть ли место с такой же ссылкой
        existing_by_url = session.query(TaskPlace).filter(TaskPlace.google_maps_url == google_maps_url).first()

        if existing_by_url:
            if update_existing:
                # Обновляем существующее место
                old_lat = existing_by_url.lat
                old_lng = existing_by_url.lng
                existing_by_url.lat = lat
                existing_by_url.lng = lng
                existing_by_url.category = category
                existing_by_url.place_type = place_type
                existing_by_url.region = region
                if promo_code:
                    existing_by_url.promo_code = promo_code
                # Обновляем название, если удалось извлечь из URL
                if name and name != "Место на карте":
                    existing_by_url.name = name
                existing_by_url.is_active = True

                session.commit()

                promo_info = f", Промокод: {promo_code}" if promo_code else ""
                print(
                    f"🔄 Обновлено: {existing_by_url.name} (ID: {existing_by_url.id}) "
                    f"({region}, {place_type}) - "
                    f"{old_lat:.6f}, {old_lng:.6f} -> {lat:.6f}, {lng:.6f}{promo_info}"
                )
                return True, "updated"
            else:
                print(f"⚠️ Место с такой ссылкой уже существует: {existing_by_url.name} (ID: {existing_by_url.id})")
                return False, "skipped"

        # Проверяем, не существует ли уже такое место по координатам
        existing_by_coords = (
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

        if existing_by_coords:
            if update_existing:
                # Обновляем ссылку и другие поля
                existing_by_coords.google_maps_url = google_maps_url
                if promo_code:
                    existing_by_coords.promo_code = promo_code
                if name and name != "Место на карте":
                    existing_by_coords.name = name
                existing_by_coords.is_active = True

                session.commit()

                promo_info = f", Промокод: {promo_code}" if promo_code else ""
                print(
                    f"🔄 Обновлено: {existing_by_coords.name} (ID: {existing_by_coords.id}) "
                    f"({region}, {place_type}) - обновлена ссылка{promo_info}"
                )
                return True, "updated"
            else:
                print(f"⚠️ Место уже существует: {existing_by_coords.name} (ID: {existing_by_coords.id})")
                return False, "skipped"

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
            promo_code=promo_code,
            is_active=True,
        )

        session.add(place)
        session.commit()

        promo_info = f", Промокод: {promo_code}" if promo_code else ""
        print(f"✅ Добавлено: {name} ({region}, {place_type}) - {lat:.6f}, {lng:.6f}{promo_info}")
        return True, "added"


def parse_simple_file(file_path: str) -> list[dict]:
    """
    Парсит упрощенный файл формата:
    category:place_type:region:promo_code (промокод опционален)
    url1|promo_code1 (промокод после ссылки через |, приоритетнее)
    url2
    url3
    """
    result = []
    current_category = None
    current_place_type = None
    current_region = None
    current_promo_code = None

    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()

            # Пропускаем пустые строки и комментарии
            if not line or line.startswith("#"):
                continue

            # Проверяем, является ли строка заголовком категории
            if ":" in line and not line.startswith("http"):
                # Формат: category:place_type:region:promo_code (все опционально кроме первых двух)
                parts = line.split(":")
                if len(parts) >= 2:
                    current_category = parts[0].strip()
                    current_place_type = parts[1].strip()
                    current_region = parts[2].strip() if len(parts) > 2 else "auto"
                    current_promo_code = parts[3].strip() if len(parts) > 3 else None
                    promo_info = f", Промокод: {current_promo_code}" if current_promo_code else ""
                    print(
                        f"\n📋 Категория: {current_category}, "
                        f"Тип: {current_place_type}, "
                        f"Регион: {current_region}{promo_info}"
                    )
                continue

            # Если это ссылка
            if line.startswith(("http://", "https://")):
                if not current_category or not current_place_type:
                    print(f"⚠️ Строка {line_num}: пропущена (нет категории/типа)")
                    continue

                # Проверяем, есть ли промокод после ссылки через |
                url = line
                promo_code = current_promo_code  # По умолчанию из заголовка
                if "|" in line:
                    parts = line.split("|", 1)
                    url = parts[0].strip()
                    promo_code = parts[1].strip() if parts[1].strip() else current_promo_code

                result.append(
                    {
                        "category": current_category,
                        "place_type": current_place_type,
                        "region": current_region,
                        "url": url,
                        "promo_code": promo_code,
                    }
                )

    return result


def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование: python scripts/add_places_from_simple_file.py <txt_file> [--update]")
        print("\nПример:")
        print("  python scripts/add_places_from_simple_file.py places_simple.txt")
        print("  python scripts/add_places_from_simple_file.py places_simple.txt --update")
        print("\nФормат файла:")
        print("  category:place_type:region:promo_code (промокод опционален)")
        print("  https://maps.google.com/ссылка1|ПРОМОКОД (промокод после ссылки, приоритетнее)")
        print("  https://maps.google.com/ссылка2")
        print("\nРежимы:")
        print("  Без --update: добавляет только новые места (существующие пропускаются)")
        print("  С --update: добавляет новые и обновляет существующие места")
        sys.exit(1)

    txt_file = sys.argv[1]
    update_existing = "--update" in sys.argv

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
    mode = "обновление" if update_existing else "добавление"
    print(f"📄 Загружаю места из файла: {txt_file} (режим: {mode})\n")
    places = parse_simple_file(txt_file)

    if not places:
        print("❌ Не найдено мест для добавления")
        sys.exit(1)

    # Добавляем/обновляем места
    added_count = 0
    updated_count = 0
    skipped_count = 0

    for place_info in places:
        try:
            success, operation_type = add_place_from_url(
                category=place_info["category"],
                place_type=place_info["place_type"],
                region=place_info["region"],
                google_maps_url=place_info["url"],
                promo_code=place_info.get("promo_code"),
                update_existing=update_existing,
            )
            if success:
                if operation_type == "added":
                    added_count += 1
                elif operation_type == "updated":
                    updated_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            skipped_count += 1

    print("\n✅ Готово!")
    if update_existing:
        print(f"   Добавлено новых: {added_count}")
        print(f"   Обновлено существующих: {updated_count}")
        print(f"   Пропущено: {skipped_count}")
    else:
        print(f"   Добавлено: {added_count}")
        print(f"   Пропущено: {skipped_count}")


if __name__ == "__main__":
    main()
