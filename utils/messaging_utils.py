#!/usr/bin/env python3
"""
Утилиты для работы с сообщениями бота в группах (изолированный модуль)
"""

import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.orm import Session

from database import BotMessage, ChatSettings

logger = logging.getLogger(__name__)


async def mark_bot_removed(session: Session, chat_id: int) -> None:
    """
    Помечает бота как удаленного из группы

    Args:
        session: SQLAlchemy сессия
        chat_id: ID группового чата
    """
    from datetime import datetime

    from sqlalchemy import select

    result = await session.execute(select(ChatSettings).where(ChatSettings.chat_id == chat_id))
    settings = result.scalar_one_or_none()

    if settings and settings.bot_status != "removed":
        settings.bot_status = "removed"
        settings.bot_removed_at = datetime.utcnow()
        await session.commit()
        logger.warning(f"🚫 Бот помечен как удаленный из группы {chat_id}")


async def auto_delete_message(bot: Bot, chat_id: int, message_id: int, delay_seconds: int):
    """Автоудаление сообщения через указанное количество секунд (только для групповых чатов)"""
    try:
        import asyncio

        logger.info(f"🕐 Запущено автоудаление сообщения {message_id} в чате {chat_id} через {delay_seconds}с")
        await asyncio.sleep(delay_seconds)

        # Проверяем права бота перед удалением
        try:
            bot_member = await bot.get_chat_member(chat_id, bot.id)
            can_delete = getattr(bot_member, "can_delete_messages", False)
            logger.info(f"🔍 Права бота в чате {chat_id}: status={bot_member.status}, can_delete_messages={can_delete}")

            if bot_member.status != "administrator" or not can_delete:
                logger.warning(
                    f"⚠️ Бот не может удалять сообщения в чате {chat_id}: "
                    f"status={bot_member.status}, can_delete={can_delete}"
                )
                return
        except Exception as perm_error:
            logger.warning(f"⚠️ Не удалось проверить права бота в чате {chat_id}: {perm_error}")
            return

        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"✅ Сообщение {message_id} автоматически удалено из чата {chat_id} через {delay_seconds}с")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось автоматически удалить сообщение {message_id}: {e}")


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
        # Получаем следующий chat_number из последовательности
        from sqlalchemy import text

        result = session.execute(text("SELECT nextval('chat_number_seq')"))
        chat_number = result.scalar()
        logger.info(f"✅ Назначен chat_number={chat_number} для чата {chat_id}")
        settings = ChatSettings(chat_id=chat_id, chat_number=chat_number)
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

    # Автоудаление через 4 минуты для определенных тегов (кроме важных уведомлений)
    if tag in ["service", "panel", "list"]:  # Не удаляем "notification" (новые события)
        asyncio.create_task(auto_delete_message(bot, chat_id, msg.message_id, 210))  # 3.5 минуты

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

    # Получаем все неудаленные сообщения (кроме "notification")
    messages = (
        session.query(BotMessage)
        .filter(
            BotMessage.chat_id == chat_id,
            BotMessage.deleted is False,
            BotMessage.tag != "notification",  # НЕ удаляем сообщения "Новое событие!"
        )
        .all()
    )

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
    logger.info(f"🔥 ensure_panel: начинаем для чата {chat_id}")

    # Получаем настройки чата
    from sqlalchemy import select, text

    result = await session.execute(select(ChatSettings).where(ChatSettings.chat_id == chat_id))
    settings = result.scalar_one_or_none()
    logger.info(f"🔥 ensure_panel: настройки чата {chat_id} = {settings}")

    if not settings:
        logger.info(f"🔥 ensure_panel: создаем новые настройки для чата {chat_id}")
        # Получаем следующий chat_number из последовательности
        result = await session.execute(text("SELECT nextval('chat_number_seq')"))
        chat_number = result.scalar()
        logger.info(f"✅ Назначен chat_number={chat_number} для чата {chat_id}")
        settings = ChatSettings(chat_id=chat_id, chat_number=chat_number)
        session.add(settings)
        await session.commit()

    # Пытаемся отредактировать существующее сообщение
    if settings.last_panel_message_id:
        logger.info(f"🔥 ensure_panel: пытаемся отредактировать message_id={settings.last_panel_message_id}")
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
    logger.info(f"🔥 ensure_panel: создаем новое сообщение для чата {chat_id}")
    try:
        msg = await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")
    except TelegramForbiddenError as e:
        logger.error(f"🚫 Бот был удален из группы {chat_id}: {e}")
        await mark_bot_removed(session, chat_id)
        raise
    except TelegramBadRequest as e:
        logger.error(f"⚠️ Ошибка отправки сообщения в группу {chat_id}: {e}")
        # Проверяем, не был ли бот удален
        if "chat not found" in str(e).lower() or "bot was kicked" in str(e).lower():
            await mark_bot_removed(session, chat_id)
        raise

    # Сохраняем ID панели и трекаем сообщение
    logger.info(f"🔥 ensure_panel: сохраняем message_id={msg.message_id} в настройках и bot_messages")
    logger.info(f"🔥 ensure_panel: chat_id={chat_id}, message_id={msg.message_id}, tag=panel")

    settings.last_panel_message_id = msg.message_id
    bot_msg = BotMessage(chat_id=chat_id, message_id=msg.message_id, tag="panel")
    session.add(bot_msg)

    logger.info("🔥 ensure_panel: перед commit - bot_msg добавлен в сессию")
    await session.commit()
    logger.info("🔥 ensure_panel: после commit - данные сохранены в БД")

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
    try:
        msg = await bot.send_message(chat_id, text, **kwargs)
    except TelegramForbiddenError as e:
        logger.error(f"🚫 Бот был удален из группы {chat_id}: {e}")
        await mark_bot_removed(session, chat_id)
        raise
    except TelegramBadRequest as e:
        logger.error(f"⚠️ Ошибка отправки сообщения в группу {chat_id}: {e}")
        # Проверяем, не был ли бот удален
        if "chat not found" in str(e).lower() or "bot was kicked" in str(e).lower():
            await mark_bot_removed(session, chat_id)
        raise

    # Трекаем сообщение
    bot_msg = BotMessage(chat_id=chat_id, message_id=msg.message_id, tag=tag)
    session.add(bot_msg)
    await session.commit()

    logger.info(f"✅ Отправлено tracked сообщение в чат {chat_id}, message_id={msg.message_id}, tag={tag}")

    # Автоудаление через 3.5 минуты для определенных тегов (кроме важных уведомлений)
    if tag in ["service", "panel", "list"]:  # Не удаляем "notification" (новые события)
        logger.info(f"🕐 Запуск автоудаления для сообщения {msg.message_id} с тегом '{tag}' в чате {chat_id}")
        asyncio.create_task(auto_delete_message(bot, chat_id, msg.message_id, 210))  # 3.5 минуты

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
    logger.info(f"🔥 delete_all_tracked: начинаем удаление для чата {chat_id}")

    # Получаем все неудаленные сообщения
    from sqlalchemy import select

    result = await session.execute(
        select(BotMessage).where(
            BotMessage.chat_id == chat_id,
            BotMessage.deleted.is_(False),
            BotMessage.tag != "notification",  # НЕ удаляем сообщения "Новое событие!"
        )
    )
    messages = result.scalars().all()

    logger.info(f"🔥 Найдено {len(messages)} сообщений для удаления в чате {chat_id}")

    if not messages:
        logger.warning(f"⚠️ В bot_messages нет записей для чата {chat_id}")
        return 0

    deleted = 0
    for bot_msg in messages:
        logger.info(f"🔥 Пытаемся удалить сообщение {bot_msg.message_id} (tag: {bot_msg.tag})")
        try:
            await bot.delete_message(chat_id, bot_msg.message_id)
            bot_msg.deleted = True
            deleted += 1
            logger.info(f"✅ Удалено сообщение {bot_msg.message_id} (tag: {bot_msg.tag})")
        except TelegramForbiddenError as e:
            # Нет прав на удаление
            logger.error(f"🚫 Нет прав на удаление сообщения {bot_msg.message_id}: {e}")
            # НЕ помечаем как удаленное!
        except TelegramBadRequest as e:
            # Сообщение уже удалено или недоступно
            logger.warning(f"⚠️ Не удалось удалить сообщение {bot_msg.message_id}: {e}")
            bot_msg.deleted = True  # Помечаем как удаленное
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка удаления сообщения {bot_msg.message_id}: {e}")
            # НЕ помечаем как удаленное при неожиданных ошибках!

    # Обнуляем ссылку на панель
    result = await session.execute(select(ChatSettings).where(ChatSettings.chat_id == chat_id))
    settings = result.scalar_one_or_none()
    if settings:
        settings.last_panel_message_id = None
        logger.info(f"🔥 Обнулена ссылка на панель для чата {chat_id}")

    await session.commit()
    logger.info(f"🔥 commit выполнен для чата {chat_id}")

    logger.info(f"✅ Удалено {deleted} из {len(messages)} сообщений бота в чате {chat_id}")
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


