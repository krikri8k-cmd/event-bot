#!/usr/bin/env python3
"""
Скрипт для добавления health мест из файла health_places_example.txt

Формат файла:
    # Комментарии
    Название места
    https://maps.app.goo.gl/...

    Название места 2
    https://maps.app.goo.gl/...|PROMOCODE

Автоматически определяет:
    - category = "health"
    - place_type из комментариев (# gym, # spa, # yoga_studio и т.д.)
    - region из разделов (# БАЛИ, # МОСКВА и т.д.)
"""

import os
import sys
from pathlib import Path

# Устанавливаем UTF-8 для stdout
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")

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


def parse_health_file(file_path: str) -> list[dict]:
    """
    Парсит файл health_places_example.txt

    Определяет:
    - region из разделов (# БАЛИ, # МОСКВА и т.д.)
    - place_type из комментариев (# gym, # spa и т.д.)
    - category всегда "health"
    """
    result = []
    current_region = None
    current_place_type = None
    pending_name = None

    # Маппинг регионов из файла в коды БД

    # Маппинг комментариев на place_type
    place_type_map = {
        "# gym": "gym",
        "# spa": "spa",
        "# lab": "lab",
        "# clinic": "clinic",
        "# nature": "nature",
        "# park": "park",
        "# beach": "beach",
        "# yoga_studio": "yoga_studio",
        "# outdoor_space": "outdoor_space",
    }

    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()
        print(f"DEBUG: Всего строк в файле: {len(lines)}")

    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()

            # Пропускаем пустые строки
            if not line:
                continue

            # Отладка для всех некомментарных строк в диапазоне мест
            if not line.startswith("#") and 24 <= line_num <= 110:
                print(
                    f"DEBUG line {line_num}: '{line[:60]}' | "
                    f"region={current_region}, type={current_place_type}, pending={pending_name}",
                    file=sys.stderr,
                    flush=True,
                )

            # Определяем регион из разделов
            # Формат: # ============================================
            #         # БАЛИ
            if line.startswith("# =") or (line.startswith("#") and "===" in line):
                # Это разделитель, следующая строка будет регионом
                continue

            if line.startswith("#") and "БАЛИ" in line.upper():
                current_region = "bali"
                current_place_type = None
                pending_name = None
                continue
            elif line.startswith("#") and "МОСКВА" in line.upper():
                current_region = "moscow"
                current_place_type = None
                pending_name = None
                continue
            elif line.startswith("#") and ("САНКТ-ПЕТЕРБУРГ" in line.upper() or "СПБ" in line.upper()):
                current_region = "spb"
                current_place_type = None
                pending_name = None
                continue
            elif line.startswith("#") and "ДЖАКАРТА" in line.upper():
                current_region = "jakarta"
                current_place_type = None
                pending_name = None
                continue

            # Пропускаем комментарии, но проверяем на place_type
            if line.startswith("#"):
                # Проверяем, не является ли это указанием типа места
                for comment, place_type in place_type_map.items():
                    if comment in line:
                        current_place_type = place_type
                        pending_name = None
                        print(
                            f"DEBUG: Установлен place_type={place_type} "
                            f"для региона={current_region} на строке {line_num}"
                        )
                        break
                # Если это не комментарий с типом места, просто пропускаем
                continue

            # Если это ссылка
            if line.startswith(("http://", "https://")):
                if not current_region:
                    print(f"WARN: Строка {line_num}: пропущена (нет региона): {line[:50]}")
                    continue

                if not current_place_type:
                    # Если нет явного типа, пробуем определить по контексту
                    # По умолчанию для health мест используем "gym"
                    current_place_type = "gym"
                    print(f"INFO: Строка {line_num}: тип места не указан, используется 'gym' по умолчанию")

                # Проверяем, есть ли промокод после ссылки через |
                url = line
                promo_code = None
                if "|" in line:
                    parts = line.split("|", 1)
                    url = parts[0].strip()
                    promo_code = parts[1].strip() if parts[1].strip() else None

                print(
                    f"DEBUG: Добавление места: name='{pending_name}', "
                    f"region={current_region}, type={current_place_type}, url={url[:50]}..."
                )

                result.append(
                    {
                        "category": "health",
                        "place_type": current_place_type,
                        "region": current_region,
                        "url": url,
                        "promo_code": promo_code,
                        "name": pending_name,
                    }
                )
                pending_name = None
            else:
                # Если это не ссылка и не комментарий - это может быть название места или заголовок
                # Пропускаем заголовки подразделов (например, "Спортзалы Убуд", "Спортзалы Чангу")
                line_lower = line.lower()
                if any(word in line_lower for word in ["спортзалы", "залы", "заведения", "места"]):
                    # Это заголовок подраздела, пропускаем
                    pending_name = None
                    continue

                # Иначе это название места
                pending_name = line

    print(f"\nDEBUG: Всего найдено мест в файле: {len(result)}")
    for i, place in enumerate(result[:5], 1):
        print(f"DEBUG место {i}: {place}")

    return result


