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
import contextlib
import logging
import re
from datetime import UTC, datetime, timedelta

from aiogram import Bot, F, Router, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database import CommunityEvent
from utils.messaging_utils import delete_all_tracked, is_chat_admin

# Константы для восстановления команд
GROUP_CMDS = [types.BotCommand(command="start", description="🎉 События чата")]
LANGS = (None, "ru", "en")  # default + ru + en


async def ensure_group_start_command(bot: Bot, chat_id: int):
    """Устанавливает команду /start для конкретной группы (ускоряет мобильный клиент)"""
    try:
        cmds = [types.BotCommand(command="start", description="🎉 События чата")]

        # Для супергрупп нужна особая обработка
        chat_type = "supergroup" if str(chat_id).startswith("-100") else "group"
        logger.info(f"🔥 Устанавливаем команды для {chat_type} {chat_id}")

        for lang in (None, "ru", "en"):
            try:
                # Для супергрупп пробуем разные подходы
                if chat_type == "supergroup":
                    # Сначала пробуем BotCommandScopeChat
                    try:
                        await bot.set_my_commands(
                            cmds, scope=types.BotCommandScopeChat(chat_id=chat_id), language_code=lang
                        )
                        logger.info(
                            f"✅ Команда /start установлена для супергруппы {chat_id} (язык: {lang or 'default'})"
                        )
                    except Exception as chat_scope_error:
                        logger.warning(
                            f"⚠️ BotCommandScopeChat не сработал для супергруппы {chat_id}: {chat_scope_error}"
                        )
                        # Fallback: используем AllGroupChats
                        await bot.set_my_commands(cmds, scope=types.BotCommandScopeAllGroupChats(), language_code=lang)
                        logger.info(
                            f"✅ Fallback: команда /start установлена через AllGroupChats "
                            f"для супергруппы {chat_id} (язык: {lang or 'default'})"
                        )
                else:
                    # Для обычных групп
                    await bot.set_my_commands(
                        cmds, scope=types.BotCommandScopeChat(chat_id=chat_id), language_code=lang
                    )
                    logger.info(f"✅ Команда /start установлена для группы {chat_id} (язык: {lang or 'default'})")
            except Exception as lang_error:
                logger.warning(f"⚠️ Ошибка установки команд для языка {lang} в {chat_type} {chat_id}: {lang_error}")

        logger.info(f"✅ Команды для {chat_type} {chat_id} установлены")
    except Exception as e:
        logger.error(f"⚠️ Ошибка ensure_group_start_command({chat_id}): {e}")


async def nudge_mobile_menu(bot: Bot, chat_id: int):
    """Мягкий пинок интерфейса - подсказка для мобильного клиента"""
    try:
        msg = await bot.send_message(
            chat_id,
            "ℹ️ Чтобы открыть команды, нажмите `/` или введите `/start@EventAroundBot`.",
            disable_notification=True,
        )
        await asyncio.sleep(3)
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id, msg.message_id)
        logger.info(f"✅ Подсказка отправлена и удалена в группе {chat_id}")
    except Exception as e:
        logger.error(f"⚠️ Ошибка nudge_mobile_menu({chat_id}): {e}")


async def restore_commands_after_hide(event_or_chat_id, bot: Bot):
    """Надежное восстановление команд после скрытия бота"""
    try:
        # 1) Вытащим chat_id безопасно
        if isinstance(event_or_chat_id, int):
            chat_id = event_or_chat_id
            thread_id = None
        else:
            msg = event_or_chat_id if isinstance(event_or_chat_id, types.Message) else event_or_chat_id.message
            chat_id = msg.chat.id  # ← ТОЛЬКО chat.id (отрицательный)
            thread_id = getattr(msg, "message_thread_id", None)

        logger.info(f"[restore] chat_id={chat_id} ({type(chat_id)}), thread_id={thread_id}")

        # 2) Убедимся, что chat_id валиден (строка -> int)
        if isinstance(chat_id, str):
            chat_id = int(chat_id)

        # 3) Убедимся, что бот состоит в чате и chat_id валиден
        try:
            chat = await bot.get_chat(chat_id)  # выбросит BadRequest если chat_id невалиден
            assert chat.type in ("supergroup", "group"), f"Unexpected chat type: {chat.type}"
            logger.info(f"[restore] Чат валиден: {chat.type} {chat_id}")
        except Exception as e:
            logger.error(f"[restore] Невалидный chat_id {chat_id}: {e}")
            return

        # 4) Иногда клиенту нужен миллисекундный таймаут после массового удаления
        await asyncio.sleep(0.5)

        # 5) Вернём кнопку "Команды бота" и /start СПЕЦИАЛЬНО для этого чата
        for lang in LANGS:
            try:
                await bot.set_my_commands(
                    GROUP_CMDS, scope=types.BotCommandScopeChat(chat_id=chat_id), language_code=lang
                )
                logger.info(f"[restore] Команды установлены для языка {lang or 'default'}")
            except Exception as e:
                logger.error(f"[restore] Ошибка установки команд для языка {lang}: {e}")

        await bot.set_chat_menu_button(chat_id=chat_id, menu_button=types.MenuButtonCommands())
        logger.info(f"[restore] Menu Button установлен для чата {chat_id}")

        # 6) Подстраховка: повтор через 2 сек (мобильный кэш Telegram)
        await asyncio.sleep(2)
        for lang in LANGS:
            try:
                await bot.set_my_commands(
                    GROUP_CMDS, scope=types.BotCommandScopeChat(chat_id=chat_id), language_code=lang
                )
            except Exception as e:
                logger.error(f"[restore] Ошибка повторной установки команд для языка {lang}: {e}")

        logger.info(f"[restore] /start восстановлена в чате {chat_id}")

    except Exception as e:
        logger.error(f"[restore] Критическая ошибка восстановления команд: {e}")


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


@group_router.message(lambda message: message.text == "/test_autodelete")
async def test_autodelete(message: Message, bot: Bot, session: AsyncSession):
    """Тестовая команда для проверки автоудаления"""
    if message.chat.type in ("group", "supergroup"):
        logger.info(f"🧪 Тест автоудаления от пользователя {message.from_user.id} в чате {message.chat.id}")

        # Отправляем тестовое сообщение с автоудалением через 10 секунд
        from utils.messaging_utils import send_tracked

        test_msg = await send_tracked(
            bot,
            session,
            chat_id=message.chat.id,
            text="🧪 Тестовое сообщение - должно удалиться через 10 секунд",
            tag="service",
        )

        # Запускаем автоудаление через 10 секунд для теста
        import asyncio

        from utils.messaging_utils import auto_delete_message

        asyncio.create_task(auto_delete_message(bot, message.chat.id, test_msg.message_id, 10))

        await message.answer("✅ Тест автоудаления запущен! Сообщение удалится через 10 секунд.")


