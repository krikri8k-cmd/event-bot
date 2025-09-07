#!/usr/bin/env python3
"""
Улучшенная версия EventBot с расширенным поиском событий (aiogram 3.x)
"""

import asyncio
import html
import logging
import os
import re
import ssl
from datetime import UTC, datetime
from math import ceil
from urllib.parse import quote_plus, urlparse

import certifi
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiohttp import TCPConnector

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

    VENUE_RX = r"(?:в|at|@)\s+([A-Za-zА-Яа-я0-9''&\s.-]+)$"

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


def create_google_maps_url(event: dict) -> str:
    """
    Создает ссылку на Google Maps с названием места (устаревшая функция)
    """
    return build_maps_url(event)


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


def is_m垃圾_url(url: str) -> bool:
    """
    Проверяет, является ли URL мусорным (пустые ссылки на Google Calendar и т.д.)
    """
    return sanitize_url(url) is None


def prepare_events_for_feed(
    events: list[dict], with_diag: bool = False
) -> tuple[list[dict], dict] | list[dict]:
    """
    Фильтрует события для показа в ленте
    """
    kept, dropped = [], []

    for e in events:
        # Определяем тип события по источнику
        source = e.get("source", "")
        event_type = "source"  # по умолчанию

        if source == "ai_generated":
            event_type = "moment"
        elif source in ["user_created", "user"]:
            event_type = "user"
        elif source in ["event_calendars", "social_media", "popular_places"]:
            event_type = "source"

        # Добавляем поле type в событие
        e["type"] = event_type

        # Для событий из источников проверяем source_url
        if event_type == "source":
            u = sanitize_url(e.get("source_url"))
            has_loc = any(
                [
                    e.get("venue_name"),
                    e.get("address"),
                    (e.get("lat") is not None and e.get("lng") is not None),
                ]
            )
            has_time = bool(e.get("when_str"))

            if not u and not (has_loc and has_time):
                dropped.append((e, "source_without_url_and_location"))
                logger.warning(
                    "skip source invalid | title=%s url=%s reason=%s",
                    e.get("title"),
                    e.get("source_url"),
                    "source_without_url_and_location",
                )
                continue
            e["source_url"] = u  # может быть None

        kept.append(enrich_venue_name(e))

    diag = {
        "in": len(events),
        "kept": len(kept),
        "dropped": len(dropped),
        "reasons": [r for _, r in dropped],
    }

    return (kept, diag) if with_diag else kept


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
    # 1) Сначала фильтруем и группируем (после всех проверок publishable)
    prepared, diag = prepare_events_for_feed(events, with_diag=True)
    logger.info(
        f"diag: in={diag['in']} kept={diag['kept']} dropped={diag['dropped']} reasons={diag['reasons']}"
    )

    # Обогащаем события названиями мест и расстояниями
    for event in prepared:
        enrich_venue_name(event)
        event["distance_km"] = haversine_km(user_lat, user_lng, event["lat"], event["lng"])

    # 2) Группируем и считаем
    groups = group_by_type(prepared)
    counts = make_counts(groups)

    # 3) Сохраняем состояние для пагинации и расширения радиуса
    user_state[message.chat.id] = {
        "prepared": prepared,
        "counts": counts,
        "lat": user_lat,
        "lng": user_lng,
        "radius": int(settings.default_radius_km),
        "page": 1,
        "diag": diag,
    }

    # 4) Рендерим страницу
    header_html = render_header(counts)
    page_html, total_pages = render_page(prepared, page=page + 1, page_size=5)
    text = header_html + "\n\n" + page_html

    # 5) Создаем клавиатуру пагинации
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

# --- Эталонные функции для рендеринга ---


def build_maps_url(e: dict) -> str:
    """Создает URL для Google Maps с приоритетом venue_name > address > coordinates"""
    name = (e.get("venue_name") or "").strip()
    addr = (e.get("address") or "").strip()
    lat, lng = e.get("lat"), e.get("lng")
    if name:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(name)}"
    if addr:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(addr)}"
    if lat and lng:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    return "https://www.google.com/maps"