def add_place_from_url(
    category: str,
    place_type: str,
    region: str,
    google_maps_url: str,
    promo_code: str | None = None,
    update_existing: bool = True,
    custom_name: str | None = None,
) -> tuple[bool, str]:
    """Добавляет или обновляет место из Google Maps ссылки"""

    # Извлекаем координаты
    coords = extract_coordinates(google_maps_url)
    if not coords:
        print(f"ERROR: Не удалось извлечь координаты из {google_maps_url}")
        return False, "error"

    lat, lng = coords

    # Определяем region автоматически, если указан "auto"
    if region == "auto":
        region = get_user_region(lat, lng)

    # Определяем task_type на основе координат (Bali = island, остальное = urban)
    if region == "bali":
        task_type = "island"
    else:
        task_type = "urban"

    # Название места
    name = custom_name if custom_name else "Место на карте"

    with get_session() as session:
        # Проверяем, есть ли место с такой же ссылкой
        existing_by_url = session.query(TaskPlace).filter(TaskPlace.google_maps_url == google_maps_url).first()

        if existing_by_url:
            if update_existing:
                existing_by_url.lat = lat
                existing_by_url.lng = lng
                existing_by_url.category = category
                existing_by_url.place_type = place_type
                existing_by_url.region = region
                existing_by_url.task_type = task_type
                if promo_code:
                    existing_by_url.promo_code = promo_code
                if custom_name:
                    existing_by_url.name = custom_name
                existing_by_url.is_active = True
                session.commit()

                promo_info = f", Промокод: {promo_code}" if promo_code else ""
                print(
                    f"🔄 Обновлено: {existing_by_url.name} (ID: {existing_by_url.id}) "
                    f"({region}, {place_type}){promo_info}"
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
                TaskPlace.lat.between(lat - 0.001, lat + 0.001),
                TaskPlace.lng.between(lng - 0.001, lng + 0.001),
            )
            .first()
        )

        if existing_by_coords:
            if update_existing:
                existing_by_coords.google_maps_url = google_maps_url
                if promo_code:
                    existing_by_coords.promo_code = promo_code
                if custom_name:
                    existing_by_coords.name = custom_name
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
        session.flush()

        # Генерируем подсказку с помощью AI
        try:
            from tasks.ai_hints_generator import generate_hint_for_place

            if generate_hint_for_place(place):
                print(f"   AI: Сгенерирована подсказка: {place.task_hint[:50]}...")
        except Exception as e:
            print(f"   WARN: Не удалось сгенерировать подсказку: {e}")

        session.commit()

        promo_info = f", Промокод: {promo_code}" if promo_code else ""
        print(f"✅ Добавлено: {name} ({region}, {place_type}) - {lat:.6f}, {lng:.6f}{promo_info}")
        return True, "added"


def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование: python scripts/add_health_places.py <txt_file> [--update]")
        print("\nПример:")
        print("  python scripts/add_health_places.py health_places_example.txt")
        print("  python scripts/add_health_places.py health_places_example.txt --update")
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
    print(f"Загрузка health мест из файла: {txt_file} (режим: {mode})\n")
    places = parse_health_file(txt_file)

    if not places:
        print("ERROR: Не найдено мест для добавления")
        print("Проверьте формат файла и наличие ссылок на Google Maps")
        sys.exit(1)

    print(f"Найдено мест: {len(places)}\n")

    # Добавляем/обновляем места
    added_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0

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
            print(f"ERROR: Ошибка при обработке {place_info.get('name', place_info['url'])}: {e}")
            error_count += 1
            skipped_count += 1

    print("\n" + "=" * 50)
    print("Готово!")
    if update_existing:
        print(f"   ✅ Добавлено новых: {added_count}")
        print(f"   🔄 Обновлено существующих: {updated_count}")
        print(f"   ⏭️  Пропущено: {skipped_count}")
    else:
        print(f"   ✅ Добавлено: {added_count}")
        print(f"   ⏭️  Пропущено: {skipped_count}")
    if error_count > 0:
        print(f"   ❌ Ошибок: {error_count}")


if __name__ == "__main__":
    main()
