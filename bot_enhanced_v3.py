#!/usr/bin/env python3
"""
Улучшенная версия EventBot с расширенным поиском событий (aiogram 3.x)
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.filters.text import Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from config import load_settings
from database import Event, User, create_all, get_session, init_engine
from enhanced_event_search import enhanced_search_events
from utils.geo_utils import haversine_km, static_map_url, to_google_maps_link

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем настройки
settings = load_settings()

# Инициализация базы данных
init_engine(settings.database_url)
create_all()

# Создание бота и диспетчера
bot = Bot(token=settings.telegram_token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния для FSM
class EventCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_time = State()
    waiting_for_location = State()


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Создаёт главное меню"""
    keyboard = [
        [KeyboardButton(text="📍 Что рядом"), KeyboardButton(text="➕ Создать")],
        [KeyboardButton(text="📋 Мои события"), KeyboardButton(text="🔗 Поделиться")],
        [KeyboardButton(text="❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id

    # Сохраняем пользователя в БД
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            user = User(
                id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            session.add(user)
            session.commit()

    welcome_text = (
        "Привет! Я EventAroundBot. Помогаю находить события рядом и создавать свои.\n\n"
        "🎯 Что я умею:\n"
        "• Искать события в радиусе 4 км от вас\n"
        "• Генерировать AI события\n"
        "• Искать в популярных местах\n"
        "• Создавать ваши собственные события\n\n"
        "Нажмите '📍 Что рядом' и отправьте геолокацию!"
    )

    await message.answer(welcome_text, reply_markup=main_menu_kb())


@dp.message(Text("📍 Что рядом"))
async def on_what_nearby(message: types.Message):
    """Обработчик кнопки 'Что рядом'"""
    await message.answer(
        "Отправь свежую геопозицию, чтобы я нашла события рядом ✨",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
            resize_keyboard=True,
        ),
    )


@dp.message(F.location)
async def on_location(message: types.Message):
    """Обработчик получения геолокации"""
    lat = message.location.latitude
    lng = message.location.longitude

    await message.answer("Смотрю, что рядом...", reply_markup=main_menu_kb())

    try:
        # Обновляем геолокацию пользователя
        with get_session() as session:
            user = session.get(User, message.from_user.id)
            if user:
                user.last_lat = lat
                user.last_lng = lng
                user.last_geo_at_utc = datetime.utcnow()
                session.commit()

        # Ищем события из всех источников
        events = await enhanced_search_events(lat, lng, radius_km=int(settings.default_radius_km))

        if not events:
            await message.answer(
                "Пока ничего не нашла. Попробуй позже или создай своё событие через '➕ Создать'.",
                reply_markup=main_menu_kb(),
            )
            return

        # Формируем ответ
        lines = []
        for i, event in enumerate(events[:10], 1):  # Показываем до 10 событий
            distance = haversine_km(lat, lng, event["lat"], event["lng"])
            url = event.get("location_url") or to_google_maps_link(event["lat"], event["lng"])
            time_part = f" — {event['time_local']}" if event.get("time_local") else ""
            source_emoji = {
                "ai_generated": "🤖",
                "popular_places": "🏛️",
                "event_calendars": "📅",
                "social_media": "📱",
            }.get(event.get("source", ""), "📌")

            lines.append(
                f"{source_emoji} **{event['title']}**{time_part}\n"
                f"📍 {event.get('location_name', 'Место не указано')}\n"
                f"📏 {distance:.1f} км\n"
                f"🔗 {url}"
            )

        text = "\n\n".join(lines)

        # Создаём карту
        points = []
        label_ord = ord("A")
        for event in events[:10]:
            points.append((chr(label_ord), event["lat"], event["lng"]))
            label_ord += 1

        map_url = static_map_url(lat, lng, points) or ""

        if map_url:
            await message.answer_photo(
                map_url,
                caption=f"🎯 Найдено {len(events)} событий рядом:\n\n{text}",
                reply_markup=main_menu_kb(),
                parse_mode="Markdown",
            )
        else:
            await message.answer(
                f"🎯 Найдено {len(events)} событий рядом:\n\n{text}",
                reply_markup=main_menu_kb(),
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Ошибка при поиске событий: {e}")
        await message.answer(
            "Произошла ошибка при поиске событий. Попробуйте позже.", reply_markup=main_menu_kb()
        )


@dp.message(Text("➕ Создать"))
async def on_create(message: types.Message):
    """Обработчик кнопки 'Создать'"""
    await dp.storage.set_state(message.from_user.id, EventCreation.waiting_for_title)
    await message.answer(
        "Создаём новое событие! 📝\n\nВведите название события:",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
        ),
    )


@dp.message(Text("❌ Отмена"))
async def cancel_creation(message: types.Message, state: FSMContext):
    """Отмена создания события"""
    await state.clear()
    await message.answer("Создание отменено.", reply_markup=main_menu_kb())


@dp.message(EventCreation.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    """Обработка названия события"""
    await state.update_data(title=message.text)
    await state.set_state(EventCreation.waiting_for_description)
    await message.answer("Введите описание события:")


@dp.message(EventCreation.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    """Обработка описания события"""
    await state.update_data(description=message.text)
    await state.set_state(EventCreation.waiting_for_time)
    await message.answer("Введите время события (например: 2024-01-15 19:00):")


@dp.message(EventCreation.waiting_for_time)
async def process_time(message: types.Message, state: FSMContext):
    """Обработка времени события"""
    await state.update_data(time_local=message.text)
    await state.set_state(EventCreation.waiting_for_location)
    await message.answer(
        "Отправьте геолокацию события:",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
            resize_keyboard=True,
        ),
    )


@dp.message(F.location, EventCreation.waiting_for_location)
async def process_location(message: types.Message, state: FSMContext):
    """Обработка геолокации события"""
    data = await state.get_data()

    # Создаём событие в БД
    with get_session() as session:
        event = Event(
            title=data["title"],
            description=data["description"],
            time_local=data["time_local"],
            lat=message.location.latitude,
            lng=message.location.longitude,
            organizer_id=message.from_user.id,
            organizer_username=message.from_user.username,
            status="open",
            is_generated_by_ai=False,
        )
        session.add(event)
        session.commit()

    await state.clear()
    await message.answer(
        f"✅ Событие '{data['title']}' создано!\n\n"
        f"Теперь другие пользователи смогут найти его через '📍 Что рядом'.",
        reply_markup=main_menu_kb(),
    )


@dp.message(Text("📋 Мои события"))
async def on_my_events(message: types.Message):
    """Обработчик кнопки 'Мои события'"""
    with get_session() as session:
        events = (
            session.query(Event)
            .filter(Event.organizer_id == message.from_user.id)
            .order_by(Event.created_at.desc())
            .limit(5)
            .all()
        )

    if not events:
        await message.answer(
            "У вас пока нет созданных событий. Создайте первое через '➕ Создать'!",
            reply_markup=main_menu_kb(),
        )
        return

    lines = []
    for event in events:
        status_emoji = "🟢" if event.status == "open" else "🔴"
        lines.append(
            f"{status_emoji} **{event.title}**\n"
            f"📅 {event.time_local or 'Время не указано'}\n"
            f"📍 {event.location_name or 'Место не указано'}\n"
            f"📊 Статус: {event.status}"
        )

    text = "\n\n".join(lines)
    await message.answer(
        f"📋 Ваши события:\n\n{text}", reply_markup=main_menu_kb(), parse_mode="Markdown"
    )


@dp.message(Text("🔗 Поделиться"))
async def on_share(message: types.Message):
    """Обработчик кнопки 'Поделиться'"""
    bot_info = await bot.get_me()
    text = (
        "Прикрепи бота в чат — чтобы всем было удобнее искать активности вместе.\n\n"
        f"Добавить: t.me/{bot_info.username}?startgroup=true\n"
        f"Личная ссылка: t.me/{bot_info.username}\n\n"
        "Можешь делиться конкретным событием, когда откроешь его карточку — я пришлю deep-link."
    )
    await message.answer(text, reply_markup=main_menu_kb())


@dp.message(Text("❓ Помощь"))
async def on_help(message: types.Message):
    """Обработчик кнопки 'Помощь'"""
    help_text = (
        "🤖 **EventAroundBot - Помощь**\n\n"
        "**📍 Что рядом** - ищет события в радиусе 4 км от вас\n"
        "**➕ Создать** - создаёт новое событие\n"
        "**📋 Мои события** - показывает ваши созданные события\n"
        "**🔗 Поделиться** - ссылки для добавления бота\n\n"
        "**Как использовать:**\n"
        "1. Нажмите '📍 Что рядом'\n"
        "2. Отправьте геолокацию\n"
        "3. Получите список событий с картой\n\n"
        "**Источники событий:**\n"
        "🤖 AI генерация\n"
        "🏛️ Популярные места\n"
        "📅 Календари событий\n"
        "📱 Социальные сети\n"
        "👥 Пользователи бота"
    )
    await message.answer(help_text, reply_markup=main_menu_kb(), parse_mode="Markdown")


@dp.message()
async def echo_message(message: types.Message):
    """Обработчик всех остальных сообщений"""
    await message.answer("Используйте кнопки меню для навигации:", reply_markup=main_menu_kb())


async def main():
    """Главная функция"""
    logger.info("Запуск улучшенного EventBot (aiogram 3.x)...")

    # Запускаем бота
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
