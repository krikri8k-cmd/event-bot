#!/usr/bin/env python3
"""
Скрипт для запуска уведомлений о заданиях по расписанию
Запускается каждые 30 минут для проверки дедлайнов
"""

import asyncio
import logging
import time

import schedule

from task_notifications import main as run_notifications

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def run_notifications_sync():
    """Синхронная обертка для асинхронной функции уведомлений"""
    try:
        asyncio.run(run_notifications())
    except Exception as e:
        logger.error(f"Ошибка при запуске уведомлений: {e}")


def main():
    """Основная функция планировщика"""
    logger.info("Запуск планировщика уведомлений о заданиях")

    # Настраиваем расписание
    # Проверяем каждые 30 минут
    schedule.every(30).minutes.do(run_notifications_sync)

    # Также проверяем каждый час в 00 минут
    schedule.every().hour.at(":00").do(run_notifications_sync)

    logger.info("Планировщик настроен:")
    logger.info("- Проверка каждые 30 минут")
    logger.info("- Проверка каждый час в 00 минут")

    # Запускаем планировщик
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Проверяем каждую минуту
        except KeyboardInterrupt:
            logger.info("Планировщик остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"Ошибка в планировщике: {e}")
            time.sleep(60)  # Ждем минуту перед повтором


if __name__ == "__main__":
    main()