@group_router.message(Command("join_event"))
async def handle_join_event_command(message: Message, bot: Bot, session: AsyncSession, command: CommandObject):
    """Обработчик команды /join_event_123 для записи на событие"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Извлекаем ID события из команды
    if not command.args:
        await message.answer("❌ Используйте команду: /join_event_123 (где 123 - ID события)")
        return

    try:
        event_id = int(command.args)
    except ValueError:
        await message.answer("❌ Неверный ID события. Используйте: /join_event_123")
        return

    logger.info(f"🔥 handle_join_event_command: пользователь {user_id} запрашивает запись на событие {event_id}")

    try:
        # Проверяем, что событие существует
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await message.answer("❌ Событие не найдено")
            return

        # Проверяем, не записан ли уже пользователь
        from utils.community_participants_service_optimized import is_participant_optimized

        is_participant = await is_participant_optimized(session, event_id, user_id)
        if is_participant:
            await message.answer("ℹ️ Вы уже записаны на это событие")
            return

        # Сразу записываем пользователя на событие (без промежуточного подтверждения)
        from utils.community_participants_service_optimized import add_participant_optimized

        username = message.from_user.username
        added = await add_participant_optimized(session, event_id, user_id, username)

        if not added:
            await message.answer("❌ Не удалось записаться на событие")
            return

        # Удаляем сообщение пользователя с командой
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            logger.info(f"✅ Удалено сообщение пользователя {user_id} с командой /joinevent{event_id}")
        except Exception as delete_error:
            logger.warning(f"⚠️ Не удалось удалить сообщение пользователя: {delete_error}")

        # Сразу обновляем список событий (удаляем старый и создаем новый с обновленными данными)
        try:
            from sqlalchemy import select

            from database import BotMessage

            # Находим все сообщения со списком событий (тег "list" или "service")
            result = await session.execute(
                select(BotMessage).where(
                    BotMessage.chat_id == chat_id,
                    BotMessage.deleted.is_(False),
                    BotMessage.tag.in_(["list", "service"]),  # Списки событий и подтверждения
                )
            )
            list_messages = result.scalars().all()

            deleted_count = 0
            for bot_msg in list_messages:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=bot_msg.message_id)
                    bot_msg.deleted = True
                    deleted_count += 1
                    logger.info(
                        f"✅ Удалено сообщение со списком событий "
                        f"(message_id={bot_msg.message_id}, tag={bot_msg.tag})"
                    )
                except Exception as delete_error:
                    logger.warning(f"⚠️ Не удалось удалить сообщение {bot_msg.message_id}: {delete_error}")
                    bot_msg.deleted = True  # Помечаем как удаленное

            await session.commit()
            logger.info(f"✅ Удалено {deleted_count} сообщений со списком событий")
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении предыдущих списков событий: {e}")

        # Создаем новый список событий с обновленными данными
        # Используем send_tracked напрямую, без callback
        from sqlalchemy import select

        from utils.messaging_utils import send_tracked

        # Получаем события для списка
        # Для Community событий starts_at теперь TIMESTAMP WITHOUT TIME ZONE, поэтому убираем timezone
        now_utc = (datetime.now(UTC) - timedelta(hours=3)).replace(tzinfo=None)
        stmt = (
            select(CommunityEvent)
            .where(
                CommunityEvent.chat_id == chat_id,
                CommunityEvent.status == "open",
                CommunityEvent.starts_at >= now_utc,
            )
            .order_by(CommunityEvent.starts_at)
            .limit(10)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        # Формируем текст списка (используем существующую логику из group_list_events_page)
        if not events:
            text = (
                "📋 **События этого чата**\n\n"
                "📭 **0 событий**\n\n"
                "В этом чате пока нет активных событий.\n\n"
                "💡 Создайте первое событие, нажав кнопку **➕ Создать событие**!"
            )
        else:
            text = f"📋 **События этого чата** ({len(events)} событий)\n\n"
            for i, event in enumerate(events, 1):
                date_str = format_community_event_time(event, "%d.%m.%Y %H:%M")
                safe_title = event.title.replace("*", "").replace("_", "").replace("`", "'")
                text += f"{i}. {safe_title}\n"
                text += f"   📅 {date_str}\n"

                city_to_show = event.city or (
                    extract_city_from_location_url(event.location_url) if event.location_url else None
                )
                if city_to_show:
                    safe_city = city_to_show.replace("*", "").replace("_", "").replace("`", "'")
                    text += f"   🏙️ {safe_city}\n"

                if event.description:
                    desc = event.description[:80] + "..." if len(event.description) > 80 else event.description
                    safe_desc = desc.replace("*", "").replace("_", "").replace("`", "'")
                    text += f"   📝 {safe_desc}\n"

                if event.location_name:
                    safe_location = event.location_name.replace("*", "").replace("_", "").replace("`", "'")
                    if event.location_url:
                        safe_url = event.location_url.replace("(", "").replace(")", "")
                        text += f"   📍 [{safe_location}]({safe_url})\n"
                    else:
                        text += f"   📍 {safe_location}\n"
                elif event.location_url:
                    safe_url = event.location_url.replace("(", "").replace(")", "")
                    text += f"   📍 [Место на карте]({safe_url})\n"

                if event.organizer_username:
                    text += f"   👤 Организатор: @{event.organizer_username}\n"

                from utils.community_participants_service_optimized import (
                    get_participants_count_optimized,
                    is_participant_optimized,
                )

                participants_count = await get_participants_count_optimized(session, event.id)
                is_user_participant = await is_participant_optimized(session, event.id, user_id)

                text += f"   👥 Участников: {participants_count}\n"

                if is_user_participant:
                    text += f"   ✅ Вы записаны | Нажмите 👉 /leaveevent{event.id} чтобы отменить\n"
                else:
                    text += f"   Нажмите 👉 /joinevent{event.id} чтобы записаться\n"

                text += "\n"

            # Проверяем, является ли пользователь админом
            is_admin = await is_chat_admin(bot, chat_id, user_id)
            if is_admin:
                text += "🔧 Админ-панель: Вы можете управлять любым событием кнопками ниже!\n"
                text += "💡 Нажмите ➕ Создать событие чтобы добавить свое!"
            else:
                text += "🔧 Ваши события: Вы можете управлять своими событиями кнопками ниже!\n"
                text += "💡 Нажмите ➕ Создать событие чтобы добавить свое!"

        # Создаем клавиатуру с кнопками управления событиями
        keyboard_buttons = []

        # Всегда показываем кнопку "Управление событиями", даже если активных событий нет
        # Это позволяет возобновлять закрытые события (в течение 24 часов после закрытия)
        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="🔧 Управление событиями",
                    callback_data="group_manage_events",
                )
            ]
        )

        keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="group_back_to_panel")])
        back_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Отправляем список через send_tracked
        is_forum = getattr(message.chat, "is_forum", False)
        thread_id = getattr(message, "message_thread_id", None)

        send_kwargs = {"reply_markup": back_kb, "parse_mode": "Markdown"}
        if is_forum and thread_id:
            send_kwargs["message_thread_id"] = thread_id

        await send_tracked(
            bot,
            session,
            chat_id=chat_id,
            text=text,
            tag="list",  # Тег для списка событий
            **send_kwargs,
        )

    except Exception as e:
        logger.error(f"❌ Ошибка показа подтверждения: {e}")
        import traceback

        logger.error(traceback.format_exc())
        from utils.messaging_utils import send_tracked

        await send_tracked(
            bot,
            session,
            chat_id=chat_id,
            text="❌ Ошибка при загрузке события",
            tag="service",
        )


# Глобальный словарь для отслеживания обработанных сообщений (защита от дублирования)
_processed_messages = set()


@group_router.message(F.text.regexp(r"^/joinevent(\d+)(@\w+)?$"))
async def handle_join_event_command_short(message: Message, bot: Bot, session: AsyncSession):
    """Обработчик команды /joinevent123 для записи на событие (без подчеркивания)"""
    # Защита от дублирования: проверяем, не обрабатывали ли мы уже это сообщение
    message_key = f"{message.chat.id}_{message.message_id}"
    if message_key in _processed_messages:
        logger.warning(f"⚠️ Сообщение {message_key} уже обработано, пропускаем")
        return

    # Помечаем сообщение как обработанное
    _processed_messages.add(message_key)

    # Очищаем старые записи (оставляем только последние 1000)
    if len(_processed_messages) > 1000:
        _processed_messages.clear()

    chat_id = message.chat.id
    user_id = message.from_user.id

    # Извлекаем ID события из текста команды
    import re

    match = re.match(r"^/joinevent(\d+)(@\w+)?$", message.text)
    if not match:
        await message.answer("❌ Используйте команду: /joinevent123 (где 123 - ID события)")
        return

    try:
        event_id = int(match.group(1))
    except (ValueError, AttributeError):
        await message.answer("❌ Неверный ID события. Используйте: /joinevent123")
        return

    logger.info(f"🔥 handle_join_event_command_short: пользователь {user_id} запрашивает запись на событие {event_id}")

    try:
        # Проверяем, что событие существует
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await message.answer("❌ Событие не найдено")
            return

        # Проверяем, не записан ли уже пользователь
        from utils.community_participants_service_optimized import is_participant_optimized

        is_participant = await is_participant_optimized(session, event_id, user_id)
        if is_participant:
            await message.answer("ℹ️ Вы уже записаны на это событие")
            return

        # Сразу записываем пользователя на событие (без промежуточного подтверждения)
        from utils.community_participants_service_optimized import add_participant_optimized

        username = message.from_user.username
        added = await add_participant_optimized(session, event_id, user_id, username)

        if not added:
            await message.answer("❌ Не удалось записаться на событие")
            return

        # Удаляем сообщение пользователя с командой
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            logger.info(f"✅ Удалено сообщение пользователя {user_id} с командой /joinevent{event_id}")
        except Exception as delete_error:
            logger.warning(f"⚠️ Не удалось удалить сообщение пользователя: {delete_error}")

        # Сразу обновляем список событий (удаляем старый и создаем новый с обновленными данными)
        try:
            from sqlalchemy import select

            from database import BotMessage

            # Находим все сообщения со списком событий (тег "list" или "service")
            result = await session.execute(
                select(BotMessage).where(
                    BotMessage.chat_id == chat_id,
                    BotMessage.deleted.is_(False),
                    BotMessage.tag.in_(["list", "service"]),  # Списки событий и подтверждения
                )
            )
            list_messages = result.scalars().all()

            deleted_count = 0
            for bot_msg in list_messages:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=bot_msg.message_id)
                    bot_msg.deleted = True
                    deleted_count += 1
                    logger.info(
                        f"✅ Удалено сообщение со списком событий "
                        f"(message_id={bot_msg.message_id}, tag={bot_msg.tag})"
                    )
                except Exception as delete_error:
                    logger.warning(f"⚠️ Не удалось удалить сообщение {bot_msg.message_id}: {delete_error}")
                    bot_msg.deleted = True  # Помечаем как удаленное

            await session.commit()
            logger.info(f"✅ Удалено {deleted_count} сообщений со списком событий")
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении предыдущих списков событий: {e}")

        # Создаем новый список событий с обновленными данными
        # Используем send_tracked напрямую, без callback
        from sqlalchemy import select

        from utils.messaging_utils import send_tracked

        # Получаем события для списка
        # Для Community событий starts_at теперь TIMESTAMP WITHOUT TIME ZONE, поэтому убираем timezone
        now_utc = (datetime.now(UTC) - timedelta(hours=3)).replace(tzinfo=None)
        stmt = (
            select(CommunityEvent)
            .where(
                CommunityEvent.chat_id == chat_id,
                CommunityEvent.status == "open",
                CommunityEvent.starts_at >= now_utc,
            )
            .order_by(CommunityEvent.starts_at)
            .limit(10)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        # Формируем текст списка (используем существующую логику из group_list_events_page)
        if not events:
            text = (
                "📋 **События этого чата**\n\n"
                "📭 **0 событий**\n\n"
                "В этом чате пока нет активных событий.\n\n"
                "💡 Создайте первое событие, нажав кнопку **➕ Создать событие**!"
            )
        else:
            text = f"📋 **События этого чата** ({len(events)} событий)\n\n"
            for i, event in enumerate(events, 1):
                date_str = format_community_event_time(event, "%d.%m.%Y %H:%M")
                safe_title = event.title.replace("*", "").replace("_", "").replace("`", "'")
                text += f"{i}. {safe_title}\n"
                text += f"   📅 {date_str}\n"

                city_to_show = event.city or (
                    extract_city_from_location_url(event.location_url) if event.location_url else None
                )
                if city_to_show:
                    safe_city = city_to_show.replace("*", "").replace("_", "").replace("`", "'")
                    text += f"   🏙️ {safe_city}\n"

                if event.description:
                    desc = event.description[:80] + "..." if len(event.description) > 80 else event.description
                    safe_desc = desc.replace("*", "").replace("_", "").replace("`", "'")
                    text += f"   📝 {safe_desc}\n"

                if event.location_name:
                    safe_location = event.location_name.replace("*", "").replace("_", "").replace("`", "'")
                    if event.location_url:
                        safe_url = event.location_url.replace("(", "").replace(")", "")
                        text += f"   📍 [{safe_location}]({safe_url})\n"
                    else:
                        text += f"   📍 {safe_location}\n"
                elif event.location_url:
                    safe_url = event.location_url.replace("(", "").replace(")", "")
                    text += f"   📍 [Место на карте]({safe_url})\n"

                if event.organizer_username:
                    text += f"   👤 Организатор: @{event.organizer_username}\n"

                from utils.community_participants_service_optimized import (
                    get_participants_count_optimized,
                    is_participant_optimized,
                )

                participants_count = await get_participants_count_optimized(session, event.id)
                is_user_participant = await is_participant_optimized(session, event.id, user_id)

                text += f"   👥 Участников: {participants_count}\n"

                if is_user_participant:
                    text += f"   ✅ Вы записаны | Нажмите 👉 /leaveevent{event.id} чтобы отменить\n"
                else:
                    text += f"   Нажмите 👉 /joinevent{event.id} чтобы записаться\n"

                text += "\n"

            # Проверяем, является ли пользователь админом
            is_admin = await is_chat_admin(bot, chat_id, user_id)
            if is_admin:
                text += "🔧 Админ-панель: Вы можете управлять любым событием кнопками ниже!\n"
                text += "💡 Нажмите ➕ Создать событие чтобы добавить свое!"
            else:
                text += "🔧 Ваши события: Вы можете управлять своими событиями кнопками ниже!\n"
                text += "💡 Нажмите ➕ Создать событие чтобы добавить свое!"

        # Создаем клавиатуру с кнопками управления событиями
        keyboard_buttons = []

        # Всегда показываем кнопку "Управление событиями", даже если активных событий нет
        # Это позволяет возобновлять закрытые события (в течение 24 часов после закрытия)
        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="🔧 Управление событиями",
                    callback_data="group_manage_events",
                )
            ]
        )

        keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="group_back_to_panel")])
        back_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Отправляем список через send_tracked
        is_forum = getattr(message.chat, "is_forum", False)
        thread_id = getattr(message, "message_thread_id", None)

        send_kwargs = {"reply_markup": back_kb, "parse_mode": "Markdown"}
        if is_forum and thread_id:
            send_kwargs["message_thread_id"] = thread_id

        await send_tracked(
            bot,
            session,
            chat_id=chat_id,
            text=text,
            tag="list",  # Тег для списка событий
            **send_kwargs,
        )

    except Exception as e:
        logger.error(f"❌ Ошибка показа подтверждения: {e}")
        import traceback

        logger.error(traceback.format_exc())
        from utils.messaging_utils import send_tracked

        await send_tracked(
            bot,
            session,
            chat_id=chat_id,
            text="❌ Ошибка при загрузке события",
            tag="service",
        )


@group_router.message(Command("leave_event"))
async def handle_leave_event_command(message: Message, bot: Bot, session: AsyncSession, command: CommandObject):
    """Обработчик команды /leave_event_123 для отмены записи на событие"""
    user_id = message.from_user.id

    # Извлекаем ID события из команды
    if not command.args:
        await message.answer("❌ Используйте команду: /leave_event_123 (где 123 - ID события)")
        return

    try:
        event_id = int(command.args)
    except ValueError:
        await message.answer("❌ Неверный ID события. Используйте: /leave_event_123")
        return

    logger.info(f"🔥 handle_leave_event_command: пользователь {user_id} отменяет запись на событие {event_id}")

    # Используем существующий обработчик
    class FakeCallback:
        def __init__(self, msg, user):
            self.message = msg
            self.from_user = user
            self.data = f"community_leave_{event_id}"

        async def answer(self, text=None, show_alert=False):
            pass

    fake_callback = FakeCallback(message, message.from_user)
    await community_leave_event(fake_callback, bot, session)

    # Удаляем сообщение пользователя с командой
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        logger.info(f"✅ Удалено сообщение пользователя {user_id} с командой /leaveevent{event_id}")
    except Exception as delete_error:
        logger.warning(f"⚠️ Не удалось удалить сообщение пользователя: {delete_error}")


@group_router.message(F.text.regexp(r"^/leaveevent(\d+)(@\w+)?$"))
async def handle_leave_event_command_short(message: Message, bot: Bot, session: AsyncSession):
    """Обработчик команды /leaveevent123 для отмены записи на событие (без подчеркивания)"""
    user_id = message.from_user.id

    # Извлекаем ID события из текста команды
    import re

    match = re.match(r"^/leaveevent(\d+)(@\w+)?$", message.text)
    if not match:
        await message.answer("❌ Используйте команду: /leaveevent123 (где 123 - ID события)")
        return

    try:
        event_id = int(match.group(1))
    except (ValueError, AttributeError):
        await message.answer("❌ Неверный ID события. Используйте: /leaveevent123")
        return

    logger.info(f"🔥 handle_leave_event_command_short: пользователь {user_id} отменяет запись на событие {event_id}")

    # Используем существующий обработчик напрямую
    # Создаем фиктивный callback для использования существующей логики
    class FakeCallback:
        def __init__(self, msg, user):
            self.message = msg
            self.from_user = user
            self.data = f"community_leave_{event_id}"

        async def answer(self, text=None, show_alert=False):
            pass

    fake_callback = FakeCallback(message, message.from_user)
    await community_leave_event(fake_callback, bot, session)

    # Удаляем сообщение пользователя с командой
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        logger.info(f"✅ Удалено сообщение пользователя {user_id} с командой /leaveevent{event_id}")
    except Exception as delete_error:
        logger.warning(f"⚠️ Не удалось удалить сообщение пользователя: {delete_error}")


@group_router.message(Command("start"))
async def handle_start_command(message: Message, bot: Bot, session: AsyncSession):
    """Обработчик команды /start в группах и каналах - показываем панель Community"""
    # Проверяем тип чата - поддерживаем группы, супергруппы и каналы
    if message.chat.type not in ("group", "supergroup", "channel"):
        logger.warning(f"⚠️ Команда /start из неподдерживаемого типа чата '{message.chat.type}' (ID: {message.chat.id})")
        return

    logger.info(
        f"🔥 Команда /start от пользователя {message.from_user.id} в чате {message.chat.id} (тип: {message.chat.type})"
    )

    # Для каналов - особая обработка (в каналах боты не могут удалять сообщения пользователей)
    is_channel = message.chat.type == "channel"

    # Инкрементируем сессию Community (только для пользователей, не для каналов)
    if not is_channel:
        try:
            from utils.user_analytics import UserAnalytics

            UserAnalytics.increment_sessions_community(message.from_user.id)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось инкрементировать сессию Community: {e}")

    # Удаляем команду /start пользователя (только в группах, не в каналах)
    if not is_channel:
        # Всегда пытаемся удалить сообщение
        # В некоторых форумах удаление может работать даже в общем чате
        try:
            await message.delete()
            logger.info(
                f"✅ Удалена команда {message.text} от пользователя {message.from_user.id} в чате {message.chat.id}"
            )
        except Exception as e:
            error_str = str(e).lower()
            # Проверяем конкретные ошибки - это нормальные ситуации
            if (
                "message to delete not found" in error_str
                or "can't delete message" in error_str
                or "сообщение невозможно удалить" in error_str
            ):
                # Логируем как информацию, не как ошибку
                is_forum = getattr(message.chat, "is_forum", False)
                thread_id = getattr(message, "message_thread_id", None)
                if is_forum and thread_id is None:
                    logger.info(
                        f"ℹ️ Не удалось удалить команду {message.text} в форуме вне темы "
                        f"(chat_id={message.chat.id}, thread_id=None) - это ограничение Telegram API"
                    )
                else:
                    logger.info(
                        f"ℹ️ Не удалось удалить команду {message.text} в чате {message.chat.id} "
                        "(возможно, нет прав на удаление или сообщение уже удалено)"
                    )
            else:
                # Другие ошибки - логируем как предупреждение
                logger.warning(f"⚠️ Не удалось удалить команду {message.text}: {e}")

    # СТОРОЖ КОМАНД: проверяем команды при каждом /start в группе
    try:
        from bot_enhanced_v3 import ensure_commands

        await ensure_commands(bot)
        logger.info(f"✅ Сторож команд выполнен при /start в группе {message.chat.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка сторожа команд при /start в группе {message.chat.id}: {e}")

    # ЛОГИРУЕМ ИНФОРМАЦИЮ О ЧАТЕ
    is_forum = message.chat.type == "supergroup"
    thread_id = getattr(message, "message_thread_id", None)
    logger.info(f"🔥 /start в группе: chat_id={message.chat.id}, is_forum={is_forum}, thread_id={thread_id}")

    # УСТАНАВЛИВАЕМ КОМАНДЫ ДЛЯ КОНКРЕТНОЙ ГРУППЫ
    await ensure_group_start_command(bot, message.chat.id)

    # Убираем промежуточное сообщение с командой

    # Показываем панель Community с InlineKeyboard под сообщением
    try:
        # Создаем InlineKeyboard для действий под сообщением
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Создать событие", url=f"https://t.me/EventAroundBot?start=group_{message.chat.id}"
                    )
                ],
                [InlineKeyboardButton(text="📋 События этого чата", callback_data="group_list")],
                [InlineKeyboardButton(text='🚀 Полная версия "World"', url="https://t.me/EventAroundBot")],
                [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_execute")],
            ]
        )

        # Отправляем панель Community с трекированием (автоудаление через 4 минуты)
        try:
            from utils.messaging_utils import send_tracked

            panel_text = (
                '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
                "🎯 Что умею:\n\n"
                "• Создавать события\n"
                "• Показывать события этого чата\n"
                '• Полная версия "World"\n\n'
                "💡 Выберите действие:"
            )

            # Передаем message_thread_id для форумов
            send_kwargs = {"reply_markup": keyboard}
            if is_forum and thread_id:
                send_kwargs["message_thread_id"] = thread_id

            await send_tracked(
                bot,
                session,
                chat_id=message.chat.id,
                text=panel_text,
                tag="panel",  # Тег для автоудаления через 4 минуты
                **send_kwargs,
            )
            logger.info(f"✅ Панель Community отправлена и трекируется в чате {message.chat.id}")
        except Exception as e:
            logger.error(f"❌ Ошибка send_tracked: {e}")
            # Проверяем, не закрыта ли тема форума
            if "TOPIC_CLOSED" in str(e):
                logger.warning(
                    f"⚠️ Тема форума закрыта в чате {message.chat.id}. "
                    "Бот не может отправлять сообщения в закрытые темы."
                )
                return
            # Fallback - обычная отправка без трекирования
            try:
                await message.answer(
                    '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
                    "🎯 Что умею:\n\n"
                    "• Создавать события\n"
                    "• Показывать события этого чата\n"
                    '• Полная версия "World"\n\n'
                    "💡 Выберите действие:",
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
            except Exception as fallback_error:
                if "TOPIC_CLOSED" in str(fallback_error):
                    logger.warning(
                        f"⚠️ Тема форума закрыта в чате {message.chat.id}. "
                        "Бот не может отправлять сообщения в закрытые темы."
                    )
                    return
                raise

        # Отправляем сообщение с ReplyKeyboard для мобильных (только в группах, не в каналах)
        # ВАЖНО: ReplyKeyboard нужен для работы сторожа команд в супергруппах
        if not is_channel:
            from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

            start_keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="/start@EventAroundBot 🎉")]],
                resize_keyboard=True,
                one_time_keyboard=False,
                persistent=True,
            )

            try:
                # Для форумов передаем message_thread_id
                answer_kwargs = {"reply_markup": start_keyboard}
                if is_forum and thread_id:
                    answer_kwargs["message_thread_id"] = thread_id
                activation_msg = await message.answer("🤖 EventAroundBot активирован!", **answer_kwargs)
            except Exception as e:
                if "TOPIC_CLOSED" in str(e):
                    logger.warning(
                        f"⚠️ Тема форума закрыта в чате {message.chat.id}. "
                        "Бот не может отправлять сообщения в закрытые темы."
                    )
                    return
                raise

            # Удаляем сообщение активации через 1 секунду (ReplyKeyboard остается)
            try:
                await asyncio.sleep(1)
                await bot.delete_message(message.chat.id, activation_msg.message_id)
                logger.info(f"✅ Сообщение активации удалено, ReplyKeyboard остался в чате {message.chat.id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить сообщение активации: {e}")

            # ПРИНУДИТЕЛЬНО для мобильных: устанавливаем команды и меню (только в группах)
            try:
                # Проверяем, является ли чат форумом
                # Для форумов может не работать BotCommandScopeChat
                is_forum_check = getattr(message.chat, "is_forum", False)
                if is_forum_check:
                    logger.info(
                        f"ℹ️ Пропускаем установку команд для конкретного чата "
                        f"(форум {message.chat.id} - команды уже установлены через BotCommandScopeAllGroupChats)"
                    )
                else:
                    # Устанавливаем команды для конкретного чата (только для не-форумов)
                    await bot.set_my_commands(
                        [types.BotCommand(command="start", description="🎉 События чата")],
                        scope=types.BotCommandScopeChat(chat_id=message.chat.id),
                    )

                # ВАЖНО: Устанавливаем MenuButton для ВСЕХ типов групп (включая форумы)
                # Это нужно для отображения кнопки "Команды бота" на всех устройствах, включая MacBook
                # Для MacBook важно установить MenuButton глобально ПЕРЕД попыткой установки для конкретного чата
                try:
                    # СНАЧАЛА устанавливаем глобально для всех групп (важно для MacBook)
                    await bot.set_chat_menu_button(menu_button=types.MenuButtonCommands())
                    logger.info("✅ MenuButton установлен глобально для всех групп (приоритет для MacBook)")

                    # Небольшая задержка для применения глобальной установки
                    await asyncio.sleep(0.5)

                    # Затем пробуем установить для конкретного чата (для других устройств)
                    try:
                        await bot.set_chat_menu_button(chat_id=message.chat.id, menu_button=types.MenuButtonCommands())
                        logger.info(
                            f"✅ MenuButton дополнительно установлен для чата {message.chat.id} "
                            f"(тип: {message.chat.type}, форум: {is_forum_check})"
                        )
                    except Exception as chat_specific_error:
                        error_str = str(chat_specific_error).lower()
                        # Для супергрупп это нормально - глобальная установка уже работает
                        if "chat_id" in error_str or "неверный" in error_str or "invalid" in error_str:
                            logger.info(
                                f"ℹ️ Установка MenuButton для конкретного чата {message.chat.id} не требуется "
                                f"(супергруппа - используем глобальную установку)"
                            )
                        else:
                            logger.warning(
                                f"⚠️ Не удалось установить MenuButton для чата {message.chat.id}: {chat_specific_error}"
                            )

                except Exception as global_error:
                    logger.warning(f"⚠️ Не удалось установить MenuButton глобально: {global_error}")
                    # Fallback: пробуем только для конкретного чата
                    try:
                        await bot.set_chat_menu_button(chat_id=message.chat.id, menu_button=types.MenuButtonCommands())
                        logger.info(f"✅ MenuButton установлен для чата {message.chat.id} (fallback)")
                    except Exception as fallback_error:
                        logger.warning(f"⚠️ Fallback установка MenuButton также не удалась: {fallback_error}")

                logger.info(f"✅ Команды и меню принудительно установлены для мобильных в чате {message.chat.id}")

            except Exception as e:
                logger.warning(f"⚠️ Не удалось установить команды для мобильных: {e}")
        else:
            # Для каналов - просто логируем успех
            logger.info(f"✅ Панель Community отправлена в канал {message.chat.id}")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки панели Community: {e}")
        # Проверяем, не закрыта ли тема форума
        if "TOPIC_CLOSED" in str(e):
            logger.warning(
                f"⚠️ Тема форума закрыта в чате {message.chat.id}. " "Бот не может отправлять сообщения в закрытые темы."
            )
            return
        try:
            fallback_msg = await message.answer("🤖 EventAroundBot активирован в этом чате!")
            # Удаляем fallback сообщение через 3 секунды
            try:
                await asyncio.sleep(3)
                await bot.delete_message(message.chat.id, fallback_msg.message_id)
                logger.info(f"✅ Fallback сообщение активации удалено в чате {message.chat.id}")
            except Exception as delete_error:
                logger.warning(f"⚠️ Не удалось удалить fallback сообщение активации: {delete_error}")
        except Exception as fallback_error:
            if "TOPIC_CLOSED" in str(fallback_error):
                logger.warning(
                    f"⚠️ Тема форума закрыта в чате {message.chat.id}. "
                    "Бот не может отправлять сообщения в закрытые темы."
                )
                return
            raise


# Убраны обработчики ReplyKeyboard кнопок - теперь используем только InlineKeyboard


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
            BotCommand(command="start", description="🎉 События чата"),
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
    '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
    "🎯 Что умею:\n"
    "• Создавать события участников чата\n"
    "• Показывать события этого чата\n"
    '• Полная версия "World"\n\n'
    "💡 Выберите действие:"
)


def group_kb(chat_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для панели группового чата"""
    # Используем статический username для надежности
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать событие", url=f"https://t.me/EventAroundBot?start=group_{chat_id}")],
            [InlineKeyboardButton(text="📋 События этого чата", callback_data="group_list")],
            [InlineKeyboardButton(text='🚀 Полная версия "World"', url="https://t.me/EventAroundBot")],
            [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_execute")],
        ]
    )


