#!/usr/bin/env python3
"""
Скрипт для ручного запуска парсера BaliForum
"""

import sys
from datetime import datetime

# Устанавливаем UTF-8 для Windows
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Добавляем текущую директорию в путь
sys.path.append(".")

import logging

from dotenv import load_dotenv

from modern_scheduler import ModernEventScheduler

load_dotenv("app.local.env")

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

print("🚀 Запуск парсера BaliForum вручную...")
print(f"⏰ Время запуска: {datetime.now()}\n")

try:
    scheduler = ModernEventScheduler()
    scheduler.ingest_baliforum()
    print("\n✅ Парсинг завершен!")
except Exception as e:
    print(f"\n❌ Ошибка при парсинге: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
