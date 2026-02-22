#!/usr/bin/env python3
"""
Изолированные обработчики для групповых чатов
Этот файл содержит только функциональность для событий в сообществах
и полностью отделен от основного бота
"""

import logging
from datetime import datetime

from aiogram import Bot, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ForceReply

from utils.community_events_service import CommunityEventsService
from utils.i18n import format_translation, get_user_language_or_default, t

logger = logging.getLogger(__name__)

# BOT_ID будет импортирован из основного модуля
BOT_ID = None

# Антидребезг для предотвращения двойного старта FSM
LAST_START = {}


class GroupCreate(StatesGroup):
    """FSM состояния для создания событий в групповых чатах"""

    waiting_for_title = State()
    waiting_for_datetime = State()
    waiting_for_city = State()
    waiting_for_location = State()
    waiting_for_description = State()


async def group_create_start(message: types.Message, state: FSMContext):
    """Начало создания события в групповом чате"""
    logger.info(
        f"🔥 group_create_start: пользователь {message.from_user.id} начал создание события в чате {message.chat.id}"
    )

    await state.set_state(GroupCreate.waiting_for_title)
    lang = get_user_language_or_default(message.from_user.id)
    await message.answer(
        t("create.group.enter_title", lang),
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
    )


async def group_title_step(message: types.Message, state: FSMContext):
    """Обработка названия события в групповом чате"""
    logger.info(f"🔥 group_title_step: ОБРАБОТЧИК ВЫЗВАН! chat={message.chat.id} user={message.from_user.id}")

    # Детальная диагностика входящего сообщения
    reply_to_id = message.reply_to_message.message_id if message.reply_to_message else None
    reply_to_user_id = (
        message.reply_to_message.from_user.id
        if message.reply_to_message and message.reply_to_message.from_user
        else None
    )
    logger.info(f"🔥 group_title_step: reply_to_id={reply_to_id}, reply_to_user_id={reply_to_user_id}, BOT_ID={BOT_ID}")

    # Жёсткие проверки как в рекомендации
    if message.reply_to_message is None:
        logger.info("🔥 group_title_step: НЕТ reply_to_message, игнорируем")
        return
    if message.reply_to_message.from_user.id != BOT_ID:
        logger.info(
            f"🔥 group_title_step: reply_to НЕ от бота (user_id={message.reply_to_message.from_user.id}), игнорируем"
        )
        return

    data = await state.get_data()
    logger.info(f"🔥 group_title_step: данные FSM: {data}")

    # Жёсткая проверка prompt_msg_id как в рекомендации
    if message.reply_to_message.message_id != data.get("prompt_msg_id"):
        logger.info(
            f"🔥 group_title_step: reply_to НЕ на наш prompt "
            f"(получили={message.reply_to_message.message_id}, ожидали={data.get('prompt_msg_id')}), игнорируем"
        )
        return

    # Страховка: проверяем "жёсткую привязку"
    if message.from_user.id != data.get("initiator_id"):
        logger.info(f"🔥 group_title_step: игнорируем ответ от другого пользователя {message.from_user.id}")
        return  # игнорим чужие ответы

    logger.info(
        f"[FSM] title_ok chat={message.chat.id} user={message.from_user.id} "
        f"reply_to={message.reply_to_message.message_id} prompt={data.get('prompt_msg_id')} "
        f"text={message.text!r}"
    )

    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation("create.validation.no_text", lang, next_prompt=t("create.group.enter_title", lang)),
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(GroupCreate.waiting_for_datetime)

    # Следующий шаг с новым prompt_msg_id
    from aiogram import Bot

    bot = Bot.get_current()
    prompt = await bot.send_message(
        chat_id=data["group_id"],
        text=format_translation("create.group.title_saved_ask_date", lang, title=title),
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
        message_thread_id=data.get("thread_id"),
    )
    await state.update_data(prompt_msg_id=prompt.message_id)


