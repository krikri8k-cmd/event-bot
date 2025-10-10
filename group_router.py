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

from database import CommunityEvent, get_session
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
async def group_start(message: Message, bot: Bot):
    """Приветствие в групповом чате - создает/редактирует панель-пост"""
    chat_id = message.chat.id
    logger.info(f"🔥 group_start: команда /start в группе {chat_id} от пользователя {message.from_user.id}")

    with get_session() as session:
        await ensure_panel(bot, session, chat_id=chat_id, text=PANEL_TEXT, kb=group_kb(chat_id))


@group_router.callback_query(F.data == "group_list")
async def group_list_events(callback: CallbackQuery, bot: Bot):
    """Показать список событий этого чата"""
    chat_id = callback.message.chat.id
    logger.info(f"🔥 group_list_events: запрос списка событий в чате {chat_id}")

    await callback.answer()  # Тост, не спамим

    with get_session() as session:
        # Получаем будущие события этого чата
        events = (
            session.query(CommunityEvent)
            .filter(
                CommunityEvent.chat_id == chat_id,
                CommunityEvent.status == "open",
                CommunityEvent.starts_at > datetime.utcnow(),
            )
            .order_by(CommunityEvent.starts_at)
            .limit(10)
            .all()
        )

        if not events:
            text = (
                "📋 **События этого чата**\n\n"
                "Пока нет предстоящих событий.\n\n"
                "Создайте первое событие, нажав кнопку **➕ Создать событие**!"
            )
        else:
            text = f"📋 **События этого чата** ({len(events)})\n\n"

            for i, event in enumerate(events, 1):
                # Форматируем дату
                date_str = event.starts_at.strftime("%d.%m.%Y %H:%M")

                # Добавляем событие в список
                text += f"{i}. **{event.title}**\n"
                text += f"   📅 {date_str}\n"

                if event.location_name:
                    text += f"   📍 {event.location_name}\n"

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


@group_router.callback_query(F.data == "group_back_to_panel")
async def group_back_to_panel(callback: CallbackQuery, bot: Bot):
    """Возврат к главной панели"""
    chat_id = callback.message.chat.id
    logger.info(f"🔥 group_back_to_panel: возврат к панели в чате {chat_id}")

    await callback.answer()

    try:
        await callback.message.edit_text(PANEL_TEXT, reply_markup=group_kb(chat_id), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования сообщения: {e}")


@group_router.callback_query(F.data == "group_hide_confirm")
async def group_hide_bot(callback: CallbackQuery, bot: Bot):
    """Удаление всех сообщений бота из чата"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    logger.info(f"🔥 group_hide_bot: удаление сообщений бота в чате {chat_id} пользователем {user_id}")

    await callback.answer("Скрываем сервисные сообщения бота…", show_alert=False)

    with get_session() as session:
        deleted = await delete_all_tracked(bot, session, chat_id=chat_id)

    # Короткое уведомление (не трекаем, чтобы не гоняться за ним)
    note = await bot.send_message(
        chat_id,
        f"👁️‍🗨️ **Бот скрыт**\n\n"
        f"Удалено сообщений: {deleted}\n"
        f"События в базе данных сохранены.\n\n"
        f"Для восстановления панели используйте /start",
        parse_mode="Markdown",
    )

    # Автоудаление через 10 секунд
    try:
        await asyncio.sleep(10)
        await bot.delete_message(chat_id, note.message_id)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить уведомление: {e}")


@group_router.callback_query(F.data.startswith("group_delete_event_"))
async def group_delete_event(callback: CallbackQuery, bot: Bot):
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

    with get_session() as session:
        # Проверяем, что событие принадлежит этому чату
        event = (
            session.query(CommunityEvent)
            .filter(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
            .first()
        )

        if not event:
            await callback.answer("❌ Событие не найдено", show_alert=True)
            return

        # Удаляем событие
        session.delete(event)
        session.commit()

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
