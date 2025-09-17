#!/usr/bin/env python3
"""
Скрипт для настройки и запуска автоматизации пополнения событий
"""

import logging
import sys
from datetime import datetime

from config import load_settings
from database import get_engine, init_engine
from modern_scheduler import ModernEventScheduler
from utils.unified_events_service import UnifiedEventsService

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def check_configuration():
    """Проверяет конфигурацию автоматизации"""
    logger.info("🔍 Проверка конфигурации...")

    settings = load_settings()

    logger.info("📋 Текущие настройки парсеров:")
    logger.info(f"   🌴 BaliForum: {'✅ включен' if settings.enable_baliforum else '❌ выключен'}")
    logger.info(f"   🤖 AI парсинг: {'✅ включен' if settings.ai_parse_enable else '❌ выключен'}")
    logger.info(f"   🎭 AI генерация: {'✅ включен' if settings.ai_generate_synthetic else '❌ выключен'}")
    logger.info(f"   📅 Meetup: {'✅ включен' if settings.enable_meetup_api else '❌ выключен'}")
    logger.info(f"   🎫 Eventbrite: {'✅ включен' if settings.enable_eventbrite_api else '❌ выключен'}")

    # Проверяем API ключи
    logger.info("🔑 API ключи:")
    logger.info(f"   OpenAI: {'✅ настроен' if settings.openai_api_key else '❌ не настроен'}")
    logger.info(f"   Google Maps: {'✅ настроен' if settings.google_maps_api_key else '❌ не настроен'}")
    logger.info(f"   Meetup: {'✅ настроен' if settings.meetup_api_key else '❌ не настроен'}")

    return settings


def check_database():
    """Проверяет подключение к базе данных"""
    logger.info("🗃️ Проверка базы данных...")

    try:
        settings = load_settings()
        init_engine(settings.database_url)
        engine = get_engine()
        service = UnifiedEventsService(engine)

        # Проверяем статистику
        stats = service.get_events_stats("bali")
        logger.info(
            f"   📊 События в Бали: {stats['total_events']} "
            f"(парсерных: {stats['parser_events']}, "
            f"пользовательских: {stats['user_events']})"
        )

        return True

    except Exception as e:
        logger.error(f"   ❌ Ошибка подключения к БД: {e}")
        return False


def run_test_cycle():
    """Запускает тестовый цикл парсинга"""
    logger.info("🧪 Запуск тестового цикла парсинга...")

    try:
        scheduler = ModernEventScheduler()
        scheduler.run_full_ingest()
        logger.info("   ✅ Тестовый цикл выполнен успешно!")
        return True

    except Exception as e:
        logger.error(f"   ❌ Ошибка тестового цикла: {e}")
        return False


def start_automation():
    """Запускает автоматизацию"""
    logger.info("🚀 Запуск автоматизации...")

    try:
        scheduler = ModernEventScheduler()
        scheduler.start()

        logger.info("✅ Автоматизация запущена!")
        logger.info("📅 Расписание:")
        logger.info("   • Полный цикл парсинга: каждые 30 минут")
        logger.info("   • Очистка старых событий: каждые 6 часов")
        logger.info("   • Первый запуск: сейчас")

        return scheduler

    except Exception as e:
        logger.error(f"   ❌ Ошибка запуска автоматизации: {e}")
        return None


def main():
    """Основная функция"""
    logger.info("🎯 === НАСТРОЙКА АВТОМАТИЗАЦИИ СОБЫТИЙ ===")
    logger.info(f"⏰ Время запуска: {datetime.now()}")

    # 1. Проверяем конфигурацию
    settings = check_configuration()

    # 2. Проверяем базу данных
    if not check_database():
        logger.error("❌ Проблемы с базой данных. Завершение.")
        sys.exit(1)

    # 3. Запускаем тестовый цикл
    if not run_test_cycle():
        logger.error("❌ Тестовый цикл не прошел. Завершение.")
        sys.exit(1)

    # 4. Запрашиваем у пользователя
    print("\n" + "=" * 50)
    print("🎯 ГОТОВО К ЗАПУСКУ АВТОМАТИЗАЦИИ!")
    print("=" * 50)
    print("📋 Что будет происходить:")
    print("   • Каждые 12 часов: парсинг BaliForum (2 раза в день)")
    if settings.ai_generate_synthetic:
        print("   • Каждые 12 часов: генерация AI событий")
    print("   • Каждые 6 часов: очистка старых событий")
    print("   • Логирование всех операций")
    print()

    response = input("🚀 Запустить автоматизацию? (y/n): ").strip().lower()

    if response in ["y", "yes", "да", "д"]:
        scheduler = start_automation()

        if scheduler:
            try:
                print("\n✅ Автоматизация работает!")
                print("💡 Для остановки нажмите Ctrl+C")
                print("📊 Логи будут выводиться в реальном времени...")
                print("-" * 50)

                # Ждем бесконечно
                import time

                while True:
                    time.sleep(10)

            except KeyboardInterrupt:
                logger.info("⏹️ Получен сигнал остановки...")
                scheduler.stop()
                logger.info("✅ Автоматизация остановлена")
        else:
            logger.error("❌ Не удалось запустить автоматизацию")
            sys.exit(1)
    else:
        logger.info("🛑 Автоматизация не запущена")
        print("💡 Для запуска позже используйте: python setup_automation.py")


if __name__ == "__main__":
    main()