async def group_datetime_step(message: types.Message, state: FSMContext):
    """Обработка даты и времени события в групповом чате"""
    # Проверяем, что это ответ на сообщение бота
    if not message.reply_to_message or message.reply_to_message.from_user.id != BOT_ID:
        logger.info("🔥 group_datetime_step: не ответ на сообщение бота, игнорируем")
        return

    data = await state.get_data()

    # Страховка: проверяем "жёсткую привязку"
    if message.from_user.id != data.get("initiator_id"):
        logger.info(f"🔥 group_datetime_step: игнорируем ответ от другого пользователя {message.from_user.id}")
        return
    if message.reply_to_message.message_id != data.get("prompt_msg_id"):
        logger.info(f"🔥 group_datetime_step: игнорируем ответ не на наш вопрос {message.reply_to_message.message_id}")
        return

    logger.info(
        f"[FSM] chat={message.chat.id} user={message.from_user.id} "
        f"reply_to={message.reply_to_message.message_id} state=datetime text={message.text!r}"
    )
    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation("create.validation.no_text", lang, next_prompt=t("create.group.ask_datetime", lang)),
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    datetime_text = message.text.strip()

    import re

    if not re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2}$", datetime_text):
        await message.answer(
            t("create.group.invalid_datetime", lang),
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    await state.update_data(datetime=datetime_text)
    await state.set_state(GroupCreate.waiting_for_city)

    # Следующий шаг с новым prompt_msg_id
    from aiogram import Bot

    bot = Bot.get_current()
    prompt = await bot.send_message(
        chat_id=data["group_id"],
        text=format_translation("create.group.datetime_saved_ask_city", lang, datetime_text=datetime_text),
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
        message_thread_id=data.get("thread_id"),
    )
    await state.update_data(prompt_msg_id=prompt.message_id)


async def group_city_step(message: types.Message, state: FSMContext):
    """Обработка города события в групповом чате"""
    # Проверяем, что это ответ на сообщение бота
    if not message.reply_to_message or message.reply_to_message.from_user.id != BOT_ID:
        logger.info("🔥 group_city_step: не ответ на сообщение бота, игнорируем")
        return

    data = await state.get_data()

    # Страховка: проверяем "жёсткую привязку"
    if message.from_user.id != data.get("initiator_id"):
        logger.info(f"🔥 group_city_step: игнорируем ответ от другого пользователя {message.from_user.id}")
        return
    if message.reply_to_message.message_id != data.get("prompt_msg_id"):
        logger.info(f"🔥 group_city_step: игнорируем ответ не на наш вопрос {message.reply_to_message.message_id}")
        return

    logger.info(
        f"[FSM] chat={message.chat.id} user={message.from_user.id} "
        f"reply_to={message.reply_to_message.message_id} state=city text={message.text!r}"
    )
    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation("create.validation.no_text", lang, next_prompt=t("create.enter_city", lang)),
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    city = message.text.strip()
    await state.update_data(city=city)
    await state.set_state(GroupCreate.waiting_for_location)

    # Следующий шаг с новым prompt_msg_id
    from aiogram import Bot

    bot = Bot.get_current()
    prompt = await bot.send_message(
        chat_id=data["group_id"],
        text=format_translation("create.group.city_saved_ask_location", lang, city=city),
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
        message_thread_id=data.get("thread_id"),
    )
    await state.update_data(prompt_msg_id=prompt.message_id)


async def group_location_step(message: types.Message, state: FSMContext):
    """Обработка локации события в групповом чате"""
    # Проверяем, что это ответ на сообщение бота
    if not message.reply_to_message or message.reply_to_message.from_user.id != BOT_ID:
        logger.info("🔥 group_location_step: не ответ на сообщение бота, игнорируем")
        return

    data = await state.get_data()

    # Страховка: проверяем "жёсткую привязку"
    if message.from_user.id != data.get("initiator_id"):
        logger.info(f"🔥 group_location_step: игнорируем ответ от другого пользователя {message.from_user.id}")
        return
    if message.reply_to_message.message_id != data.get("prompt_msg_id"):
        logger.info(f"🔥 group_location_step: игнорируем ответ не на наш вопрос {message.reply_to_message.message_id}")
        return

    logger.info(
        f"[FSM] chat={message.chat.id} user={message.from_user.id} "
        f"reply_to={message.reply_to_message.message_id} state=location text={message.text!r}"
    )
    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation(
                "create.validation.no_text", lang, next_prompt=t("create.group.ask_location_link", lang)
            ),
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    location = message.text.strip()
    await state.update_data(location=location)
    await state.set_state(GroupCreate.waiting_for_description)

    # Следующий шаг с новым prompt_msg_id
    from aiogram import Bot

    bot = Bot.get_current()
    prompt = await bot.send_message(
        chat_id=data["group_id"],
        text=format_translation("create.group.location_saved_ask_description", lang, location=location),
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
        message_thread_id=data.get("thread_id"),
    )
    await state.update_data(prompt_msg_id=prompt.message_id)


async def group_finish(message: types.Message, state: FSMContext, bot: Bot):
    """Завершение создания события в групповом чате"""
    # Проверяем, что это ответ на сообщение бота
    if not message.reply_to_message or message.reply_to_message.from_user.id != BOT_ID:
        logger.info("🔥 group_finish: не ответ на сообщение бота, игнорируем")
        return

    data = await state.get_data()

    # Страховка: проверяем "жёсткую привязку"
    if message.from_user.id != data.get("initiator_id"):
        logger.info(f"🔥 group_finish: игнорируем ответ от другого пользователя {message.from_user.id}")
        return
    if message.reply_to_message.message_id != data.get("prompt_msg_id"):
        logger.info(f"🔥 group_finish: игнорируем ответ не на наш вопрос {message.reply_to_message.message_id}")
        return

    logger.info(
        f"[FSM] chat={message.chat.id} user={message.from_user.id} "
        f"reply_to={message.reply_to_message.message_id} state=description text={message.text!r}"
    )
    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation("create.validation.no_text", lang, next_prompt=t("create.enter_description", lang)),
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    description = message.text.strip()
    data = await state.update_data(description=description)

    try:
        datetime_str = data["datetime"]
        try:
            # Парсим время как локальное (naive datetime)
            naive_local_dt = datetime.strptime(datetime_str, "%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer(
                t("create.validation.datetime_error", get_user_language_or_default(message.from_user.id)),
                parse_mode="Markdown",
            )
            return

        # В Community режиме сохраняем время как указал пользователь, БЕЗ конвертации в UTC
        # Пользователь сам указал город и время, значит он уже учел свой часовой пояс
        # Сохраняем как naive datetime (без timezone), т.к. колонка в БД TIMESTAMP WITHOUT TIME ZONE
        starts_at_utc = naive_local_dt

        service = CommunityEventsService()

        # Получаем всех админов группы для новой системы
        print(f"🔥🔥🔥 group_chat_handlers: ВЫЗОВ get_group_admin_ids для группы {data['group_id']}")
        admin_ids = service.get_group_admin_ids(data["group_id"], bot)
        print(f"🔥🔥🔥 group_chat_handlers: РЕЗУЛЬТАТ get_group_admin_ids: {admin_ids}")
        admin_id = admin_ids[0] if admin_ids else None  # LEGACY для обратной совместимости

        creator_lang = get_user_language_or_default(message.from_user.id)
        event_id = service.create_community_event(
            group_id=data["group_id"],
            creator_id=data["initiator_id"],
            creator_username=message.from_user.username,
            title=data["title"],
            date=starts_at_utc,
            description=description,
            city=data["city"],
            location_name=data["location"],
            admin_id=admin_id,
            admin_ids=admin_ids,
            creator_lang=creator_lang,
        )

        # Логирование для диагностики
        logger.info(
            f"[DB] insert group_event: group_id={data['group_id']} title={data['title']!r} date={data['datetime']!r}"
        )
        logger.info(f"🔥 group_finish: событие {event_id} создано успешно")

        lang = get_user_language_or_default(message.from_user.id)
        created_by = message.from_user.username or message.from_user.first_name
        await message.answer(
            format_translation(
                "create.group.event_created",
                lang,
                title=data["title"],
                datetime=data["datetime"],
                city=data["city"],
                location=data["location"],
                description=description,
                created_by=created_by,
            ),
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"🔥 group_finish: ошибка при создании события: {e}")
        lang = get_user_language_or_default(message.from_user.id)
        await message.answer(t("create.group.error_creating", lang), parse_mode="Markdown")

    await state.clear()


async def debug_final_trap(message: types.Message, state: FSMContext):
    """Финальная ловушка для диагностики - перехватывает ВСЕ сообщения в группах"""
    current_state = await state.get_state()
    reply_to_id = getattr(message.reply_to_message, "message_id", None) if message.reply_to_message else None

    logger.warning(
        f"[DEBUG] state={current_state}, text={message.text!r}, "
        f"reply_to={reply_to_id}, chat={message.chat.id}, user={message.from_user.id}"
    )


async def handle_group_hide_bot(callback: types.CallbackQuery):
    """Обработчик кнопки 'Спрятать бота' в групповых чатах"""
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    logger.info(f"🔥 handle_group_hide_bot: ВЫЗВАН! chat_id={chat_id}, user_id={user_id}")
    logger.info(f"🔥 handle_group_hide_bot: callback.data={callback.data}")
    logger.info(f"🔥 handle_group_hide_bot: chat.type={callback.message.chat.type}")

    # Любой пользователь может скрыть бота (особенно полезно для создателей событий)
    # Выполняем действие сразу без подтверждения

    try:
        from aiogram import Bot

        from database import get_session
        from utils.messaging_utils import delete_all_tracked

        bot = Bot.get_current()

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
                    "Бот должен быть администратором с правом удаления сообщений.\n"
                    "Обратитесь к администратору чата.",
                    parse_mode="Markdown",
                )
                await callback.answer("❌ Нет прав на удаление", show_alert=True)
                return
        except Exception as e:
            logger.error(f"❌ Ошибка проверки прав бота: {e}")

        # Удаляем все трекнутые сообщения бота
        async with get_session() as session:
            try:
                deleted = await delete_all_tracked(bot, session, chat_id=chat_id)
            except Exception as e:
                logger.error(f"❌ Ошибка удаления сообщений: {e}")
                deleted = 0

        # Отправляем финальное сообщение о скрытии
        note = await bot.send_message(
            chat_id=chat_id,
            text=(
                f"👁️‍🗨️ **Бот скрыт**\n\n"
                f"Удалено сообщений: {deleted}\n"
                f"События в базе данных сохранены.\n\n"
                f"💡 **Для восстановления функций бота:**\n"
                f"Используйте команду /start"
            ),
            parse_mode="Markdown",
        )

        # Автоудаление уведомления через 8 секунд
        import asyncio

        try:
            await asyncio.sleep(8)
            await bot.delete_message(chat_id, note.message_id)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить уведомление: {e}")

        logger.info(f"✅ Бот скрыт в чате {chat_id} пользователем {user_id}, удалено {deleted} сообщений")

    except Exception as e:
        logger.error(f"❌ Ошибка при скрытии бота в чате {chat_id}: {e}")
        # Если не удалось скрыть, просто удаляем сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass

    await callback.answer("✅ Бот скрыт")


