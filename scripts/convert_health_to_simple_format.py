#!/usr/bin/env python3
"""
Конвертирует health_places_example.txt в формат для add_places_from_simple_file.py
"""

import sys

# Устанавливаем UTF-8 для stdout
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")

from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

input_file = project_root / "health_places_example.txt"
output_file = project_root / "health_places_simple.txt"

current_region = None
current_place_type = None

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

with open(input_file, encoding="utf-8") as f_in, open(output_file, "w", encoding="utf-8") as f_out:
    line_num = 0
    for line in f_in:
        line_num += 1
        line_stripped = line.strip()

        # Пропускаем пустые строки
        if not line_stripped:
            continue

        # Отладка для первых ссылок
        if line_stripped.startswith("http") and line_num <= 30:
            print(f"DEBUG line {line_num}: ссылка найдена, region={current_region}, type={current_place_type}")

        # Определяем регион
        if line_stripped.startswith("#") and "БАЛИ" in line_stripped.upper():
            current_region = "bali"
            current_place_type = None
            continue
        elif line_stripped.startswith("#") and "МОСКВА" in line_stripped.upper():
            current_region = "moscow"
            current_place_type = None
            continue
        elif line_stripped.startswith("#") and (
            "САНКТ-ПЕТЕРБУРГ" in line_stripped.upper() or "СПБ" in line_stripped.upper()
        ):
            current_region = "spb"
            current_place_type = None
            continue
        elif line_stripped.startswith("#") and "ДЖАКАРТА" in line_stripped.upper():
            current_region = "jakarta"
            current_place_type = None
            continue

        # Определяем тип места
        if line_stripped.startswith("#"):
            found_type = False
            for comment, place_type in place_type_map.items():
                if comment in line_stripped:
                    current_place_type = place_type
                    found_type = True
                    print(f"DEBUG line {line_num}: Установлен place_type={place_type} для region={current_region}")
                    break
            # Пропускаем все комментарии (включая те, что не содержат тип места)
            continue

        # Если это ссылка
        if line_stripped.startswith(("http://", "https://")):
            print(f"DEBUG: Найдена ссылка, region={current_region}, type={current_place_type}")
            if not current_region:
                print(f"WARN: Пропущена ссылка (нет региона): {line_stripped[:50]}")
                continue
            if not current_place_type:
                # Если нет типа, используем gym по умолчанию
                current_place_type = "gym"
                print(f"INFO: Используется 'gym' по умолчанию для ссылки: {line_stripped[:50]}")
            # Записываем в формате: health:place_type:region
            f_out.write(f"health:{current_place_type}:{current_region}:\n")
            f_out.write(f"{line_stripped}\n\n")
            print(f"DEBUG: Записано место: health:{current_place_type}:{current_region}")
            continue

        # Если это не ссылка и не комментарий - это может быть название места
        # Но мы его пропускаем, так как в простом формате название берется из URL или reverse geocoding

print(f"OK: Конвертировано в {output_file}")
print("Теперь можно запустить:")
print(f"  python scripts/add_places_to_production.py {output_file}")
