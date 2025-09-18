#!/usr/bin/env python3
"""Скрипт для поиска файлов-сирот (никто не импортирует)"""

import glob
import os
import re


def find_python_files():
    """Находит все Python файлы в проекте"""
    python_files = []
    for pattern in ["**/*.py"]:
        for file in glob.glob(pattern, recursive=True):
            if not any(skip in file for skip in ["__pycache__", ".git", "venv", "reports"]):
                python_files.append(file)
    return python_files


def extract_imports(file_path):
    """Извлекает импорты из Python файла"""
    imports = set()
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # Ищем импорты
        import_patterns = [
            r"from\s+(\w+(?:\.\w+)*)\s+import",
            r"import\s+(\w+(?:\.\w+)*)",
        ]

        for pattern in import_patterns:
            matches = re.findall(pattern, content)
            imports.update(matches)

    except Exception as e:
        print(f"Ошибка чтения {file_path}: {e}")

    return imports


def find_orphans():
    """Находит файлы-сироты"""
    python_files = find_python_files()

    # Собираем все импорты
    all_imports = set()
    file_modules = {}

    for file_path in python_files:
        # Определяем имя модуля
        module_name = file_path.replace("/", ".").replace("\\", ".").replace(".py", "")
        if module_name.endswith(".__init__"):
            module_name = module_name[:-9]

        file_modules[file_path] = module_name

        # Извлекаем импорты
        imports = extract_imports(file_path)
        all_imports.update(imports)

    # Ищем сирот
    orphans = []
    for file_path, module_name in file_modules.items():
        # Проверяем различные варианты имени модуля
        module_variants = [
            module_name,
            module_name.split(".")[-1],  # только последняя часть
            os.path.basename(file_path).replace(".py", ""),  # имя файла
        ]

        is_imported = any(variant in all_imports for variant in module_variants)

        # Исключаем основные файлы
        is_main = any(
            main in file_path
            for main in [
                "bot_enhanced_v3.py",
                "app.py",
                "__main__.py",
                "run_",
                "start_",
                "check_",
                "test_",
                "apply_",
                "setup_",
            ]
        )

        if not is_imported and not is_main:
            orphans.append((file_path, module_name))

    return orphans


def main():
    print("🔍 Поиск файлов-сирот...")
    orphans = find_orphans()

    print(f"\n📊 Найдено потенциальных сирот: {len(orphans)}")
    print("\n=== ФАЙЛЫ-СИРОТЫ ===")

    for file_path, module_name in orphans:
        file_size = os.path.getsize(file_path)
        print(f"📄 {file_path}")
        print(f"   Модуль: {module_name}")
        print(f"   Размер: {file_size} байт")
        print()


if __name__ == "__main__":
    main()
