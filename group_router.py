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
import re
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database import CommunityEvent
from utils.messaging_utils import delete_all_tracked, ensure_panel, is_chat_admin

logger = logging.getLogger(__name__)


# === УТИЛИТЫ ===


def extract_city_from_location_url(location_url: str) -> str | None:
    """Извлекает город из Google Maps ссылки или адреса"""
    if not location_url:
        return None

    # Список известных городов/районов для приоритетного извлечения
    known_cities = [
        # Бали
        "Canggu",
        "Seminyak",
        "Ubud",
        "Sanur",
        "Kuta",
        "Denpasar",
        "Uluwatu",
        "Nusa Dua",
        # Вьетнам
        "Nha Trang",
        "Ho Chi Minh",
        "Hanoi",
        "Da Nang",
        "Hoi An",
        "Phu Quoc",
        # Россия
        "Moscow",
        "Saint Petersburg",
        "SPB",
        "Novosibirsk",
        "Yekaterinburg",
        # Другие популярные
        "Bangkok",
        "Phuket",
        "Chiang Mai",
        "Jakarta",
        "Bali",
        "Singapore",
    ]

    # Сначала ищем известные города
    for city in known_cities:
        if city.lower() in location_url.lower():
            return city

    # Если не нашли известный город, пробуем извлечь по паттернам
    patterns = [
        # Google Maps URL с адресом: "Street, City, Region, Country"
        r",\s*([A-Za-z\s]+),\s*[A-Za-z\s]+,\s*[A-Za-z\s]+$",  # Последний элемент перед страной
        r",\s*([A-Za-z\s]+),\s*\d{5}",  # Город перед почтовым индексом
        r",\s*([A-Za-z\s]+),\s*[A-Z]{2}\s*\d{5}",  # Город, штат, почтовый индекс
    ]

    for pattern in patterns:
        match = re.search(pattern, location_url, re.IGNORECASE)
        if match:
            city = match.group(1).strip()
            # Очищаем от лишних символов и цифр
            city = re.sub(r"[^\w\s-]", "", city).strip()
            city = re.sub(r"\d+", "", city).strip()  # Убираем цифры
            if city and len(city) > 2:  # Минимум 3 символа для города
                return city

    return None


# === КОНФИГУРАЦИЯ ===

# Username бота для deep-links (будет установлен при инициализации)
MAIN_BOT_USERNAME = None  # Будет установлен в set_bot_username()

# === РОУТЕР ===

group_router = Router(name="group_router")


@group_router.message(Command("start"))
async def handle_start_command(message: Message, bot: Bot, session: AsyncSession):
    """Обработчик команды /start в группах - удаляем команду пользователя и показываем панель Community"""
    if message.chat.type in ("group", "supergroup"):
        logger.info(f"🔥 Команда /start от пользователя {message.from_user.id} в чате {message.chat.id}")

        # Удаляем команду /start пользователя (как было раньше)
        try:
            await message.delete()
            logger.info(f"✅ Удалена команда /start от пользователя {message.from_user.id} в чате {message.chat.id}")
        except Exception as e:
            logger.error(f"❌ Не удалось удалить команду /start: {e}")

        # Показываем панель Community
        try:
            # Создаем панель с кнопками Community
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Создать событие", url=f"https://t.me/EventAroundBot?start=group_{message.chat.id}"
                        )
                    ],
                    [InlineKeyboardButton(text="📋 События этого чата", callback_data="group_list")],
                    [InlineKeyboardButton(text='🚀 Расширенная версия "World"', url="https://t.me/EventAroundBot")],
                    [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_execute")],
                ]
            )

            # Отправляем панель Community с трекированием (автоудаление через 4 минуты)
            try:
                from utils.messaging_utils import send_tracked

                await send_tracked(
                    bot,
                    session,
                    chat_id=message.chat.id,
                    text=(
                        '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
                        "🎯 Что умею:\n\n"
                        "• Создавать события участников чата\n"
                        "• Показывать события этого чата\n"
                        '• Переводить в полный бот - версия "World"\n\n'
                        "💡 Выберите действие:"
                    ),
                    tag="panel",  # Тег для автоудаления через 4 минуты
                    reply_markup=keyboard,
                )
                logger.info(f"✅ Панель Community отправлена и трекируется в чате {message.chat.id}")
            except Exception as e:
                logger.error(f"❌ Ошибка send_tracked: {e}")
                # Fallback - обычная отправка без трекирования
                await message.answer(
                    '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
                    "🎯 Что умею:\n\n"
                    "• Создавать события участников чата\n"
                    "• Показывать события этого чата\n"
                    '• Переводить в полный бот - версия "World"\n\n'
                    "💡 Выберите действие:",
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )

        except Exception as e:
            logger.error(f"❌ Ошибка отправки панели Community: {e}")
            await message.answer("🤖 EventAroundBot активирован в этом чате!")


