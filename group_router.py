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
from datetime import UTC, datetime

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
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
                [InlineKeyboardButton(text='🚀 Расширенная версия "World"', url="https://t.me/EventAroundBot")],
                [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_execute")],
            ]
        )

        # Отправляем панель Community с трекированием (автоудаление через 4 минуты)
        try:
            from utils.messaging_utils import send_tracked

            panel_text = (
                '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
                "🎯 Что умею:\n\n"
                "• Создавать события участников чата\n"
                "• Показывать события этого чата\n"
                '• Переводить в полный бот - версия "World"\n\n'
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
                    "• Создавать события участников чата\n"
                    "• Показывать события этого чата\n"
                    '• Переводить в полный бот - версия "World"\n\n'
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
    '• Переводить в полный бот - версия "World"\n\n'
    "💡 Выберите действие:"
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

    logger.info(
        f"🔥 group_list_events_page: запрос списка событий в чате {chat_id}, страница {page}, thread_id={thread_id}"
    )

    await callback.answer()  # Тост, не спамим

    try:
        # Получаем будущие события этого чата

        from sqlalchemy import func, select

        # Важно: показываем ВСЕ будущие события (даже через неделю или год),
        # но НЕ показываем прошедшие события (starts_at >= NOW())
        # Это гарантирует, что события, у которых день уже прошел, не отображаются
        now_utc = datetime.now(UTC)

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
                # Форматируем дату
                date_str = event.starts_at.strftime("%d.%m.%Y %H:%M")

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
            await callback.message.edit_text(text, reply_markup=back_kb, parse_mode="Markdown")
            logger.info("✅ Список событий успешно обновлен")
        except Exception as e:
            logger.error(f"❌ Ошибка редактирования сообщения: {e}")

            # Специальная обработка для ошибки "сообщение не изменено"
            if "message is not modified" in str(e).lower():
                logger.info("🔥 Сообщение не изменилось, отправляем новое сообщение")
                try:
                    answer_kwargs = {"reply_markup": back_kb, "parse_mode": "Markdown"}
                    if is_forum and thread_id:
                        answer_kwargs["message_thread_id"] = thread_id
                    await callback.message.answer(text, **answer_kwargs)
                    logger.info("✅ Новое сообщение со списком событий отправлено")
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
    is_forum = getattr(callback.message.chat, "is_forum", False)
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

    # Короткое уведомление о результате (не трекаем, чтобы не гоняться за ним)
    send_kwargs = {
        "text": f"👁️‍🗨️ **Бот скрыт**\n\n"
        f"✅ Удалено сообщений бота: {deleted}\n"
        f"✅ Команды /start автоматически удаляются\n"
        f"✅ События в базе данных сохранены\n\n"
        f"💡 **Для восстановления функций бота:**\n"
        f"Используйте команду /start",
        "parse_mode": "Markdown",
    }
    if is_forum and thread_id:
        send_kwargs["message_thread_id"] = thread_id
    note = await bot.send_message(chat_id, **send_kwargs)

    # ВОССТАНАВЛИВАЕМ КОМАНДЫ ПОСЛЕ СКРЫТИЯ БОТА (НАДЕЖНО)
    await ensure_group_start_command(bot, chat_id)

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

    # Получаем thread_id для форумов
    is_forum = getattr(callback.message.chat, "is_forum", False)
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
        deleted = await delete_all_tracked(bot, session, chat_id=chat_id)
    except Exception as e:
        logger.error(f"❌ Ошибка удаления сообщений: {e}")
        deleted = 0

    # Короткое уведомление о результате (не трекаем, чтобы не гоняться за ним)
    send_kwargs = {
        "text": f"👁️‍🗨️ **Бот скрыт**\n\n"
        f"Удалено сообщений: {deleted}\n"
        f"События в базе данных сохранены.\n\n"
        f"Для восстановления панели используйте /start",
        "parse_mode": "Markdown",
    }
    if is_forum and thread_id:
        send_kwargs["message_thread_id"] = thread_id
    note = await bot.send_message(chat_id, **send_kwargs)

    # ВОССТАНАВЛИВАЕМ КОМАНДЫ ПОСЛЕ СКРЫТИЯ БОТА (НАДЕЖНО)
    await ensure_group_start_command(bot, chat_id)

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
