#!/usr/bin/env python3
"""
Скрипт для проверки переменных окружения Railway
"""

import os


def check_required_env_vars():
    """Проверяет наличие обязательных переменных окружения"""

    required_vars = ["DATABASE_URL", "TELEGRAM_TOKEN", "WEBHOOK_URL"]

    optional_vars = [
        "GOOGLE_MAPS_API_KEY",
        "OPENAI_API_KEY",
        "ADMIN_IDS",
        "BOT_RUN_MODE",
        "GEOCODE_ENABLE",
        "DEFAULT_RADIUS_KM",
        "KUDAGO_ENABLED",
        "BALIFORUM_ENABLE",
    ]

    print("🔍 Проверка переменных окружения Railway:")
    print("=" * 50)

    missing_required = []
    present_optional = []

    print("\n📋 ОБЯЗАТЕЛЬНЫЕ переменные:")
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Скрываем чувствительные данные
            if "TOKEN" in var or "URL" in var:
                masked_value = value[:10] + "..." + value[-10:] if len(value) > 20 else "***"
                print(f"  ✅ {var}: {masked_value}")
            else:
                print(f"  ✅ {var}: {value}")
        else:
            print(f"  ❌ {var}: НЕ НАЙДЕНА")
            missing_required.append(var)

    print("\n📋 ОПЦИОНАЛЬНЫЕ переменные:")
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"  ✅ {var}: {value}")
            present_optional.append(var)
        else:
            print(f"  ⚪ {var}: не установлена")

    print("\n" + "=" * 50)

    if missing_required:
        print(f"❌ ОШИБКА: Отсутствуют обязательные переменные: {', '.join(missing_required)}")
        print("\n🔧 Для исправления добавьте эти переменные в Railway:")
        for var in missing_required:
            if var == "DATABASE_URL":
                print(f"  {var}=postgresql://user:password@host:port/database")
            elif var == "TELEGRAM_TOKEN":
                print(f"  {var}=your_bot_token_from_botfather")
            elif var == "WEBHOOK_URL":
                print(f"  {var}=https://your-railway-app.up.railway.app/webhook")
        return False
    else:
        print("✅ Все обязательные переменные настроены!")
        return True


if __name__ == "__main__":
    check_required_env_vars()
