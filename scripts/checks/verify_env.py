#!/usr/bin/env python3
"""
Скрипт проверки переменных окружения.
Проверяет наличие критически важных переменных в .env.local
"""

import os
import sys

from dotenv import load_dotenv


def main():
    # Загружаем переменные из .env.local
    load_dotenv(".env.local")

    ok = True

    # Проверяем критически важные переменные
    critical_vars = ["OPENAI_API_KEY", "DATABASE_URL"]

    for key in critical_vars:
        val = os.getenv(key)
        status = "SET" if val else "MISSING"
        print(f"{key}: {status}")
        if not val:
            ok = False

    # Проверяем опциональные переменные
    optional_vars = ["AI_INGEST_ENABLED", "TELEGRAM_TOKEN", "GOOGLE_MAPS_API_KEY"]

    for key in optional_vars:
        val = os.getenv(key)
        status = "SET" if val else "MISSING"
        print(f"{key}: {status}")

    # Проверяем AI_INGEST_ENABLED отдельно
    ai_enabled = os.getenv("AI_INGEST_ENABLED", "MISSING")
    print(f"AI_INGEST_ENABLED: {ai_enabled}")

    if not ok:
        print("\n❌ Критические переменные отсутствуют!")
        sys.exit(1)
    else:
        print("\n✅ Все критические переменные настроены!")
        sys.exit(0)


if __name__ == "__main__":
    main()