# === ОБРАБОТЧИКИ ===


# УБРАНО: обработчики кнопок Reply Keyboard - теперь бот работает только через команды и меню


# ПРИНУДИТЕЛЬНАЯ КЛАВИАТУРА ПРИ ДОБАВЛЕНИИ БОТА В ГРУППУ ИЛИ КАНАЛ
@group_router.message(F.new_chat_members, F.chat.type.in_({"group", "supergroup", "channel"}))
async def handle_new_members(message: Message, bot: Bot, session: AsyncSession):
    """Обработчик добавления новых участников в группу или канал"""
    logger.info(
        f"🔥 handle_new_members: получено событие new_chat_members в чате {message.chat.id} (тип: {message.chat.type})"
    )

    # Получаем информацию о нашем боте
    bot_info = await bot.get_me()
    logger.info(f"🔥 Наш бот ID: {bot_info.id}, username: {bot_info.username}")

    # Логируем всех новых участников
    for member in message.new_chat_members:
        logger.info(f"🔥 Новый участник: id={member.id}, is_bot={member.is_bot}, username={member.username}")

    # Проверяем, добавили ли именно нашего бота (по ID)
    bot_added = any(member.id == bot_info.id and member.is_bot for member in message.new_chat_members)

    if bot_added:
        chat_type_name = "канал" if message.chat.type == "channel" else "группу"
        logger.info(f"✅ Наш бот добавлен в {chat_type_name} {message.chat.id} (тип: {message.chat.type})")

        # Определяем, кто добавил бота (для начисления награды)
        # Пробуем использовать message.from_user, если доступен
        adder_user_id = None
        if message.from_user and not message.from_user.is_bot:
            adder_user_id = message.from_user.id
            logger.info(f"🎯 Определен пользователь, добавивший бота: {adder_user_id} (из message.from_user)")
        else:
            # Если from_user недоступен или это бот, пробуем получить первого админа
            try:
                from utils.community_events_service import CommunityEventsService

                community_service = CommunityEventsService()
                admin_ids = await community_service.get_cached_admin_ids(bot, message.chat.id)
                if admin_ids:
                    adder_user_id = admin_ids[0]  # Берем первого админа
                    logger.info(f"🎯 Определен пользователь, добавивший бота: {adder_user_id} (первый админ)")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось определить, кто добавил бота: {e}")

        # Создаем или обновляем запись в chat_settings сразу
        import json

        from sqlalchemy import select, text

        from database import ChatSettings

        try:
            result = await session.execute(select(ChatSettings).where(ChatSettings.chat_id == message.chat.id))
            settings = result.scalar_one_or_none()

            if not settings:
                logger.info(f"🔥 Создаем запись в chat_settings для нового чата {message.chat.id}")
                # Получаем следующий chat_number
                result = await session.execute(text("SELECT nextval('chat_number_seq')"))
                chat_number = result.scalar()
                logger.info(f"✅ Назначен chat_number={chat_number} для чата {message.chat.id}")

                # Получаем админов группы
                admin_ids = []
                admin_count = 0
                try:
                    from utils.community_events_service import CommunityEventsService

                    community_service = CommunityEventsService()
                    admin_ids = await community_service.get_cached_admin_ids(bot, message.chat.id)
                    admin_count = len(admin_ids)
                    logger.info(f"✅ Получены админы для нового чата {message.chat.id}: count={admin_count}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить админов для чата {message.chat.id}: {e}")

                settings = ChatSettings(
                    chat_id=message.chat.id,
                    chat_number=chat_number,
                    admin_ids=json.dumps(admin_ids) if admin_ids else None,
                    admin_count=admin_count,
                    bot_status="active",
                    total_events=0,  # Инициализируем счетчик событий
                )
                session.add(settings)
                await session.commit()
                logger.info(f"✅ Запись chat_settings создана для чата {message.chat.id}, chat_number={chat_number}")

                # Начисляем награду за добавление бота в чат (только для групп, не каналов)
                if adder_user_id and message.chat.type != "channel":
                    try:
                        from sqlalchemy import select

                        from database import User

                        # Начисляем 150 ракет напрямую через асинхронную сессию
                        user_result = await session.execute(select(User).where(User.id == adder_user_id))
                        user = user_result.scalar_one_or_none()

                        if user:
                            user.rockets_balance = (user.rockets_balance or 0) + 150
                            settings.added_by_user_id = adder_user_id
                            settings.rockets_awarded_at = datetime.now(UTC)
                            await session.commit()
                            logger.info(
                                f"🎉 Начислено 150 ракет пользователю {adder_user_id} "
                                f"за добавление бота в чат {message.chat.id}"
                            )
                        else:
                            logger.warning(f"⚠️ Пользователь {adder_user_id} не найден в БД")
                    except Exception as e:
                        logger.error(f"❌ Ошибка при начислении награды за добавление бота: {e}", exc_info=True)
            else:
                logger.info(f"🔥 Запись chat_settings уже существует для чата {message.chat.id}, обновляем статус")
                # Обновляем статус и админов при повторном добавлении
                settings.bot_status = "active"
                settings.bot_removed_at = None

                # Обновляем админов
                try:
                    from utils.community_events_service import CommunityEventsService

                    community_service = CommunityEventsService()
                    admin_ids = await community_service.get_cached_admin_ids(bot, message.chat.id)
                    admin_count = len(admin_ids)
                    settings.admin_ids = json.dumps(admin_ids) if admin_ids else None
                    settings.admin_count = admin_count
                    logger.info(f"✅ Обновлены админы для чата {message.chat.id}: count={admin_count}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось обновить админов для чата {message.chat.id}: {e}")

                # Проверяем, нужно ли начислить награду (только для групп, не каналов)
                if adder_user_id and message.chat.type != "channel":
                    # Проверяем, была ли уже награда за этот чат
                    if settings.added_by_user_id != adder_user_id or settings.rockets_awarded_at is None:
                        try:
                            from sqlalchemy import select

                            from database import User

                            # Начисляем 150 ракет напрямую через асинхронную сессию
                            user_result = await session.execute(select(User).where(User.id == adder_user_id))
                            user = user_result.scalar_one_or_none()

                            if user:
                                user.rockets_balance = (user.rockets_balance or 0) + 150
                                settings.added_by_user_id = adder_user_id
                                settings.rockets_awarded_at = datetime.now(UTC)
                                await session.commit()
                                logger.info(
                                    f"🎉 Начислено 150 ракет пользователю {adder_user_id} "
                                    f"за добавление бота в чат {message.chat.id}"
                                )
                            else:
                                logger.warning(f"⚠️ Пользователь {adder_user_id} не найден в БД")
                        except Exception as e:
                            logger.error(f"❌ Ошибка при начислении награды за добавление бота: {e}", exc_info=True)
                    else:
                        logger.info(
                            f"ℹ️ Пользователь {adder_user_id} уже получал награду "
                            f"за добавление бота в чат {message.chat.id}"
                        )

                # Проверяем, нужно ли начислить награду (только для групп, не каналов)
                if adder_user_id and message.chat.type != "channel":
                    # Проверяем, была ли уже награда за этот чат
                    if settings.added_by_user_id != adder_user_id or settings.rockets_awarded_at is None:
                        try:
                            from sqlalchemy import select

                            from database import User

                            # Начисляем 150 ракет напрямую через асинхронную сессию
                            user_result = await session.execute(select(User).where(User.id == adder_user_id))
                            user = user_result.scalar_one_or_none()

                            if user:
                                user.rockets_balance = (user.rockets_balance or 0) + 150
                                settings.added_by_user_id = adder_user_id
                                settings.rockets_awarded_at = datetime.now(UTC)
                                await session.commit()
                                logger.info(
                                    f"🎉 Начислено 150 ракет пользователю {adder_user_id} "
                                    f"за добавление бота в чат {message.chat.id}"
                                )
                            else:
                                logger.warning(f"⚠️ Пользователь {adder_user_id} не найден в БД")
                        except Exception as e:
                            logger.error(f"❌ Ошибка при начислении награды за добавление бота: {e}", exc_info=True)
                    else:
                        logger.info(
                            f"ℹ️ Пользователь {adder_user_id} уже получал награду "
                            f"за добавление бота в чат {message.chat.id}"
                        )

                await session.commit()
                logger.info(f"✅ Запись chat_settings обновлена для чата {message.chat.id}")

            # Простое приветствие без выбора ветки (только в группах, не в каналах)
            if message.chat.type != "channel":
                # ВАЖНО: Устанавливаем MenuButton при добавлении бота в группу
                # Это нужно для отображения кнопки "Команды бота" на всех устройствах, включая MacBook
                # Для MacBook важно установить MenuButton глобально ПЕРЕД попыткой установки для конкретного чата
                try:
                    # СНАЧАЛА устанавливаем глобально для всех групп (важно для MacBook)
                    await bot.set_chat_menu_button(menu_button=types.MenuButtonCommands())
                    logger.info("✅ MenuButton установлен глобально при добавлении бота (приоритет для MacBook)")

                    # Небольшая задержка для применения глобальной установки
                    await asyncio.sleep(0.5)

                    # Затем пробуем установить для конкретного чата (для других устройств)
                    try:
                        await bot.set_chat_menu_button(chat_id=message.chat.id, menu_button=types.MenuButtonCommands())
                        logger.info(f"✅ MenuButton дополнительно установлен для чата {message.chat.id} при добавлении")
                    except Exception as chat_specific_error:
                        error_str = str(chat_specific_error).lower()
                        # Для супергрупп это нормально - глобальная установка уже работает
                        if "chat_id" in error_str or "неверный" in error_str or "invalid" in error_str:
                            logger.info(
                                f"ℹ️ Установка MenuButton для конкретного чата {message.chat.id} не требуется "
                                f"при добавлении (супергруппа - используем глобальную установку)"
                            )
                        else:
                            logger.warning(
                                f"⚠️ Не удалось установить MenuButton для чата {message.chat.id} "
                                f"при добавлении: {chat_specific_error}"
                            )

                except Exception as global_error:
                    logger.warning(f"⚠️ Не удалось установить MenuButton глобально при добавлении: {global_error}")
                    # Fallback: пробуем только для конкретного чата
                    try:
                        await bot.set_chat_menu_button(chat_id=message.chat.id, menu_button=types.MenuButtonCommands())
                        logger.info(f"✅ MenuButton установлен для чата {message.chat.id} при добавлении (fallback)")
                    except Exception as fallback_error:
                        logger.warning(
                            f"⚠️ Fallback установка MenuButton при добавлении также не удалась: {fallback_error}"
                        )

                # Устанавливаем команды для конкретного чата
                try:
                    await bot.set_my_commands(
                        [types.BotCommand(command="start", description="🎉 События чата")],
                        scope=types.BotCommandScopeChat(chat_id=message.chat.id),
                    )
                    logger.info(f"✅ Команды установлены при добавлении бота в группу {message.chat.id}")
                except Exception as cmd_error:
                    logger.warning(
                        f"⚠️ Не удалось установить команды при добавлении в группу {message.chat.id}: {cmd_error}"
                    )

                try:
                    welcome_text = (
                        "🎉 Бот добавлен в группу!\n\n"
                        "Жми /start для создания и поиска событий\n\n"
                        "📌 Закрепи, что бы все знали"
                    )
                    await message.answer(welcome_text, parse_mode="Markdown")
                    logger.info(f"✅ Приветственное сообщение отправлено в чат {message.chat.id}")
                except Exception as answer_error:
                    logger.error(
                        f"❌ Ошибка при отправке приветственного сообщения в чат {message.chat.id}: {answer_error}",
                        exc_info=True,
                    )
                    # Проверяем, не закрыта ли тема форума
                    if "TOPIC_CLOSED" in str(answer_error):
                        logger.warning(
                            f"⚠️ Тема форума закрыта в чате {message.chat.id}. "
                            "Бот не может отправлять приветственное сообщение в закрытую тему."
                        )
                    else:
                        logger.warning(f"⚠️ Не удалось отправить приветственное сообщение: {answer_error}")
            else:
                # Для каналов - логируем, что бот готов к работе
                logger.info(f"✅ Бот готов к работе в канале {message.chat.id}. Используйте /start для начала работы")
        except Exception as e:
            error_str = str(e)
            # Проверяем, не закрыта ли тема форума
            if "TOPIC_CLOSED" in error_str:
                logger.warning(
                    f"⚠️ Тема форума закрыта в чате {message.chat.id}. "
                    "Бот не может отправлять сообщения в закрытую тему."
                )
            else:
                logger.error(
                    f"❌ ОШИБКА при создании/обновлении chat_settings для чата {message.chat.id}: {e}", exc_info=True
                )
            # Пробуем откатить транзакцию
            try:
                await session.rollback()
            except Exception as rollback_error:
                logger.error(f"❌ Ошибка при откате транзакции: {rollback_error}")
    else:
        logger.info(f"ℹ️ В чат {message.chat.id} добавлен не наш бот или не бот вообще")


