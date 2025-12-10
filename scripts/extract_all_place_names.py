#!/usr/bin/env python3
"""
Скрипт для извлечения названий мест из всех Google Maps ссылок в файле
"""

import asyncio
import re
import sys
from pathlib import Path

# Настройка кодировки для Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.geo_utils import parse_google_maps_link


async def get_place_name(url: str) -> str | None:
    """Получает название места из Google Maps ссылки"""
    try:
        result = await parse_google_maps_link(url)
        if result and result.get("name"):
            name = result["name"]
            # Если название слишком общее, возвращаем None
            if name in ["Место на карте", "Place"]:
                return None
            return name
    except Exception as e:
        print(f"⚠️ Ошибка при получении названия для {url[:50]}...: {e}")
    return None


async def process_file(file_path: str) -> None:
    """Обрабатывает файл, добавляя названия перед ссылками, которые их не имеют"""
    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    processed_count = 0

    while i < len(lines):
        line = lines[i].rstrip()

        # Проверяем, является ли строка Google Maps ссылкой
        if re.match(r"https?://(maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.com|www\.google\.com/maps)", line):
            # Это ссылка, проверяем, есть ли уже название перед ней
            prev_line = new_lines[-1].rstrip() if new_lines else ""

            # Название есть, если предыдущая строка не пустая, не ссылка, не комментарий и не формат places:...:
            has_name_before = (
                prev_line
                and prev_line.strip() != ""
                and not re.match(r"https?://", prev_line)
                and not prev_line.startswith("#")
                and not re.match(r"^places?:", prev_line)
                and prev_line != "Чангу"  # Исключаем заголовки регионов
            )

            if not has_name_before:
                # Нет названия перед ссылкой, пытаемся получить
                print(f"🔍 Обрабатываю ссылку: {line[:50]}...")
                name = await get_place_name(line)

                if name:
                    # Добавляем название перед ссылкой
                    new_lines.append(f"{name}\n")
                    print(f"  ✅ Найдено название: {name}")
                    processed_count += 1
                else:
                    print("  ⚠️ Не удалось извлечь название")

            new_lines.append(f"{line}\n")
        else:
            # Обычная строка, просто добавляем
            new_lines.append(f"{line}\n")

        i += 1

    # Записываем обновленный файл
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"\n✅ Файл обновлен: {file_path}")
    print(f"📊 Обработано ссылок: {processed_count}")


async def main():
    if len(sys.argv) < 2:
        print("Использование: python scripts/extract_all_place_names.py <путь_к_файлу>")
        print("Пример: python scripts/extract_all_place_names.py interesting_places_example.txt")
        sys.exit(1)

    file_path = sys.argv[1]
    if not Path(file_path).exists():
        print(f"❌ Файл не найден: {file_path}")
        sys.exit(1)

    await process_file(file_path)


if __name__ == "__main__":
    asyncio.run(main())
