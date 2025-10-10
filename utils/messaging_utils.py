#!/usr/bin/env python3
"""
Утилиты для работы с сообщениями бота в группах (изолированный модуль)
"""

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.orm import Session

from database import BotMessage, ChatSettings

logger = logging.getLogger(__name__)


# === SYNC ВЕРСИИ (для синхронной SQLAlchemy session) ===


def ensure_panel_sync(bot: Bot, session: Session, *, chat_id: int, text: str, kb: InlineKeyboardMarkup) -> int:
    """
    Редактирует существующий панель-пост или создает новый (синхронная версия)

    Args:
        bot: Экземпляр бота
        session: SQLAlchemy сессия (синхронная)
        chat_id: ID группового чата
        text: Текст панели
        kb: Клавиатура

    Returns:
        message_id созданного/обновленного сообщения
    """
    # Получаем настройки чата
    settings = session.query(ChatSettings).filter(ChatSettings.chat_id == chat_id).first()

    if not settings:
        settings = ChatSettings(chat_id=chat_id)
        session.add(settings)
        session.commit()

    # Пытаемся отредактировать существующее сообщение
    if settings.last_panel_message_id:
        try:
            # NOTE: Это синхронный код, но aiogram требует async
            # В реальности нужно использовать asyncio.run или async версию
            import asyncio

            asyncio.run(
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=settings.last_panel_message_id,
                    text=text,
                    reply_markup=kb,
                    parse_mode="Markdown",
                )
            )
            logger.info(f"✅ Отредактирован панель-пост в чате {chat_id}, message_id={settings.last_panel_message_id}")
            return settings.last_panel_message_id
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отредактировать панель-пост: {e}")

    # Создаем новое сообщение
    import asyncio

    msg = asyncio.run(bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown"))

    # Сохраняем ID панели и трекаем сообщение
    settings.last_panel_message_id = msg.message_id
    bot_msg = BotMessage(chat_id=chat_id, message_id=msg.message_id, tag="panel")
    session.add(bot_msg)
    session.commit()

    logger.info(f"✅ Создан новый панель-пост в чате {chat_id}, message_id={msg.message_id}")
    return msg.message_id


def send_tracked_sync(bot: Bot, session: Session, *, chat_id: int, text: str, tag: str = "service", **kwargs) -> Any:
    """
    Отправляет сообщение и сохраняет его ID для последующего удаления (синхронная версия)

    Args:
        bot: Экземпляр бота
        session: SQLAlchemy сессия (синхронная)
        chat_id: ID чата
        text: Текст сообщения
        tag: Тег сообщения (panel, service, notification)
        **kwargs: Дополнительные параметры для send_message

    Returns:
        Отправленное сообщение
    """
    import asyncio

    msg = asyncio.run(bot.send_message(chat_id, text, **kwargs))

    # Трекаем сообщение
    bot_msg = BotMessage(chat_id=chat_id, message_id=msg.message_id, tag=tag)
    session.add(bot_msg)
    session.commit()

    logger.info(f"✅ Отправлено tracked сообщение в чат {chat_id}, message_id={msg.message_id}, tag={tag}")
    return msg


def delete_all_tracked_sync(bot: Bot, session: Session, *, chat_id: int) -> int:
    """
    Удаляет все трекнутые сообщения бота в чате (синхронная версия)

    Args:
        bot: Экземпляр бота
        session: SQLAlchemy сессия (синхронная)
        chat_id: ID группового чата

    Returns:
        Количество удаленных сообщений
    """
    import asyncio

    # Получаем все неудаленные сообщения
    messages = session.query(BotMessage).filter(BotMessage.chat_id == chat_id, BotMessage.deleted is False).all()

    deleted = 0
    for bot_msg in messages:
        try:
            asyncio.run(bot.delete_message(chat_id, bot_msg.message_id))
            bot_msg.deleted = True
            deleted += 1
        except TelegramBadRequest as e:
            # Сообщение уже удалено или недоступно
            logger.warning(f"⚠️ Не удалось удалить сообщение {bot_msg.message_id}: {e}")
            bot_msg.deleted = True  # Помечаем как удаленное
        except Exception as e:
            logger.error(f"❌ Ошибка удаления сообщения {bot_msg.message_id}: {e}")

    # Обнуляем ссылку на панель
    settings = session.query(ChatSettings).filter(ChatSettings.chat_id == chat_id).first()
    if settings:
        settings.last_panel_message_id = None

    session.commit()

    logger.info(f"✅ Удалено {deleted} сообщений бота в чате {chat_id}")
    return deleted


# === ASYNC ВЕРСИИ (для асинхронной работы) ===


async def ensure_panel(bot: Bot, session: Session, *, chat_id: int, text: str, kb: InlineKeyboardMarkup) -> int:
    """
    Редактирует существующий панель-пост или создает новый (ASYNC версия)

    Args:
        bot: Экземпляр бота
        session: SQLAlchemy сессия
        chat_id: ID группового чата
        text: Текст панели
        kb: Клавиатура

    Returns:
        message_id созданного/обновленного сообщения
    """
    # Получаем настройки чата
    settings = session.query(ChatSettings).filter(ChatSettings.chat_id == chat_id).first()

    if not settings:
        settings = ChatSettings(chat_id=chat_id)
        session.add(settings)
        session.commit()

    # Пытаемся отредактировать существующее сообщение
    if settings.last_panel_message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=settings.last_panel_message_id,
                text=text,
                reply_markup=kb,
                parse_mode="Markdown",
            )
            logger.info(f"✅ Отредактирован панель-пост в чате {chat_id}, message_id={settings.last_panel_message_id}")
            return settings.last_panel_message_id
        except TelegramBadRequest as e:
            logger.warning(f"⚠️ Не удалось отредактировать панель-пост: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка редактирования панель-поста: {e}")

    # Создаем новое сообщение
    msg = await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

    # Сохраняем ID панели и трекаем сообщение
    settings.last_panel_message_id = msg.message_id
    bot_msg = BotMessage(chat_id=chat_id, message_id=msg.message_id, tag="panel")
    session.add(bot_msg)
    session.commit()

    logger.info(f"✅ Создан новый панель-пост в чате {chat_id}, message_id={msg.message_id}")
    return msg.message_id


