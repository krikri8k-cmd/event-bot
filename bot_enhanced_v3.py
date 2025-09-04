#!/usr/bin/env python3
"""
Улучшенная версия EventBot с расширенным поиском событий (aiogram 3.x)
"""

import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot_health import health_server
from config import load_settings
from database import Event, User, create_all, get_session, init_engine
from enhanced_event_search import enhanced_search_events
from utils.geo_utils import haversine_km, static_map_url


def get_source_link(event: dict) -> str:
    """
    Генерирует ссылку на источник события
    """
    source = event.get("source", "")

    if source == "ai_generated":
        return "AI генерация"
    elif source == "popular_places":
        return "Популярные места"
    elif source == "event_calendars":
        return "Календари событий"
    elif source == "social_media":
        return "Социальные сети"
    else:
        return "Неизвестный источник"


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем настройки
# Для бота — токен обязателен
settings = load_settings(require_bot=True)

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
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="🚀 Старт")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


@dp.message(Command("start"))
@dp.message(F.text == "🚀 Старт")
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
        "• Искать события в радиусе 5 км от вас\n"
        "• Генерировать AI события\n"
        "• Искать в популярных местах\n"
        "• Создавать ваши собственные события\n\n"
        "Нажмите '📍 Что рядом' и отправьте геолокацию!"
    )

    await message.answer(welcome_text, reply_markup=main_menu_kb())


@dp.message(Command("nearby"))
@dp.message(F.text == "📍 Что рядом")
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
                user.last_geo_at_utc = datetime.now(UTC)
                session.commit()

        # Ищем события из всех источников
        try:
            logger.info(f"🔍 Начинаем поиск событий для координат ({lat}, {lng})")
            events = await enhanced_search_events(
                lat, lng, radius_km=int(settings.default_radius_km)
            )
            logger.info(f"✅ Поиск завершен, найдено {len(events)} событий")
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске событий: {e}")
            await message.answer(
                "Произошла ошибка при поиске событий. Попробуйте позже.",
                reply_markup=main_menu_kb(),
            )
            return

        if not events:
            logger.info("📭 События не найдены")
            await message.answer(
                "Пока ничего не нашла. Попробуй позже или создай своё событие через '➕ Создать'.",
                reply_markup=main_menu_kb(),
            )
            return

        # Формируем ответ с нумерацией
        lines = []
        for i, event in enumerate(events[:8], 1):  # Показываем до 8 событий
            distance = haversine_km(lat, lng, event["lat"], event["lng"])
            time_part = f" — {event['time_local']}" if event.get("time_local") else ""

            # Эмодзи для источника
            source_emoji = {
                "ai_generated": "🤖",
                "popular_places": "🏛️",
                "event_calendars": "📅",
                "social_media": "📱",
            }.get(event.get("source", ""), "📌")

            # Ссылка на источник
            source_link = get_source_link(event)
            source_info = f"🔗 {source_link}" if source_link else ""

            # Ограничиваем длину названия и места
            title = event["title"][:50] + "..." if len(event["title"]) > 50 else event["title"]
            location = event.get("location_name", "Место не указано")
            location = location[:40] + "..." if len(location) > 40 else location

            lines.append(
                f"**{i}) {title}**{time_part}\n"
                f"📍 {location}\n"
                f"📏 {distance:.1f} км\n"
                f"{source_emoji} {event.get('source', 'unknown')} {source_info}"
            )

        text = "\n\n".join(lines)

        # Создаём карту с нумерованными метками
        points = []
        for i, event in enumerate(events[:8], 1):  # Используем те же 8 событий
            event_lat = event.get("lat")
            event_lng = event.get("lng")

            # Проверяем что координаты валидные
            if event_lat is not None and event_lng is not None:
                if -90 <= event_lat <= 90 and -180 <= event_lng <= 180:
                    points.append((str(i), event_lat, event_lng))  # Метки 1, 2, 3
                    logger.info(
                        f"Событие {i}: {event['title']} - координаты ({event_lat:.6f}, {event_lng:.6f})"
                    )
                else:
                    logger.warning(f"Событие {i}: неверные координаты ({event_lat}, {event_lng})")
            else:
                logger.warning(f"Событие {i}: отсутствуют координаты")

        map_url = static_map_url(lat, lng, points)

        # --- DEBUG: persist & log map url ---
        from pathlib import Path

        try:
            Path("last_map_url.txt").write_text(map_url, encoding="utf-8")
        except Exception as e:
            logger.warning("Cannot write last_map_url.txt: %s", e)
        logger.info("Map URL: %s", map_url)
        print(f"MAP_URL={map_url}")
        # --- END DEBUG ---

        if map_url and map_url.startswith("http"):
            try:
                await message.answer_photo(
                    map_url,
                    caption=f"🎯 Найдено {len(events)} событий рядом:\n\n{text}",
                    reply_markup=main_menu_kb(),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.exception("Failed to send map image, will send URL as text: %s", e)
                await message.answer(
                    f"Не удалось загрузить изображение карты. Вот URL для проверки:\n{map_url}"
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


@dp.message(Command("create"))
@dp.message(F.text == "➕ Создать")
async def on_create(message: types.Message):
    """Обработчик кнопки 'Создать'"""
    await dp.storage.set_state(message.from_user.id, EventCreation.waiting_for_title)
    await message.answer(
        "Создаём новое событие! 📝\n\nВведите название события:",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
        ),
    )


@dp.message(F.text == "❌ Отмена")
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


@dp.message(Command("myevents"))
@dp.message(F.text == "📋 Мои события")
async def on_my_events(message: types.Message):
    """Обработчик кнопки 'Мои события'"""
    with get_session() as session:
        events = (
            session.query(Event)
            .filter(Event.organizer_id == message.from_user.id)
            .order_by(Event.created_at_utc.desc())
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


@dp.message(Command("share"))
@dp.message(F.text == "🔗 Поделиться")
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


@dp.message(Command("help"))
@dp.message(F.text == "❓ Помощь")
async def on_help(message: types.Message):
    """Обработчик кнопки 'Помощь'"""
    help_text = (
        "🤖 **EventAroundBot - Помощь**\n\n"
        "**📍 Что рядом** - ищет события в радиусе 5 км от вас\n"
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

    # Запускаем health check сервер для Railway
    try:
        if health_server.start():
            logger.info("Health check сервер запущен")
        else:
            logger.warning("Не удалось запустить health check сервер")
    except Exception as e:
        logger.warning(f"Ошибка запуска health check сервера: {e}")

    # Устанавливаем команды бота для удобства пользователей
    try:
        await bot.set_my_commands(
            [
                types.BotCommand(command="start", description="🚀 Запустить бота и показать меню"),
                types.BotCommand(command="help", description="❓ Показать справку"),
                types.BotCommand(command="nearby", description="📍 Найти события рядом"),
                types.BotCommand(command="create", description="➕ Создать событие"),
                types.BotCommand(command="myevents", description="📋 Мои события"),
                types.BotCommand(command="share", description="🔗 Поделиться ботом"),
            ]
        )
        logger.info("Команды бота установлены")
    except Exception as e:
        logger.warning(f"Не удалось установить команды бота: {e}")

    # Запускаем бота
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