@group_router.callback_query(F.data == "group_list")
async def group_list_events(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Показать список событий этого чата (первая страница)"""
    chat_id = callback.message.chat.id

    # Проверяем, пришли ли мы из сообщения об отмене записи
    message_text = callback.message.text or ""
    is_from_cancellation = "Вы больше не записаны" in message_text or "не записаны на событие" in message_text

    # Удаляем сообщение с подтверждением (из которого была нажата кнопка)
    try:
        await callback.message.delete()
        logger.info(f"✅ Удалено сообщение с подтверждением (message_id={callback.message.message_id})")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить сообщение с подтверждением: {e}")

    if is_from_cancellation:
        # Если пришли из сообщения об отмене - удаляем старый список и создаем новый на его месте (как при записи)
        logger.info("🔥 Обновляем список событий после отмены записи (удаляем старый и создаем новый)")
        try:
            from sqlalchemy import select

            from database import BotMessage

            # Находим все сообщения со списком событий (тег "list" или "service")
            result = await session.execute(
                select(BotMessage).where(
                    BotMessage.chat_id == chat_id,
                    BotMessage.deleted.is_(False),
                    BotMessage.tag.in_(["list", "service"]),  # Списки событий и подтверждения
                )
            )
            list_messages = result.scalars().all()

            deleted_count = 0
            for bot_msg in list_messages:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=bot_msg.message_id)
                    bot_msg.deleted = True
                    deleted_count += 1
                    logger.info(
                        f"✅ Удалено сообщение со списком событий (message_id={bot_msg.message_id}, tag={bot_msg.tag})"
                    )
                except Exception as delete_error:
                    logger.warning(f"⚠️ Не удалось удалить сообщение {bot_msg.message_id}: {delete_error}")
                    bot_msg.deleted = True  # Помечаем как удаленное

            await session.commit()
            logger.info(f"✅ Удалено {deleted_count} сообщений со списком событий")
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении предыдущих списков событий: {e}")

        # Создаем новый список событий на месте старого
        # Помечаем, что мы пришли из group_list, чтобы создать новое сообщение вместо редактирования
        callback._from_group_list = True
        await group_list_events_page(callback, bot, session, page=1)
    else:
        # Если пришли не из сообщения об отмене - удаляем все старые списки и создаем новый
        try:
            from sqlalchemy import select

            from database import BotMessage

            # Находим все сообщения со списком событий (тег "list" или "service")
            result = await session.execute(
                select(BotMessage).where(
                    BotMessage.chat_id == chat_id,
                    BotMessage.deleted.is_(False),
                    BotMessage.tag.in_(["list", "service"]),  # Списки событий и подтверждения
                )
            )
            list_messages = result.scalars().all()

            deleted_count = 0
            for bot_msg in list_messages:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=bot_msg.message_id)
                    bot_msg.deleted = True
                    deleted_count += 1
                    logger.info(
                        f"✅ Удалено сообщение со списком событий (message_id={bot_msg.message_id}, tag={bot_msg.tag})"
                    )
                except Exception as delete_error:
                    logger.warning(f"⚠️ Не удалось удалить сообщение {bot_msg.message_id}: {delete_error}")
                    bot_msg.deleted = True  # Помечаем как удаленное

            await session.commit()
            logger.info(f"✅ Удалено {deleted_count} сообщений со списком событий")
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении предыдущих списков событий: {e}")

        # Создаем новый список событий
        # Помечаем, что мы пришли из group_list, чтобы создать новое сообщение вместо редактирования
        callback._from_group_list = True
        await group_list_events_page(callback, bot, session, page=1)


@group_router.callback_query(F.data.startswith("group_list_page_"))
async def group_list_events_page_handler(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Обработчик навигации по страницам списка событий"""
    try:
        page = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        page = 1
    await group_list_events_page(callback, bot, session, page)


async def group_list_events_page(callback: CallbackQuery, bot: Bot, session: AsyncSession, page: int = 1):
    """Показать список событий этого чата с пагинацией"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    events_per_page = 10

    # Получаем thread_id для форумов
    is_forum = getattr(callback.message.chat, "is_forum", False)
    thread_id = getattr(callback.message, "message_thread_id", None)

    # Проверяем, является ли сообщение сообщением бота (можно редактировать только сообщения бота)
    bot_info = await bot.get_me()
    is_bot_message = callback.message.from_user is not None and callback.message.from_user.id == bot_info.id

    logger.info(
        f"🔥 group_list_events_page: запрос списка событий в чате {chat_id}, страница {page}, thread_id={thread_id}"
    )

    # Пытаемся ответить на callback (только если это реальный callback, не фейковый)
    try:
        await callback.answer()  # Тост, не спамим
    except (RuntimeError, AttributeError) as e:
        # Игнорируем ошибки для фейковых callback (например, из команд)
        logger.debug(f"⚠️ Не удалось ответить на callback (возможно, фейковый): {e}")

    try:
        # Получаем будущие события этого чата

        from sqlalchemy import func, select

        # Важно: показываем ВСЕ будущие события (даже через неделю или год),
        # но НЕ показываем события, которые начались более 3 часов назад (starts_at >= NOW() - 3 hours)
        # Это позволяет видеть события в течение 3 часов после начала (для долгих событий: вечеринки, выставки)
        # Для Community событий starts_at теперь TIMESTAMP WITHOUT TIME ZONE, поэтому убираем timezone
        now_utc = (datetime.now(UTC) - timedelta(hours=3)).replace(tzinfo=None)

        # Сначала получаем общее количество событий
        count_stmt = select(func.count(CommunityEvent.id)).where(
            CommunityEvent.chat_id == chat_id,
            CommunityEvent.status == "open",
            CommunityEvent.starts_at >= now_utc,  # Только будущие события, без ограничения по времени
        )
        total_result = await session.execute(count_stmt)
        total_events = total_result.scalar() or 0

        # Вычисляем offset для текущей страницы
        offset = (page - 1) * events_per_page
        total_pages = (total_events + events_per_page - 1) // events_per_page if total_events > 0 else 1

        # Получаем события для текущей страницы
        stmt = (
            select(CommunityEvent)
            .where(
                CommunityEvent.chat_id == chat_id,
                CommunityEvent.status == "open",
                CommunityEvent.starts_at >= now_utc,  # Только будущие события, без ограничения по времени
            )
            .order_by(CommunityEvent.starts_at)
            .offset(offset)
            .limit(events_per_page)
        )

        result = await session.execute(stmt)
        events = result.scalars().all()

        # Проверяем, является ли пользователь админом группы
        is_admin = await is_chat_admin(bot, chat_id, callback.from_user.id)

        if not events:
            text = (
                "📋 **События этого чата**\n\n"
                "📭 **0 событий**\n\n"
                "В этом чате пока нет активных событий.\n\n"
                "💡 Создайте первое событие, нажав кнопку **➕ Создать событие**!"
            )
        else:
            # Формируем заголовок с информацией о пагинации
            if total_pages > 1:
                text = f"📋 **События этого чата** ({total_events} событий, стр. {page}/{total_pages})\n\n"
            else:
                text = f"📋 **События этого чата** ({total_events} событий)\n\n"

            for i, event in enumerate(events, 1):
                # Номер события на текущей странице (с учетом offset)
                event_number = offset + i
                # Форматируем дату с конвертацией в часовой пояс города
                date_str = format_community_event_time(event, "%d.%m.%Y %H:%M")

                # Добавляем событие в список (безопасная версия)
                safe_title = event.title.replace("*", "").replace("_", "").replace("`", "'")
                text += f"{event_number}. {safe_title}\n"
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

                # Место с ссылкой на карту (если есть)
                if event.location_name:
                    safe_location = event.location_name.replace("*", "").replace("_", "").replace("`", "'")
                    if event.location_url:
                        # Создаем ссылку на карту в Markdown формате
                        safe_url = event.location_url.replace("(", "").replace(")", "")
                        text += f"   📍 [{safe_location}]({safe_url})\n"
                    else:
                        text += f"   📍 {safe_location}\n"
                elif event.location_url:
                    # Если есть только ссылка, без названия места
                    safe_url = event.location_url.replace("(", "").replace(")", "")
                    text += f"   📍 [Место на карте]({safe_url})\n"

                # Организатор
                if event.organizer_username:
                    text += f"   👤 Организатор: @{event.organizer_username}\n"

                # Получаем количество участников и добавляем в текст
                from utils.community_participants_service_optimized import (
                    get_participants_count_optimized,
                    is_participant_optimized,
                )

                participants_count = await get_participants_count_optimized(session, event.id)
                is_user_participant = await is_participant_optimized(session, event.id, user_id)

                # Добавляем информацию об участниках (кнопка будет добавлена в клавиатуру)
                text += f"   👥 Участников: {participants_count}\n"

                # Добавляем ссылку на запись прямо в тексте (через команду)
                # В групповых чатах используем команды, которые можно вызвать
                if is_user_participant:
                    text += f"   ✅ Вы записаны | Нажмите 👉 /leaveevent{event.id} чтобы отменить\n"
                else:
                    text += f"   Нажмите 👉 /joinevent{event.id} чтобы записаться\n"

                text += "\n"

            if is_admin:
                text += "🔧 Админ-панель: Вы можете управлять любым событием кнопками ниже!\n"
                text += "💡 Нажмите ➕ Создать событие чтобы добавить свое!"
            else:
                text += "🔧 Ваши события: Вы можете управлять своими событиями кнопками ниже!\n"
                text += "💡 Нажмите ➕ Создать событие чтобы добавить свое!"

        # Создаем клавиатуру с кнопками управления событиями
        keyboard_buttons = []

        # Всегда показываем кнопку "Управление событиями", даже если активных событий нет
        # Это позволяет возобновлять закрытые события (в течение 24 часов после закрытия)
        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="🔧 Управление событиями",
                    callback_data="group_manage_events",
                )
            ]
        )

        # Добавляем кнопки навигации по страницам
        navigation_buttons = []
        if total_pages > 1:
            if page > 1:
                navigation_buttons.append(
                    InlineKeyboardButton(text="◀️ Предыдущая", callback_data=f"group_list_page_{page - 1}")
                )
            if page < total_pages:
                navigation_buttons.append(
                    InlineKeyboardButton(text="▶️ Следующая", callback_data=f"group_list_page_{page + 1}")
                )
            if navigation_buttons:
                keyboard_buttons.append(navigation_buttons)

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

            # Убираем проблемные символы из текста, но сохраняем Markdown ссылки
            import re
            import uuid

            # Сначала извлекаем все ссылки и заменяем их на уникальные маркеры
            link_pattern = r"\[([^\]]+)\]\(([^\)]+)\)"
            links_map = {}  # Маркер -> (link_text, link_url)

            def replace_with_marker(match):
                link_text = match.group(1)
                link_url = match.group(2)
                # Используем уникальный маркер без подчеркиваний и других проблемных символов
                marker = f"LINKMARKER{uuid.uuid4().hex}"
                links_map[marker] = (link_text, link_url)
                return marker

            # Заменяем все ссылки на маркеры
            text = re.sub(link_pattern, replace_with_marker, text)

            # Теперь безопасно убираем проблемные символы (маркеры не содержат их)
            text = text.replace("`", "'").replace("*", "").replace("_", "").replace("[", "(").replace("]", ")")

            # Восстанавливаем ссылки из маркеров
            for marker, (link_text, link_url) in links_map.items():
                # Очищаем текст и URL от проблемных символов
                safe_text = link_text.replace("*", "").replace("_", " ").replace("[", "").replace("]", "")
                safe_url = link_url.replace("(", "%28").replace(")", "%29")
                text = text.replace(marker, f"[{safe_text}]({safe_url})")

            # Отправляем с Markdown для поддержки ссылок
            # Если это сообщение пользователя (не бота) или мы пришли из group_list (удаляем старые списки),
            # отправляем новое сообщение через send_tracked с тегом "list"
            from utils.messaging_utils import send_tracked

            if is_bot_message and not hasattr(callback, "_from_group_list"):
                # Редактируем существующее сообщение со списком
                await callback.message.edit_text(text, reply_markup=back_kb, parse_mode="Markdown")
                logger.info("✅ Список событий успешно обновлен")

                # Убеждаемся, что отредактированное сообщение трекируется и будет автоудалено
                import asyncio

                from sqlalchemy import select

                from database import BotMessage
                from utils.messaging_utils import auto_delete_message

                # Проверяем, есть ли уже запись в БД
                result = await session.execute(
                    select(BotMessage).where(
                        BotMessage.chat_id == chat_id,
                        BotMessage.message_id == callback.message.message_id,
                    )
                )
                bot_msg = result.scalar_one_or_none()

                if not bot_msg:
                    # Если сообщение не трекируется, добавляем его в БД
                    bot_msg = BotMessage(
                        chat_id=chat_id,
                        message_id=callback.message.message_id,
                        tag="list",
                    )
                    session.add(bot_msg)
                    await session.commit()
                    logger.info(
                        f"✅ Отредактированное сообщение {callback.message.message_id} "
                        f"добавлено в трекинг для автоудаления"
                    )

                # Запускаем автоудаление (если еще не запущено)
                # Проверяем, не помечено ли сообщение как удаленное
                if not bot_msg.deleted:

                    async def safe_auto_delete():
                        try:
                            await auto_delete_message(bot, chat_id, callback.message.message_id, 210)  # 3.5 минуты
                        except Exception as e:
                            logger.error(
                                f"❌ Ошибка автоудаления для отредактированного сообщения "
                                f"{callback.message.message_id}: {e}"
                            )

                    task = asyncio.create_task(safe_auto_delete())
                    task.add_done_callback(
                        lambda t: logger.error(f"❌ Задача автоудаления завершилась с ошибкой: {t.exception()}")
                        if t.exception()
                        else None
                    )
                    logger.info(
                        f"🕐 Запущено автоудаление для отредактированного сообщения "
                        f"{callback.message.message_id} в чате {chat_id}"
                    )
            else:
                # Отправляем новое сообщение через send_tracked для трекинга
                send_kwargs = {"reply_markup": back_kb, "parse_mode": "Markdown"}
                if is_forum and thread_id:
                    send_kwargs["message_thread_id"] = thread_id

                await send_tracked(
                    bot,
                    session,
                    chat_id=chat_id,
                    text=text,
                    tag="list",  # Тег для списка событий
                    **send_kwargs,
                )
                logger.info("✅ Новое сообщение со списком событий отправлено и трекируется")
        except Exception as e:
            logger.error(f"❌ Ошибка редактирования сообщения: {e}")

            # Специальная обработка для ошибки "сообщение не изменено"
            if "message is not modified" in str(e).lower():
                logger.info("🔥 Сообщение не изменилось, отправляем новое сообщение")
                try:
                    answer_kwargs = {"reply_markup": back_kb, "parse_mode": "Markdown"}
                    if is_forum and thread_id:
                        answer_kwargs["message_thread_id"] = thread_id
                    # Используем send_tracked вместо answer для автоудаления
                    await send_tracked(
                        bot,
                        session,
                        chat_id=chat_id,
                        text=text,
                        tag="list",
                        **answer_kwargs,
                    )
                    logger.info("✅ Новое сообщение со списком событий отправлено и трекируется")
                except Exception as e2:
                    logger.error(f"❌ Ошибка отправки нового сообщения: {e2}")
                    await callback.answer("❌ Ошибка отображения событий", show_alert=True)
            elif "message can't be edited" in str(e).lower():
                # Сообщение нельзя редактировать (например, это сообщение пользователя)
                logger.info("🔥 Сообщение нельзя редактировать, отправляем новое сообщение")
                try:
                    answer_kwargs = {"reply_markup": back_kb, "parse_mode": "Markdown"}
                    if is_forum and thread_id:
                        answer_kwargs["message_thread_id"] = thread_id
                    # Используем send_tracked вместо answer для автоудаления
                    await send_tracked(
                        bot,
                        session,
                        chat_id=chat_id,
                        text=text,
                        tag="list",
                        **answer_kwargs,
                    )
                    logger.info("✅ Новое сообщение со списком событий отправлено и трекируется")
                except Exception as e2:
                    logger.error(f"❌ Ошибка отправки нового сообщения: {e2}")
                    await callback.answer("❌ Ошибка отображения событий", show_alert=True)
            else:
                # Fallback: отправляем новое сообщение с Markdown
                try:
                    answer_kwargs = {"reply_markup": back_kb, "parse_mode": "Markdown"}
                    if is_forum and thread_id:
                        answer_kwargs["message_thread_id"] = thread_id
                    await callback.message.answer(text, **answer_kwargs)
                except Exception as e2:
                    logger.error(f"❌ Ошибка отправки нового сообщения: {e2}")
                    # Последний fallback: отправляем без клавиатуры
                try:
                    answer_kwargs = {
                        "text": "📋 **События этого чата**\n\n❌ Ошибка отображения. Попробуйте позже.",
                        "parse_mode": "Markdown",
                    }
                    if is_forum and thread_id:
                        answer_kwargs["message_thread_id"] = thread_id
                    await callback.message.answer(**answer_kwargs)
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
            # Fallback: отправляем новое сообщение
            try:
                is_forum = getattr(callback.message.chat, "is_forum", False)
                thread_id = getattr(callback.message, "message_thread_id", None)
                answer_kwargs = {"reply_markup": back_kb, "parse_mode": "Markdown"}
                if is_forum and thread_id:
                    answer_kwargs["message_thread_id"] = thread_id
                await callback.message.answer(error_text, **answer_kwargs)
            except Exception as fallback_error:
                logger.error(f"❌ Критическая ошибка отправки сообщения об ошибке: {fallback_error}")


@group_router.callback_query(F.data == "group_show_commands")
async def group_show_commands(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Показ инструкции по использованию команд бота"""
    chat_id = callback.message.chat.id
    logger.info(f"🔥 group_show_commands: пользователь {callback.from_user.id} запросил команды в чате {chat_id}")

    await callback.answer()

    commands_text = (
        "⌨️ **Команды бота в группе:**\n\n"
        "📋 **Доступные команды:**\n"
        "• `/start` - Открыть панель Community\n\n"
        "💻 **Как открыть команды на MacBook:**\n"
        "1. Нажмите `/` в поле ввода сообщения\n"
        "2. Или введите `/start@EventAroundBot`\n"
        "3. Или нажмите на кнопку **⌨️ Команды бота** в панели\n\n"
        "📱 **На мобильных устройствах:**\n"
        "Нажмите на иконку меню (☰) рядом с полем ввода"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к панели", callback_data="group_back_to_panel")],
        ]
    )

    try:
        await callback.message.edit_text(commands_text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования сообщения: {e}")


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
            # Получаем thread_id для форумов
            is_forum = getattr(callback.message.chat, "is_forum", False)
            thread_id = getattr(callback.message, "message_thread_id", None)

            send_kwargs = {"reply_markup": keyboard}
            if is_forum and thread_id:
                send_kwargs["message_thread_id"] = thread_id

            await send_tracked(
                bot,
                session,
                chat_id=chat_id,
                text=confirmation_text,
                tag="service",
                **send_kwargs,
            )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки подтверждения: {e}")


@group_router.callback_query(F.data == "group_hide_execute")
async def group_hide_execute_direct(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Прямое выполнение скрытия бота без подтверждения"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    # Получаем thread_id для форумов
    getattr(callback.message.chat, "is_forum", False)
    thread_id = getattr(callback.message, "message_thread_id", None)

    logger.info(
        f"🔥 group_hide_execute_direct: пользователь {user_id} скрывает бота в чате {chat_id}, thread_id={thread_id}"
    )

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

    # Сообщение о скрытии бота убрано - бот просто скрывается без уведомления
    # ВОССТАНАВЛИВАЕМ КОМАНДЫ ПОСЛЕ СКРЫТИЯ БОТА (НАДЕЖНО)
    await ensure_group_start_command(bot, chat_id)

    logger.info(f"✅ Бот скрыт в чате {chat_id} пользователем {user_id}, удалено сообщений: {deleted}")


@group_router.callback_query(F.data.startswith("group_hide_execute_"))
async def group_hide_execute(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Выполнение скрытия бота"""
    chat_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    # Получаем thread_id для форумов
    getattr(callback.message.chat, "is_forum", False)
    thread_id = getattr(callback.message, "message_thread_id", None)

    logger.info(
        f"🔥 group_hide_execute: пользователь {user_id} подтвердил скрытие бота в чате {chat_id}, thread_id={thread_id}"
    )

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
        await delete_all_tracked(bot, session, chat_id=chat_id)
    except Exception as e:
        logger.error(f"❌ Ошибка удаления сообщений: {e}")

    # Сообщение о скрытии бота убрано - бот просто скрывается без уведомления
    # ВОССТАНАВЛИВАЕМ КОМАНДЫ ПОСЛЕ СКРЫТИЯ БОТА (НАДЕЖНО)
    await ensure_group_start_command(bot, chat_id)


@group_router.callback_query(F.data.startswith("community_members_"))
async def community_show_members(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Показать список участников события"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    # Извлекаем ID события
    try:
        event_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(f"🔥 community_show_members: пользователь {user_id} просматривает участников события {event_id}")

    await callback.answer()

    try:
        # Получаем событие
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await callback.message.answer("❌ Событие не найдено")
            return

        # Получаем участников
        from utils.community_participants_service_optimized import get_participants_optimized

        participants = await get_participants_optimized(session, event_id)
        participants_count = len(participants)

        # Формируем текст сообщения
        safe_title = event.title.replace("*", "").replace("_", "").replace("`", "'")
        text = f"👥 **Участники события: {safe_title}**\n\n"
        text += f"**Всего:** {participants_count}\n\n"

        if participants_count > 0:
            for i, participant in enumerate(participants, 1):
                username = participant.get("username")
                if username:
                    text += f"{i}. @{username}\n"
                else:
                    text += f"{i}. Пользователь {participant.get('user_id')}\n"
        else:
            text += "Пока нет участников. Станьте первым! 👇"

        # Создаем клавиатуру
        keyboard_buttons = []

        # Кнопки записи/отмены записи убраны - запись происходит через команды /joinevent и /leaveevent в списке событий

        # Кнопка "Управление" убрана - она дублирует кнопку "Назад", которая ведет к тому же меню

        # Добавляем кнопку "Назад" для возврата к меню управления событием
        # Нужно найти индекс события в списке управляемых событий
        is_admin = await is_chat_admin(bot, chat_id, user_id)
        manageable_events = await _get_manageable_community_events(session, chat_id, user_id, is_admin)

        # Находим индекс события в списке
        event_index = None
        for i, e in enumerate(manageable_events):
            if e.id == event_id:
                event_index = i
                break

        if event_index is not None:
            # Используем callback для возврата к меню управления с правильным индексом
            keyboard_buttons.append(
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"group_prev_event_{event_index}")]
            )
        else:
            # Fallback: если не нашли индекс, используем старый обработчик
            keyboard_buttons.append(
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"group_manage_event_{event_id}")]
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Редактируем существующее сообщение вместо создания нового
        is_forum = getattr(callback.message.chat, "is_forum", False)
        thread_id = getattr(callback.message, "message_thread_id", None)

        send_kwargs = {
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": keyboard,
        }
        if is_forum and thread_id:
            send_kwargs["message_thread_id"] = thread_id

        try:
            await callback.message.edit_text(**send_kwargs)
        except Exception:
            # Если не удалось отредактировать, отправляем новое сообщение
            await callback.message.answer(**send_kwargs)

    except Exception as e:
        logger.error(f"❌ Ошибка показа участников: {e}")
        await callback.message.answer("❌ Ошибка при загрузке участников")


@group_router.callback_query(F.data.startswith("community_join_") & ~F.data.startswith("community_join_confirm_"))
async def community_join_event(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Показ подтверждения записи на событие"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    # Извлекаем ID события
    try:
        event_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(
        f"🔥 community_join_event: пользователь {user_id} запрашивает подтверждение записи на событие {event_id}"
    )

    await callback.answer()

    try:
        # Проверяем, что событие существует
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await callback.message.answer("❌ Событие не найдено")
            return

        # Проверяем, не записан ли уже пользователь
        from utils.community_participants_service_optimized import is_participant_optimized

        is_participant = await is_participant_optimized(session, event_id, user_id)
        if is_participant:
            await callback.message.answer("ℹ️ Вы уже записаны на это событие")
            return

        # Формируем текст подтверждения
        safe_title = event.title.replace("*", "").replace("_", "").replace("`", "'")
        date_str = format_community_event_time(event, "%d.%m.%Y %H:%M") if event.starts_at else "Дата не указана"

        confirmation_text = (
            f"✅ **Записаться на событие?**\n\n"
            f"**{safe_title}**\n"
            f"📅 {date_str}\n\n"
            f"Вы будете добавлены в список участников этого события."
        )

        # Создаем клавиатуру с подтверждением
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, записаться", callback_data=f"community_join_confirm_{event_id}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="group_list")],
            ]
        )

        # Отправляем сообщение с подтверждением
        is_forum = getattr(callback.message.chat, "is_forum", False)
        thread_id = getattr(callback.message, "message_thread_id", None)

        send_kwargs = {
            "text": confirmation_text,
            "parse_mode": "Markdown",
            "reply_markup": keyboard,
        }
        if is_forum and thread_id:
            send_kwargs["message_thread_id"] = thread_id

        await callback.message.answer(**send_kwargs)

    except Exception as e:
        logger.error(f"❌ Ошибка показа подтверждения: {e}")
        await callback.message.answer("❌ Ошибка при загрузке события")


@group_router.callback_query(F.data.startswith("community_join_confirm_"))
async def community_join_confirm(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Подтверждение и выполнение записи на событие"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    username = callback.from_user.username

    # Извлекаем ID события и message_id исходного сообщения пользователя
    try:
        parts = callback.data.split("_")
        event_id = int(parts[-2]) if len(parts) >= 4 else int(parts[-1])
        user_message_id = int(parts[-1]) if len(parts) >= 4 and parts[-1].isdigit() else 0
    except (ValueError, IndexError):
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(f"🔥 community_join_confirm: пользователь {user_id} подтверждает запись на событие {event_id}")

    try:
        # Проверяем, что событие существует
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await callback.answer("❌ Событие не найдено", show_alert=True)
            return

        # Добавляем участника
        from utils.community_participants_service_optimized import add_participant_optimized

        added = await add_participant_optimized(session, event_id, user_id, username)

        if added:
            await callback.answer("✅ Вы записались на событие!")
            # Удаляем сообщение с подтверждением
            try:
                await callback.message.delete()
            except Exception:
                pass

            # Удаляем исходное сообщение пользователя с командой (если оно было передано)
            if user_message_id > 0:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=user_message_id)
                    logger.info(
                        f"✅ Удалено исходное сообщение пользователя {user_id} "
                        f"с командой (message_id={user_message_id})"
                    )
                except Exception as delete_error:
                    logger.warning(f"⚠️ Не удалось удалить исходное сообщение пользователя: {delete_error}")
        else:
            await callback.answer("ℹ️ Вы уже записаны на это событие", show_alert=True)
            return

        # Показываем успешное сообщение с кнопкой возврата к списку
        safe_title = event.title.replace("*", "").replace("_", "").replace("`", "'")
        success_text = (
            f"✅ **Вы записались на событие!**\n\n"
            f"**{safe_title}**\n\n"
            f"Теперь вы в списке участников. Нажмите 'Вернуться к списку' чтобы увидеть обновленный счетчик."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Вернуться к списку", callback_data="group_list")]]
        )

        is_forum = getattr(callback.message.chat, "is_forum", False)
        thread_id = getattr(callback.message, "message_thread_id", None)

        send_kwargs = {
            "text": success_text,
            "parse_mode": "Markdown",
            "reply_markup": keyboard,
        }
        if is_forum and thread_id:
            send_kwargs["message_thread_id"] = thread_id

        await callback.message.answer(**send_kwargs)

    except Exception as e:
        logger.error(f"❌ Ошибка записи на событие: {e}")
        await callback.answer("❌ Ошибка при записи на событие", show_alert=True)


@group_router.callback_query(F.data.startswith("community_leave_"))
async def community_leave_event(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Отменить запись на событие"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    # Извлекаем ID события
    try:
        event_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(f"🔥 community_leave_event: пользователь {user_id} отменяет запись на событие {event_id}")

    try:
        # Проверяем, что событие существует
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await callback.answer("❌ Событие не найдено", show_alert=True)
            return

        # Удаляем участника
        from utils.community_participants_service_optimized import remove_participant_optimized

        removed = await remove_participant_optimized(session, event_id, user_id)

        if removed:
            await callback.answer("✅ Запись отменена")

            # Сразу обновляем список событий (удаляем старый и создаем новый с обновленными данными)
            try:
                from sqlalchemy import select

                from database import BotMessage

                # Находим все сообщения со списком событий (тег "list" или "service")
                result = await session.execute(
                    select(BotMessage).where(
                        BotMessage.chat_id == chat_id,
                        BotMessage.deleted.is_(False),
                        BotMessage.tag.in_(["list", "service"]),  # Списки событий и подтверждения
                    )
                )
                list_messages = result.scalars().all()

                deleted_count = 0
                for bot_msg in list_messages:
                    try:
                        await bot.delete_message(chat_id=chat_id, message_id=bot_msg.message_id)
                        bot_msg.deleted = True
                        deleted_count += 1
                        logger.info(
                            f"✅ Удалено сообщение со списком событий "
                            f"(message_id={bot_msg.message_id}, tag={bot_msg.tag})"
                        )
                    except Exception as delete_error:
                        logger.warning(f"⚠️ Не удалось удалить сообщение {bot_msg.message_id}: {delete_error}")
                        bot_msg.deleted = True  # Помечаем как удаленное

                await session.commit()
                logger.info(f"✅ Удалено {deleted_count} сообщений со списком событий")
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении предыдущих списков событий: {e}")

            # Создаем новый список событий с обновленными данными
            callback._from_group_list = True
            await group_list_events_page(callback, bot, session, page=1)
        else:
            await callback.answer("ℹ️ Вы не были записаны на это событие")

    except Exception as e:
        logger.error(f"❌ Ошибка отмены записи: {e}")
        await callback.answer("❌ Ошибка при отмене записи", show_alert=True)


@group_router.callback_query(F.data == "group_manage_events")
async def group_manage_events(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Обработчик кнопки Управление событиями (главная кнопка, как в World режиме)"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    logger.info(f"🔥 group_manage_events: пользователь {user_id} открывает управление событиями в чате {chat_id}")

    await callback.answer()

    try:
        # Проверяем, является ли пользователь админом
        is_admin = await is_chat_admin(bot, chat_id, user_id)

        # Получаем события, которыми может управлять пользователь
        manageable_events = await _get_manageable_community_events(session, chat_id, user_id, is_admin)

        if not manageable_events:
            text = (
                "📋 **Управление событиями**\n\n"
                "У вас нет событий для управления.\n\n"
                "💡 Вы можете:\n"
                "• Создать новое событие через кнопку ➕ Создать событие\n"
                "• Возобновить закрытые события (если они были закрыты менее 24 часов назад)"
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад к списку", callback_data="group_list")]]
            )
            try:
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
            except Exception:
                await callback.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
            return

        # Показываем первое событие
        await _show_community_manage_event(callback, bot, session, manageable_events, 0, chat_id, user_id, is_admin)

    except Exception as e:
        logger.error(f"❌ Ошибка показа управления событиями: {e}")
        import traceback

        logger.error(traceback.format_exc())
        await callback.answer("❌ Ошибка при загрузке событий", show_alert=True)


async def _show_community_manage_event(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    events: list[CommunityEvent],
    index: int,
    chat_id: int,
    user_id: int,
    is_admin: bool,
):
    """Показывает событие под нужным индексом с навигацией"""
    if not events:
        return

    total = len(events)
    if index < 0 or index >= total:
        index = 0

    event = events[index]

    # Проверяем права доступа
    can_manage = event.organizer_id == user_id or is_admin
    if not can_manage:
        await callback.answer("❌ У вас нет прав для управления этим событием", show_alert=True)
        return

    header = f"🔧 Управление событием ({index + 1}/{total}):\n\n"
    text = f"{header}{format_community_event_for_display(event)}"

    # Получаем username бота для deep-link
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "EventAroundBot"

    # Получаем кнопки управления (передаем также updated_at для проверки времени закрытия)
    buttons = get_community_status_buttons(event.id, event.status, event.updated_at, chat_id, bot_username)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=btn["text"],
                    callback_data=btn.get("callback_data"),
                    url=btn.get("url"),
                )
            ]
            for btn in buttons
        ]
    )

    # Добавляем навигацию: всегда показываем 3 кнопки (Список, Назад, Вперед)
    nav_row = [
        InlineKeyboardButton(text="📋 Список", callback_data="group_list"),
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"group_prev_event_{max(0, index-1)}"),
        InlineKeyboardButton(text="▶️ Вперед", callback_data=f"group_next_event_{min(total-1, index+1)}"),
    ]
    keyboard.inline_keyboard.append(nav_row)

    # Сохраняем список событий в callback для последующего использования
    callback._manageable_events = events
    callback._chat_id = chat_id
    callback._user_id = user_id
    callback._is_admin = is_admin

    # Отправляем или редактируем сообщение
    is_forum = getattr(callback.message.chat, "is_forum", False)
    thread_id = getattr(callback.message, "message_thread_id", None)

    send_kwargs = {
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard,
    }
    if is_forum and thread_id:
        send_kwargs["message_thread_id"] = thread_id

    # Проверяем, является ли сообщение сообщением бота (можно редактировать только сообщения бота)
    bot_info = await bot.get_me()
    is_bot_message = callback.message.from_user is not None and callback.message.from_user.id == bot_info.id

    import logging

    logger = logging.getLogger(__name__)

    # Пытаемся отредактировать сообщение только если это сообщение бота и есть текст/подпись
    if is_bot_message and (callback.message.text or callback.message.caption):
        try:
            await callback.message.edit_text(**send_kwargs)
        except Exception as e:
            # Логируем ошибку для отладки
            logger.warning(
                f"⚠️ Не удалось отредактировать сообщение {callback.message.message_id}: {type(e).__name__}: {e}"
            )
            # Если не удалось отредактировать, отправляем новое сообщение
            try:
                await callback.message.answer(**send_kwargs)
            except Exception as e2:
                logger.error(f"❌ Не удалось отправить новое сообщение: {type(e2).__name__}: {e2}")
    else:
        # Если это не сообщение бота или нет текста/подписи, отправляем новое сообщение
        if not is_bot_message:
            from_user_id = callback.message.from_user.id if callback.message.from_user else None
            logger.debug(
                f"Сообщение {callback.message.message_id} не от бота "
                f"(from_user.id={from_user_id}, bot.id={bot_info.id}), "
                f"отправляем новое"
            )
        else:
            logger.debug(f"Сообщение {callback.message.message_id} не имеет текста/подписи, отправляем новое")
        try:
            await callback.message.answer(**send_kwargs)
        except Exception as e:
            logger.error(f"❌ Не удалось отправить новое сообщение: {type(e).__name__}: {e}")


@group_router.callback_query(F.data.startswith("group_next_event_"))
async def group_next_event(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Переход к следующему событию"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    try:
        target_index = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный индекс", show_alert=True)
        return

    is_admin = await is_chat_admin(bot, chat_id, user_id)
    manageable_events = await _get_manageable_community_events(session, chat_id, user_id, is_admin)

    if target_index >= len(manageable_events):
        await callback.answer("Больше событий нет")
        return

    await _show_community_manage_event(
        callback, bot, session, manageable_events, target_index, chat_id, user_id, is_admin
    )
    await callback.answer()


@group_router.callback_query(F.data.startswith("group_prev_event_"))
async def group_prev_event(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Переход к предыдущему событию"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    try:
        target_index = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный индекс", show_alert=True)
        return

    is_admin = await is_chat_admin(bot, chat_id, user_id)
    manageable_events = await _get_manageable_community_events(session, chat_id, user_id, is_admin)

    if target_index < 0 or target_index >= len(manageable_events):
        await callback.answer("Это первое событие")
        return

    await _show_community_manage_event(
        callback, bot, session, manageable_events, target_index, chat_id, user_id, is_admin
    )
    await callback.answer()


@group_router.callback_query(F.data.startswith("group_manage_event_"))
async def group_manage_event(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Меню управления событием (для создателя и админов)"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    # Извлекаем ID события из callback_data
    try:
        event_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(f"🔥 group_manage_event: пользователь {user_id} открывает меню управления событием {event_id}")

    await callback.answer()

    try:
        # Проверяем, что событие существует
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await callback.answer("❌ Событие не найдено", show_alert=True)
            return

        # Проверяем права доступа
        is_admin = await is_chat_admin(bot, chat_id, user_id)
        can_manage = event.organizer_id == user_id or is_admin

        if not can_manage:
            await callback.answer("❌ У вас нет прав для управления этим событием", show_alert=True)
            return

        # Получаем количество участников
        from utils.community_participants_service_optimized import get_participants_count_optimized

        participants_count = await get_participants_count_optimized(session, event_id)

        # Формируем текст с информацией о событии
        safe_title = event.title.replace("*", "").replace("_", "").replace("`", "'")
        date_str = format_community_event_time(event, "%d.%m.%Y %H:%M") if event.starts_at else "Дата не указана"

        text = "⚙️ **Управление событием**\n\n"
        text += f"**{safe_title}**\n"
        text += f"📅 {date_str}\n"
        text += f"👥 Участников: {participants_count}\n"

        # Создаем клавиатуру с опциями управления
        keyboard_buttons = [
            [InlineKeyboardButton(text="👥 Участники", callback_data=f"community_members_{event_id}")],
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"group_edit_event_{event_id}")],
            [InlineKeyboardButton(text="❌ Удалить", callback_data=f"group_delete_event_{event_id}")],
            [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="group_list")],
        ]

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Отправляем или редактируем сообщение
        is_forum = getattr(callback.message.chat, "is_forum", False)
        thread_id = getattr(callback.message, "message_thread_id", None)

        send_kwargs = {
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": keyboard,
        }
        if is_forum and thread_id:
            send_kwargs["message_thread_id"] = thread_id

        try:
            await callback.message.edit_text(**send_kwargs)
        except Exception:
            # Если не удалось отредактировать, отправляем новое сообщение
            await callback.message.answer(**send_kwargs)

    except Exception as e:
        logger.error(f"❌ Ошибка показа меню управления событием: {e}")
        import traceback

        logger.error(traceback.format_exc())
        await callback.answer("❌ Ошибка при загрузке события", show_alert=True)


@group_router.callback_query(F.data.startswith("group_close_event_"))
async def group_close_event(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Закрытие события (завершение мероприятия)"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    try:
        event_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(f"🔥 group_close_event: пользователь {user_id} закрывает событие {event_id} в чате {chat_id}")

    try:
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await callback.answer("❌ Событие не найдено", show_alert=True)
            return

        # Проверяем права
        is_admin = await is_chat_admin(bot, chat_id, user_id)
        can_manage = event.organizer_id == user_id or is_admin

        if not can_manage:
            await callback.answer("❌ У вас нет прав для управления этим событием", show_alert=True)
            return

        # Закрываем событие
        event.status = "closed"
        event.updated_at = datetime.now(UTC)
        await session.commit()

        await callback.answer("✅ Событие завершено")

        # Обновляем отображение события
        manageable_events = await _get_manageable_community_events(session, chat_id, user_id, is_admin)
        # Находим индекс закрытого события
        event_index = next((i for i, e in enumerate(manageable_events) if e.id == event_id), 0)
        await _show_community_manage_event(
            callback, bot, session, manageable_events, event_index, chat_id, user_id, is_admin
        )

    except Exception as e:
        logger.error(f"❌ Ошибка закрытия события: {e}")
        import traceback

        logger.error(traceback.format_exc())
        await callback.answer("❌ Ошибка при закрытии события", show_alert=True)


@group_router.callback_query(F.data.startswith("group_open_event_"))
async def group_open_event(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Возобновление события (открытие закрытого мероприятия)"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    try:
        event_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(f"🔥 group_open_event: пользователь {user_id} возобновляет событие {event_id} в чате {chat_id}")

    try:
        from sqlalchemy import select

        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            await callback.answer("❌ Событие не найдено", show_alert=True)
            return

        # Проверяем права
        is_admin = await is_chat_admin(bot, chat_id, user_id)
        can_manage = event.organizer_id == user_id or is_admin

        if not can_manage:
            await callback.answer("❌ У вас нет прав для управления этим событием", show_alert=True)
            return

        # Проверяем, что событие закрыто
        if event.status != "closed":
            await callback.answer("❌ Событие не закрыто, его нельзя возобновить", show_alert=True)
            return

        # Проверяем, что событие было закрыто в течение последних 24 часов
        from datetime import timedelta

        # Для Community событий updated_at имеет timezone, но starts_at - нет
        day_ago = datetime.now(UTC) - timedelta(hours=24)
        if event.updated_at and event.updated_at < day_ago:
            await callback.answer(
                "❌ Возобновление возможно только в течение 24 часов после закрытия события", show_alert=True
            )
            return

        # Проверяем, что событие еще не началось (не прошло по времени)
        # Если событие уже прошло, просто не обрабатываем запрос (событие не должно было попасть в список)
        # Для Community событий starts_at теперь TIMESTAMP WITHOUT TIME ZONE, поэтому убираем timezone
        now_naive = datetime.now(UTC).replace(tzinfo=None)
        if event.starts_at and event.starts_at < now_naive:
            # Событие уже прошло - просто игнорируем (не должно было попасть в список)
            await callback.answer()
            return

        # Открываем событие
        event.status = "open"
        event.updated_at = datetime.now(UTC)
        await session.commit()

        await callback.answer("✅ Событие возобновлено")

        # Обновляем отображение события
        manageable_events = await _get_manageable_community_events(session, chat_id, user_id, is_admin)
        # Находим индекс возобновленного события
        event_index = next((i for i, e in enumerate(manageable_events) if e.id == event_id), 0)
        await _show_community_manage_event(
            callback, bot, session, manageable_events, event_index, chat_id, user_id, is_admin
        )

    except Exception as e:
        logger.error(f"❌ Ошибка возобновления события: {e}")
        import traceback

        logger.error(traceback.format_exc())
        await callback.answer("❌ Ошибка при возобновлении события", show_alert=True)


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
        # Используем метод CommunityEventsService для правильного архивирования
        from utils.community_events_service import CommunityEventsService

        community_service = CommunityEventsService()
        deleted = community_service.delete_community_event(event_id, chat_id)

        if deleted:
            logger.info(f"✅ Событие {event_id} успешно удалено и заархивировано в events_community_archive")
        else:
            logger.warning(f"⚠️ Не удалось удалить событие {event_id} (возможно, уже удалено)")
            # Пробуем удалить через ORM как fallback
            try:
                await session.delete(event)
                await session.commit()
                logger.info(f"✅ Событие {event_id} удалено через fallback")
            except Exception as fallback_error:
                logger.error(f"❌ Ошибка fallback удаления: {fallback_error}")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления события: {e}")
        await callback.answer("❌ Ошибка удаления события", show_alert=True)
        return

    await callback.answer("✅ Событие удалено!", show_alert=False)
    logger.info(f"🔥 Обновляем список событий после удаления {event_id}")

    # Обновляем список событий
    await group_list_events(callback, bot, session)


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===


async def _get_manageable_community_events(
    session: AsyncSession, chat_id: int, user_id: int, is_admin: bool
) -> list[CommunityEvent]:
    """Получает события, которыми может управлять пользователь (созданные им или все, если админ)"""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    # Получаем активные события и недавно закрытые (в течение 24 часов)
    # Для Community событий starts_at теперь TIMESTAMP WITHOUT TIME ZONE, поэтому убираем timezone
    now_utc = datetime.now(UTC)
    now_naive = now_utc.replace(tzinfo=None)  # Для сравнения с starts_at
    day_ago = datetime.now(UTC) - timedelta(hours=24)

    # Получаем активные события (которые еще не начались)
    stmt = select(CommunityEvent).where(
        CommunityEvent.chat_id == chat_id,
        CommunityEvent.status == "open",
        CommunityEvent.starts_at >= now_naive,  # Событие еще не началось
    )

    if not is_admin:
        # Если не админ, показываем только свои события
        stmt = stmt.where(CommunityEvent.organizer_id == user_id)

    result = await session.execute(stmt)
    active_events = list(result.scalars().all())

    # Получаем недавно закрытые события (в течение 24 часов)
    # Важно: событие должно быть закрыто менее 24 часов назад И еще не началось (starts_at >= now_naive)
    # Если событие уже прошло (starts_at < now_naive), его нельзя возобновить
    closed_stmt = select(CommunityEvent).where(
        CommunityEvent.chat_id == chat_id,
        CommunityEvent.status == "closed",
        CommunityEvent.updated_at >= day_ago,  # Закрыто менее 24 часов назад
        CommunityEvent.starts_at >= now_naive,  # Событие еще не началось (можно возобновить)
    )

    if not is_admin:
        closed_stmt = closed_stmt.where(CommunityEvent.organizer_id == user_id)

    closed_result = await session.execute(closed_stmt)
    closed_events = list(closed_result.scalars().all())

    # Дополнительная фильтрация: исключаем прошедшие события (на случай, если они попали в список)
    now_naive = datetime.now(UTC).replace(tzinfo=None)
    active_events = [e for e in active_events if e.starts_at and e.starts_at >= now_naive]
    closed_events = [e for e in closed_events if e.starts_at and e.starts_at >= now_naive]

    # Объединяем и сортируем по дате начала
    all_events = active_events + closed_events
    # Для Community событий starts_at теперь TIMESTAMP WITHOUT TIME ZONE (naive datetime)
    all_events.sort(key=lambda e: e.starts_at if e.starts_at else datetime.min)

    return all_events


def format_community_event_time(event: CommunityEvent, format_str: str = "%d.%m.%Y %H:%M") -> str:
    """Форматирует время события БЕЗ конвертации - как указал пользователь"""
    if not event.starts_at:
        return "Время не указано"

    import logging

    logger = logging.getLogger(__name__)

    starts_at = event.starts_at

    # Логируем для отладки
    logger.debug(
        f"🕐 Событие {event.id} ({event.title}): "
        f"starts_at={starts_at}, tzinfo={starts_at.tzinfo}, type={type(starts_at)}"
    )

    # Если время с timezone, просто форматируем как есть (БЕЗ конвертации)
    if starts_at.tzinfo is not None:
        # Форматируем время напрямую, без конвертации
        result = starts_at.strftime(format_str)
        logger.debug(f"🕐 Событие {event.id}: результат={result} (без конвертации, timezone={starts_at.tzinfo})")
        return result

    # Если время без timezone (старые события), форматируем как есть
    logger.warning(f"⚠️ Событие {event.id} имеет naive datetime: {starts_at}. Форматируем как есть.")
    result = starts_at.strftime(format_str)
    logger.debug(f"🕐 Событие {event.id}: результат={result}")
    return result


def format_community_event_for_display(event: CommunityEvent) -> str:
    """Форматирует Community событие для отображения в Telegram"""
    lines = []

    # Заголовок
    safe_title = event.title.replace("*", "").replace("_", "").replace("`", "'")
    status_emoji = "🟢" if event.status == "open" else "🔴" if event.status == "closed" else "⚫"
    lines.append(f"{status_emoji} **{safe_title}**")

    # Время (конвертируем из UTC в локальный часовой пояс города)
    if event.starts_at:
        date_str = format_community_event_time(event, "%d.%m.%Y | %H:%M")
        lines.append(f"📅 {date_str}")
    else:
        lines.append("📅 Время не указано")

    # Место
    if event.location_name:
        safe_location = event.location_name.replace("*", "").replace("_", "").replace("`", "'")
        lines.append(f"📍 {safe_location}")

    # Статус
    status_desc = "Активно" if event.status == "open" else "Закрыто" if event.status == "closed" else "Отменено"
    lines.append(f"📊 Статус: {status_desc}")

    # Описание (если есть)
    if event.description:
        desc = event.description[:100] + "..." if len(event.description) > 100 else event.description
        safe_desc = desc.replace("*", "").replace("_", "").replace("`", "'")
        lines.append(f"📄 {safe_desc}")

    return "\n".join(lines)


def get_community_status_buttons(
    event_id: int, current_status: str, updated_at=None, chat_id: int = None, bot_username: str = None
) -> list[dict[str, str]]:
    """Возвращает кнопки для управления Community событием"""
    from datetime import UTC, datetime, timedelta

    buttons = []

    # Кнопки в зависимости от текущего статуса
    if current_status == "open":
        buttons.append({"text": "⛔ Завершить мероприятие", "callback_data": f"group_close_event_{event_id}"})
    elif current_status == "closed":
        # Показываем кнопку "Возобновить" только если событие закрыто менее 24 часов назад
        can_resume = True
        if updated_at:
            day_ago = datetime.now(UTC) - timedelta(hours=24)
            # Если updated_at это datetime без timezone, добавляем UTC
            if updated_at.tzinfo is None:
                updated_at_utc = updated_at.replace(tzinfo=UTC)
            else:
                updated_at_utc = updated_at
            if updated_at_utc < day_ago:
                can_resume = False

        if can_resume:
            buttons.append({"text": "🔄 Возобновить мероприятие", "callback_data": f"group_open_event_{event_id}"})

    # Кнопка просмотра участников
    buttons.append({"text": "👥 Участники", "callback_data": f"community_members_{event_id}"})

    # Кнопка редактирования (всегда доступна) - используем deep-link для прямого перехода
    if chat_id and bot_username:
        edit_link = f"https://t.me/{bot_username}?start=edit_group_{event_id}_{chat_id}"
        buttons.append({"text": "✏️ Редактировать", "url": edit_link})
    else:
        # Fallback на callback_data, если нет данных для deep-link
        buttons.append({"text": "✏️ Редактировать", "callback_data": f"group_edit_event_{event_id}"})

    # Кнопка удаления убрана - для закрытия события используется "Завершить мероприятие"
    # Кнопка "Вернуться к списку" теперь встроена в навигацию, а не отдельная кнопка

    return buttons


def format_event_short(event: CommunityEvent) -> str:
    """Краткое форматирование события для списка"""
    date_str = format_community_event_time(event, "%d.%m %H:%M")
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


# === FSM СОСТОЯНИЯ ДЛЯ РЕДАКТИРОВАНИЯ COMMUNITY СОБЫТИЙ ===
class CommunityEventEditing(StatesGroup):
    choosing_field = State()
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_location = State()
    waiting_for_description = State()


def group_edit_event_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для выбора поля редактирования Community события"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📌 Название", callback_data=f"group_edit_title_{event_id}")],
            [InlineKeyboardButton(text="📅 Дата", callback_data=f"group_edit_date_{event_id}")],
            [InlineKeyboardButton(text="⏰ Время", callback_data=f"group_edit_time_{event_id}")],
            [InlineKeyboardButton(text="📍 Локация", callback_data=f"group_edit_location_{event_id}")],
            [InlineKeyboardButton(text="📝 Описание", callback_data=f"group_edit_description_{event_id}")],
            [InlineKeyboardButton(text="✅ Завершить", callback_data=f"group_edit_finish_{event_id}")],
        ]
    )


async def update_community_event_field(
    session: AsyncSession, event_id: int, field: str, value: str, user_id: int, chat_id: int, is_admin: bool
) -> bool:
    """Обновляет поле Community события в базе данных"""
    try:
        # Проверяем права доступа
        event = await session.get(CommunityEvent, event_id)
        if not event:
            logger.warning(f"Событие {event_id} не найдено")
            return False

        if event.chat_id != chat_id:
            logger.warning(f"Событие {event_id} не принадлежит чату {chat_id}")
            return False

        can_edit = event.organizer_id == user_id or is_admin
        if not can_edit:
            logger.warning(f"Пользователь {user_id} не имеет прав для редактирования события {event_id}")
            return False

        # Обновляем поле
        if field == "title":
            event.title = value
            logger.info(f"Обновлено название события {event_id}: '{value}'")
        elif field == "starts_at":
            # Для Community событий starts_at - это TIMESTAMP WITHOUT TIME ZONE (naive datetime)
            # Парсим дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ
            try:
                # Парсим дату и время (используем глобальный datetime из импортов)
                dt = datetime.strptime(value.strip(), "%d.%m.%Y %H:%M")
                event.starts_at = dt  # Сохраняем как naive datetime
                logger.info(f"Обновлена дата/время события {event_id}: {dt}")
            except ValueError:
                logger.error(f"Неверный формат даты/времени для события {event_id}: {value}")
                return False
        elif field == "location_name":
            event.location_name = value
            logger.info(f"Обновлена локация события {event_id}: '{value}'")
        elif field == "description":
            event.description = value
            logger.info(f"Обновлено описание события {event_id}: '{value}'")
        elif field == "location_url":
            event.location_url = value
            logger.info(f"Обновлен URL локации события {event_id}: '{value}'")
        else:
            logger.error(f"Неизвестное поле для обновления: {field}")
            return False

        # Обновляем updated_at
        event.updated_at = datetime.now(UTC)
        await session.commit()
        logger.info(f"Событие {event_id} успешно обновлено в БД")
        return True

    except Exception as e:
        logger.error(f"Ошибка обновления события {event_id}: {e}")
        await session.rollback()
        return False


@group_router.callback_query(F.data.startswith("group_edit_event_"))
async def group_edit_event(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    """Начало редактирования Community события - перекидывает в основной бот (fallback для старых кнопок)"""
    # Этот обработчик теперь используется только как fallback, если кнопка не была обновлена
    # Обычно кнопка "Редактировать" теперь использует deep-link напрямую
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    # Извлекаем ID события из callback_data
    try:
        event_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌ Неверный ID события", show_alert=True)
        return

    logger.info(f"🔥 group_edit_event: пользователь {user_id} запрашивает редактирование события {event_id} (fallback)")

    # Проверяем права доступа
    is_admin = await is_chat_admin(bot, chat_id, user_id)
    event = await session.get(CommunityEvent, event_id)

    if not event or event.chat_id != chat_id:
        await callback.answer("❌ Событие не найдено", show_alert=True)
        return

    can_edit = event.organizer_id == user_id or is_admin
    if not can_edit:
        await callback.answer("❌ У вас нет прав для редактирования этого события", show_alert=True)
        return

    # Получаем username бота для deep-link
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "EventAroundBot"

    # Создаем deep-link для редактирования в основном боте
    edit_link = f"https://t.me/{bot_username}?start=edit_group_{event_id}_{chat_id}"

    # Просто отвечаем и перекидываем через deep-link
    await callback.answer("Переход в приватный чат...", show_alert=False)
    # Отправляем сообщение с кнопкой для перехода (на случай, если deep-link не сработал)
    await callback.message.answer(
        "✏️ Для редактирования перейдите в приватный чат:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✏️ Редактировать событие", url=edit_link)]]
        ),
    )


# === ОБРАБОТЧИКИ ВЫБОРА ПОЛЕЙ ДЛЯ РЕДАКТИРОВАНИЯ ===
@group_router.callback_query(F.data.startswith("group_edit_title_"))
async def group_edit_title_choice(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Выбор редактирования названия"""
    event_id = int(callback.data.split("_")[-1])
    chat_id = callback.message.chat.id
    await state.update_data(event_id=event_id)
    await state.set_state(CommunityEventEditing.waiting_for_title)

    # Удаляем предыдущее меню редактирования, если есть
    data = await state.get_data()
    last_menu_msg_id = data.get("last_menu_msg_id")
    if last_menu_msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=last_menu_msg_id)
        except Exception:
            pass

    # Отправляем запрос и сохраняем его ID
    prompt_msg = await callback.message.answer("✍️ Введите новое название события:")
    await state.update_data(prompt_msg_id=prompt_msg.message_id)
    await callback.answer()


@group_router.callback_query(F.data.startswith("group_edit_date_"))
async def group_edit_date_choice(callback: CallbackQuery, state: FSMContext):
    """Выбор редактирования даты"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)
    await state.set_state(CommunityEventEditing.waiting_for_date)
    await callback.message.answer("📅 Введите новую дату в формате ДД.ММ.ГГГГ:")
    await callback.answer()


@group_router.callback_query(F.data.startswith("group_edit_time_"))
async def group_edit_time_choice(callback: CallbackQuery, state: FSMContext):
    """Выбор редактирования времени"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)
    await state.set_state(CommunityEventEditing.waiting_for_time)
    await callback.message.answer("⏰ Введите новое время в формате ЧЧ:ММ:")
    await callback.answer()


@group_router.callback_query(F.data.startswith("group_edit_location_"))
async def group_edit_location_choice(callback: CallbackQuery, state: FSMContext):
    """Выбор редактирования локации"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)
    await state.set_state(CommunityEventEditing.waiting_for_location)
    await callback.message.answer(
        "📍 Введите новую локацию:\n" "• Название места\n" "• Ссылка Google Maps\n" "• Координаты (широта, долгота)"
    )
    await callback.answer()


@group_router.callback_query(F.data.startswith("group_edit_description_"))
async def group_edit_description_choice(callback: CallbackQuery, state: FSMContext):
    """Выбор редактирования описания"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)
    await state.set_state(CommunityEventEditing.waiting_for_description)
    await callback.message.answer("📝 Введите новое описание:")
    await callback.answer()


@group_router.callback_query(F.data.startswith("group_edit_finish_"))
async def group_edit_finish(callback: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """Завершение редактирования Community события"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = callback.from_user.id
    is_admin = data.get("is_admin", False)

    if event_id and chat_id:
        # Получаем список всех событий для навигации
        manageable_events = await _get_manageable_community_events(session, chat_id, user_id, is_admin)
        # Находим индекс обновленного события
        event_index = next((i for i, e in enumerate(manageable_events) if e.id == event_id), None)

        if event_index is not None:
            # Показываем событие через _show_community_manage_event с навигацией
            await _show_community_manage_event(
                callback, bot, session, manageable_events, event_index, chat_id, user_id, is_admin
            )
            await callback.answer("✅ Событие обновлено!")
        else:
            # Если событие не найдено, получаем его напрямую
            event = await session.get(CommunityEvent, event_id)
            if event and event.chat_id == chat_id:
                text = f"✅ **Событие обновлено!**\n\n{format_community_event_for_display(event)}"
                # Получаем username бота для deep-link
                bot_info = await bot.get_me()
                bot_username = bot_info.username or "EventAroundBot"
                buttons = get_community_status_buttons(event.id, event.status, event.updated_at, chat_id, bot_username)
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=btn["text"],
                                callback_data=btn.get("callback_data"),
                                url=btn.get("url"),
                            )
                        ]
                        for btn in buttons
                    ]
                )
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
                await callback.answer("✅ Событие обновлено!")
            else:
                await callback.answer("❌ Событие не найдено")

    await state.clear()


# === ОБРАБОТЧИКИ ВВОДА ДАННЫХ ДЛЯ РЕДАКТИРОВАНИЯ ===
@group_router.message(CommunityEventEditing.waiting_for_title)
async def group_handle_title_input(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """Обработка ввода нового названия"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    is_admin = data.get("is_admin", False)

    if event_id and message.text:
        success = await update_community_event_field(
            session, event_id, "title", message.text.strip(), user_id, chat_id, is_admin
        )
        if success:
            # Удаляем сообщение с запросом и сообщение пользователя
            prompt_msg_id = data.get("prompt_msg_id")
            if prompt_msg_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=prompt_msg_id)
                except Exception:
                    pass
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            except Exception:
                pass

            # Отправляем подтверждение и меню
            confirm_msg = await message.answer("✅ Название обновлено!")
            keyboard = group_edit_event_keyboard(event_id)
            menu_msg = await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)

            # Сохраняем ID сообщений для последующего удаления
            await state.update_data(
                last_confirm_msg_id=confirm_msg.message_id,
                last_menu_msg_id=menu_msg.message_id,
            )
            await state.set_state(CommunityEventEditing.choosing_field)
        else:
            await message.answer("❌ Ошибка при обновлении названия")
    else:
        await message.answer("❌ Введите корректное название")


@group_router.message(CommunityEventEditing.waiting_for_date)
async def group_handle_date_input(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """Обработка ввода новой даты"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    is_admin = data.get("is_admin", False)

    if event_id and message.text:
        # Получаем текущее событие для получения времени
        event = await session.get(CommunityEvent, event_id)
        if event and event.starts_at:
            # Сохраняем текущее время и обновляем только дату
            current_time = event.starts_at.strftime("%H:%M")
            new_datetime = f"{message.text.strip()} {current_time}"
            success = await update_community_event_field(
                session, event_id, "starts_at", new_datetime, user_id, chat_id, is_admin
            )
        else:
            # Если нет текущей даты, используем введенную дату с временем по умолчанию
            new_datetime = f"{message.text.strip()} 12:00"
            success = await update_community_event_field(
                session, event_id, "starts_at", new_datetime, user_id, chat_id, is_admin
            )

        if success:
            await message.answer("✅ Дата обновлена!")
            keyboard = group_edit_event_keyboard(event_id)
            await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
            await state.set_state(CommunityEventEditing.choosing_field)
        else:
            await message.answer("❌ Ошибка при обновлении даты. Проверьте формат (ДД.ММ.ГГГГ)")
    else:
        await message.answer("❌ Введите корректную дату")


@group_router.message(CommunityEventEditing.waiting_for_time)
async def group_handle_time_input(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """Обработка ввода нового времени"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    is_admin = data.get("is_admin", False)

    if event_id and message.text:
        # Получаем текущее событие для получения даты
        event = await session.get(CommunityEvent, event_id)
        if event and event.starts_at:
            # Сохраняем текущую дату и обновляем только время
            current_date = event.starts_at.strftime("%d.%m.%Y")
            new_datetime = f"{current_date} {message.text.strip()}"
            success = await update_community_event_field(
                session, event_id, "starts_at", new_datetime, user_id, chat_id, is_admin
            )
        else:
            # Если нет текущей даты, используем сегодняшнюю
            today = datetime.now().strftime("%d.%m.%Y")
            new_datetime = f"{today} {message.text.strip()}"
            success = await update_community_event_field(
                session, event_id, "starts_at", new_datetime, user_id, chat_id, is_admin
            )

        if success:
            await message.answer("✅ Время обновлено!")
            keyboard = group_edit_event_keyboard(event_id)
            await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
            await state.set_state(CommunityEventEditing.choosing_field)
        else:
            await message.answer("❌ Ошибка при обновлении времени. Проверьте формат (ЧЧ:ММ)")
    else:
        await message.answer("❌ Введите корректное время")


@group_router.message(CommunityEventEditing.waiting_for_location)
async def group_handle_location_input(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """Обработка ввода новой локации"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    is_admin = data.get("is_admin", False)

    if not event_id or not message.text:
        await message.answer("❌ Введите корректную локацию")
        return

    location_input = message.text.strip()
    logger.info(f"group_handle_location_input: редактирование локации для события {event_id}, ввод: {location_input}")

    # Проверяем, является ли это Google Maps ссылкой
    if any(domain in location_input.lower() for domain in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl"]):
        # Парсим ссылку Google Maps
        from utils.geo_utils import parse_google_maps_link

        location_data = await parse_google_maps_link(location_input)

        if location_data:
            # Обновляем событие с данными из ссылки
            success = await update_community_event_field(
                session,
                event_id,
                "location_name",
                location_data.get("name", "Место на карте"),
                user_id,
                chat_id,
                is_admin,
            )
            if success:
                # Обновляем URL
                await update_community_event_field(
                    session, event_id, "location_url", location_input, user_id, chat_id, is_admin
                )
                await message.answer(
                    f"✅ Локация обновлена: *{location_data.get('name', 'Место на карте')}*", parse_mode="Markdown"
                )
            else:
                await message.answer("❌ Ошибка при обновлении локации")
        else:
            await message.answer(
                "❌ Не удалось распознать ссылку Google Maps.\n\n"
                "Попробуйте:\n"
                "• Скопировать ссылку из приложения Google Maps\n"
                "• Или ввести координаты в формате: широта, долгота"
            )

    # Проверяем, являются ли это координаты (широта, долгота)
    elif "," in location_input and len(location_input.split(",")) == 2:
        try:
            lat_str, lng_str = location_input.split(",")
            lat = float(lat_str.strip())
            lng = float(lng_str.strip())

            # Проверяем валидность координат
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                # Обновляем событие с координатами
                success = await update_community_event_field(
                    session, event_id, "location_name", "Место по координатам", user_id, chat_id, is_admin
                )
                if success:
                    await update_community_event_field(
                        session, event_id, "location_url", location_input, user_id, chat_id, is_admin
                    )
                    await message.answer(f"✅ Локация обновлена: *{lat:.6f}, {lng:.6f}*", parse_mode="Markdown")
                else:
                    await message.answer("❌ Ошибка при обновлении локации")
            else:
                await message.answer("❌ Координаты вне допустимого диапазона")
        except ValueError:
            await message.answer("❌ Неверный формат координат. Используйте: широта, долгота")

    else:
        # Обычный текст - обновляем только название
        success = await update_community_event_field(
            session, event_id, "location_name", location_input, user_id, chat_id, is_admin
        )
        if success:
            await message.answer(f"✅ Локация обновлена: *{location_input}*", parse_mode="Markdown")
        else:
            await message.answer("❌ Ошибка при обновлении локации")

    # Возвращаемся к меню редактирования
    keyboard = group_edit_event_keyboard(event_id)
    await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
    await state.set_state(CommunityEventEditing.choosing_field)


@group_router.message(CommunityEventEditing.waiting_for_description)
async def group_handle_description_input(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """Обработка ввода нового описания"""
    description = message.text.strip()
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    is_admin = data.get("is_admin", False)

    # Защита от спама - запрет ссылок и подозрительного контента в описании
    spam_indicators = [
        "/",
        "http",
        "www.",
        ".com",
        ".ru",
        ".org",
        ".net",
        "telegram.me",
        "t.me",
        "@",
        "tg://",
        "bit.ly",
        "goo.gl",
    ]

    description_lower = description.lower()
    if any(indicator in description_lower for indicator in spam_indicators):
        await message.answer(
            "❌ В описании нельзя указывать ссылки и контакты!\n\n"
            "📝 Пожалуйста, опишите событие своими словами:\n"
            "• Что будет происходить\n"
            "• Кому будет интересно\n"
            "• Что взять с собой\n\n"
            "Контакты можно указать после создания события."
        )
        return

    if event_id and description:
        success = await update_community_event_field(
            session, event_id, "description", description, user_id, chat_id, is_admin
        )
        if success:
            await message.answer("✅ Описание обновлено!")
            keyboard = group_edit_event_keyboard(event_id)
            await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
            await state.set_state(CommunityEventEditing.choosing_field)
        else:
            await message.answer("❌ Ошибка при обновлении описания")
    else:
        await message.answer("❌ Введите корректное описание")
