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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python scripts/add_places_to_production.py <txt_file> [DATABASE_URL] [--yes]")
        print("\nПримеры:")
        print("  1. С DATABASE_URL из переменной окружения:")
        print("     python scripts/add_places_to_production.py places_simple.txt")
        print("  2. С DATABASE_URL из Railway (скопируй из Railway → Database → Connect):")
        print("     python scripts/add_places_to_production.py places_simple.txt 'postgresql://...'")
        print("  3. С автоподтверждением:")
        print("     python scripts/add_places_to_production.py places_simple.txt --yes")
        print("\n⚠️  ВАЖНО: Убедись, что это продакшн-база!")
        sys.exit(1)

    txt_file = sys.argv[1]
    auto_confirm = "--yes" in sys.argv

    # Получаем DATABASE_URL (пропускаем --yes если есть)
    db_url = None
    for arg in sys.argv[2:]:
        if arg != "--yes" and arg.startswith("postgresql"):
            db_url = arg
            break

    if not db_url:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print("❌ DATABASE_URL не найден!")
            print("\nКак получить DATABASE_URL из Railway:")
            print("  1. Открой Railway → твой проект → Database → Connect")
            print("  2. Скопируй строку подключения (Public Network или Private Network)")
            print("  3. Запусти скрипт так:")
            print("     python scripts/add_places_to_production.py places_simple.txt 'postgresql://...'")
            sys.exit(1)
        print("🔗 Используется DATABASE_URL из переменной окружения")
    else:
        print("🔗 Используется DATABASE_URL из аргумента")

    # Показываем урезанный URL для безопасности
    db_url_short = db_url[:50] + "..." if len(db_url) > 50 else db_url
    print(f"📊 Подключение: {db_url_short}")

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

    # Парсим файл
    if not os.path.exists(txt_file):
        print(f"❌ Файл не найден: {txt_file}")
        sys.exit(1)

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
                promo_code=place_info.get("promo_code"),
                custom_name=place_info.get("name"),  # Используем название из файла
            ):
                added_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            skipped_count += 1

    print("\n✅ Готово!")
    print(f"   ✅ Добавлено: {added_count}")
    print(f"   ⏭️  Пропущено (уже существуют): {skipped_count}")
