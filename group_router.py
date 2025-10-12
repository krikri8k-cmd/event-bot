#!/usr/bin/env python3
"""
Изолированный роутер для групповых чатов (EventAroundBot - версия для чатов)

ВАЖНО: Этот модуль полностью изолирован от основного бота!
- Работает ТОЛЬКО в group/supergroup чатах
- НЕ импортирует FSM состояния из основного бота
- НЕ импортирует сервисы из основного бота
- Связь с основным ботом только через deep-link
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database import CommunityEvent
from utils.messaging_utils import delete_all_tracked, ensure_panel, is_chat_admin

logger = logging.getLogger(__name__)

# === КОНФИГУРАЦИЯ ===

# Username бота для deep-links (будет установлен при инициализации)
MAIN_BOT_USERNAME = None  # Будет установлен в set_bot_username()

# === РОУТЕР ===

group_router = Router(name="group_router")


# === ИНИЦИАЛИЗАЦИЯ ===


def set_bot_username(username: str):
    """Устанавливает username бота для deep-links"""
    global MAIN_BOT_USERNAME
    MAIN_BOT_USERNAME = username
    logger.info(f"✅ Установлен username бота для группового роутера: {username}")


# Жёсткая изоляция: роутер работает ТОЛЬКО в группах
group_router.message.filter(F.chat.type.in_({"group", "supergroup"}))
group_router.callback_query.filter(F.message.chat.type.in_({"group", "supergroup"}))

# === ТЕКСТЫ И КЛАВИАТУРЫ ===

PANEL_TEXT = (
    "👋 **Привет! Я EventAroundBot для группового чата!**\n\n"
    "🎯 **Я умею:**\n"
    "• Создавать события участниками чата\n"
    "• Показывать события этого чата\n"
    "• Переводить в полный бот для геопоиска\n\n"
    "💡 **Выберите действие:**"
)


def group_kb(chat_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для панели группового чата"""
    username = MAIN_BOT_USERNAME or "EventAroundBot"  # fallback
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать событие", url=f"https://t.me/{username}?start=chat_{chat_id}")],
            [InlineKeyboardButton(text="📋 События этого чата", callback_data="group_list")],
            [InlineKeyboardButton(text="🚀 Полный бот (с геолокацией)", url=f"https://t.me/{username}")],
            [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_confirm")],
        ]
    )


# === ОБРАБОТЧИКИ ===


@group_router.message(Command("start"))
async def group_start(message: Message, bot: Bot, session: AsyncSession):
    """Приветствие в групповом чате - создает/редактирует панель-пост"""
    chat_id = message.chat.id
    logger.info(f"🔥 group_start: команда /start в группе {chat_id} от пользователя {message.from_user.id}")

    try:
        logger.info(f"🔥 group_start: вызываем ensure_panel для чата {chat_id}")
        panel_id = await ensure_panel(bot, session, chat_id=chat_id, text=PANEL_TEXT, kb=group_kb(chat_id))
        logger.info(f"🔥 group_start: ensure_panel вернул message_id={panel_id}")
    except Exception as e:
        logger.error(f"❌ group_start: ошибка при создании панели: {e}")
        # Fallback - отправляем обычное сообщение
        await message.answer(PANEL_TEXT, reply_markup=group_kb(chat_id), parse_mode="Markdown")