def get_source_url(e: dict) -> str | None:
    """Единая точка истины для получения URL источника"""
    t = e.get("type")
    candidates: list[str | None] = []

    if t == "source":
        candidates = [e.get("source_url")]
    elif t == "user":
        candidates = [e.get("author_url"), e.get("chat_url")]
    elif t in ("ai", "ai_generated", "moment"):
        # НЕ используем location_url, если это placeholder / example.*
        candidates = [e.get("location_url")]
    else:
        candidates = [e.get("source_url")]

    for u in candidates:
        u = sanitize_url(u)
        if u:
            return u
    return None  # нет реального источника — лучше не показывать ссылку


def render_event_html(e: dict, idx: int) -> str:
    """Рендерит одну карточку события в HTML"""
    title = html.escape(e.get("title", "Событие"))
    when = e.get("when_str", "")
    dist = f"{e['distance_km']:.1f} км" if e.get("distance_km") is not None else ""
    venue = html.escape(e.get("venue_name") or e.get("address") or "Локация уточняется")

    src = get_source_url(e)
    src_part = f'🔗 <a href="{html.escape(src)}">Источник</a>' if src else "ℹ️ Источник не указан"
    map_part = f'<a href="{build_maps_url(e)}">Маршрут</a>'

    return (
        f"{idx}) <b>{title}</b> — {when} ({dist})\n" f"📍 {venue}\n" f"{src_part}  🚗 {map_part}\n"
    )


def render_fallback(lat: float, lng: float) -> str:
    """Fallback страница при ошибках в пайплайне"""
    return (
        f"🗺 <b>Найдено рядом: 0</b>\n"
        f"• ⚡ Мгновенные: 0\n\n"
        f"1) <b>Попробуйте расширить поиск</b> — (0.0 км)\n"
        f"📍 Локация уточняется\n"
        f'ℹ️ Источник не указан  🚗 <a href="https://www.google.com/maps/search/?api=1&query={lat},{lng}">Маршрут</a>\n\n'
        f"2) <b>Создайте своё событие</b> — (0.0 км)\n"
        f"📍 Локация уточняется\n"
        f'ℹ️ Источник не указан  🚗 <a href="https://www.google.com/maps/search/?api=1&query={lat},{lng}">Маршрут</a>\n\n'
        f"3) <b>Проверьте позже</b> — (0.0 км)\n"
        f"📍 Локация уточняется\n"
        f'ℹ️ Источник не указан  🚗 <a href="https://www.google.com/maps/search/?api=1&query={lat},{lng}">Маршрут</a>'
    )