# === ИНИЦИАЛИЗАЦИЯ ===


def set_bot_username(username: str):
    """Устанавливает username бота для deep-links"""
    global MAIN_BOT_USERNAME
    MAIN_BOT_USERNAME = username
    logger.info(f"✅ Установлен username бота для группового роутера: {username}")


async def setup_group_menu_button(bot, group_id: int = None):
    """Настройка Menu Button для групповых чатов с принудительной установкой"""
    try:
        from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, MenuButtonCommands

        # Команды только для групп
        group_commands = [
            BotCommand(command="start", description="🚀 Запустить бота"),
        ]

        # Устанавливаем команды только для групп (без языка и с русской локалью)
        await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats(), language_code="ru")

        # Небольшая задержка для применения команд
        import asyncio

        await asyncio.sleep(1)

        # ПРИНУДИТЕЛЬНАЯ установка Menu Button для групп
        try:
            # Сначала проверяем текущий Menu Button
            current_button = await bot.get_chat_menu_button()
            logger.info(f"🔍 Текущий Menu Button для групп: {current_button}")

            # Если это WebApp, сбрасываем на Default, потом на Commands
            if hasattr(current_button, "type") and current_button.type == "web_app":
                logger.warning("⚠️ Menu Button для групп перекрыт WebApp! Сбрасываем...")
                from aiogram.types import MenuButtonDefault

                await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
                await asyncio.sleep(1)

            # ПРИНУДИТЕЛЬНО устанавливаем Commands для ВСЕХ групп
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.info("✅ Menu Button принудительно установлен для всех групп")

            # Если указана конкретная группа - дополнительно устанавливаем для неё
            if group_id:
                await bot.set_chat_menu_button(chat_id=group_id, menu_button=MenuButtonCommands())
                logger.info(f"✅ Menu Button дополнительно установлен для группы {group_id}")

        except Exception as e:
            logger.warning(f"⚠️ Menu Button для групп не удалось установить: {e}")

        logger.info("✅ Menu Button настроен для групповых чатов")
    except Exception as e:
        logger.error(f"❌ Ошибка настройки Menu Button для групп: {e}")


# УБРАНО: функции создания Reply Keyboard - теперь используем только команды и меню


# Жёсткая изоляция: роутер работает ТОЛЬКО в группах
group_router.message.filter(F.chat.type.in_({"group", "supergroup"}))
group_router.callback_query.filter(F.message.chat.type.in_({"group", "supergroup"}))


