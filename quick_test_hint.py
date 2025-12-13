#!/usr/bin/env python3
"""Быстрый тест генерации подсказки"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from config import load_settings
    from tasks.ai_hints_generator import generate_task_hint

    print("=" * 60)
    print("🧪 ТЕСТ AI ГЕНЕРАЦИИ ПОДСКАЗОК")
    print("=" * 60)

    # Проверка настроек
    settings = load_settings()
    if not settings.openai_api_key:
        print("\n❌ ОШИБКА: OPENAI_API_KEY не настроен")
        print("   Добавьте в app.local.env: OPENAI_API_KEY=sk-...")
        sys.exit(1)

    print(f"\n✅ OpenAI API ключ найден: {settings.openai_api_key[:15]}...")

    # Тест генерации
    print("\n📝 Тестирую генерацию подсказки...")
    print("   Место: Кофейня на Арбате")
    print("   Категория: food, Тип: cafe")
    print("   Генерирую...", end=" ", flush=True)

    hint = generate_task_hint(place_name="Кофейня на Арбате", category="food", place_type="cafe")

    if hint:
        print("✅ УСПЕХ!")
        print("\n📋 Сгенерированная подсказка:")
        print(f"   {hint}")
        print(f"\n📊 Длина: {len(hint)} символов")
        print("   Лимит БД: 200 символов")

        if len(hint) <= 200:
            print("   ✅ В пределах лимита")
        else:
            print("   ⚠️ Превышает лимит (будет обрезано)")

        print("\n" + "=" * 60)
        print("✅ ТЕСТ ПРОЙДЕН!")
        print("=" * 60)
    else:
        print("❌ ОШИБКА")
        print("\n⚠️ Не удалось сгенерировать подсказку")
        print("   Возможные причины:")
        print("   - Проблема с OpenAI API")
        print("   - Нет интернет-соединения")
        print("   - Проблема с API ключом")
        print("\n" + "=" * 60)
        print("❌ ТЕСТ НЕ ПРОЙДЕН")
        print("=" * 60)
        sys.exit(1)

except ImportError as e:
    print(f"\n❌ ОШИБКА ИМПОРТА: {e}")
    print("   Проверьте, что все зависимости установлены")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ ОШИБКА: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
