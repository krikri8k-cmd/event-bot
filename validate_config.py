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
    }

    # WEBHOOK_URL опционален, если есть RAILWAY_PUBLIC_DOMAIN или PUBLIC_URL
    webhook_url = os.getenv("WEBHOOK_URL")
    railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    public_url = os.getenv("PUBLIC_URL")

    if not webhook_url and not railway_public_domain and not public_url:
        required_vars["WEBHOOK_URL"] = "https://your-app.up.railway.app/webhook"

    missing_vars = []

    print("\n📋 Проверка обязательных переменных:")
    for var, example in required_vars.items():
        value = os.getenv(var)
        if value:
            # Маскируем чувствительные данные
            if "TOKEN" in var:
                # Для токенов показываем только первые 4 символа
                if len(value) > 4:
                    masked = value[:4] + "***" + " (скрыто)"
                else:
                    masked = "***"
                print(f"  ✅ {var}: {masked}")
            elif "DATABASE_URL" in var:
                # Маскируем пароль в DATABASE_URL
                if "@" in value:
                    parts = value.split("@")
                    if len(parts) == 2:
                        # Маскируем часть с паролем (между :// и @)
                        scheme_part = parts[0].split("://")
                        if len(scheme_part) == 2:
                            masked = f"{scheme_part[0]}://***@{parts[1]}"
                        else:
                            masked = "***"
                    else:
                        masked = "***"
                else:
                    masked = "***"
                print(f"  ✅ {var}: {masked}")
            elif "URL" in var:
                # Для других URL показываем только домен
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(value)
                    if parsed.netloc:
                        masked = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    else:
                        masked = "***"
                except Exception:
                    masked = "***"
                print(f"  ✅ {var}: {masked}")
            else:
                print(f"  ✅ {var}: {value}")
        else:
            print(f"  ❌ {var}: НЕ НАЙДЕНА")
            missing_vars.append(var)

    # Проверяем опциональные переменные для webhook
    if not webhook_url:
        if railway_public_domain:
            print(f"  ⚠️ WEBHOOK_URL: не установлен, но используется RAILWAY_PUBLIC_DOMAIN={railway_public_domain}")
        elif public_url:
            print(f"  ⚠️ WEBHOOK_URL: не установлен, но используется PUBLIC_URL={public_url}")
        else:
            # WEBHOOK_URL уже добавлен в missing_vars выше, если он обязателен
            pass

    if missing_vars:
        print(f"\n❌ ОШИБКА: Отсутствуют обязательные переменные: {', '.join(missing_vars)}")
        print("\n🔧 Для Railway добавьте эти переменные в настройках проекта:")
        for var in missing_vars:
            if var in required_vars:
                print(f"  {var}={required_vars[var]}")
        print("\n💡 Альтернатива для WEBHOOK_URL:")
        print("  Railway автоматически предоставляет RAILWAY_PUBLIC_DOMAIN")
        print("  Или установите PUBLIC_URL=https://your-app.up.railway.app")
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
