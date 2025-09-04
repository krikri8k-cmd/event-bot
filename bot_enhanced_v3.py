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
from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
)

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


def get_short_source_link(event: dict) -> str:
    """
    Генерирует короткую ссылку на источник события для карты
    """
    source = event.get("source", "")

    if source == "ai_generated":
        return "🤖"
    elif source == "popular_places":
        return "🏛️"
    elif source == "event_calendars":
        return "📅"
    elif source == "social_media":
        return "📱"
    else:
        return "📌"


def create_enhanced_google_maps_url(user_lat: float, user_lng: float, events: list) -> str:
    """
    Создает расширенную ссылку на Google Maps с информацией о событиях
    """
    # Базовая ссылка на Google Maps
    base_url = "https://www.google.com/maps/search/"

    # Добавляем события как поисковые запросы
    search_queries = []
    for i, event in enumerate(events[:8], 1):  # Максимум 8 событий для URL
        title = event.get("title", "").replace(" ", "+")
        time_part = event.get("time_local", "").replace(" ", "+") if event.get("time_local") else ""

        # Формируем поисковый запрос: "Название+события+время+координаты"
        search_query = f"{title}"
        if time_part:
            search_query += f"+{time_part}"

        search_queries.append(search_query)

    # Объединяем все поисковые запросы
    if search_queries:
        combined_search = "+".join(search_queries)
        return f"{base_url}{combined_search}/@{user_lat:.6f},{user_lng:.6f},13z"
    else:
        return f"{base_url}@{user_lat:.6f},{user_lng:.6f},13z"


def sort_events_by_time(events: list) -> list:
    """
    Сортирует события по времени (ближайшие первыми)
    """

    def get_event_time(event):
        time_str = event.get("time_local", "")
        if not time_str:
            return float("inf")  # События без времени в конец

        try:
            # Парсим время в формате "2025-01-04 19:00"
            from datetime import datetime

            event_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            return event_time.timestamp()
        except (ValueError, TypeError):
            return float("inf")  # При ошибке парсинга в конец

    return sorted(events, key=get_event_time)


def create_event_links(event: dict) -> str:
    """
    Создает кликабельные ссылки для события
    """
    links = []

    # Ссылка на Google Maps
    if event.get("lat") and event.get("lng"):
        maps_url = (
            f"https://www.google.com/maps/search/?api=1&query={event['lat']:.6f},{event['lng']:.6f}"
        )
        links.append(f"🗺️ [Google Maps]({maps_url})")

    # Ссылка на сайт места (если есть)
    if event.get("website"):
        links.append(f"🌐 [Сайт]({event['website']})")

    # Ссылка на бронирование (если есть)
    if event.get("booking_url"):
        links.append(f"📅 [Забронировать]({event['booking_url']})")

    return " | ".join(links) if links else "🔗 [Google Maps](https://maps.google.com)"


async def send_detailed_events_list(
    message: types.Message, events: list, user_lat: float, user_lng: float
):
    """
    Отправляет детальный список событий отдельным сообщением
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    # Разбиваем события на части (Telegram лимит ~4096 символов)
    events_per_message = 5
    total_parts = (len(events) + events_per_message - 1) // events_per_message

    for part in range(total_parts):
        start_idx = part * events_per_message
        end_idx = min(start_idx + events_per_message, len(events))
        part_events = events[start_idx:end_idx]

        # Формируем текст для части
        lines = []
        for i, event in enumerate(part_events, start_idx + 1):
            distance = haversine_km(user_lat, user_lng, event["lat"], event["lng"])
            time_part = f" — {event['time_local']}" if event.get("time_local") else ""

            # Эмодзи для источника
            source_emoji = {
                "ai_generated": "🤖",
                "popular_places": "🏛️",
                "event_calendars": "📅",
                "social_media": "📱",
            }.get(event.get("source", ""), "📌")

            # Кликабельные ссылки для события
            event_links = create_event_links(event)

            # Ограничиваем длину названия и места
            title = event["title"][:50] + "..." if len(event["title"]) > 50 else event["title"]
            location = event.get("location_name", "Место не указано")
            location = location[:40] + "..." if len(location) > 40 else location

            lines.append(
                f"**{i}) {title}**{time_part}\n"
                f"📍 {location}\n"
                f"📏 {distance:.1f} км\n"
                f"{source_emoji} {event.get('source', 'unknown')}\n"
                f"{event_links}\n"
            )

        text = "\n".join(lines)

        # Добавляем заголовок части
        if total_parts > 1:
            text = f"📋 **События (часть {part + 1} из {total_parts}):**\n\n{text}"
        else:
            text = f"📋 **Все найденные события:**\n\n{text}"

        # Создаем инлайн клавиатуру для перехода в Google Maps
        maps_url = f"https://www.google.com/maps/search/?api=1&query={user_lat:.6f},{user_lng:.6f}"
        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🗺️ Открыть в Google Maps", url=maps_url)]]
        )

        # Отправляем часть событий
        await message.answer(
            text,
            reply_markup=inline_kb,
            parse_mode="Markdown",
        )


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

        # Сортируем события по времени (ближайшие первыми)
        events = sort_events_by_time(events)
        logger.info("📅 События отсортированы по времени")

        # Формируем краткую подпись для карты с короткими ссылками
        events_to_show = events[:12]  # Показываем до 12 событий на карте

        # Создаем краткую подпись для карты
        short_caption = f"🎯 Найдено {len(events)} событий рядом!\n\n"

        # Добавляем краткую информацию о событиях с короткими ссылками
        for i, event in enumerate(events_to_show[:5], 1):  # Показываем первые 5
            distance = haversine_km(lat, lng, event["lat"], event["lng"])
            time_part = f" {event['time_local']}" if event.get("time_local") else ""
            title = event["title"][:25] + "..." if len(event["title"]) > 25 else event["title"]

            # Короткая ссылка на источник
            short_link = get_short_source_link(event)

            short_caption += f"**{i}) {title}**{time_part} • {distance:.1f}км {short_link}\n"

        if len(events) > 5:
            short_caption += f"\n... и еще {len(events) - 5} событий"

        short_caption += (
            "\n\n💡 **Нажми на карту чтобы открыть в Google Maps с полной информацией!**"
        )

        # Создаём карту с нумерованными метками
        points = []
        for i, event in enumerate(events_to_show, 1):  # Используем те же события
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

        # Увеличиваем размер карты для отображения всех событий
        map_url = static_map_url(lat, lng, points, size="800x600", zoom=14)

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
                # Создаем инлайн клавиатуру с ссылкой на Google Maps
                from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

                # Создаем расширенную ссылку на Google Maps с информацией о событиях
                maps_url = create_enhanced_google_maps_url(lat, lng, events_to_show)

                inline_kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🗺️ Открыть в Google Maps с событиями", url=maps_url
                            )
                        ]
                    ]
                )

                # Отправляем карту с краткой подписью
                await message.answer_photo(
                    map_url,
                    caption=short_caption,
                    reply_markup=inline_kb,
                    parse_mode="Markdown",
                )

                # Отправляем детальный список событий отдельным сообщением
                await send_detailed_events_list(message, events, lat, lng)
            except Exception as e:
                logger.exception("Failed to send map image, will send URL as text: %s", e)
                await message.answer(
                    f"Не удалось загрузить изображение карты. Вот URL для проверки:\n{map_url}"
                )
        else:
            # Если карта не сгенерировалась, отправляем только список событий
            await send_detailed_events_list(message, events, lat, lng)

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