# ПРИНУДИТЕЛЬНАЯ КЛАВИАТУРА ДЛЯ ВСЕХ СООБЩЕНИЙ В ГРУППЕ
# УБРАНО: force_keyboard_for_all_messages - больше не принудительно добавляем клавиатуру к каждому сообщению


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
    # Используем статический username для надежности
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать событие", url=f"https://t.me/EventAroundBot?start=group_{chat_id}")],
            [InlineKeyboardButton(text="📋 События этого чата", callback_data="group_list")],
            [InlineKeyboardButton(text='🚀 Расширенная версия "World"', url="https://t.me/EventAroundBot")],
            [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_execute")],
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

        # ПРИНУДИТЕЛЬНО отправляем простую клавиатуру для максимальной совместимости
        await message.answer(
            "🚀 **Бот активирован!**\n\n" "Используйте команды для управления:",
        )

        # УБРАНО: дополнительная клавиатура - теперь используем только команды

    except Exception as e:
        logger.error(f"❌ group_start: ошибка при создании панели: {e}")
        # Fallback - отправляем обычное сообщение без клавиатуры
        await message.answer(
            PANEL_TEXT + "\n\n🚀 **Используйте команды для управления:**",
            parse_mode="Markdown",
        )


# УБРАНО: обработчики кнопок Reply Keyboard - теперь бот работает только через команды и меню


# ПРИНУДИТЕЛЬНАЯ КЛАВИАТУРА ПРИ ДОБАВЛЕНИИ БОТА В ГРУППУ
@group_router.message(F.new_chat_members)
async def handle_new_members(message: Message):
    """Обработчик добавления новых участников в группу"""
    # Проверяем, добавили ли бота
    bot_added = any(member.is_bot for member in message.new_chat_members)

    if bot_added:
        logger.info(f"🔥 Бот добавлен в группу {message.chat.id}")

        # УБРАНО: автоматическая отправка клавиатуры при добавлении бота
        # Теперь бот работает только через команды и меню, как в веб-версии


@group_router.callback_query(F.data == "group_list")
async def group_list_events(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Показать список событий этого чата"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    logger.info(f"🔥 group_list_events: запрос списка событий в чате {chat_id} от пользователя {user_id}")

    await callback.answer()  # Тост, не спамим

    try:
        # Получаем будущие события этого чата
        from sqlalchemy import select

        stmt = (
            select(CommunityEvent)
            .where(
                CommunityEvent.chat_id == chat_id,
                CommunityEvent.status == "open",
                CommunityEvent.starts_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            )
            .order_by(CommunityEvent.starts_at)
            .limit(10)
        )

        result = await session.execute(stmt)
        events = result.scalars().all()

        # Проверяем, является ли пользователь админом группы
        is_admin = await is_chat_admin(bot, chat_id, callback.from_user.id)

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

                # Добавляем событие в список (безопасная версия)
                safe_title = event.title.replace("*", "").replace("_", "").replace("`", "'")
                text += f"{i}. {safe_title}\n"
                text += f"   📅 {date_str}\n"

                # Город (приоритет: ручной ввод, затем автоматическое извлечение)
                city_to_show = None
                if event.city:
                    city_to_show = event.city
                elif event.location_url:
                    city_to_show = extract_city_from_location_url(event.location_url)

                if city_to_show:
                    safe_city = city_to_show.replace("*", "").replace("_", "").replace("`", "'")
                    text += f"   🏙️ {safe_city}\n"

                # Описание (если есть)
                if event.description:
                    desc = event.description[:80] + "..." if len(event.description) > 80 else event.description
                    safe_desc = desc.replace("*", "").replace("_", "").replace("`", "'")
                    text += f"   📝 {safe_desc}\n"

                # Место (без ссылок для безопасности)
                if event.location_name:
                    safe_location = event.location_name.replace("*", "").replace("_", "").replace("`", "'")
                    text += f"   📍 {safe_location}\n"

                # Организатор
                if event.organizer_username:
                    text += f"   👤 Организатор: @{event.organizer_username}\n"

                text += "\n"

            if is_admin:
                text += "🔧 Админ-панель: Вы можете удалить любое событие кнопками ниже!\n"
                text += "💡 Нажмите ➕ Создать событие чтобы добавить свое!"
            else:
                text += "🔧 Ваши события: Вы можете удалить свои события кнопками ниже!\n"
                text += "💡 Нажмите ➕ Создать событие чтобы добавить свое!"

        # Создаем клавиатуру с кнопками
        keyboard_buttons = []

        if events:
            # Добавляем кнопки удаления для событий, которые пользователь может удалить
            for i, event in enumerate(events, 1):
                # Проверяем, может ли пользователь удалить это событие
                can_delete_this_event = False

                # 1. Создатель события может удалить свое событие
                if event.organizer_id == user_id:
                    can_delete_this_event = True
                # 2. Админ группы может удалить любое событие
                elif is_admin:
                    can_delete_this_event = True

                if can_delete_this_event:
                    # Безопасное обрезание названия события
                    safe_title = event.title[:15] if len(event.title) > 15 else event.title
                    # Убираем проблемные символы
                    safe_title = safe_title.replace("\n", " ").replace("\r", " ").strip()

                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(
                                text=f"❌ Удалить: {safe_title}",
                                callback_data=f"group_delete_event_{event.id}",
                            )
                        ]
                    )

        # Кнопка "Назад"
        keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="group_back_to_panel")])

        back_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Логирование для диагностики
        logger.info(
            f"🔥 group_list_events: готовим сообщение длиной {len(text)} символов, {len(keyboard_buttons)} кнопок"
        )
        if keyboard_buttons:
            for i, button_row in enumerate(keyboard_buttons):
                for j, button in enumerate(button_row):
                    logger.info(f"🔥 Кнопка {i},{j}: '{button.text}' -> '{button.callback_data}'")

        try:
            # Ограничиваем длину текста для Telegram
            if len(text) > 4000:
                text = text[:3900] + "\n\n... (текст обрезан)"

            # Убираем проблемные символы из текста
            text = text.replace("`", "'").replace("*", "").replace("_", "").replace("[", "(").replace("]", ")")

            # Пробуем без Markdown сначала
            await callback.message.edit_text(text, reply_markup=back_kb)
            logger.info("✅ Список событий успешно обновлен")
        except Exception as e:
            logger.error(f"❌ Ошибка редактирования сообщения: {e}")

            # Специальная обработка для ошибки "сообщение не изменено"
            if "message is not modified" in str(e).lower():
                logger.info("🔥 Сообщение не изменилось, отправляем новое сообщение")
                try:
                    await callback.message.answer(text, reply_markup=back_kb)
                    logger.info("✅ Новое сообщение со списком событий отправлено")
                except Exception as e2:
                    logger.error(f"❌ Ошибка отправки нового сообщения: {e2}")
                    await callback.answer("❌ Ошибка отображения событий", show_alert=True)
            else:
                # Fallback: отправляем новое сообщение без Markdown
                try:
                    await callback.message.answer(text, reply_markup=back_kb)
                except Exception as e2:
                    logger.error(f"❌ Ошибка отправки нового сообщения: {e2}")
                    # Последний fallback: отправляем без клавиатуры
                try:
                    await callback.message.answer(
                        "📋 **События этого чата**\n\n❌ Ошибка отображения. Попробуйте позже."
                    )
                except Exception as e3:
                    logger.error(f"❌ Критическая ошибка: {e3}")
                    await callback.answer("❌ Ошибка отображения событий", show_alert=True)
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