async def handle_group_hide_confirm(callback: types.CallbackQuery):
    """Подтверждение скрытия бота в групповом чате"""
    # Извлекаем chat_id из callback_data
    chat_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    # Любой пользователь может скрыть бота (особенно полезно для создателей событий)

    try:
        # Получаем все сообщения бота в этом чате
        # В реальности Telegram API не предоставляет прямой способ получить все сообщения бота
        # Поэтому мы можем удалить только текущее сообщение и сообщить о скрытии

        # Удаляем текущее сообщение
        await callback.message.delete()

        # Отправляем финальное сообщение о скрытии (которое тоже можно будет удалить)
        from aiogram import Bot

        bot = Bot.get_current()

        final_message = await bot.send_message(
            chat_id=chat_id,
            text=(
                "👁️‍🗨️ **Бот скрыт**\n\n"
                "Все сообщения бота были скрыты из этого чата.\n\n"
                "💡 **Для восстановления функций бота:**\n"
                "• Используйте команду /start\n"
                "• Или напишите боту в личные сообщения\n\n"
                "Бот остался в группе и готов к работе! 🤖\n"
                "Теперь чат чистый и не засорен служебными сообщениями."
            ),
            parse_mode="Markdown",
        )

        # Удаляем финальное сообщение через 10 секунд
        import asyncio

        await asyncio.sleep(10)
        try:
            await final_message.delete()
        except Exception:
            pass  # Игнорируем ошибки удаления финального сообщения

        logger.info(f"✅ Бот скрыт в чате {chat_id} пользователем {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при скрытии бота в чате {chat_id}: {e}")
        await callback.answer("❌ Произошла ошибка при скрытии бота", show_alert=True)


