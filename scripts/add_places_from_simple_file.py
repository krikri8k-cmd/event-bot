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

import sys

# Устанавливаем UTF-8 для stdout
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        # Для старых версий Python
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Добавляем корень проекта в путь для импортов
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Импорт geo_utils тянет config.py → load_dotenv(app.local.env, override=True) и может
# затереть DATABASE_URL из `railway run`. Сохраняем URL из окружения до импортов.
_preserved_database_url = (os.environ.get("DATABASE_URL") or "").strip() or None

from database import TaskPlace, get_session, init_engine  # noqa: E402
from tasks_location_service import get_user_region  # noqa: E402
from utils.geo_utils import parse_google_maps_link  # noqa: E402

if _preserved_database_url:
    os.environ["DATABASE_URL"] = _preserved_database_url

# Загружаем переменные окружения (override по умолчанию False — не затираем восстановленный URL)
env_path = project_root / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)


async def extract_coordinates_async(google_maps_url: str) -> tuple[float, float] | None:
    """Извлекает координаты из Google Maps ссылки (асинхронно)"""
    result = await parse_google_maps_link(google_maps_url)
    if result and result.get("lat") and result.get("lng"):
        return result["lat"], result["lng"]
    return None


def extract_coordinates(google_maps_url: str, fallback_name: str | None = None) -> tuple[float, float] | None:
    """Извлекает координаты из Google Maps ссылки

    Args:
        google_maps_url: Ссылка на Google Maps
        fallback_name: Название места для геокодирования, если координаты не найдены в URL
    """
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(extract_coordinates_async(google_maps_url))
        # Если координаты не найдены, но есть fallback_name, пробуем геокодировать по нему
        if not result and fallback_name:
            from utils.geo_utils import geocode_address

            coords = loop.run_until_complete(geocode_address(fallback_name))
            if coords:
                print(f"✅ Геокодирование по названию '{fallback_name}' успешно: {coords[0]}, {coords[1]}")
                return coords
        return result
    finally:
        loop.close()


def extract_place_name_from_url(url: str) -> str:
    """Пытается извлечь название места из URL"""
    if not url:
        return "Место на карте"

    # Паттерн 1: /place/Название+Места/... (самый частый)
    # Берем всё до /data= или до следующего /
    place_pattern = r"/place/([^/@]+?)(?:/data=|/|$)"
    match = re.search(place_pattern, url)
    if match:
        name = match.group(1)
        # Декодируем URL-кодированные символы
        try:
            from urllib.parse import unquote

            name = unquote(name)
            # Заменяем + и %20 на пробелы
            name = name.replace("+", " ").replace("%20", " ")
            # Убираем лишние пробелы
            name = " ".join(name.split())
            # Убираем адрес после названия (всё после запятой)
            if "," in name:
                name = name.split(",")[0].strip()
            if name:
                return name
        except Exception:
            pass

    # Паттерн 2: Старый формат /place/Название+Места/...
    match = re.search(r"/place/([^/@]+)", url)
    if match:
        name = match.group(1).replace("+", " ").replace("%20", " ")
        try:
            from urllib.parse import unquote

            name = unquote(name)
            if "," in name:
                name = name.split(",")[0].strip()
            if name:
                return name
        except Exception:
            pass

    # Если не нашли, возвращаем общее название
    return "Место на карте"