async def get_chat_administrators(bot: Bot, chat_id: int) -> list[dict]:
    """
    Получает список всех администраторов чата

    Args:
        bot: Экземпляр бота
        chat_id: ID группового чата

    Returns:
        Список словарей с информацией об админах:
        [
            {
                "user_id": int,
                "username": str | None,
                "first_name": str,
                "last_name": str | None,
                "status": str,  # "creator" или "administrator"
                "can_delete_messages": bool,
                "can_restrict_members": bool,
                "can_promote_members": bool,
                # ... другие права
            }
        ]
    """
    try:
        administrators = await bot.get_chat_administrators(chat_id)
        admin_list = []

        for admin in administrators:
            admin_info = {
                "user_id": admin.user.id,
                "username": admin.user.username,
                "first_name": admin.user.first_name,
                "last_name": admin.user.last_name,
                "status": admin.status,
                "can_delete_messages": getattr(admin, "can_delete_messages", False),
                "can_restrict_members": getattr(admin, "can_restrict_members", False),
                "can_promote_members": getattr(admin, "can_promote_members", False),
                "can_change_info": getattr(admin, "can_change_info", False),
                "can_invite_users": getattr(admin, "can_invite_users", False),
                "can_pin_messages": getattr(admin, "can_pin_messages", False),
                "can_manage_chat": getattr(admin, "can_manage_chat", False),
                "can_manage_video_chats": getattr(admin, "can_manage_video_chats", False),
            }
            admin_list.append(admin_info)

        logger.info(f"✅ Получен список из {len(admin_list)} администраторов чата {chat_id}")
        return admin_list

    except Exception as e:
        logger.error(f"❌ Ошибка получения списка администраторов чата {chat_id}: {e}")
        return []


async def get_chat_creator(bot: Bot, chat_id: int) -> dict | None:
    """
    Получает информацию о создателе чата

    Args:
        bot: Экземпляр бота
        chat_id: ID группового чата

    Returns:
        Словарь с информацией о создателе или None если не найден
    """
    try:
        administrators = await get_chat_administrators(bot, chat_id)
        creator = next((admin for admin in administrators if admin["status"] == "creator"), None)

        if creator:
            logger.info(f"✅ Найден создатель чата {chat_id}: {creator['first_name']} (@{creator['username']})")
        else:
            logger.warning(f"⚠️ Создатель чата {chat_id} не найден")

        return creator

    except Exception as e:
        logger.error(f"❌ Ошибка получения создателя чата {chat_id}: {e}")
        return None