def render_page(events: list[dict], page: int, page_size: int = 5) -> tuple[str, int]:
    """
    Рендерит страницу событий
    events — уже отфильтрованные prepared (publishable) и отсортированные по distance/time
    page    — 1..N
    return: (html_text, total_pages)
    """
    if not events:
        return "Поблизости пока ничего не нашли.", 1

    total_pages = max(1, ceil(len(events) / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size

    parts = []
    for idx, e in enumerate(events[start:end], start=start + 1):
        parts.append(render_event_html(e, idx))

    return "\n".join(parts).strip(), total_pages


def kb_pager(page: int, total: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру пагинации"""
    prev_cb = f"pg:{page-1}" if page > 1 else "pg:noop"
    next_cb = f"pg:{page+1}" if page < total else "pg:noop"

    buttons = [
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data=prev_cb),
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=next_cb),
        ],
        [InlineKeyboardButton(text=f"Стр. {page}/{total}", callback_data="pg:noop")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def group_by_type(events):
    """Группирует события по типам"""
    return {
        "moment": [e for e in events if e["type"] == "moment"],
        "user": [e for e in events if e["type"] == "user"],
        "source": [e for e in events if e["type"] == "source"],
    }


def make_counts(groups):
    """Создает счетчики по группам"""
    total = sum(len(v) for v in groups.values())
    return {
        "all": total,
        "moments": len(groups["moment"]),
        "user": len(groups["user"]),
        "sources": len(groups["source"]),
    }


def render_header(counts) -> str:
    """Рендерит заголовок с счетчиками (только ненулевые)"""
    lines = [f"🗺 Найдено рядом: <b>{counts['all']}</b>"]
    if counts["moments"]:
        lines.append(f"• ⚡ Мгновенные: {counts['moments']}")
    if counts["user"]:
        lines.append(f"• 👥 От пользователей: {counts['user']}")
    if counts["sources"]:
        lines.append(f"• 🌐 Из источников: {counts['sources']}")
    return "\n".join(lines)


# --- /Эталонные функции ---

# Загружаем настройки
# Для бота — токен обязателен
settings = load_settings(require_bot=True)

# Хранилище состояния для сохранения prepared событий по chat_id
user_state = {}

# ---------- URL helpers ----------
BLACKLIST_DOMAINS = {"example.com", "example.org", "example.net"}


def sanitize_url(u: str | None) -> str | None:
    """Фильтрует мусорные URL включая example.com"""
    if not u:
        return None
    try:
        p = urlparse(u)
    except Exception:
        return None
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    host = p.netloc.lower()
    if any(host == d or host.endswith("." + d) for d in BLACKLIST_DOMAINS):
        return None
    # глушим общий календарь без конкретного события
    if "calendar.google.com" in host and "eid=" not in u:
        return None
    return u


# Инициализация базы данных
init_engine(settings.database_url)
create_all()

# Создание SSL контекста и connector для корректной работы с Telegram API
ssl_context = ssl.create_default_context(cafile=certifi.where())
connector = TCPConnector(ssl=ssl_context)

# Создание бота и диспетчера с SSL connector
session = AiohttpSession(connector=connector)
bot = Bot(token=settings.telegram_token, session=session)
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
        except Exception:
            logger.exception("❌ Ошибка при поиске событий")
            fallback = render_fallback(lat, lng)
            await message.answer(
                fallback,
                parse_mode="HTML",
                disable_web_page_preview=True,
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

        # Единый конвейер: prepared → groups → counts → render
        try:
            prepared, diag = prepare_events_for_feed(events, with_diag=True)
            logger.info(
                f"diag: in={diag['in']} kept={diag['kept']} dropped={diag['dropped']} reasons={diag['reasons']}"
            )

            # Обогащаем события названиями мест и расстояниями
            for event in prepared:
                enrich_venue_name(event)
                event["distance_km"] = haversine_km(lat, lng, event["lat"], event["lng"])

            # Группируем и считаем
            groups = group_by_type(prepared)
            counts = make_counts(groups)

            # Сохраняем состояние для пагинации и расширения радиуса
            user_state[message.chat.id] = {
                "prepared": prepared,
                "counts": counts,
                "lat": lat,
                "lng": lng,
                "radius": int(settings.default_radius_km),
                "page": 1,
                "diag": diag,
            }

            # 4) Формируем заголовок с правильным отчётом
            header_html = render_header(counts)

            # 5) Рендерим первые 3 события для карты
            page_html, _ = render_page(prepared, page=1, page_size=3)
            short_caption = header_html + "\n\n" + page_html

            if len(prepared) > 3:
                short_caption += f"\n\n... и еще {len(prepared) - 3} событий"

            short_caption += "\n\n💡 <b>Нажми кнопку ниже для Google Maps!</b>"

            # Создаём карту с нумерованными метками
            points = []
            for i, event in enumerate(prepared[:12], 1):  # Используем отфильтрованные события
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
                        logger.warning(
                            f"Событие {i}: неверные координаты ({event_lat}, {event_lng})"
                        )
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
                    maps_url = create_enhanced_google_maps_url(lat, lng, prepared[:12])

                    # Создаем кнопки для расширения радиуса, если событий мало
                    keyboard_buttons = [
                        [
                            InlineKeyboardButton(
                                text="🗺️ Открыть в Google Maps с событиями", url=maps_url
                            )
                        ]
                    ]

                    # Добавляем кнопки расширения радиуса, если событий меньше 3
                    if counts["all"] < 3:
                        keyboard_buttons.append(
                            [
                                InlineKeyboardButton(
                                    text="🔍 Расширить до 10 км", callback_data="rx:10"
                                )
                            ]
                        )
                        keyboard_buttons.append(
                            [
                                InlineKeyboardButton(
                                    text="🔍 Расширить до 15 км", callback_data="rx:15"
                                )
                            ]
                        )

                    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

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

        except Exception:
            logger.exception(
                "nearby_pipeline_failed | chat=%s lat=%s lng=%s r=%s",
                message.chat.id,
                lat,
                lng,
                int(settings.default_radius_km),
            )
            fallback = render_fallback(lat, lng)
            await message.answer(
                fallback,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=main_menu_kb(),
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


@dp.message(Command("diag_last"))
async def on_diag_last(message: types.Message):
    """Обработчик команды /diag_last для диагностики последнего запроса"""
    try:
        # Получаем состояние последнего запроса
        state = user_state.get(message.chat.id)
        if not state:
            await message.answer("Нет данных о последнем запросе. Отправьте геолокацию.")
            return

        # Формируем диагностическую информацию
        diag = state.get("diag", {})
        counts = state.get("counts", {})
        prepared = state.get("prepared", [])

        info_lines = [
            "<b>🔍 Диагностика последнего запроса</b>",
            f"<b>Координаты:</b> {state.get('lat', 'N/A')}, {state.get('lng', 'N/A')}",
            f"<b>Радиус:</b> {state.get('radius', 'N/A')} км",
            f"<b>Страница:</b> {state.get('page', 'N/A')}",
            "",
            "<b>📊 Статистика обработки:</b>",
            f"• Входных событий: {diag.get('in', 0)}",
            f"• Сохранено: {diag.get('kept', 0)}",
            f"• Отброшено: {diag.get('dropped', 0)}",
            f"• Причины отбраковки: {', '.join(diag.get('reasons', []))}",
            "",
            "<b>📈 Итоговые счетчики:</b>",
            f"• Всего: {counts.get('all', 0)}",
            f"• Мгновенные: {counts.get('moments', 0)}",
            f"• От пользователей: {counts.get('user', 0)}",
            f"• Из источников: {counts.get('sources', 0)}",
        ]

        # Показываем первые 5 событий
        if prepared:
            info_lines.extend(["", f"<b>📋 Первые {min(5, len(prepared))} событий:</b>"])
            for i, event in enumerate(prepared[:5], 1):
                event_type = event.get("type", "unknown")
                title = html.escape(event.get("title", "Без названия"))
                has_url = bool(get_source_url(event))
                info_lines.append(
                    f"{i}) <b>{title}</b> (тип: {event_type}, URL: {'да' if has_url else 'нет'})"
                )

        text = "\n".join(info_lines)
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка в команде diag_last: {e}")
        await message.answer("Произошла ошибка при получении диагностики")


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
        token = callback.data.split(":", 1)[1]
        if token == "noop":
            await callback.answer("Это крайняя страница")
            return

        page = int(token)

        # Получаем сохраненное состояние
        state = user_state.get(callback.message.chat.id)
        if not state:
            await callback.answer("Состояние не найдено. Отправьте новую геолокацию.")
            return

        prepared = state["prepared"]
        counts = state["counts"]

        # Рендерим страницу
        page_html, total_pages = render_page(prepared, page, page_size=5)

        # Обновляем сообщение
        await callback.message.edit_text(
            render_header(counts) + "\n\n" + page_html,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=kb_pager(page, total_pages),
        )

        # Обновляем состояние
        state["page"] = page
        user_state[callback.message.chat.id] = state

        await callback.answer()

    except (ValueError, IndexError) as e:
        logger.error(f"❌ Ошибка обработки пагинации: {e}")
        await callback.answer("Ошибка обработки запроса")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в пагинации: {e}")
        await callback.answer("Произошла ошибка")


@dp.callback_query(F.data.startswith("rx:"))
async def handle_expand_radius(callback: types.CallbackQuery):
    """Обработчик расширения радиуса поиска"""

    try:
        # Извлекаем новый радиус из callback_data: rx:radius
        new_radius = int(callback.data.split(":")[1])

        # Получаем сохраненное состояние
        state = user_state.get(callback.message.chat.id)
        if not state:
            await callback.answer("Состояние не найдено. Отправьте новую геолокацию.")
            return

        lat = state["lat"]
        lng = state["lng"]

        logger.info(f"🔍 Расширяем поиск до {new_radius} км от ({lat}, {lng})")

        # Ищем события с расширенным радиусом
        try:
            events = await enhanced_search_events(lat, lng, radius_km=new_radius)
            events = sort_events_by_time(events)
        except Exception as e:
            logger.error(f"❌ Ошибка при расширенном поиске: {e}")
            await callback.answer("Ошибка при поиске событий")
            return

        if not events:
            await callback.answer("События не найдены даже в расширенном радиусе")
            return

        # Фильтруем и обогащаем события
        prepared, diag = prepare_events_for_feed(events, with_diag=True)
        logger.info(
            f"diag: in={diag['in']} kept={diag['kept']} dropped={diag['dropped']} reasons={diag['reasons']}"
        )

        for event in prepared:
            enrich_venue_name(event)
            event["distance_km"] = haversine_km(lat, lng, event["lat"], event["lng"])

        # Группируем и считаем
        groups = group_by_type(prepared)
        counts = make_counts(groups)

        # Обновляем состояние
        user_state[callback.message.chat.id] = {
            "prepared": prepared,
            "counts": counts,
            "lat": lat,
            "lng": lng,
            "radius": new_radius,
            "page": 1,
            "diag": diag,
        }

        # Рендерим первую страницу
        header_html = render_header(counts)
        page_html, total_pages = render_page(prepared, page=1, page_size=5)

        # Обновляем сообщение
        await callback.message.edit_text(
            header_html + "\n\n" + page_html,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=kb_pager(1, total_pages),
        )
        await callback.answer(f"Радиус расширен до {new_radius} км")

    except (ValueError, IndexError) as e:
        logger.error(f"❌ Ошибка обработки расширения радиуса: {e}")
        await callback.answer("Ошибка обработки запроса")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в расширении радиуса: {e}")
        await callback.answer("Произошла ошибка")


async def main():
    """Главная функция"""
    logger.info("Запуск улучшенного EventBot (aiogram 3.x)...")

    # Запускаем health check сервер для Railway (только в polling режиме)
    RUN_MODE = os.getenv("BOT_RUN_MODE", "polling")
    if RUN_MODE != "webhook":
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
                types.BotCommand(
                    command="diag_last", description="📊 Диагностика последнего запроса"
                ),
            ]
        )
        logger.info("Команды бота установлены")
    except Exception as e:
        logger.warning(f"Не удалось установить команды бота: {e}")

    # Определяем режим запуска
    RUN_MODE = os.getenv("BOT_RUN_MODE", "polling")
    logger.info(f"Режим запуска: {RUN_MODE}")

    # Запускаем бота в зависимости от режима
    try:
        if RUN_MODE == "webhook":
            # Webhook режим для Railway
            WEBHOOK_URL = os.getenv("WEBHOOK_URL")
            if not WEBHOOK_URL:
                logger.error("WEBHOOK_URL не установлен для webhook режима")
                return

            # Гарантированно выключаем getUpdates на стороне Telegram
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook установлен: {WEBHOOK_URL}")

            # Запускаем webhook сервер на отдельном порту
            from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
            from aiohttp import web

            # Создаем aiohttp приложение
            app = web.Application()

            # Настраиваем webhook handler
            webhook_path = "/webhook"
            webhook_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
            )
            webhook_handler.register(app, path=webhook_path)

            # Настраиваем приложение
            setup_application(app, dp, bot=bot)

            # Добавляем health check endpoint в webhook сервер
            import time

            async def health_check(request):
                return web.json_response(
                    {
                        "status": "healthy",
                        "service": "EventBot Telegram Bot",
                        "timestamp": time.time(),
                        "uptime": "running",
                    }
                )

            app.router.add_get("/health", health_check)
            app.router.add_get("/", health_check)

            # Запускаем объединенный сервер (webhook + health check)
            port = int(os.getenv("PORT", "8000"))
            logger.info(f"Запуск объединенного сервера (webhook + health) на порту {port}")
            await web._run_app(app, host="0.0.0.0", port=port)

            logger.info("Webhook режим активирован")

        else:
            # Polling режим для локальной разработки
            # Перед стартом снимаем вебхук
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook удален, запускаем polling")

            await dp.start_polling(bot)

    except asyncio.CancelledError:
        # Штатная отмена задач при завершении — не шумим
        logger.info("Polling cancelled (shutdown).")
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем (KeyboardInterrupt).")
    finally:
        # Закрыть сетевые коннекторы аккуратно
        try:
            await dp.storage.close()
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass
        logger.info("Бот остановлен корректно.")


if __name__ == "__main__":
    asyncio.run(main())