async def send_tracked(bot: Bot, session: Session, *, chat_id: int, text: str, tag: str = "service", **kwargs) -> Any:
    """
    Отправляет сообщение и сохраняет его ID для последующего удаления (ASYNC версия)

    Args:
        bot: Экземпляр бота
        session: SQLAlchemy сессия
        chat_id: ID чата
        text: Текст сообщения
        tag: Тег сообщения (panel, service, notification)
        **kwargs: Дополнительные параметры для send_message

    Returns:
        Отправленное сообщение
    """
    msg = await bot.send_message(chat_id, text, **kwargs)

    # Трекаем сообщение
    bot_msg = BotMessage(chat_id=chat_id, message_id=msg.message_id, tag=tag)
    session.add(bot_msg)
    session.commit()

    logger.info(f"✅ Отправлено tracked сообщение в чат {chat_id}, message_id={msg.message_id}, tag={tag}")
    return msg


async def delete_all_tracked(bot: Bot, session: Session, *, chat_id: int) -> int:
    """
    Удаляет все трекнутые сообщения бота в чате (ASYNC версия)

    Args:
        bot: Экземпляр бота
        session: SQLAlchemy сессия
        chat_id: ID группового чата

    Returns:
        Количество удаленных сообщений
    """
    # Получаем все неудаленные сообщения
    messages = session.query(BotMessage).filter(BotMessage.chat_id == chat_id, BotMessage.deleted is False).all()

    deleted = 0
    for bot_msg in messages:
        try:
            await bot.delete_message(chat_id, bot_msg.message_id)
            bot_msg.deleted = True
            deleted += 1
        except TelegramBadRequest as e:
            # Сообщение уже удалено или недоступно
            logger.warning(f"⚠️ Не удалось удалить сообщение {bot_msg.message_id}: {e}")
            bot_msg.deleted = True  # Помечаем как удаленное
        except Exception as e:
            logger.error(f"❌ Ошибка удаления сообщения {bot_msg.message_id}: {e}")

    # Обнуляем ссылку на панель
    settings = session.query(ChatSettings).filter(ChatSettings.chat_id == chat_id).first()
    if settings:
        settings.last_panel_message_id = None

    session.commit()

    logger.info(f"✅ Удалено {deleted} сообщений бота в чате {chat_id}")
    return deleted


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором чата

    Args:
        bot: Экземпляр бота
        chat_id: ID группового чата
        user_id: ID пользователя

    Returns:
        True если пользователь - админ, False иначе
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception as e:
        logger.error(f"❌ Ошибка проверки прав админа: {e}")
        return False
