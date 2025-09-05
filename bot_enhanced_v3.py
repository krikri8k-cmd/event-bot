#!/usr/bin/env python3
"""
Улучшенная версия EventBot с расширенным поиском событий (aiogram 3.x)
"""

import asyncio
import html
import logging
from datetime import UTC, datetime
from urllib.parse import quote_plus, urlparse

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


def is_valid_url(url: str) -> bool:
    """
    Проверяет, является ли строка валидным URL
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


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


def enrich_venue_name(e: dict) -> dict:
    """
    Обогащает событие названием места, если его нет
    """
    if e.get("venue_name") and e.get("venue_name") not in [
        "",
        "Место проведения",
        "Место не указано",
    ]:
        return e

    # 1) из title/description
    import re

    VENUE_RX = r"(?:в|at|@)\s+([A-Za-zА-Яа-я0-9''\-&\.\s]+)$"

    for field in ("title", "description"):
        v = (e.get(field) or "").strip()
        m = re.search(VENUE_RX, v)
        if m:
            venue_name = m.group(1).strip()
            # Проверяем, что это не просто часть названия события
            if len(venue_name) > 3 and venue_name not in ["момент", "событие", "встреча"]:
                e["venue_name"] = venue_name
                return e

    # 2) если всё ещё пустое, используем fallback
    if not e.get("venue_name") or e.get("venue_name") in [
        "",
        "Место проведения",
        "Место не указано",
    ]:
        e["venue_name"] = "📍 Локация уточняется"

    return e


def build_maps_url(event: dict) -> str:
    """
    Создает корректную ссылку на Google Maps с названием места
    """
    name = (event.get("venue_name") or "").strip()
    addr = (event.get("address") or "").strip()
    lat, lng = event.get("lat"), event.get("lng")

    if name:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(name)}"
    if addr:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(addr)}"
    if lat and lng:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    return "https://www.google.com/maps"


def create_google_maps_url(event: dict) -> str:
    """
    Создает ссылку на Google Maps с названием места (устаревшая функция)
    """
    return build_maps_url(event)


def get_source_url(event: dict) -> str:
    """
    Возвращает URL источника события
    """
    source = event.get("source", "")
    event_type = event.get("type", "")

    # Если есть прямая ссылка на источник
    if event.get("source_url"):
        return event["source_url"]

    # Если есть URL события
    if event.get("url"):
        return event["url"]

    # Если есть website
    if event.get("website"):
        return event["website"]

    # Если есть location_url
    if event.get("location_url"):
        return event["location_url"]

    # Fallback для разных типов событий
    if event_type == "user":
        # Для пользовательских событий - ссылка на профиль автора
        organizer_id = event.get("organizer_id")
        if organizer_id:
            return f"https://t.me/user{organizer_id}"
        return "https://t.me/EventAroundBot"
    elif event_type == "moment":
        # Для мгновенных событий - ссылка на создателя
        creator_id = event.get("creator_id")
        if creator_id:
            return f"https://t.me/user{creator_id}"
        return "https://t.me/EventAroundBot"
    elif source == "ai_generated":
        return "https://t.me/EventAroundBot"  # Ссылка на бота
    elif source == "popular_places":
        return "https://maps.google.com"  # Ссылка на карты
    elif source == "event_calendars":
        return "https://calendar.google.com"  # Ссылка на календарь
    elif source == "social_media":
        return "https://t.me/EventAroundBot"  # Ссылка на бота
    else:
        return "https://t.me/EventAroundBot"  # Fallback на бота


def get_venue_name(event: dict) -> str:
    """
    Возвращает название места для события
    """
    # Приоритет: venue_name -> location_name -> address
    venue_name = event.get("venue_name") or event.get("location_name") or event.get("address") or ""

    # Фильтруем мусорные названия
    if venue_name in ["Место проведения", "Место не указано", "Локация", ""]:
        venue_name = ""

    # Если название пустое, пытаемся извлечь из описания
    if not venue_name and event.get("description"):
        description = event.get("description", "")
        # Простые регулярки для извлечения места
        import re

        # Ищем паттерны типа "в Canggu Studio", "at Museum", "@Place"
        patterns = [
            r"в\s+([^,.\n]+)",
            r"at\s+([^,.\n]+)",
            r"@([^\s,.\n]+)",
            r"место:\s*([^,.\n]+)",
            r"адрес:\s*([^,.\n]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                venue_name = match.group(1).strip()
                break

    # Если всё ещё пустое, используем fallback
    if not venue_name:
        venue_name = "📍 Локация уточняется"

    # Ограничиваем длину для компактности
    if len(venue_name) > 30:
        return venue_name[:27] + "..."

    return venue_name


def get_event_type_info(event: dict) -> tuple[str, str]:
    """
    Возвращает информацию о типе события (emoji, название)
    """
    source = event.get("source", "")
    event_type = event.get("type", "")

    if event_type == "user":
        return "👥", "Пользовательские"
    elif event_type == "moment":
        return "⚡", "Мгновенные"
    elif source == "ai_generated":
        return "🤖", "AI генерация"
    elif source == "popular_places":
        return "🏛️", "Популярные места"
    elif source == "event_calendars":
        return "📅", "Календари"
    elif source == "social_media":
        return "📱", "Социальные сети"
    else:
        return "📌", "Другие"


def create_event_links(event: dict) -> str:
    """
    Создает кликабельные ссылки для события (устаревшая функция, используется для совместимости)
    """
    maps_url = create_google_maps_url(event)
    source_url = get_source_url(event)

    links = [f"🗺️ [Маршрут]({maps_url})", f"🔗 [Источник]({source_url})"]
    return " | ".join(links)


def group_events_by_type(events: list) -> dict[str, list]:
    """
    Группирует события по типам
    """
    groups = {
        "sources": [],  # Из источников (календари, соцсети)
        "users": [],  # От пользователей
        "moments": [],  # Мгновенные события
    }

    for event in events:
        event_type = event.get("type", "")
        event.get("source", "")

        if event_type == "user":
            groups["users"].append(event)
        elif event_type == "moment":
            groups["moments"].append(event)
        else:
            # Все остальные считаем источниками
            groups["sources"].append(event)

    return groups


def is_valid_source_url(u: str | None) -> bool:
    """
    Проверяет, является ли source_url валидным
    """
    if not u:
        return False

    import re
    from urllib.parse import urlparse

    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        return False

    # Если домен calendar.google.com — должен быть конкретный эвент
    if p.netloc.endswith("calendar.google.com"):
        GCAL_OK = re.compile(r"^https?://calendar\.google\.com/.*(event\?eid=|r/eventedit)", re.I)
        return bool(GCAL_OK.search(u))

    return True


def is_m垃圾_url(url: str) -> bool:
    """
    Проверяет, является ли URL мусорным (пустые ссылки на Google Calendar и т.д.)
    """
    return not is_valid_source_url(url)


def prepare_events_for_feed(events: list[dict]) -> list[dict]:
    """
    Фильтрует события для показа в ленте
    """
    out = []
    for e in events:
        if e["type"] == "source" and not is_valid_source_url(e.get("source_url")):
            # не публикуем источник без валидной ссылки
            e["is_publishable"] = False
            logger.warning(
                "skip source without valid url | id=%s title=%s url=%s",
                e.get("id"),
                e.get("title"),
                e.get("source_url"),
            )
            continue
        out.append(e)
    return out


def render_event_html(e: dict, idx: int = None) -> str:
    """
    Рендерит событие в HTML формате с кликабельными ссылками
    """
    title = html.escape(e["title"])
    when = e.get("when_str", e.get("time_local", ""))
    dist = f"{e.get('distance_km', 0):.1f} км" if e.get("distance_km") else ""
    venue = html.escape(e.get("venue_name") or e.get("address") or "Локация уточняется")

    src_url = e.get("source_url")
    src_link = (
        f'<a href="{html.escape(src_url)}">Источник</a>' if src_url else "Источник недоступен"
    )
    map_link = f'<a href="{build_maps_url(e)}">Маршрут</a>'

    # Добавляем номер события если указан
    prefix = f"{idx}) " if idx is not None else ""

    return f"{prefix}🏷 <b>{title}</b> — {when} ({dist})\n📍 {venue}\n🔗 {src_link}  🚗 {map_link}"


def render_header(counts: dict) -> str:
    """
    Рендерит заголовок с подсчетом событий по типам
    """
    lines = [f"🗺 Найдено рядом: <b>{counts['all']}</b>"]
    if counts["moments"]:
        lines.append(f"• ⚡ Мгновенные: {counts['moments']}")
    if counts["user"]:
        lines.append(f"• 👥 От пользователей: {counts['user']}")
    if counts["sources"]:
        lines.append(f"• 🌐 Из источников: {counts['sources']}")
    return "\n".join(lines)


def kb_pager(page: int, total_pages: int):
    """
    Создает клавиатуру пагинации
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    prev_cb = f"pg:{page-1}" if page > 1 else "pg:noop"
    next_cb = f"pg:{page+1}" if page < total_pages else "pg:noop"

    buttons = [
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data=prev_cb),
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=next_cb),
        ],
        [InlineKeyboardButton(text=f"Стр. {page}/{total_pages}", callback_data="pg:noop")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_events_summary(events: list) -> str:
    """
    Создает сводку по типам событий (устаревшая функция)
    """
    groups = group_events_by_type(events)

    summary_lines = [f"🗺 Найдено {len(events)} событий рядом!"]

    if groups["sources"]:
        summary_lines.append(f"• Из источников: {len(groups['sources'])}")
    if groups["users"]:
        summary_lines.append(f"• От пользователей: {len(groups['users'])}")
    if groups["moments"]:
        summary_lines.append(f"• Мгновенные ⚡: {len(groups['moments'])}")

    return "\n".join(summary_lines)


async def send_compact_events_list(
    message: types.Message, events: list, user_lat: float, user_lng: float, page: int = 0
):
    """
    Отправляет компактный список событий с пагинацией в HTML формате
    """
    # 1) сначала фильтруем и группируем (после всех проверок publishable)
    prepared = prepare_events_for_feed(events)

    # Обогащаем события названиями мест
    for event in prepared:
        enrich_venue_name(event)
        # Добавляем расстояние
        event["distance_km"] = haversine_km(user_lat, user_lng, event["lat"], event["lng"])

    groups = {
        "moment": [e for e in prepared if e["type"] == "moment"],
        "user": [e for e in prepared if e["type"] == "user"],
        "source": [e for e in prepared if e["type"] == "source"],
    }
    counts = {
        "all": len(prepared),
        "moments": len(groups["moment"]),
        "user": len(groups["user"]),
        "sources": len(groups["source"]),
    }

    # Настройки пагинации
    events_per_page = 4
    total_pages = (len(prepared) + events_per_page - 1) // events_per_page
    page = max(0, min(page, total_pages - 1))

    # Получаем события для текущей страницы
    start_idx = page * events_per_page
    end_idx = min(start_idx + events_per_page, len(prepared))
    page_events = prepared[start_idx:end_idx]

    # Формируем заголовок
    header_html = render_header(counts)

    # Формируем HTML карточки событий
    event_lines = []
    for idx, event in enumerate(page_events, start=start_idx + 1):
        event_html = render_event_html(event, idx)
        event_lines.append(event_html)

    text = header_html + "\n\n" + "\n".join(event_lines)

    # Создаем клавиатуру пагинации
    inline_kb = kb_pager(page + 1, total_pages) if total_pages > 1 else None

    try:
        # Отправляем компактный список событий в HTML формате
        await message.answer(
            text, reply_markup=inline_kb, parse_mode="HTML", disable_web_page_preview=True
        )
        logger.info(f"✅ Страница {page + 1} событий отправлена (HTML)")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки страницы {page + 1}: {e}")
        # Fallback - отправляем без форматирования
        await message.answer(
            f"📋 События (страница {page + 1} из {total_pages}):\n\n{text}", reply_markup=inline_kb
        )


async def edit_events_list_message(
    message: types.Message, events: list, user_lat: float, user_lng: float, page: int = 0
):
    """
    Редактирует сообщение со списком событий (для пагинации)
    """
    # 1) сначала фильтруем и группируем (после всех проверок publishable)
    prepared = prepare_events_for_feed(events)

    # Обогащаем события названиями мест
    for event in prepared:
        enrich_venue_name(event)
        # Добавляем расстояние
        event["distance_km"] = haversine_km(user_lat, user_lng, event["lat"], event["lng"])

    groups = {
        "moment": [e for e in prepared if e["type"] == "moment"],
        "user": [e for e in prepared if e["type"] == "user"],
        "source": [e for e in prepared if e["type"] == "source"],
    }
    counts = {
        "all": len(prepared),
        "moments": len(groups["moment"]),
        "user": len(groups["user"]),
        "sources": len(groups["source"]),
    }

    # Настройки пагинации
    events_per_page = 4
    total_pages = (len(prepared) + events_per_page - 1) // events_per_page
    page = max(0, min(page, total_pages - 1))

    # Получаем события для текущей страницы
    start_idx = page * events_per_page
    end_idx = min(start_idx + events_per_page, len(prepared))
    page_events = prepared[start_idx:end_idx]

    # Формируем заголовок
    header_html = render_header(counts)

    # Формируем HTML карточки событий
    event_lines = []
    for idx, event in enumerate(page_events, start=start_idx + 1):
        event_html = render_event_html(event, idx)
        event_lines.append(event_html)

    text = header_html + "\n\n" + "\n".join(event_lines)

    # Создаем клавиатуру пагинации
    inline_kb = kb_pager(page + 1, total_pages) if total_pages > 1 else None

    try:
        # Редактируем сообщение
        await message.edit_text(
            text, reply_markup=inline_kb, parse_mode="HTML", disable_web_page_preview=True
        )
        logger.info(f"✅ Страница {page + 1} событий отредактирована (HTML)")
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования страницы {page + 1}: {e}")


async def send_detailed_events_list(
    message: types.Message, events: list, user_lat: float, user_lng: float
):
    """
    Отправляет детальный список событий отдельным сообщением (устаревшая функция)
    """
    # Используем новую компактную функцию
    await send_compact_events_list(message, events, user_lat, user_lng, page=0)


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

        # Создаем краткую подпись для карты с правильным отчётом
        # 1) сначала фильтруем и группируем (после всех проверок publishable)
        prepared = prepare_events_for_feed(events)

        # Обогащаем события названиями мест
        for event in prepared:
            enrich_venue_name(event)

        groups = {
            "moment": [e for e in prepared if e["type"] == "moment"],
            "user": [e for e in prepared if e["type"] == "user"],
            "source": [e for e in prepared if e["type"] == "source"],
        }
        counts = {
            "all": len(prepared),
            "moments": len(groups["moment"]),
            "user": len(groups["user"]),
            "sources": len(groups["source"]),
        }

        # Формируем заголовок с правильным отчётом
        header_lines = [f"🗺 Найдено рядом: <b>{counts['all']}</b>"]
        if counts["moments"]:
            header_lines.append(f"• ⚡ Мгновенные: {counts['moments']}")
        if counts["user"]:
            header_lines.append(f"• 👥 От пользователей: {counts['user']}")
        if counts["sources"]:
            header_lines.append(f"• 🌐 Из источников: {counts['sources']}")

        short_caption = "\n".join(header_lines) + "\n\n"

        # Добавляем краткую информацию о событиях с короткими ссылками
        for i, event in enumerate(events_to_show[:3], 1):  # Показываем только первые 3
            distance = haversine_km(lat, lng, event["lat"], event["lng"])
            time_part = f" {event['time_local']}" if event.get("time_local") else ""
            title = event["title"][:20] + "..." if len(event["title"]) > 20 else event["title"]

            # Короткая ссылка на источник
            short_link = get_short_source_link(event)

            short_caption += f"<b>{i}) {title}</b>{time_part} • {distance:.1f}км {short_link}\n"

        if len(events) > 3:
            short_caption += f"\n... и еще {len(events) - 3} событий"

        short_caption += "\n\n💡 <b>Нажми кнопку ниже для Google Maps!</b>"

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
                    parse_mode="HTML",
                )

                # Отправляем компактный список событий отдельным сообщением
                try:
                    await send_compact_events_list(message, events, lat, lng, page=0)
                    logger.info("✅ Компактный список событий отправлен")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки компактного списка: {e}")
                    # Fallback - отправляем краткий список
                    await message.answer(
                        f"📋 **Все {len(events)} событий:**\n\n"
                        f"💡 Нажми кнопку '🗺️ Открыть в Google Maps с событиями' выше "
                        f"чтобы увидеть полную информацию о каждом событии!",
                        parse_mode="Markdown",
                    )
            except Exception as e:
                logger.exception("Failed to send map image, will send URL as text: %s", e)
                await message.answer(
                    f"Не удалось загрузить изображение карты. Вот URL для проверки:\n{map_url}"
                )
        else:
            # Если карта не сгенерировалась, отправляем только список событий
            try:
                await send_compact_events_list(message, events, lat, lng, page=0)
                logger.info("✅ Компактный список событий отправлен (без карты)")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки компактного списка: {e}")
                # Fallback - отправляем краткий список
                await message.answer(
                    f"📋 **Все {len(events)} событий:**\n\n"
                    f"💡 К сожалению, карта не загрузилась, но все события найдены!",
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


@dp.message(Command("admin_event"))
async def on_admin_event(message: types.Message):
    """Обработчик команды /admin_event для диагностики событий"""
    # Проверяем, что это админ (можно добавить проверку по user_id)
    try:
        # Извлекаем ID события из команды
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.answer("Использование: /admin_event <id_события>")
            return

        event_id = int(command_parts[1])

        # Ищем событие в БД
        with get_session() as session:
            event = session.get(Event, event_id)
            if not event:
                await message.answer(f"Событие с ID {event_id} не найдено")
                return

            # Формируем диагностическую информацию в HTML
            title = html.escape(event.title)
            description = html.escape(event.description or "Не указано")
            location = html.escape(event.location_name or "Не указано")
            address = html.escape(getattr(event, "address", "Не указано"))
            url = html.escape(event.url or "Не указано")
            location_url = html.escape(event.location_url or "Не указано")
            source = html.escape(event.source or "Не указано")
            organizer = html.escape(event.organizer_username or "Не указано")

            info_lines = [
                f"🔍 <b>Диагностика события #{event_id}</b>",
                f"<b>Название:</b> {title}",
                f"<b>Описание:</b> {description}",
                f"<b>Время:</b> {event.time_local or 'Не указано'}",
                f"<b>Место:</b> {location}",
                f"<b>Адрес:</b> {address}",
                f"<b>Координаты:</b> {event.lat}, {event.lng}",
                f"<b>URL события:</b> {url}",
                f"<b>URL места:</b> {location_url}",
                f"<b>Источник:</b> {source}",
                f"<b>Организатор:</b> {organizer}",
                f"<b>AI генерация:</b> {'Да' if event.is_generated_by_ai else 'Нет'}",
            ]

            # Проверяем наличие venue_name
            if not hasattr(event, "venue_name") or not getattr(event, "venue_name", None):
                info_lines.append("⚠️ <b>ПРЕДУПРЕЖДЕНИЕ:</b> venue_name отсутствует!")
                logger.warning(f"Событие {event_id}: venue_name отсутствует")

            # Проверяем publishable
            is_publishable = bool(event.url or event.location_url)
            info_lines.append(f"<b>Публикуемо:</b> {'Да' if is_publishable else 'Нет'}")

            if not is_publishable:
                info_lines.append("⚠️ <b>ПРЕДУПРЕЖДЕНИЕ:</b> Нет source_url для публикации!")

            text = "\n".join(info_lines)
            await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

    except ValueError:
        await message.answer("ID события должен быть числом")
    except Exception as e:
        logger.error(f"Ошибка в команде admin_event: {e}")
        await message.answer("Произошла ошибка при получении информации о событии")


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


@dp.callback_query(F.data.startswith("pg:"))
async def handle_pagination(callback: types.CallbackQuery):
    """Обработчик пагинации событий"""

    try:
        # Извлекаем номер страницы из callback_data
        data = callback.data.split(":")[1]
        if data == "noop":
            await callback.answer("Это крайняя страница")
            return

        page = int(data) - 1  # конвертируем в 0-based индекс

        # Получаем геолокацию пользователя из БД
        with get_session() as session:
            user = session.get(User, callback.from_user.id)
            if not user or not user.last_lat or not user.last_lng:
                await callback.answer("Геолокация не найдена. Отправьте новую геолокацию.")
                return

            user_lat = user.last_lat
            user_lng = user.last_lng

        # Ищем события заново
        try:
            events = await enhanced_search_events(
                user_lat, user_lng, radius_km=int(settings.default_radius_km)
            )
            events = sort_events_by_time(events)
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске событий для пагинации: {e}")
            await callback.answer("Ошибка при загрузке событий")
            return

        if not events:
            await callback.answer("События не найдены")
            return

        # Редактируем сообщение с новой страницей
        await edit_events_list_message(callback.message, events, user_lat, user_lng, page)
        await callback.answer()

    except (ValueError, IndexError) as e:
        logger.error(f"❌ Ошибка обработки пагинации: {e}")
        await callback.answer("Ошибка обработки запроса")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в пагинации: {e}")
        await callback.answer("Произошла ошибка")


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
                types.BotCommand(
                    command="admin_event", description="🔍 Диагностика события (админ)"
                ),
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
