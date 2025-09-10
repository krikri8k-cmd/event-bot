#!/usr/bin/env python3
"""
Проверка конфигурации проекта
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_settings


def check_configuration():
    """Проверяет конфигурацию проекта"""

    print("🔧 Проверка конфигурации проекта")
    print("=" * 50)

    try:
        settings = load_settings()

        # Проверяем обязательные настройки
        required_settings = [
            ("telegram_token", "TELEGRAM_TOKEN"),
            ("database_url", "DATABASE_URL"),
            ("default_radius_km", "DEFAULT_RADIUS_KM"),
            ("max_radius_km", "MAX_RADIUS_KM"),
            ("radius_step_km", "RADIUS_STEP_KM"),
        ]

        print("📋 Основные настройки:")
        missing = []
        for attr, env_name in required_settings:
            value = getattr(settings, attr, None)
            if value:
                if attr == "telegram_token":
                    # Скрываем токен для безопасности
                    display_value = f"{value[:10]}...{value[-4:]}" if len(value) > 14 else "***"
                elif attr == "database_url":
                    # Скрываем пароль в URL
                    if "@" in value:
                        parts = value.split("@")
                        if len(parts) == 2:
                            display_value = f"{parts[0].split('://')[0]}://***@{parts[1]}"
                        else:
                            display_value = "***"
                    else:
                        display_value = "***"
                else:
                    display_value = value
                print(f"  ✅ {env_name}: {display_value}")
            else:
                print(f"  ❌ {env_name}: НЕ НАСТРОЕНО")
                missing.append(env_name)

        print()

        # Проверяем настройки моментов
        print("⚡ Настройки моментов:")
        moments_settings = [
            ("moments_enable", "MOMENTS_ENABLE"),
            ("moment_ttl_options", "MOMENT_TTL_OPTIONS"),
            ("moment_daily_limit", "MOMENT_DAILY_LIMIT"),
            ("moment_max_radius_km", "MOMENT_MAX_RADIUS_KM"),
        ]

        for attr, env_name in moments_settings:
            value = getattr(settings, attr, None)
            if value is not None:
                print(f"  ✅ {env_name}: {value}")
            else:
                print(f"  ❌ {env_name}: НЕ НАСТРОЕНО")
                missing.append(env_name)

        print()

        # Проверяем настройки AI
        print("🤖 Настройки AI:")
        ai_settings = [
            ("ai_parse_enable", "AI_PARSE_ENABLE"),
            ("ai_generate_synthetic", "AI_GENERATE_SYNTHETIC"),
            ("strict_source_only", "STRICT_SOURCE_ONLY"),
        ]

        for attr, env_name in ai_settings:
            value = getattr(settings, attr, None)
            if value is not None:
                print(f"  ✅ {env_name}: {value}")
            else:
                print(f"  ❌ {env_name}: НЕ НАСТРОЕНО")
                missing.append(env_name)

        print()

        # Проверяем источники событий
        print("🔗 Источники событий:")
        source_settings = [
            ("enable_meetup_api", "ENABLE_MEETUP_API"),
            ("enable_ics_feeds", "ENABLE_ICS_FEEDS"),
            ("enable_eventbrite_api", "ENABLE_EVENTBRITE_API"),
        ]

        for attr, env_name in source_settings:
            value = getattr(settings, attr, None)
            if value is not None:
                status = "✅ Включен" if value else "❌ Отключен"
                print(f"  {status} {env_name}: {value}")
            else:
                print(f"  ❌ {env_name}: НЕ НАСТРОЕНО")
                missing.append(env_name)

        # Проверяем ICS фиды
        if settings.ics_feeds:
            print(f"  ✅ ICS_FEEDS: {len(settings.ics_feeds)} фидов")
            for i, feed in enumerate(settings.ics_feeds[:3], 1):
                print(f"    {i}. {feed}")
            if len(settings.ics_feeds) > 3:
                print(f"    ... и еще {len(settings.ics_feeds) - 3}")
        else:
            print("  ⚠️ ICS_FEEDS: нет фидов")

        print()

        # Проверяем геокодирование
        print("🗺️ Геокодирование:")
        geo_settings = [
            ("google_maps_api_key", "GOOGLE_MAPS_API_KEY"),
        ]

        for attr, env_name in geo_settings:
            value = getattr(settings, attr, None)
            if value:
                display_value = f"{value[:10]}...{value[-4:]}" if len(value) > 14 else "***"
                print(f"  ✅ {env_name}: {display_value}")
            else:
                print(f"  ❌ {env_name}: НЕ НАСТРОЕНО")
                missing.append(env_name)

        print()

        # Итоговый результат
        if missing:
            print("❌ ПРОБЛЕМЫ КОНФИГУРАЦИИ:")
            for setting in missing:
                print(f"  • {setting}")
            print()
            print("💡 Добавьте недостающие переменные в app.local.env")
            return False
        else:
            print("✅ ВСЕ НАСТРОЙКИ КОРРЕКТНЫ!")
            return True

    except Exception as e:
        print(f"❌ Ошибка при проверке конфигурации: {e}")
        return False


if __name__ == "__main__":
    success = check_configuration()
    sys.exit(0 if success else 1)