@group_router.callback_query(F.data == "group_hide_execute")
async def group_hide_execute_direct(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Прямое выполнение скрытия бота без подтверждения"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    logger.info(f"🔥 group_hide_execute_direct: пользователь {user_id} скрывает бота в чате {chat_id}")

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

    # Используем асинхронную версию delete_all_tracked (панель теперь трекируется)
    try:
        deleted = await delete_all_tracked(bot, session, chat_id=chat_id)
    except Exception as e:
        logger.error(f"❌ Ошибка удаления трекированных сообщений: {e}")
        deleted = 0

    # Короткое уведомление о результате (не трекаем, чтобы не гоняться за ним)
    note = await bot.send_message(
        chat_id,
        f"👁️‍🗨️ **Бот скрыт**\n\n"
        f"✅ Удалено сообщений бота: {deleted}\n"
        f"✅ Команды /start автоматически удаляются\n"
        f"✅ События в базе данных сохранены\n\n"
        f"💡 **Для восстановления функций бота:**\n"
        f"Используйте команду /start",
        parse_mode="Markdown",
    )

    # Удаляем уведомление через 5 секунд
    try:
        import asyncio

        await asyncio.sleep(5)
        await note.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления уведомления

    logger.info(f"✅ Бот скрыт в чате {chat_id} пользователем {user_id}, удалено сообщений: {deleted}")


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

    # Извлекаем ID события из callback_data
    try:
        event_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(f"🔥 group_delete_event: пользователь {user_id} пытается удалить событие {event_id} в чате {chat_id}")

    try:
        # Проверяем, что событие принадлежит этому чату
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)

        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await callback.answer("❌ Событие не найдено", show_alert=True)
            return

        # Проверяем права на удаление:
        # 1. Создатель события может удалить свое событие
        # 2. Админ группы (из admin_ids) может удалить любое событие
        # 3. LEGACY: админ группы (из admin_id) может удалить любое событие
        # 4. FALLBACK: проверка в реальном времени
        can_delete = False

        if event.organizer_id == user_id:
            # Создатель события
            can_delete = True
            logger.info(f"✅ Пользователь {user_id} - создатель события {event_id}")
        else:
            # Проверяем admin_ids (новый подход)
            if event.admin_ids:
                try:
                    import json

                    saved_admin_ids = json.loads(event.admin_ids)
                    if user_id in saved_admin_ids:
                        can_delete = True
                        logger.info(f"✅ Пользователь {user_id} - админ группы (из admin_ids) для события {event_id}")
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"⚠️ Не удалось распарсить admin_ids: {event.admin_ids}")

            # LEGACY: проверяем admin_id (для обратной совместимости)
            if not can_delete and event.admin_id == user_id:
                can_delete = True
                logger.info(f"✅ Пользователь {user_id} - админ группы (LEGACY admin_id) для события {event_id}")

            # FALLBACK: проверка в реальном времени
            if not can_delete and await is_chat_admin(bot, chat_id, user_id):
                can_delete = True
                logger.info(f"✅ Пользователь {user_id} - админ группы (проверка в реальном времени)")

        if not can_delete:
            await callback.answer(
                "❌ Только создатель события или администратор группы могут удалять события!", show_alert=True
            )
            return

        # Удаляем событие
        await session.delete(event)
        await session.commit()
        logger.info(f"✅ Событие {event_id} успешно удалено из базы данных")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления события: {e}")
        await callback.answer("❌ Ошибка удаления события", show_alert=True)
        return

    await callback.answer("✅ Событие удалено!", show_alert=False)
    logger.info(f"🔥 Обновляем список событий после удаления {event_id}")

    # Обновляем список событий
    await group_list_events(callback, bot, session)


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===


def format_event_short(event: CommunityEvent) -> str:
    """Краткое форматирование события для списка"""
    date_str = event.starts_at.strftime("%d.%m %H:%M")
    text = f"**{event.title}**\n📅 {date_str}"

    # Город (приоритет: ручной ввод, затем автоматическое извлечение)
    city_to_show = None
    if event.city:
        city_to_show = event.city
    elif event.location_url:
        city_to_show = extract_city_from_location_url(event.location_url)

    if city_to_show:
        text += f"\n🏙️ {city_to_show}"

    if event.location_name:
        text += f"\n📍 {event.location_name}"

    return text