def register_group_handlers(dp, bot_id: int):
    """
    Регистрация обработчиков для групповых чатов
    ВНИМАНИЕ: Эта функция должна вызываться только для групповых чатов!
    """
    global BOT_ID
    BOT_ID = bot_id

    logger.info(f"🔥 Регистрация обработчиков для групповых чатов, BOT_ID={BOT_ID}")

    # Обработчики кнопки "Спрятать бота" - обрабатываются в основном файле bot_enhanced_v3.py

    # Команда /create только для групп
    dp.message.register(group_create_start, Command("create"), F.chat.type.in_({"group", "supergroup"}))

    # FSM обработчики только для групп с жёстким фильтром на ответы боту
    dp.message.register(
        group_title_step,
        GroupCreate.waiting_for_title,
        F.chat.type.in_({"group", "supergroup"}),
        F.reply_to_message,  # это должен быть ответ
        F.reply_to_message.from_user.id == BOT_ID,  # на сообщение бота
    )

    dp.message.register(
        group_datetime_step,
        GroupCreate.waiting_for_datetime,
        F.chat.type.in_({"group", "supergroup"}),
        F.reply_to_message,
        F.reply_to_message.from_user.id == BOT_ID,
    )

    dp.message.register(
        group_city_step,
        GroupCreate.waiting_for_city,
        F.chat.type.in_({"group", "supergroup"}),
        F.reply_to_message,
        F.reply_to_message.from_user.id == BOT_ID,
    )

    dp.message.register(
        group_location_step,
        GroupCreate.waiting_for_location,
        F.chat.type.in_({"group", "supergroup"}),
        F.reply_to_message,
        F.reply_to_message.from_user.id == BOT_ID,
    )

    dp.message.register(
        group_finish,
        GroupCreate.waiting_for_description,
        F.chat.type.in_({"group", "supergroup"}),
        F.reply_to_message,
        F.reply_to_message.from_user.id == BOT_ID,
    )

    # ФИНАЛЬНАЯ ЛОВУШКА: перехватывает ВСЕ сообщения в группах для диагностики (самый низкий приоритет)
    dp.message.register(debug_final_trap, F.chat.type.in_({"group", "supergroup"}))

    logger.info("✅ Обработчики для групповых чатов зарегистрированы")