@group_router.callback_query(F.data == "group_list")
async def group_list_events(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Показать список событий этого чата"""
    chat_id = callback.message.chat.id
    logger.info(f"🔥 group_list_events: запрос списка событий в чате {chat_id}")

    await callback.answer()  # Тост, не спамим

    try:
        # Получаем будущие события этого чата
        from sqlalchemy import select

        stmt = (
            select(CommunityEvent)
            .where(
                CommunityEvent.chat_id == chat_id,
                CommunityEvent.status == "open",
                CommunityEvent.starts_at > datetime.utcnow(),
            )
            .order_by(CommunityEvent.starts_at)
            .limit(10)
        )

        result = await session.execute(stmt)
        events = result.scalars().all()

        if not events:
            text = (
                "📋 **События этого чата**\n\n"
                "📭 **0 событий**\n\n"
                "В этом чате пока нет созданных событий.\n\n"
                "💡 Создайте первое событие, нажав кнопку **➕ Создать событие**!"
            )
        else:
            text = f"📋 **События этого чата** ({len(events)} событий)\n\n"

            for i, event in enumerate(events, 1):
                # Форматируем дату
                date_str = event.starts_at.strftime("%d.%m.%Y %H:%M")

                # Добавляем событие в список
                text += f"{i}. **{event.title}**\n"
                text += f"   📅 {date_str}\n"

                # Описание (если есть)
                if event.description:
                    desc = event.description[:80] + "..." if len(event.description) > 80 else event.description
                    text += f"   📝 {desc}\n"

                # Место (с ссылкой если есть URL)
                if event.location_url:
                    location_name = event.location_name or "Место"
                    text += f"   📍 [{location_name}]({event.location_url})\n"
                elif event.location_name:
                    text += f"   📍 {event.location_name}\n"

                # Организатор
                if event.organizer_username:
                    text += f"   👤 Организатор: @{event.organizer_username}\n"

                text += "\n"

            text += "💡 Нажмите **➕ Создать событие** чтобы добавить свое!"

        # Создаем клавиатуру с кнопкой "Назад"
        back_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="group_back_to_panel")],
            ]
        )

        try:
            await callback.message.edit_text(text, reply_markup=back_kb, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"❌ Ошибка редактирования сообщения: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка получения событий: {e}")
        # Отправляем сообщение об ошибке пользователю
        error_text = (
            "📋 **События этого чата**\n\n"
            "❌ Произошла ошибка при загрузке событий.\n\n"
            "Попробуйте позже или обратитесь к администратору."
        )
        back_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="group_back_to_panel")],
            ]
        )
        try:
            await callback.message.edit_text(error_text, reply_markup=back_kb, parse_mode="Markdown")
        except Exception as edit_error:
            logger.error(f"❌ Ошибка отправки сообщения об ошибке: {edit_error}")


@group_router.callback_query(F.data == "group_back_to_panel")
async def group_back_to_panel(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Возврат к главной панели"""
    chat_id = callback.message.chat.id
    logger.info(f"🔥 group_back_to_panel: возврат к панели в чате {chat_id}")

    await callback.answer()

    try:
        await callback.message.edit_text(PANEL_TEXT, reply_markup=group_kb(chat_id), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования сообщения: {e}")


@group_router.callback_query(F.data == "group_hide_confirm")
async def group_hide_confirm(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Показ диалога подтверждения скрытия бота - редактируем панель"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    logger.info(f"🔥 group_hide_confirm: пользователь {user_id} запросил подтверждение скрытия бота в чате {chat_id}")

    await callback.answer("Показываем подтверждение...", show_alert=False)

    confirmation_text = (
        "👁️‍🗨️ **Спрятать бота**\n\n"
        "Вы действительно хотите скрыть все сообщения бота из этого чата?\n\n"
        "⚠️ **Это действие:**\n"
        "• Удалит все сообщения бота из чата\n"
        "• Очистит историю взаимодействий\n"
        "• Бот останется в группе, но не будет засорять чат\n\n"
        "💡 **Особенно полезно после создания события** - освобождает чат от служебных сообщений\n\n"
        "Для восстановления функций бота используйте команду /start"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, спрятать", callback_data=f"group_hide_execute_{chat_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="group_back_to_panel")],
        ]
    )

    # Редактируем панель вместо создания нового сообщения
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=callback.message.message_id,
            text=confirmation_text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования панели: {e}")
        # Fallback - отправляем новое сообщение через send_tracked
        from utils.messaging_utils import send_tracked

        try:
            await send_tracked(
                bot,
                session,
                chat_id=chat_id,
                text=confirmation_text,
                reply_markup=keyboard,
                tag="service",
            )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки подтверждения: {e}")


@group_router.callback_query(F.data.startswith("group_hide_execute_"))
async def group_hide_execute(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Выполнение скрытия бота"""
    chat_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    logger.info(f"🔥 group_hide_execute: пользователь {user_id} подтвердил скрытие бота в чате {chat_id}")

    await callback.answer("Скрываем сервисные сообщения бота…", show_alert=False)

    # Проверяем права бота на удаление сообщений
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        logger.info(
            f"🔥 Права бота в чате {chat_id}: status={bot_member.status}, "
            f"can_delete_messages={getattr(bot_member, 'can_delete_messages', None)}"
        )

        if bot_member.status != "administrator" or not getattr(bot_member, "can_delete_messages", False):
            logger.warning(f"🚫 У бота нет прав на удаление сообщений в чате {chat_id}")
            await callback.message.edit_text(
                "❌ **Ошибка: Нет прав на удаление**\n\n"
                "Бот должен быть администратором с правом 'Удаление сообщений'.\n\n"
                "Попросите администратора группы:\n"
                "1. Сделать бота администратором\n"
                "2. Включить право 'Удаление сообщений'\n\n"
                "После этого попробуйте снова.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="◀️ Назад к панели", callback_data="group_back_to_panel")]
                    ]
                ),
            )
            return
    except Exception as e:
        logger.error(f"❌ Ошибка проверки прав бота: {e}")

    # Используем асинхронную версию delete_all_tracked
    try:
        deleted = await delete_all_tracked(bot, session, chat_id=chat_id)
    except Exception as e:
        logger.error(f"❌ Ошибка удаления сообщений: {e}")
        deleted = 0

    # Короткое уведомление о результате (не трекаем, чтобы не гоняться за ним)
    note = await bot.send_message(
        chat_id,
        f"👁️‍🗨️ **Бот скрыт**\n\n"
        f"Удалено сообщений: {deleted}\n"
        f"События в базе данных сохранены.\n\n"
        f"Для восстановления панели используйте /start",
        parse_mode="Markdown",
    )

    # Автоудаление через 8 секунд
    try:
        await asyncio.sleep(8)
        await bot.delete_message(chat_id, note.message_id)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить уведомление: {e}")


@group_router.callback_query(F.data.startswith("group_delete_event_"))
async def group_delete_event(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Удаление события (только для админов)"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    # Проверяем права админа
    if not await is_chat_admin(bot, chat_id, user_id):
        await callback.answer("❌ Только администраторы могут удалять события!", show_alert=True)
        return

    # Извлекаем ID события из callback_data
    try:
        event_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(f"🔥 group_delete_event: админ {user_id} удаляет событие {event_id} в чате {chat_id}")

    try:
        # Проверяем, что событие принадлежит этому чату
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)

        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await callback.answer("❌ Событие не найдено", show_alert=True)
            return

        # Удаляем событие
        session.delete(event)
        await session.commit()
    except Exception as e:
        logger.error(f"❌ Ошибка удаления события: {e}")
        await callback.answer("❌ Ошибка удаления события", show_alert=True)
        return

    await callback.answer("✅ Событие удалено!", show_alert=False)

    # Обновляем список событий
    await group_list_events(callback, bot)


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===


def format_event_short(event: CommunityEvent) -> str:
    """Краткое форматирование события для списка"""
    date_str = event.starts_at.strftime("%d.%m %H:%M")
    text = f"**{event.title}**\n📅 {date_str}"

    if event.location_name:
        text += f"\n📍 {event.location_name}"

    return text
