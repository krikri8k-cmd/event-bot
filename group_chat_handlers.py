#!/usr/bin/env python3
"""
Изолированные обработчики для групповых чатов
Этот файл содержит только функциональность для событий в сообществах
и полностью отделен от основного бота
"""

import logging
from datetime import datetime

from aiogram import F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ForceReply

from utils.community_events_service import CommunityEventsService

logger = logging.getLogger(__name__)

# BOT_ID будет импортирован из основного модуля
BOT_ID = None


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
    await message.answer(
        "✍️ **Введите название мероприятия:**", parse_mode="Markdown", reply_markup=ForceReply(selective=True)
    )


async def group_title_step(message: types.Message, state: FSMContext):
    """Обработка названия события в групповом чате"""
    logger.info(
        f"🔥 group_title_step: получено название '{message.text}' "
        f"от пользователя {message.from_user.id} в чате {message.chat.id} "
        f"thread_id={message.message_thread_id}"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n" "✍️ **Введите название мероприятия:**",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    title = message.text.strip()
    await state.update_data(
        title=title, group_id=message.chat.id, thread_id=message.message_thread_id, creator_id=message.from_user.id
    )
    await state.set_state(GroupCreate.waiting_for_date)

    await message.answer(
        f"**Название сохранено:** *{title}* ✅\n\n" "📅 **Укажите дату** (например: 10.10.2025 18:00):",
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
    )


async def group_datetime_step(message: types.Message, state: FSMContext):
    """Обработка даты и времени события в групповом чате"""
    logger.info(
        f"🔥 group_datetime_step: получена дата '{message.text}' "
        f"от пользователя {message.from_user.id} в чате {message.chat.id}"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n"
            "📅 **Укажите дату и время** (например: 10.10.2025 18:00):",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    datetime_text = message.text.strip()

    import re

    if not re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2}$", datetime_text):
        await message.answer(
            "❌ **Неверный формат даты!**\n\n"
            "📅 Введите дату в формате **ДД.ММ.ГГГГ ЧЧ:ММ**\n"
            "Например: 10.10.2025 18:00",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    await state.update_data(datetime=datetime_text)
    await state.set_state(GroupCreate.waiting_for_city)

    await message.answer(
        f"**Дата и время сохранены:** {datetime_text} ✅\n\n" "🏙️ **Введите город** (например: Москва):",
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
    )


async def group_city_step(message: types.Message, state: FSMContext):
    """Обработка города события в групповом чате"""
    logger.info(
        f"🔥 group_city_step: получен город '{message.text}' "
        f"от пользователя {message.from_user.id} в чате {message.chat.id}"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n" "🏙️ **Введите город** (например: Москва):",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    city = message.text.strip()
    await state.update_data(city=city)
    await state.set_state(GroupCreate.waiting_for_location)

    await message.answer(
        f"**Город сохранен:** {city} ✅\n\n" "📍 **Отправьте ссылку на место** (Google Maps или адрес):",
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
    )


async def group_location_step(message: types.Message, state: FSMContext):
    """Обработка локации события в групповом чате"""
    logger.info(
        f"🔥 group_location_step: получена локация '{message.text}' "
        f"от пользователя {message.from_user.id} в чате {message.chat.id}"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n"
            "📍 **Отправьте ссылку на место** (Google Maps или адрес):",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    location = message.text.strip()
    await state.update_data(location=location)
    await state.set_state(GroupCreate.waiting_for_description)

    await message.answer(
        f"**Локация сохранена:** {location} ✅\n\n" "📝 **Введите описание события:**",
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
    )


async def group_finish(message: types.Message, state: FSMContext):
    """Завершение создания события в групповом чате"""
    logger.info(f"🔥 group_finish: получено описание от пользователя {message.from_user.id} в чате {message.chat.id}")

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n" "📝 **Введите описание события:**",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True),
        )
        return

    description = message.text.strip()
    data = await state.update_data(description=description)

    try:
        datetime_str = data["datetime"]
        try:
            parsed_datetime = datetime.strptime(datetime_str, "%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer("❌ **Ошибка в формате даты!** Попробуйте еще раз.", parse_mode="Markdown")
            return

        service = CommunityEventsService()
        event_id = service.create_community_event(
            group_id=data["group_id"],
            creator_id=data["creator_id"],
            title=data["title"],
            date=parsed_datetime,
            description=description,
            city=data["city"],
            location_name=data["location"],
        )

        logger.info(f"🔥 group_finish: событие {event_id} создано успешно")

        await message.answer(
            f"✅ **Событие создано!**\n\n"
            f"**📌 {data['title']}**\n"
            f"📅 {data['datetime']}\n"
            f"🏙️ {data['city']}\n"
            f"📍 {data['location']}\n"
            f"📝 {description}\n\n"
            f"*Создано пользователем @{message.from_user.username or message.from_user.first_name}*",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"🔥 group_finish: ошибка при создании события: {e}")
        await message.answer("❌ **Произошла ошибка при создании события.** Попробуйте еще раз.", parse_mode="Markdown")

    await state.clear()


def register_group_handlers(dp, bot_id: int):
    """
    Регистрация обработчиков для групповых чатов
    ВНИМАНИЕ: Эта функция должна вызываться только для групповых чатов!
    """
    global BOT_ID
    BOT_ID = bot_id

    logger.info(f"🔥 Регистрация обработчиков для групповых чатов, BOT_ID={BOT_ID}")

    # Команда /create только для групп
    dp.message.register(group_create_start, Command("create"), F.chat.type.in_({"group", "supergroup"}))

    # FSM обработчики только для групп с фильтром на ответы боту
    dp.message.register(
        group_title_step,
        GroupCreate.waiting_for_title,
        F.chat.type.in_({"group", "supergroup"}),
        F.reply_to_message,
        F.reply_to_message.from_user.id == BOT_ID,
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

    logger.info("✅ Обработчики для групповых чатов зарегистрированы")