def add_place_from_url(
    category: str,
    place_type: str,
    region: str,
    google_maps_url: str,
    promo_code: str | None = None,
    update_existing: bool = True,
    custom_name: str | None = None,
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

    # Извлекаем координаты (используем custom_name как fallback для геокодирования)
    coords = extract_coordinates(google_maps_url, fallback_name=custom_name)
    if not coords:
        print(f"ERROR: Не удалось извлечь координаты из: {google_maps_url[:50]}...")
        if custom_name:
            print(f"   (пробовали геокодировать по названию '{custom_name}', но не получилось)")

        # Если есть custom_name и место уже существует, попробуем обновить только название
        if custom_name and update_existing:
            with get_session() as session:
                existing_by_url = session.query(TaskPlace).filter(TaskPlace.google_maps_url == google_maps_url).first()
                if existing_by_url:
                    existing_by_url.name = custom_name
                    session.commit()
                    print(f"📝 Обновлено только название (без координат): {custom_name}")
                    return True, "updated"

        return False, "skipped"

    lat, lng = coords

    # Определяем регион, если не указан
    if not region or region.lower() == "auto":
        region = get_user_region(lat, lng)

    # Используем указанное название или извлекаем из URL
    # Сначала пробуем извлечь из расширенной ссылки (если она была расширена)
    name = None
    if custom_name:
        name = custom_name.strip()
    else:
        # Пытаемся извлечь название из URL
        name = extract_place_name_from_url(google_maps_url)
        if name and name != "Место на карте":
            print(f"📝 Название извлечено из URL: {name}")

        # Если не удалось извлечь и есть координаты, пробуем reverse geocoding
        if not name or name == "Место на карте":
            try:
                import asyncio

                from utils.geo_utils import reverse_geocode

                # Запускаем асинхронную функцию для получения названия по координатам
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    reverse_name = loop.run_until_complete(reverse_geocode(lat, lng))
                    if reverse_name:
                        name = reverse_name
                        print(f"📍 Название получено через reverse geocoding: {name}")
                finally:
                    loop.close()
            except Exception as e:
                print(f"⚠️ Не удалось получить название через reverse geocoding: {e}")

    # Если всё ещё не нашли название, используем fallback
    if not name or name == "Место на карте":
        name = "Место на карте"

    with get_session() as session:
        # Сначала проверяем, есть ли место с такой же ссылкой
        existing_by_url = session.query(TaskPlace).filter(TaskPlace.google_maps_url == google_maps_url).first()

        if existing_by_url:
            if update_existing:
                # Определяем task_type на основе региона (Bali = island, остальное = urban)
                task_type = "island" if region == "bali" else "urban"

                # Обновляем существующее место
                old_lat = existing_by_url.lat
                old_lng = existing_by_url.lng
                existing_by_url.lat = lat
                existing_by_url.lng = lng
                existing_by_url.category = category
                existing_by_url.place_type = place_type
                existing_by_url.region = region
                existing_by_url.task_type = task_type
                if promo_code:
                    existing_by_url.promo_code = promo_code
                # Обновляем название, если указано или удалось извлечь из URL
                # Всегда обновляем название, если оно найдено (даже если старое было "Место на карте")
                if custom_name:
                    existing_by_url.name = custom_name
                    print(f"📝 Использовано название из файла: {custom_name}")
                elif name and name != "Место на карте":
                    existing_by_url.name = name
                    print(f"📝 Обновлено название из URL: {name}")
                # Если название всё ещё "Место на карте", пробуем reverse geocoding
                elif existing_by_url.name == "Место на карте":
                    # Название уже было обновлено выше через reverse geocoding, если получилось
                    pass
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
                print(f"WARN: Место с такой ссылкой уже существует: {existing_by_url.name} (ID: {existing_by_url.id})")
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
                # Определяем task_type на основе региона (Bali = island, остальное = urban)
                task_type = "island" if region == "bali" else "urban"

                # Обновляем ссылку и другие поля
                existing_by_coords.google_maps_url = google_maps_url
                existing_by_coords.task_type = task_type
                if promo_code:
                    existing_by_coords.promo_code = promo_code
                if custom_name:
                    existing_by_coords.name = custom_name
                elif name and name != "Место на карте":
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
                print(f"WARN: Место уже существует: {existing_by_coords.name} (ID: {existing_by_coords.id})")
                return False, "skipped"

        # Определяем task_type на основе региона (Bali = island, остальное = urban)
        task_type = "island" if region == "bali" else "urban"

        # Создаем новое место
        place = TaskPlace(
            category=category,
            place_type=place_type,
            region=region,
            task_type=task_type,
            name=name,
            description=None,
            lat=lat,
            lng=lng,
            google_maps_url=google_maps_url,
            promo_code=promo_code,
            is_active=True,
        )

        session.add(place)
        session.flush()  # Получаем ID места для генерации подсказки

        # Генерируем подсказку с помощью AI
        try:
            from tasks.ai_hints_generator import generate_hint_for_place

            if generate_hint_for_place(place):
                print(f"   AI: Сгенерирована подсказка: {place.task_hint[:50]}...")
        except Exception as e:
            print(f"   WARN: Не удалось сгенерировать подсказку: {e}")

        session.commit()

        promo_info = f", Промокод: {promo_code}" if promo_code else ""
        print(f"OK: Добавлено: {name} ({region}, {place_type}) - {lat:.6f}, {lng:.6f}{promo_info}")
        return True, "added"


def parse_simple_file(file_path: str) -> list[dict]:
    """
    Парсит упрощенный файл формата:
    category:place_type:region:promo_code (промокод опционален)
    url1|promo_code1 (промокод после ссылки через |, приоритетнее)
    url2
    url3

    Также поддерживает формат с названиями:
    Название места
    https://maps.app.goo.gl/...
    """
    result = []
    current_category = None
    current_place_type = None
    current_region = None
    current_promo_code = None
    pending_name = None  # Название места, ожидающее ссылку

    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            show = (line[:80] + "...") if len(line) > 80 else line
            print(f">>> Обрабатываю строку {line_num}: {show!r}")

            # Пропускаем пустые строки и комментарии
            if not line or line.startswith("#"):
                if not line:
                    print("!!! СТРОКА ПРОПУЩЕНА: пустая")
                else:
                    print("!!! СТРОКА ПРОПУЩЕНА: комментарий")
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
                        f">>> Результат парсинга заголовка: Category={current_category}, "
                        f"Type={current_place_type}, Region={current_region}{promo_info}"
                    )
                    pending_name = None  # Сбрасываем название при смене категории
                else:
                    print("!!! СТРОКА ПРОПУЩЕНА: заголовок с ':', но частей < 2")
                continue

            # Если это ссылка
            if line.startswith(("http://", "https://")):
                if not current_category or not current_place_type:
                    print("!!! СТРОКА ПРОПУЩЕНА: нет категории/типа (ссылка без заголовка)")
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
                        "name": pending_name,  # Используем сохраненное название, если есть
                    }
                )
                print(f">>> Результат парсинга: Name={pending_name!r}, URL={url[:50]}..., Category={current_category}")
                pending_name = None  # Сбрасываем после использования
            else:
                # Если это не ссылка и не заголовок - это может быть название места
                # Сохраняем его для следующей ссылки
                pending_name = line
                print(f">>> Результат парсинга (название для след. ссылки): {line!r}")

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
        print(f"ERROR: Файл не найден: {txt_file}")
        sys.exit(1)

    # Инициализируем БД
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL не найден в переменных окружения")
        print("   Убедитесь, что файл app.local.env существует и содержит DATABASE_URL")
        sys.exit(1)

    init_engine(db_url)

    # Парсим файл
    mode = "обновление" if update_existing else "добавление"
    print(f"Loading places from file: {txt_file} (mode: {mode})\n")
    places = parse_simple_file(txt_file)

    if not places:
        print("ERROR: Не найдено мест для добавления")
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
                custom_name=place_info.get("name"),
            )
            if success:
                if operation_type == "added":
                    added_count += 1
                elif operation_type == "updated":
                    updated_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"ERROR: Ошибка: {e}")
            skipped_count += 1

    print("\nDone!")
    if update_existing:
        print(f"   Добавлено новых: {added_count}")
        print(f"   Обновлено существующих: {updated_count}")
        print(f"   Пропущено: {skipped_count}")
    else:
        print(f"   Добавлено: {added_count}")
        print(f"   Пропущено: {skipped_count}")


if __name__ == "__main__":
    main()
