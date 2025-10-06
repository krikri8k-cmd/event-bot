#!/usr/bin/env python3
"""
Скрипт для валидации конфигурации бота
Работает как локально, так и в Railway
"""

import os
import sys
from pathlib import Path


def load_env_file():
    """Загружает переменные из .env файла если он существует"""
    env_files = [".env", "app.local.env", "railway.env"]

    for env_file in env_files:
        if Path(env_file).exists():
            print(f"📁 Загружаем переменные из {env_file}")
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        if key not in os.environ:  # Не перезаписываем существующие
                            os.environ[key] = value
            return True

    print("⚠️ Файл .env не найден, используем только переменные окружения")
    return False


def validate_config():
    """Валидирует конфигурацию бота"""

    print("🔍 Валидация конфигурации Event-Bot...")
    print("=" * 50)

    # Загружаем .env файл если есть
    load_env_file()

    # Проверяем обязательные переменные
    required_vars = {
        "DATABASE_URL": "postgresql://user:pass@host:port/db",
        "TELEGRAM_TOKEN": "bot_token_from_botfather",
        "WEBHOOK_URL": "https://your-app.up.railway.app/webhook",
    }

    missing_vars = []

    print("\n📋 Проверка обязательных переменных:")
    for var, example in required_vars.items():
        value = os.getenv(var)
        if value:
            # Маскируем чувствительные данные
            if "TOKEN" in var or "URL" in var:
                if len(value) > 20:
                    masked = value[:10] + "..." + value[-10:]
                else:
                    masked = "***"
                print(f"  ✅ {var}: {masked}")
            else:
                print(f"  ✅ {var}: {value}")
        else:
            print(f"  ❌ {var}: НЕ НАЙДЕНА")
            missing_vars.append(var)

    if missing_vars:
        print(f"\n❌ ОШИБКА: Отсутствуют обязательные переменные: {', '.join(missing_vars)}")
        print("\n🔧 Для Railway добавьте эти переменные в настройках проекта:")
        for var in missing_vars:
            print(f"  {var}={required_vars[var]}")
        return False

    # Проверяем загрузку конфигурации
    print("\n🔧 Проверка загрузки конфигурации...")
    try:
        from config import load_settings

        settings = load_settings()
        print("✅ Конфигурация загружена успешно")
        print(f"   📊 BaliForum: {settings.enable_baliforum}")
        print(f"   📊 KudaGo: {settings.kudago_enabled}")
        print(f"   🤖 AI parsing: {settings.ai_parse_enable}")
        print(f"   ⏰ Moments: {settings.moments_enable}")
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        return False


if __name__ == "__main__":
    success = validate_config()
    if not success:
        sys.exit(1)
    print("\n🎉 Конфигурация валидна! Готово к деплою.")
