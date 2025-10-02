#!/usr/bin/env python3
"""
Скрипт для отправки уведомлений о приближающихся дедлайнах заданий
"""

import asyncio
import logging
import os

from aiogram import Bot
from dotenv import load_dotenv

from tasks_service import get_tasks_approaching_deadline, mark_tasks_as_expired

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv("app.local.env")

# Инициализируем бота
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))


async def send_deadline_notifications():
    """Отправляет уведомления о приближающихся дедлайнах"""
    try:
        # Получаем задания, приближающиеся к дедлайну (за 2 часа)
        approaching_tasks = get_tasks_approaching_deadline(hours_before=2)

        if not approaching_tasks:
            logger.info("Нет заданий, приближающихся к дедлайну")
            return

        logger.info(f"Найдено {len(approaching_tasks)} заданий, приближающихся к дедлайну")

        for task_info in approaching_tasks:
            user_id = task_info["user_id"]
            task_title = task_info["task_title"]
            hours_left = task_info["hours_left"]

            # Формируем сообщение
            if hours_left < 1:
                message = (
                    f"⏰ **Срочно!**\n\n"
                    f"Задание **{task_title}** истекает менее чем через час!\n\n"
                    f"Успейте завершить и получить ракеты! 🚀"
                )
            else:
                message = (
                    f"⏰ **Напоминание**\n\n"
                    f"Задание **{task_title}** истекает через {int(hours_left)} часов.\n\n"
                    f"Не забудьте завершить и написать фидбек! 📝"
                )

            try:
                await bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
                logger.info(f"Отправлено уведомление пользователю {user_id} о задании {task_title}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений: {e}")


async def mark_expired_tasks():
    """Помечает просроченные задания как истекшие"""
    try:
        expired_count = mark_tasks_as_expired()
        if expired_count > 0:
            logger.info(f"Помечено как истекшие: {expired_count} заданий")
        else:
            logger.info("Нет просроченных заданий")
    except Exception as e:
        logger.error(f"Ошибка при пометке просроченных заданий: {e}")


async def main():
    """Основная функция"""
    logger.info("Запуск системы уведомлений о заданиях")

    try:
        # Помечаем просроченные задания
        await mark_expired_tasks()

        # Отправляем уведомления о приближающихся дедлайнах
        await send_deadline_notifications()

        logger.info("Система уведомлений завершила работу")

    except Exception as e:
        logger.error(f"Ошибка в основной функции: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
