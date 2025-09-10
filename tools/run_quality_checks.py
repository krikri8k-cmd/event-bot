#!/usr/bin/env python3
"""
Главный скрипт для запуска всех проверок качества проекта
"""

import asyncio
import subprocess
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_command(cmd, description):
    """Запускает команду и возвращает результат"""
    print(f"🔧 {description}")
    print(f"   Команда: {cmd}")

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("   ✅ Успешно")
            if result.stdout.strip():
                print(f"   Вывод: {result.stdout.strip()}")
            return True
        else:
            print(f"   ❌ Ошибка (код {result.returncode})")
            if result.stderr.strip():
                print(f"   Ошибка: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print("   ⏰ Таймаут")
        return False
    except Exception as e:
        print(f"   ❌ Исключение: {e}")
        return False


async def run_async_command(script_path, description, *args):
    """Запускает асинхронный скрипт"""
    print(f"🔧 {description}")
    print(f"   Скрипт: {script_path} {' '.join(args)}")

    try:
        cmd = [sys.executable, script_path] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print("   ✅ Успешно")
            if result.stdout.strip():
                print(f"   Вывод: {result.stdout.strip()}")
            return True
        else:
            print(f"   ❌ Ошибка (код {result.returncode})")
            if result.stderr.strip():
                print(f"   Ошибка: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print("   ⏰ Таймаут")
        return False
    except Exception as e:
        print(f"   ❌ Исключение: {e}")
        return False


async def main():
    """Главная функция проверки качества"""

    print("🚀 Запуск проверки качества проекта")
    print("=" * 60)
    print()

    checks = []

    # 1. Проверка линтеров
    print("1️⃣ ПРОВЕРКА ЛИНТЕРОВ")
    print("-" * 30)

    checks.append(("Линтер ruff", run_command("python -m ruff check . --select=E,W,F", "Проверка ruff")))
    checks.append(("Форматирование black", run_command("python -m black . --check", "Проверка black")))

    print()

    # 2. Проверка конфигурации
    print("2️⃣ ПРОВЕРКА КОНФИГУРАЦИИ")
    print("-" * 30)

    config_ok = await run_async_command("tools/check_config.py", "Проверка конфигурации")
    checks.append(("Конфигурация", config_ok))

    print()

    # 3. Проверка базы данных
    print("3️⃣ ПРОВЕРКА БАЗЫ ДАННЫХ")
    print("-" * 30)

    db_ok = await run_async_command("tools/check_database.py", "Проверка базы данных")
    checks.append(("База данных", db_ok))

    print()

    # 4. Проверка импортов
    print("4️⃣ ПРОВЕРКА ИМПОРТОВ")
    print("-" * 30)

    import_checks = [
        (
            "utils.geo_utils",
            "from utils.geo_utils import haversine_km, bbox_around, validate_coordinates",
        ),
        ("api.services.events", "from api.services.events import get_events_nearby"),
        (
            "bot_enhanced_v3",
            "from bot_enhanced_v3 import prepare_events_for_feed, render_event_html",
        ),
        ("config", "from config import load_settings"),
    ]

    for module, import_cmd in import_checks:
        import_ok = run_command(f'python -c "{import_cmd}"', f"Импорт {module}")
        checks.append((f"Импорт {module}", import_ok))

    print()

    # 5. Dry-run тестирование
    print("5️⃣ DRY-RUN ТЕСТИРОВАНИЕ")
    print("-" * 30)

    dry_run_ok = await run_async_command(
        "tools/dry_run.py",
        "Dry-run тестирование",
        "--lat",
        "-8.5069",
        "--lng",
        "115.2625",
        "--radius",
        "10",
    )
    checks.append(("Dry-run тестирование", dry_run_ok))

    print()

    # 6. Проверка тестов
    print("6️⃣ ПРОВЕРКА ТЕСТОВ")
    print("-" * 30)

    test_checks = [
        (
            "Тест haversine",
            run_command(
                'python -c "from utils.geo_utils import haversine_km; '
                "print('✅ haversine_km работает:', haversine_km(-8.65, 115.22, -8.65, 115.22))\"",
                "Тест haversine_km",
            ),
        ),
        (
            "Тест конфигурации",
            run_command(
                'python -c "from config import load_settings; s=load_settings(); '
                "print('✅ Конфигурация загружается:', s.default_radius_km)\"",
                "Тест загрузки конфигурации",
            ),
        ),
    ]

    for test_name, test_ok in test_checks:
        checks.append((test_name, test_ok))

    print()

    # Итоговый отчет
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 60)

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)

    print(f"✅ Пройдено: {passed}/{total}")
    print(f"❌ Провалено: {total - passed}/{total}")
    print()

    print("Детали:")
    for check_name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {check_name}")

    print()

    if passed == total:
        print("🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
        print("Проект готов к работе! 🚀")
        return True
    else:
        print("⚠️ ЕСТЬ ПРОБЛЕМЫ!")
        print("Исправьте ошибки и запустите проверку снова.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
