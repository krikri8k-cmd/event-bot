#!/usr/bin/env python3
"""
Скрипт для обновления Google Maps ссылок в таблице task_places

Использование:
    # Обновить одно место по ID
    python scripts/update_place_url.py <place_id> <new_google_maps_url>

    # Обновить несколько мест из CSV файла
    python scripts/update_place_url.py --file places_to_update.csv

Формат CSV файла:
    id,google_maps_url
    1,https://maps.google.com/?q=55.7558,37.6176
    2,https://maps.app.goo.gl/...
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Добавляем корень проекта в путь для импортов
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import TaskPlace, get_session, init_engine  # noqa: E402
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
    import re
    from urllib.parse import unquote

    # Пробуем найти название в URL
    match = re.search(r"/place/([^/@]+)", url)
    if match:
        name = match.group(1).replace("+", " ").replace("%20", " ")
        try:
            name = unquote(name)
        except Exception:
            pass
        return name

    return "Место на карте"


def update_place_url(place_id: int, new_google_maps_url: str, update_name: bool = False) -> bool:
    """
    Обновляет Google Maps ссылку для места и пересчитывает координаты

    Args:
        place_id: ID места в БД
        new_google_maps_url: Новая Google Maps ссылка
        update_name: Обновить ли название места из URL (по умолчанию False)

    Returns:
        True если успешно, False если ошибка
    """
    new_google_maps_url = new_google_maps_url.strip()

    if not new_google_maps_url or not new_google_maps_url.startswith(("http", "https")):
        print(f"❌ Неверный формат ссылки: {new_google_maps_url}")
        return False

    # Извлекаем координаты из новой ссылки
    coords = extract_coordinates(new_google_maps_url)
    if not coords:
        print(f"❌ Не удалось извлечь координаты из: {new_google_maps_url[:50]}...")
        return False

    lat, lng = coords

    with get_session() as session:
        # Находим место
        place = session.query(TaskPlace).filter(TaskPlace.id == place_id).first()
        if not place:
            print(f"❌ Место с ID {place_id} не найдено")
            return False

        # Сохраняем старые значения для вывода
        old_url = place.google_maps_url
        old_lat = place.lat
        old_lng = place.lng
        old_name = place.name

        # Обновляем ссылку и координаты
        place.google_maps_url = new_google_maps_url
        place.lat = lat
        place.lng = lng

        # Опционально обновляем название
        if update_name:
            new_name = extract_place_name_from_url(new_google_maps_url)
            if new_name and new_name != "Место на карте":
                place.name = new_name

        session.commit()

        print(f"✅ Обновлено место ID {place_id}:")
        print(f"   Название: {place.name}")
        old_url_display = f"{old_url[:60]}..." if old_url and len(old_url) > 60 else old_url
        print(f"   Старая ссылка: {old_url_display}")
        new_url_display = f"{new_google_maps_url[:60]}..." if len(new_google_maps_url) > 60 else new_google_maps_url
        print(f"   Новая ссылка: {new_url_display}")
        print(f"   Координаты: {old_lat:.6f}, {old_lng:.6f} -> {lat:.6f}, {lng:.6f}")
        if update_name and place.name != old_name:
            print(f"   Название: {old_name} -> {place.name}")

        return True


def update_from_csv(csv_file: str, update_name: bool = False) -> None:
    """Обновляет места из CSV файла"""
    import csv

    if not os.path.exists(csv_file):
        print(f"❌ Файл не найден: {csv_file}")
        return

    updated_count = 0
    error_count = 0

    with open(csv_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):  # Начинаем с 2, т.к. первая строка - заголовок
            try:
                place_id = int(row.get("id", "").strip())
                new_url = row.get("google_maps_url", "").strip()

                if not new_url:
                    print(f"⚠️ Строка {row_num}: пропущена (нет ссылки)")
                    error_count += 1
                    continue

                if update_place_url(place_id, new_url, update_name):
                    updated_count += 1
                else:
                    error_count += 1
            except ValueError:
                print(f"⚠️ Строка {row_num}: неверный ID места")
                error_count += 1
            except Exception as e:
                print(f"❌ Строка {row_num}: ошибка - {e}")
                error_count += 1

    print("\n✅ Готово!")
    print(f"   Обновлено: {updated_count}")
    print(f"   Ошибок: {error_count}")


def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование:")
        print("  # Обновить одно место:")
        print("  python scripts/update_place_url.py <place_id> <new_google_maps_url> [--update-name]")
        print("\n  # Обновить из CSV файла:")
        print("  python scripts/update_place_url.py --file <csv_file> [--update-name]")
        print("\nПримеры:")
        print("  python scripts/update_place_url.py 1 https://maps.google.com/?q=55.7558,37.6176")
        print("  python scripts/update_place_url.py --file places_to_update.csv")
        print("\nФормат CSV файла:")
        print("  id,google_maps_url")
        print("  1,https://maps.google.com/?q=55.7558,37.6176")
        print("  2,https://maps.app.goo.gl/...")
        sys.exit(1)

    # Инициализируем БД
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        print("   Убедитесь, что файл app.local.env существует и содержит DATABASE_URL")
        sys.exit(1)

    init_engine(db_url)

    # Проверяем флаги
    update_name = "--update-name" in sys.argv

    # Обрабатываем аргументы
    if sys.argv[1] == "--file":
        if len(sys.argv) < 3:
            print("❌ Укажите путь к CSV файлу")
            sys.exit(1)
        csv_file = sys.argv[2]
        update_from_csv(csv_file, update_name)
    else:
        # Обновляем одно место
        if len(sys.argv) < 3:
            print("❌ Укажите ID места и новую ссылку")
            sys.exit(1)

        try:
            place_id = int(sys.argv[1])
            new_url = sys.argv[2]

            if not update_place_url(place_id, new_url, update_name):
                sys.exit(1)
        except ValueError:
            print("❌ ID места должен быть числом")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
