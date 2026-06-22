#!/usr/bin/env python3
"""
Скрипт для добавления мест в продакшн-базу Railway
Использование: python scripts/add_places_to_production.py places_simple.txt
"""

import os
import sys
from pathlib import Path

# Добавляем корень проекта в путь для импортов
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import init_engine  # noqa: E402
from scripts.add_places_from_simple_file import add_place_from_url, parse_simple_file  # noqa: E402
from utils.task_places_safety import refuse_unsafe_task_places_import  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python scripts/add_places_to_production.py <txt_file> [DATABASE_URL] [--yes] [--dry-run]")
        print("\nПримеры:")
        print("  1. Только парсинг (без записи в БД):")
        print("     python scripts/add_places_to_production.py food_places_example.txt --dry-run")
        print("  2. С DATABASE_URL из переменной окружения:")
        print("     python scripts/add_places_to_production.py places_simple.txt")
        print("  3. С DATABASE_URL из Railway (Public URL!):")
        print(
            "     python scripts/add_places_to_production.py places_simple.txt 'postgresql://...@interchange.proxy.rlwy.net:23764/railway'"
        )
        print("  4. С автоподтверждением:")
        print("     python scripts/add_places_to_production.py places_simple.txt --yes")
        print("\n⚠️  ВАЖНО: С компа используй Public URL (interchange.proxy.rlwy.net), не .internal!")
        sys.exit(1)

    txt_file = sys.argv[1]
    auto_confirm = "--yes" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if not dry_run:
        refuse_unsafe_task_places_import(txt_file, update_existing=True)

    # Получаем DATABASE_URL (пропускаем --yes и --dry-run если есть)
    db_url = None
    for arg in sys.argv[2:]:
        if arg not in ("--yes", "--dry-run") and arg.startswith("postgresql"):
            db_url = arg
            break

    if not db_url:
        db_url = os.getenv("DATABASE_URL")
        if not db_url and not dry_run:
            print("❌ DATABASE_URL не найден!")
            print("\nКак получить DATABASE_URL из Railway:")
            print("  1. Открой Railway → твой проект → Database → Connect")
            print("  2. Скопируй строку подключения (Public Network или Private Network)")
            print("  3. Запусти скрипт так:")
            print("     python scripts/add_places_to_production.py places_simple.txt 'postgresql://...'")
            sys.exit(1)
        if db_url:
            print("🔗 Используется DATABASE_URL из переменной окружения")
    elif db_url:
        print("🔗 Используется DATABASE_URL из аргумента")

    if db_url:
        # Извлекаем хост для лога
        try:
            rest = db_url.split("@", 1)[1]
            host = rest.split("/")[0].rsplit(":", 1)[0] if ":" in rest.split("/")[0] else rest.split("/")[0]
        except IndexError:
            host = "(не удалось извлечь)"
        print(f"Connecting to host: {host}")
        if ".internal" in host:
            print(
                "⚠️  ВНИМАНИЕ: используется внутренний хост (.internal). "
                "С компа он недоступен! Используй Public URL (interchange.proxy.rlwy.net)."
            )

    # Парсим файл
    if not os.path.exists(txt_file):
        print(f"❌ Файл не найден: {txt_file}")
        sys.exit(1)

    print(f"📄 Загружаю места из файла: {txt_file}\n")
    places = parse_simple_file(txt_file)

    if not places:
        print("❌ Не найдено мест для добавления")
        sys.exit(1)

    # Проверка: видит ли парсер Honey Murena
    honey_found = any(p.get("name") and "Honey" in (p.get("name") or "") for p in places)
    chef_found = any(p.get("name") and "Chef" in (p.get("name") or "") for p in places)
    print(
        f"\n📋 Парсер нашёл мест: {len(places)}. "
        f"Honey Murena в списке: {'ДА' if honey_found else 'НЕТ'}. "
        f"Chef's Crate в списке: {'ДА' if chef_found else 'НЕТ'}"
    )

    if dry_run:
        print("\n[DRY RUN] Запись в базу не производится. Запусти без --dry-run для импорта.")
        sys.exit(0)

    if not db_url:
        print("❌ Для импорта нужен DATABASE_URL")
        sys.exit(1)

    # Подтверждение (можно пропустить с флагом --yes)
    if not auto_confirm:
        print("\n⚠️  ВНИМАНИЕ: Ты добавляешь места в ПРОДАКШН-БАЗУ!")
        response = input("Продолжить? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Отменено")
            sys.exit(0)
    else:
        print("\n⚠️  ВНИМАНИЕ: Добавление мест в ПРОДАКШН-БАЗУ (автоподтверждение)")

    # Инициализируем БД
    try:
        init_engine(db_url)
        print("✅ Подключение к базе успешно\n")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        sys.exit(1)

    # Добавляем места
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
                custom_name=place_info.get("name"),  # Используем название из файла
                update_existing=True,  # Явно указываем, что нужно обновлять существующие места
            )
            if success:
                if operation_type == "added":
                    added_count += 1
                elif operation_type == "updated":
                    updated_count += 1
                elif operation_type == "skipped":
                    skipped_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            skipped_count += 1

    print("\n✅ Готово!")
    print(f"   ✅ Добавлено: {added_count}")
    if updated_count > 0:
        print(f"   🔄 Обновлено: {updated_count}")
    print(f"   ⏭️  Пропущено: {skipped_count}")

    # Контрольный запрос: есть ли Honey в task_places
    from sqlalchemy import text

    from database import get_session

    print("\n📋 Контрольный запрос: SELECT id, name FROM task_places WHERE name ILIKE '%Honey%'")
    try:
        with get_session() as session:
            rows = session.execute(text("SELECT id, name FROM task_places WHERE name ILIKE '%Honey%'")).fetchall()
            if rows:
                for r in rows:
                    print(f"   id={r[0]}, name={r[1]}")
            else:
                print("   (записей не найдено)")
    except Exception as e:
        print(f"   Ошибка запроса: {e}")
