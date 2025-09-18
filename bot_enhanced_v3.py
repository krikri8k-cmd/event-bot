#!/usr/bin/env python3
"""
Улучшенная версия EventBot с расширенным поиском событий (aiogram 3.x)
"""

import asyncio
import html
import logging
import os
import re
from datetime import UTC, datetime
from math import ceil
from urllib.parse import quote_plus, urlparse

from aiogram import Bot, Dispatcher, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    ReplyKeyboardMarkup,
)

from config import load_settings
from database import Event, Moment, User, create_all, get_session, init_engine
from simple_status_manager import (
    auto_close_events,
    change_event_status,
    format_event_for_display,
    get_status_change_buttons,
    get_user_events,
)
from utils.geo_utils import haversine_km
from utils.static_map import build_static_map_url, fetch_static_map
from utils.unified_events_service import UnifiedEventsService


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


def is_blacklisted_url(url: str) -> bool:
    """
    Проверяет, является ли URL в черном списке доменов
    """
    if not url:
        return True
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        host = p.netloc.lower()
        return any(host == d or host.endswith("." + d) for d in BLACKLIST_DOMAINS)
    except Exception:
        return True


def prepare_events_for_feed(
    events: list[dict],
    user_point: tuple[float, float] = None,
    radius_km: float = None,
    with_diag: bool = False,
) -> tuple[list[dict], dict] | list[dict]:
    """
    Фильтрует события для показа в ленте с улучшенной диагностикой
    Поддерживает три типа событий: source, user (moments), ai_parsed
    """
    from config import load_settings
    from logging_helpers import DropStats
    from venue_enrich import enrich_venue_from_text

    settings = load_settings()
    drop = DropStats()
    kept = []
    kept_by_type = {"source": 0, "user": 0, "ai_parsed": 0}

    for e in events:
        # 0) Сначала обогащаем локацию из текста
        e = enrich_venue_from_text(e)

        # Определяем тип события согласно ТЗ
        source = e.get("source", "")
        input_type = e.get("type", "")
        event_type = "source"  # по умолчанию

        # Проверяем, является ли это моментом пользователя
        if input_type == "user" or source in ["user_created", "user"]:
            event_type = "user"
        # Проверяем, является ли это AI-парсингом
        elif input_type in ["ai", "ai_parsed", "ai_generated"] or e.get("ai_parsed") or source == "ai_parsed":
            event_type = input_type if input_type in ["ai", "ai_parsed", "ai_generated"] else "ai_parsed"
        # Все остальное - источники
        else:
            event_type = "source"

        # Добавляем поле type в событие
        e["type"] = event_type

        title = (e.get("title") or "").strip() or "—"

        # 1) Проверяем URL согласно ТЗ
        url = get_source_url(e)

        # Для ai_parsed URL обязателен
        if event_type == "ai_parsed" and not url:
            drop.add("no_url", title)
            continue

        # Для user (moments) URL не обязателен
        if event_type == "user" and not url:
            # Моменты могут не иметь URL
            pass

        # 2) Проверяем наличие локации (venue_name ИЛИ address ИЛИ coords)
        venue = e.get("venue", {})
        has_loc = any(
            [
                venue.get("name"),
                venue.get("address"),
                (venue.get("lat") is not None and venue.get("lon") is not None),
                e.get("venue_name"),
                e.get("address"),
                (e.get("lat") is not None and e.get("lng") is not None),
            ]
        )

        # Для source и ai*: пропускать события без URL И без локации
        if event_type in ["source", "ai_parsed", "ai", "ai_generated"] and not url and not has_loc:
            drop.add("source_without_url_and_location", title)
            continue

        if not has_loc:
            drop.add("no_venue_or_location", title)
            continue

        # 3) Специальные проверки для моментов пользователей
        if event_type == "user":
            # Проверяем TTL для моментов
            from datetime import UTC, datetime

            expires_utc = e.get("expires_utc")
            if expires_utc:
                if isinstance(expires_utc, str):
                    try:
                        expires_utc = datetime.fromisoformat(expires_utc.replace("Z", "+00:00"))
                    except Exception:
                        drop.add("invalid_expires_time", title)
                        continue

                if expires_utc < datetime.now(UTC):
                    drop.add("moment_expired", title)
                    continue

            # Для моментов используем специальный радиус
            moment_radius = settings.moment_max_radius_km
            if user_point and moment_radius is not None:
                # Получаем координаты события
                event_lat = None
                event_lng = None

                # Проверяем новую структуру venue
                venue = e.get("venue", {})
                if venue.get("lat") is not None and venue.get("lon") is not None:
                    event_lat = venue.get("lat")
                    event_lng = venue.get("lon")
                # Проверяем старую структуру
                elif e.get("lat") is not None and e.get("lng") is not None:
                    event_lat = e.get("lat")
                    event_lng = e.get("lng")

                if event_lat is not None and event_lng is not None:
                    # Вычисляем расстояние
                    from utils.geo_utils import haversine_km

                    distance = haversine_km(user_point[0], user_point[1], event_lat, event_lng)
                    if distance > moment_radius:
                        drop.add("moment_out_of_radius", title)
                        continue
                    # Добавляем расстояние к событию
                    e["distance_km"] = round(distance, 2)

        # 4) Проверяем радиус для обычных событий (если указан user_point и radius_km)
        elif user_point and radius_km is not None:
            # Получаем координаты события
            event_lat = None
            event_lng = None

            # Проверяем новую структуру venue
            venue = e.get("venue", {})
            if venue.get("lat") is not None and venue.get("lon") is not None:
                event_lat = venue.get("lat")
                event_lng = venue.get("lon")
            # Проверяем старую структуру
            elif e.get("lat") is not None and e.get("lng") is not None:
                event_lat = e.get("lat")
                event_lng = e.get("lng")

            if event_lat is not None and event_lng is not None:
                # Вычисляем расстояние
                from utils.geo_utils import haversine_km

                distance = haversine_km(user_point[0], user_point[1], event_lat, event_lng)
                if distance > radius_km:
                    drop.add("out_of_radius", title)
                    continue
                # Добавляем расстояние к событию
                e["distance_km"] = round(distance, 2)

        # 5) Проверяем доменные/спам-правила (только для событий с URL)
        if url and is_blacklisted_url(url):
            drop.add("blacklist_domain", title)
            continue

        # 6) Проверяем AI_GENERATE_SYNTHETIC флаг
        if event_type == "ai_parsed" and not settings.ai_generate_synthetic:
            # Если AI генерация запрещена, проверяем что у события есть валидный URL
            if not url or not sanitize_url(url):
                drop.add("ai_synthetic_blocked", title)
                continue

        # OK — оставляем событие
        e = enrich_venue_name(e)
        kept.append(e)
        kept_by_type[event_type] = kept_by_type.get(event_type, 0) + 1

    # Логируем сводку
    radius_info = (
        f"radius_km={radius_km}, user_point=({user_point[0]:.4f},{user_point[1]:.4f})"
        if user_point and radius_km is not None
        else "no_radius_filter"
    )
    logger.info(f"{drop.summary(kept_by_type=kept_by_type, total=len(events))} | {radius_info}")

    diag = {
        "in": len(events),
        "kept": len(kept),
        "dropped": sum(drop.reasons.values()),
        "found_by_stream": {
            "source": kept_by_type["source"],
            "ai_parsed": kept_by_type["ai_parsed"],
            "moments": kept_by_type["user"],
        },
        "kept_by_type": kept_by_type,
        "reasons": list(drop.reasons.keys()),
        "reasons_top3": [f"{r}({n})" for r, n in drop.reasons.most_common(3)],
    }

    return (kept, diag) if with_diag else kept


def create_events_summary(events: list) -> str:
    """
    Создает сводку по типам событий согласно ТЗ
    """
    # Подсчитываем события по типам
    source_count = sum(1 for e in events if e.get("type") == "source")
    ai_parsed_count = sum(1 for e in events if e.get("type") == "ai_parsed")
    moments_count = sum(1 for e in events if e.get("type") == "user")

    summary_lines = [f"🗺 Найдено {len(events)} событий рядом!"]

    # Показываем только ненулевые счетчики
    if source_count > 0:
        summary_lines.append(f"• Из источников: {source_count}")
    if ai_parsed_count > 0:
        summary_lines.append(f"• AI-парсинг: {ai_parsed_count}")
    if moments_count > 0:
        summary_lines.append(f"• Моменты: {moments_count}")

    return "\n".join(summary_lines)


async def send_compact_events_list(
    message: types.Message,
    events: list,
    user_lat: float,
    user_lng: float,
    page: int = 0,
    user_radius: float = None,
):
    """
    Отправляет компактный список событий с пагинацией в HTML формате
    """
    from config import load_settings

    settings = load_settings()

    # Используем радиус пользователя или дефолтный
    radius = get_user_radius(message.from_user.id, settings.default_radius_km)

    # Добавляем моменты к списку событий, если включены
    if settings.moments_enable:
        try:
            moments = await get_active_moments_nearby(user_lat, user_lng, radius)
            events.extend(moments)
            logger.info(f"Добавлено {len(moments)} моментов к {len(events) - len(moments)} событиям")
        except Exception as e:
            logger.error(f"Ошибка загрузки моментов: {e}")

    # 1) Сначала фильтруем и группируем (после всех проверок publishable)
    prepared, diag = prepare_events_for_feed(events, user_point=(user_lat, user_lng), with_diag=True)
    logger.info(f"prepared: kept={diag['kept']} dropped={diag['dropped']} reasons_top3={diag['reasons_top3']}")
    logger.info(
        f"found_by_stream: source={diag['found_by_stream']['source']} ai_parsed={diag['found_by_stream']['ai_parsed']} moments={diag['found_by_stream']['moments']}"
    )
    logger.info(
        f"kept_by_type: source={diag['kept_by_type'].get('source', 0)} user={diag['kept_by_type'].get('user', 0)} ai_parsed={diag['kept_by_type'].get('ai_parsed', 0)}"
    )

    # Обогащаем события названиями мест и расстояниями
    for event in prepared:
        enrich_venue_name(event)
        event["distance_km"] = haversine_km(user_lat, user_lng, event["lat"], event["lng"])

    # 2) Группируем и считаем
    groups = group_by_type(prepared)
    counts = make_counts(groups)

    # 3) Определяем регион пользователя
    region = "bali"  # По умолчанию Бали
    if 55.0 <= user_lat <= 60.0 and 35.0 <= user_lng <= 40.0:  # Москва
        region = "moscow"
    elif 59.0 <= user_lat <= 60.5 and 29.0 <= user_lng <= 31.0:  # СПб
        region = "spb"
    elif -9.0 <= user_lat <= -8.0 and 114.0 <= user_lng <= 116.0:  # Бали
        region = "bali"

    # 4) Сохраняем состояние для пагинации и расширения радиуса
    user_state[message.chat.id] = {
        "prepared": prepared,
        "counts": counts,
        "lat": user_lat,
        "lng": user_lng,
        "radius": int(radius),
        "page": 1,
        "diag": diag,
        "region": region,  # Добавляем регион
    }

    # 5) Рендерим страницу
    header_html = render_header(counts, radius_km=int(radius))
    page_html, total_pages = render_page(prepared, page=page + 1, page_size=5)
    text = header_html + "\n\n" + page_html

    # 6) Создаем клавиатуру пагинации с кнопками расширения радиуса
    inline_kb = kb_pager(page + 1, total_pages, int(radius)) if total_pages > 1 else None

    try:
        # Отправляем компактный список событий в HTML формате
        await message.answer(text, reply_markup=inline_kb, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"✅ Страница {page + 1} событий отправлена (HTML)")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки страницы {page + 1}: {e}")
        # Fallback - отправляем без форматирования
        await message.answer(f"📋 События (страница {page + 1} из {total_pages}):\n\n{text}", reply_markup=inline_kb)

    # Возвращаем пользователя к основному меню после отправки списка событий
    await send_main_menu(message)


async def edit_events_list_message(
    message: types.Message, events: list, user_lat: float, user_lng: float, page: int = 0
):
    """
    Редактирует сообщение со списком событий (для пагинации)
    """
    # Получаем радиус пользователя
    radius = get_user_radius(message.from_user.id, settings.default_radius_km)

    # 1) сначала фильтруем и группируем (после всех проверок publishable)
    prepared = prepare_events_for_feed(events, user_point=(user_lat, user_lng))

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
    header_html = render_header(counts, radius_km=int(radius))

    # Формируем HTML карточки событий
    event_lines = []
    for idx, event in enumerate(page_events, start=start_idx + 1):
        event_html = render_event_html(event, idx)
        event_lines.append(event_html)

    text = header_html + "\n\n" + "\n".join(event_lines)

    # Создаем клавиатуру пагинации с кнопками расширения радиуса
    inline_kb = kb_pager(page + 1, total_pages, int(radius)) if total_pages > 1 else None

    try:
        # Редактируем сообщение
        await message.edit_text(text, reply_markup=inline_kb, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"✅ Страница {page + 1} событий отредактирована (HTML)")
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования страницы {page + 1}: {e}")


async def send_detailed_events_list(message: types.Message, events: list, user_lat: float, user_lng: float):
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
    # Поддерживаем новую структуру venue и старую
    venue = e.get("venue", {})
    name = (venue.get("name") or e.get("venue_name") or "").strip()
    addr = (venue.get("address") or e.get("address") or "").strip()
    lat = venue.get("lat") or e.get("lat")
    lng = venue.get("lon") or e.get("lng")

    if name:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(name)}"
    if addr:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(addr)}"
    if lat and lng:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    return "https://www.google.com/maps"


def get_source_url(e: dict) -> str | None:
    """Единая точка истины для получения URL источника согласно ТЗ"""
    t = e.get("type")
    candidates: list[str | None] = []

    if t == "source":
        # Для источников: url > booking_url > ticket_url > source_url
        candidates = [e.get("url"), e.get("booking_url"), e.get("ticket_url"), e.get("source_url"), e.get("link")]
    elif t in ("ai", "ai_parsed", "ai_generated"):
        # Для AI-парсинга: source_url > url > original_url > location_url
        candidates = [e.get("source_url"), e.get("url"), e.get("original_url"), e.get("location_url")]
    elif t == "moment":
        # Для моментов пользователей URL не обязателен
        candidates = [e.get("author_url"), e.get("chat_url"), e.get("location_url")]
    elif t == "user":
        # Для моментов пользователей URL не обязателен
        candidates = [e.get("author_url"), e.get("chat_url")]
    else:
        # Fallback для неизвестных типов
        candidates = [e.get("source_url"), e.get("url"), e.get("link")]

    for u in candidates:
        if u:
            sanitized = sanitize_url(u)
            if sanitized:
                return sanitized
    return None  # нет реального источника — лучше не показывать ссылку


def render_event_html(e: dict, idx: int) -> str:
    """Рендерит одну карточку события в HTML согласно ТЗ"""
    title = html.escape(e.get("title", "Событие"))
    when = e.get("when_str", "")
    dist = f"{e['distance_km']:.1f} км" if e.get("distance_km") is not None else ""

    # Определяем тип события, если не установлен
    event_type = e.get("type")
    if not event_type:
        source = e.get("source", "")
        if source == "user":
            event_type = "user"
        else:
            event_type = "source"

    # Поддерживаем новую структуру venue и старую
    venue = e.get("venue", {})
    venue_name = venue.get("name") or e.get("venue_name")
    venue_address = venue.get("address") or e.get("address")

    # Приоритет: venue_name → address → coords
    if venue_name:
        venue_display = html.escape(venue_name)
    elif venue_address:
        venue_display = html.escape(venue_address)
    elif e.get("lat") and e.get("lng"):
        venue_display = f"координаты ({e['lat']:.4f}, {e['lng']:.4f})"
    else:
        venue_display = "📍 Локация уточняется"

    # Источник/Автор согласно ТЗ
    if event_type == "user":
        # Для пользовательских событий показываем автора
        author_username = e.get("organizer_username") or e.get("creator_username") or e.get("author_username")
        if author_username:
            # Создаем кликабельную ссылку на пользователя
            src_part = (
                f'👤 <a href="tg://user?id={e.get("organizer_id", "")}">Автор @{html.escape(author_username)}</a>'
            )
        else:
            # Если username нет, но есть organizer_id, показываем только ID
            organizer_id = e.get("organizer_id")
            if organizer_id:
                src_part = f'👤 <a href="tg://user?id={organizer_id}">Автор</a>'
            else:
                src_part = "👤 Автор"
    else:
        # Для источников и AI-парсинга показываем источник
        src = get_source_url(e)
        if src:
            # Извлекаем домен для красивого отображения
            from urllib.parse import urlparse

            try:
                domain = urlparse(src).netloc
                src_part = f'🔗 <a href="{html.escape(src)}">Источник ({domain})</a>'
            except Exception:
                src_part = f'🔗 <a href="{html.escape(src)}">Источник</a>'
        else:
            src_part = "ℹ️ Источник не указан"

    # Маршрут с приоритетом venue_name → address → coords
    map_part = f'🚗 <a href="{build_maps_url(e)}">Маршрут</a>'

    # Добавляем таймер для моментов
    timer_part = ""
    if event_type == "user":
        expires_utc = e.get("expires_utc")
        if expires_utc:
            from datetime import UTC, datetime

            try:
                if isinstance(expires_utc, str):
                    expires_utc = datetime.fromisoformat(expires_utc.replace("Z", "+00:00"))

                now = datetime.now(UTC)
                if expires_utc > now:
                    remaining = expires_utc - now
                    hours = int(remaining.total_seconds() // 3600)
                    minutes = int((remaining.total_seconds() % 3600) // 60)

                    if hours > 0:
                        timer_part = f" ⏳ ещё {hours}ч {minutes}м"
                    else:
                        timer_part = f" ⏳ ещё {minutes}м"
            except Exception:
                pass

    return f"{idx}) <b>{title}</b> — {when} ({dist}){timer_part}\n📍 {venue_display}\n{src_part}  {map_part}\n"


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


def kb_pager(page: int, total: int, current_radius: int = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру пагинации с кнопками расширения радиуса"""
    from config import load_settings

    settings = load_settings()

    prev_cb = f"pg:{page - 1}" if page > 1 else "pg:noop"
    next_cb = f"pg:{page + 1}" if page < total else "pg:noop"

    buttons = [
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data=prev_cb),
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=next_cb),
        ],
        [InlineKeyboardButton(text=f"Стр. {page}/{total}", callback_data="pg:noop")],
    ]

    # Добавляем кнопки расширения радиуса, если текущий радиус меньше максимального
    if current_radius is None:
        current_radius = int(settings.default_radius_km)

    radius_step = int(settings.radius_step_km)
    max_radius = int(settings.max_radius_km)

    # Добавляем кнопки расширения радиуса
    next_radius = current_radius + radius_step
    while next_radius <= max_radius:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🔍 Расширить до {next_radius} км",
                    callback_data=f"rx:{next_radius}",
                )
            ]
        )
        next_radius += radius_step

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def group_by_type(events):
    """Группирует события по типам согласно ТЗ"""
    return {
        "source": [e for e in events if e.get("type") == "source"],
        "user": [e for e in events if e.get("type") == "user"],
        "ai_parsed": [e for e in events if e.get("type") == "ai_parsed"],
        "ai": [e for e in events if e.get("type") == "ai"],
        "ai_generated": [e for e in events if e.get("type") == "ai_generated"],
    }


def make_counts(groups):
    """Создает счетчики по группам"""
    total = sum(len(v) for v in groups.values())
    ai_count = len(groups.get("ai", [])) + len(groups.get("ai_parsed", [])) + len(groups.get("ai_generated", []))
    return {
        "all": total,
        "moments": len(groups.get("user", [])),  # Моменты хранятся в ключе "user"
        "user": len(groups.get("user", [])),
        "sources": len(groups.get("source", [])) + ai_count,  # AI события считаются как источники
    }


def render_header(counts, radius_km: int = None) -> str:
    """Рендерит заголовок с счетчиками (только ненулевые)"""
    if radius_km:
        lines = [f"🗺 В радиусе {radius_km} км найдено: <b>{counts['all']}</b>"]
    else:
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

# ---------- Радиус поиска ----------
RADIUS_OPTIONS = (5, 10, 15, 20)
CB_RADIUS_PREFIX = "rx:"  # callback_data вроде "rx:10"
RADIUS_KEY = "radius_km"


def get_user_radius(user_id: int, default_km: int) -> int:
    """Получает радиус пользователя из состояния или возвращает дефолтный"""
    state = user_state.get(user_id) or {}
    value = state.get(RADIUS_KEY)
    return int(value) if isinstance(value, int | float | str) and str(value).isdigit() else default_km


def set_user_radius(user_id: int, radius_km: int) -> None:
    """Устанавливает радиус пользователя в состоянии"""
    st = user_state.setdefault(user_id, {})
    st[RADIUS_KEY] = int(radius_km)


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
    # Разрешаем Google Calendar ссылки с параметрами события
    if "calendar.google.com" in host:
        # Проверяем наличие параметров события
        if any(param in u for param in ["eid=", "event=", "cid="]):
            return u
        # Отбрасываем пустые календарные ссылки
        return None
    return u


# Функции для работы с моментами
async def check_daily_limit(user_id: int) -> tuple[bool, int]:
    """Проверяет, не превышен ли дневной лимит моментов для пользователя"""
    from datetime import UTC, datetime

    from config import load_settings

    settings = load_settings()

    with get_session() as session:
        # Получаем начало текущего дня по UTC
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        # Считаем моменты, созданные сегодня
        count = (
            session.query(Moment)
            .filter(
                Moment.user_id == user_id,
                Moment.created_at >= today_start,
                Moment.is_active is True,
            )
            .count()
        )

        return count < settings.moment_daily_limit, count


async def create_moment(user_id: int, username: str, title: str, lat: float, lng: float, ttl_minutes: int) -> Moment:
    """Создает новый момент пользователя с проверкой лимитов"""
    from datetime import UTC, datetime, timedelta

    from config import load_settings

    settings = load_settings()

    # Проверяем дневной лимит
    can_create, current_count = await check_daily_limit(user_id)
    if not can_create:
        raise ValueError(f"Достигнут лимит: {settings.moment_daily_limit} момента в день")

    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)

    with get_session() as session:
        moment = Moment(
            user_id=user_id,
            username=username,
            title=title,
            location_lat=lat,
            location_lng=lng,
            created_at=datetime.now(UTC),
            expires_at=expires_at,
            is_active=True,
            # Legacy поля для совместимости
            template=title,
            text=title,
            lat=lat,
            lng=lng,
            created_utc=datetime.now(UTC),
            expires_utc=expires_at,
            status="open",
        )
        session.add(moment)
        session.commit()
        session.refresh(moment)
        return moment


async def get_active_moments_nearby(lat: float, lng: float, radius_km: float = None) -> list[dict]:
    """Получает активные моменты рядом с координатами"""
    from datetime import UTC, datetime

    from config import load_settings

    settings = load_settings()
    if radius_km is None:
        radius_km = settings.moment_max_radius_km

    with get_session() as session:
        # Получаем все активные моменты
        moments = session.query(Moment).filter(Moment.is_active is True, Moment.expires_at > datetime.now(UTC)).all()

        # Фильтруем по радиусу и конвертируем в формат событий
        nearby_moments = []
        for moment in moments:
            # Используем новые поля, fallback на legacy
            moment_lat = moment.location_lat or moment.lat
            moment_lng = moment.location_lng or moment.lng

            if moment_lat and moment_lng:
                distance = haversine_km(lat, lng, moment_lat, moment_lng)
                if distance <= radius_km:
                    # Используем username из момента или из User
                    creator_username = moment.username
                    if not creator_username:
                        try:
                            creator = session.get(User, moment.user_id)
                            if creator and creator.username:
                                creator_username = creator.username
                        except Exception:
                            pass

                    # Конвертируем момент в формат события
                    event_dict = {
                        "id": f"moment_{moment.id}",
                        "type": "user",
                        "title": moment.title or moment.template or "Момент",
                        "description": moment.text or moment.title,
                        "lat": moment_lat,
                        "lng": moment_lng,
                        "venue": {"lat": moment_lat, "lon": moment_lng},
                        "creator_id": moment.user_id,
                        "creator_username": creator_username,
                        "expires_utc": (moment.expires_at or moment.expires_utc).isoformat(),
                        "created_utc": (moment.created_at or moment.created_utc).isoformat(),
                        "distance_km": round(distance, 2),
                        "when_str": "сейчас",
                        "source": "user_created",
                    }
                    nearby_moments.append(event_dict)

        return nearby_moments


async def cleanup_expired_moments():
    """Очищает истекшие моменты"""
    from datetime import UTC, datetime

    try:
        with get_session() as session:
            # Проверяем существование поля is_active
            try:
                # Деактивируем истекшие моменты
                expired_count = (
                    session.query(Moment)
                    .filter(Moment.is_active is True, Moment.expires_at < datetime.now(UTC))
                    .update({"is_active": False})
                )
                session.commit()
                logger.info(f"Очистка моментов: деактивировано {expired_count}")
                return expired_count
            except Exception as e:
                if "column" in str(e) and "is_active" in str(e):
                    logger.warning("⚠️ Поле is_active не существует, пропускаем очистку")
                    return 0
                else:
                    raise
    except Exception as e:
        logger.error(f"❌ Ошибка очистки моментов: {e}")
        return 0


# Инициализация базы данных
init_engine(settings.database_url)
create_all()

# Health check сервер будет запущен в main() вместе с webhook

# Создание бота и диспетчера
bot = Bot(token=settings.telegram_token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния для FSM
class EventCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_location_type = State()  # Выбор типа локации
    waiting_for_location_link = State()  # Ввод ссылки Google Maps
    waiting_for_location = State()  # Legacy - для обратной совместимости
    waiting_for_description = State()
    confirmation = State()


class MomentCreation(StatesGroup):
    waiting_for_template = State()
    waiting_for_custom_title = State()
    waiting_for_location = State()
    location_confirmed = State()
    waiting_for_ttl = State()
    preview_confirmed = State()


class EventEditing(StatesGroup):
    choosing_field = State()
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_location = State()
    waiting_for_description = State()


def edit_event_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для редактирования события"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📌 Название", callback_data=f"edit_title_{event_id}")],
            [InlineKeyboardButton(text="📅 Дата", callback_data=f"edit_date_{event_id}")],
            [InlineKeyboardButton(text="⏰ Время", callback_data=f"edit_time_{event_id}")],
            [InlineKeyboardButton(text="📍 Локация", callback_data=f"edit_location_{event_id}")],
            [InlineKeyboardButton(text="📝 Описание", callback_data=f"edit_description_{event_id}")],
            [InlineKeyboardButton(text="✅ Завершить", callback_data=f"edit_finish_{event_id}")],
        ]
    )


def update_event_field(event_id: int, field: str, value: str, user_id: int) -> bool:
    """Обновляет поле события в базе данных"""
    from datetime import datetime

    try:
        with get_session() as session:
            # Проверяем, что событие принадлежит пользователю
            event = session.query(Event).filter(Event.id == event_id, Event.organizer_id == user_id).first()

            if not event:
                logging.warning(f"Событие {event_id} не найдено или не принадлежит пользователю {user_id}")
                return False

            # Обновляем поле
            if field == "title":
                event.title = value
                logging.info(f"Обновлено название события {event_id}: '{value}'")
            elif field == "starts_at":
                # Для даты/времени нужно парсить
                try:
                    if " " in value:
                        # Полная дата и время
                        event.starts_at = datetime.strptime(value, "%d.%m.%Y %H:%M")
                    else:
                        # Только дата - сохраняем существующее время
                        new_date = datetime.strptime(value, "%d.%m.%Y")
                        if event.starts_at:
                            # Сохраняем существующее время
                            existing_time = event.starts_at.time()
                            event.starts_at = new_date.replace(
                                hour=existing_time.hour, minute=existing_time.minute, second=existing_time.second
                            )
                        else:
                            # Если времени не было, устанавливаем 00:00
                            event.starts_at = new_date
                    logging.info(f"Обновлена дата события {event_id}: '{value}'")
                except ValueError as ve:
                    logging.error(f"Ошибка парсинга даты '{value}': {ve}")
                    return False
            elif field == "location_name":
                event.location_name = value
                logging.info(f"Обновлена локация события {event_id}: '{value}'")
            elif field == "description":
                event.description = value
                logging.info(f"Обновлено описание события {event_id}: '{value}'")
            else:
                logging.error(f"Неизвестное поле для обновления: {field}")
                return False

            event.updated_at_utc = datetime.now(UTC)
            session.commit()
            logging.info(f"Событие {event_id} успешно обновлено в БД")
            return True

    except Exception as e:
        logging.error(f"Ошибка обновления события {event_id}: {e}")
        return False


async def send_main_menu(message_or_callback, text: str = "🏠 Выберите действие:"):
    """Отправляет главное меню пользователю"""
    if hasattr(message_or_callback, "message"):
        # Это callback query
        await message_or_callback.message.answer(text, reply_markup=main_menu_kb())
    else:
        # Это обычное сообщение
        await message_or_callback.answer(text, reply_markup=main_menu_kb())


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Создаёт главное меню"""
    from config import load_settings

    settings = load_settings()

    keyboard = [
        [KeyboardButton(text="📍 Что рядом"), KeyboardButton(text="➕ Создать")],
    ]

    # Добавляем кнопку для моментов, если они включены
    if settings.moments_enable:
        keyboard.append([KeyboardButton(text="⚡ Создать Момент")])

    keyboard.extend(
        [
            [KeyboardButton(text="📋 Мои события"), KeyboardButton(text="🔗 Поделиться")],
            [KeyboardButton(text="🔧 Настройки радиуса"), KeyboardButton(text="❓ Помощь")],
            [KeyboardButton(text="🚀 Старт")],
        ]
    )

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def kb_radius(current: int | None = None) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора радиуса поиска с выделением текущего"""
    buttons = []
    for km in RADIUS_OPTIONS:
        label = f"{'✅ ' if km == current else ''}{km} км"
        buttons.append(InlineKeyboardButton(text=label, callback_data=f"{CB_RADIUS_PREFIX}{km}"))
    # одна строка из 4 кнопок
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def radius_selection_kb() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора радиуса поиска (legacy)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 5 км", callback_data="radius:5"),
                InlineKeyboardButton(text="🔍 10 км", callback_data="radius:10"),
                InlineKeyboardButton(text="🔍 15 км", callback_data="radius:15"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="radius:cancel")],
        ]
    )


@dp.message(F.text == "🔧 Настройки радиуса")
async def cmd_radius_settings(message: types.Message):
    """Обработчик настройки радиуса поиска"""
    user_id = message.from_user.id

    # Получаем текущий радиус пользователя из состояния или БД
    current_radius = get_user_radius(user_id, settings.default_radius_km)

    await message.answer(
        f"🔧 **Настройки радиуса поиска**\n\n"
        f"Текущий радиус: **{current_radius} км**\n\n"
        f"Выбери новый радиус для поиска событий:",
        parse_mode="Markdown",
        reply_markup=kb_radius(current_radius),
    )


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

    # Логируем получение геолокации
    logger.info(f"📍 Получена геолокация пользователя: lat={lat} lon={lng} (источник=пользователь)")

    # Показываем индикатор загрузки
    loading_message = await message.answer(
        "🔍 Ищу события рядом...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍", callback_data="loading")]]),
    )

    try:
        # Обновляем геолокацию пользователя и получаем его радиус
        radius = get_user_radius(message.from_user.id, settings.default_radius_km)
        with get_session() as session:
            user = session.get(User, message.from_user.id)
            if user:
                user.last_lat = lat
                user.last_lng = lng
                user.last_geo_at_utc = datetime.now(UTC)
                session.commit()

        # Логируем параметры поиска
        logger.info(f"🔎 Поиск с координатами=({lat}, {lng}) радиус={radius}км источник=пользователь")

        # Ищем события из всех источников
        try:
            logger.info(f"🔍 Начинаем поиск событий для координат ({lat}, {lng}) с радиусом {radius} км")

            # Используем новую упрощенную архитектуру
            from database import get_engine
            from utils.simple_timezone import get_city_from_coordinates

            engine = get_engine()
            events_service = UnifiedEventsService(engine)

            # Определяем город по координатам
            city = get_city_from_coordinates(lat, lng)
            logger.info(f"🌍 Определен город: {city}")

            # Ищем события
            events = events_service.search_events_today(city=city, user_lat=lat, user_lng=lng, radius_km=int(radius))

            # Конвертируем в старый формат для совместимости
            formatted_events = []
            for event in events:
                formatted_events.append(
                    {
                        "title": event["title"],
                        "description": event["description"],
                        "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M"),
                        "location_name": event["location_name"],
                        "location_url": event["location_url"],
                        "lat": event["lat"],
                        "lng": event["lng"],
                        "source": event["source_type"],
                        "url": event.get("event_url", ""),
                        "community_name": "",
                        "community_link": "",
                        # Добавляем поля автора для пользовательских событий
                        "organizer_id": event.get("organizer_id"),
                        "organizer_username": event.get("organizer_username"),
                    }
                )

            events = formatted_events
            logger.info(f"✅ Поиск завершен, найдено {len(events)} событий")
        except Exception:
            logger.exception("❌ Ошибка при поиске событий")
            # Удаляем сообщение загрузки при ошибке
            try:
                await loading_message.delete()
            except Exception:
                pass
            fallback = render_fallback(lat, lng)
            await message.answer(
                fallback,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=main_menu_kb(),
            )
            return

        # Сортируем события по времени (ближайшие первыми)
        events = sort_events_by_time(events)
        logger.info("📅 События отсортированы по времени")

        # Единый конвейер: prepared → groups → counts → render
        try:
            prepared, diag = prepare_events_for_feed(
                events, user_point=(lat, lng), radius_km=int(radius), with_diag=True
            )
            logger.info(f"prepared: kept={diag['kept']} dropped={diag['dropped']} reasons_top3={diag['reasons_top3']}")
            logger.info(
                f"kept_by_type: ai={diag['kept_by_type'].get('ai_parsed', 0)} user={diag['kept_by_type'].get('user', 0)} source={diag['kept_by_type'].get('source', 0)}"
            )

            # Обогащаем события названиями мест (расстояния уже вычислены в prepare_events_for_feed)
            for event in prepared:
                enrich_venue_name(event)

            # Группируем и считаем
            groups = group_by_type(prepared)
            counts = make_counts(groups)

            # Проверяем, есть ли события после фильтрации
            if not prepared:
                logger.info("📭 События не найдены после фильтрации")

                # Создаем кнопки расширения радиуса
                keyboard_buttons = []
                current_radius = int(radius)
                radius_step = int(settings.radius_step_km)
                max_radius = int(settings.max_radius_km)

                # Добавляем кнопки расширения радиуса
                next_radius = current_radius + radius_step
                while next_radius <= max_radius:
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(
                                text=f"🔍 Расширить поиск до {next_radius} км",
                                callback_data=f"rx:{next_radius}",
                            )
                        ]
                    )
                    next_radius += radius_step

                # Добавляем кнопку создания события
                keyboard_buttons.append(
                    [
                        InlineKeyboardButton(
                            text="➕ Создать событие",
                            callback_data="create_event",
                        )
                    ]
                )

                inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

                # Удаляем сообщение загрузки
                try:
                    await loading_message.delete()
                except Exception:
                    pass

                # Определяем регион пользователя
                region = "bali"  # По умолчанию Бали
                if 55.0 <= lat <= 60.0 and 35.0 <= lng <= 40.0:  # Москва
                    region = "moscow"
                elif 59.0 <= lat <= 60.5 and 29.0 <= lng <= 31.0:  # СПб
                    region = "spb"
                elif -9.0 <= lat <= -8.0 and 114.0 <= lng <= 116.0:  # Бали
                    region = "bali"

                # Сохраняем состояние даже когда событий нет
                user_state[message.chat.id] = {
                    "prepared": [],
                    "counts": {},
                    "lat": lat,
                    "lng": lng,
                    "radius": int(current_radius),
                    "page": 1,
                    "diag": diag,
                    "region": region,
                }
                logger.info(
                    f"💾 Состояние сохранено для пользователя {message.chat.id}: lat={lat}, lng={lng}, radius={current_radius}, region={region}"
                )

                await message.answer(
                    f"📅 В радиусе {current_radius} км событий на сегодня не найдено.\n\n"
                    f"💡 Попробуй расширить поиск до {current_radius + int(settings.radius_step_km)} км или создай своё событие!",
                    reply_markup=inline_kb,
                )

                # Возвращаем основное меню
                await send_main_menu(message)
                return

            # Сохраняем состояние для пагинации и расширения радиуса
            user_state[message.chat.id] = {
                "prepared": prepared,
                "counts": counts,
                "lat": lat,
                "lng": lng,
                "radius": int(radius),
                "page": 1,
                "diag": diag,
            }
            logger.info(
                f"💾 Состояние сохранено для пользователя {message.chat.id}: lat={lat}, lng={lng}, radius={radius}"
            )

            # 4) Формируем заголовок с правильным отчётом
            header_html = render_header(counts, radius_km=int(radius))

            # 5) Рендерим первые 3 события для карты
            page_html, _ = render_page(prepared, page=1, page_size=3)
            short_caption = header_html + "\n\n" + page_html

            if len(prepared) > 3:
                short_caption += f"\n\n... и еще {len(prepared) - 3} событий"

            short_caption += "\n\n💡 <b>Нажми кнопку ниже для Google Maps!</b>"

            # Добавляем подсказку о расширении поиска, если событий мало
            if counts["all"] < 5:
                next_radius = int(radius) + int(settings.radius_step_km)
                short_caption += f"\n🔍 <i>Можно расширить поиск до {next_radius} км</i>"

            # Создаём карту с нумерованными метками
            points = []
            for i, event in enumerate(prepared[:12], 1):  # Используем отфильтрованные события
                event_lat = event.get("lat")
                event_lng = event.get("lng")

                # Проверяем что координаты валидные
                if event_lat is not None and event_lng is not None:
                    if -90 <= event_lat <= 90 and -180 <= event_lng <= 180:
                        points.append((str(i), event_lat, event_lng))  # Метки 1, 2, 3
                        logger.info(f"Событие {i}: {event['title']} - координаты ({event_lat:.6f}, {event_lng:.6f})")
                    else:
                        logger.warning(f"Событие {i}: неверные координаты ({event_lat}, {event_lng})")
                else:
                    logger.warning(f"Событие {i}: отсутствуют координаты")

            # УНИВЕРСАЛЬНЫЙ ФОЛБЭК: пробуем карту, если не получается - отправляем без неё

            # Создаем расширенную ссылку на Google Maps с информацией о событиях
            maps_url = create_enhanced_google_maps_url(lat, lng, prepared[:12])

            # Создаем кнопки для расширения радиуса
            keyboard_buttons = [[InlineKeyboardButton(text="🗺️ Открыть в Google Maps с событиями", url=maps_url)]]

            # Всегда добавляем кнопки расширения радиуса для лучшего UX
            current_radius = int(settings.default_radius_km)
            radius_step = int(settings.radius_step_km)
            max_radius = int(settings.max_radius_km)

            # Создаем кнопки для расширения радиуса
            next_radius = current_radius + radius_step
            while next_radius <= max_radius:
                keyboard_buttons.append(
                    [
                        InlineKeyboardButton(
                            text=f"🔍 Расширить до {next_radius} км",
                            callback_data=f"rx:{next_radius}",
                        )
                    ]
                )
                next_radius += radius_step

            inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            # Пробуем получить изображение карты (с circuit breaker)
            map_bytes = None
            if settings.google_maps_api_key and points:
                # Конвертируем points в нужный формат для новой функции
                event_points = [(p[1], p[2]) for p in points]  # (lat, lng)
                map_bytes = await fetch_static_map(
                    build_static_map_url(lat, lng, event_points, settings.google_maps_api_key)
                )

            # Короткая подпись для карты/сообщения
            caption = f"🗺️ **В радиусе {radius} км найдено: {len(events)}**\n"
            caption += f"• 🌟 Мгновенные: {counts.get('moments', 0)}\n"
            caption += f"• 👥 От пользователей: {counts.get('user', 0)}\n"
            caption += f"• 🌐 Из источников: {counts.get('source', 0)}"

            # Удаляем сообщение загрузки
            try:
                await loading_message.delete()
            except Exception:
                pass

            # Отправляем ответ (с картой или без)
            try:
                if map_bytes:
                    # Отправляем с изображением карты
                    from aiogram.types import BufferedInputFile

                    map_file = BufferedInputFile(map_bytes, filename="map.png")
                    await message.answer_photo(
                        map_file,
                        caption=caption,
                        reply_markup=inline_kb,
                        parse_mode="HTML",
                    )
                    logger.info("✅ Карта отправлена успешно")
                else:
                    # Отправляем без карты (graceful fallback)
                    await message.answer(
                        caption,
                        reply_markup=inline_kb,
                        parse_mode="HTML",
                    )
                    logger.info("✅ События отправлены без карты (graceful fallback)")

                # Отправляем компактный список событий отдельным сообщением
                try:
                    await send_compact_events_list(message, events, lat, lng, page=0, user_radius=radius)
                    logger.info("✅ Компактный список событий отправлен")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки компактного списка: {e}")
                    # Fallback - отправляем краткий список
                    await message.answer(
                        f"📋 **Все {len(events)} событий:**\n\n"
                        f"💡 Нажми кнопку '🗺️ Открыть в Google Maps с событиями' выше "
                        f"чтобы увидеть полную информацию о каждом событии!",
                        parse_mode="Markdown",
                        reply_markup=main_menu_kb(),
                    )

            except Exception as e:
                logger.error(f"❌ Ошибка отправки ответа: {e}")
                # Критический fallback - простое сообщение
                await message.answer(
                    f"📋 Найдено {len(events)} событий в радиусе {radius} км", reply_markup=main_menu_kb()
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
        await message.answer("Произошла ошибка при поиске событий. Попробуйте позже.", reply_markup=main_menu_kb())


@dp.message(Command("create"))
@dp.message(F.text == "➕ Создать")
async def on_create(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Создать'"""
    await state.set_state(EventCreation.waiting_for_title)
    await message.answer(
        "Создаём новое событие! 📝\n\n✍ Введите название мероприятия (например: Прогулка):",
        reply_markup=types.ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True),
    )


@dp.message(F.text == "❌ Отмена")
async def cancel_creation(message: types.Message, state: FSMContext):
    """Отмена создания события"""
    await state.clear()
    await message.answer("Создание отменено.", reply_markup=main_menu_kb())


@dp.message(Command("myevents"))
@dp.message(F.text == "📋 Мои события")
async def on_my_events(message: types.Message):
    """Обработчик кнопки 'Мои события' с управлением статусами"""
    user_id = message.from_user.id

    # Автомодерация: закрываем прошедшие события
    closed_count = auto_close_events()
    if closed_count > 0:
        await message.answer(f"🤖 Автоматически закрыто {closed_count} прошедших событий")

    # Получаем события пользователя
    events = get_user_events(user_id)

    if not events:
        await message.answer(
            "У вас пока нет созданных событий. Создайте первое через '➕ Создать'!",
            reply_markup=main_menu_kb(),
        )
        return

    # Отправляем первое событие с кнопками управления
    if events:
        first_event = events[0]
        text = f"📋 **Ваши события:**\n\n{format_event_for_display(first_event)}"

        # Создаем кнопки управления
        buttons = get_status_change_buttons(first_event["id"], first_event["status"])
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
            ]
        )

        # Добавляем кнопку "Следующее событие" если есть еще события
        if len(events) > 1:
            keyboard.inline_keyboard.append([InlineKeyboardButton(text="➡️ Следующее", callback_data="next_event_1")])

        await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


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


@dp.message(Command("diag_webhook"))
async def on_diag_webhook(message: types.Message):
    """Диагностика webhook"""
    try:
        # Получаем информацию о webhook
        webhook_info = await bot.get_webhook_info()

        # Получаем переменные окружения
        run_mode = os.getenv("BOT_RUN_MODE", "webhook")
        webhook_url = os.getenv("WEBHOOK_URL", "не установлен")

        info_lines = [
            "🔗 <b>Диагностика Webhook</b>",
            "",
            f"<b>Режим запуска:</b> {run_mode}",
            f"<b>WEBHOOK_URL:</b> {webhook_url}",
            f"<b>Текущий webhook:</b> {webhook_info.url or 'пустой'}",
            f"<b>Pending updates:</b> {webhook_info.pending_update_count}",
            f"<b>Has custom certificate:</b> {webhook_info.has_custom_certificate}",
            f"<b>Allowed updates:</b> {', '.join(webhook_info.allowed_updates) if webhook_info.allowed_updates else 'все'}",
        ]

        await message.answer("\n".join(info_lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в диагностике webhook: {e}")
        await message.answer(f"❌ Ошибка диагностики: {e}")


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
        state.get("counts", {})
        prepared = state.get("prepared", [])

        found_by_stream = diag.get("found_by_stream", {})
        kept_by_type = diag.get("kept_by_type", {})

        info_lines = [
            "<b>🔍 Диагностика последнего запроса</b>",
            f"<b>Координаты:</b> {state.get('lat', 'N/A')}, {state.get('lng', 'N/A')}",
            f"<b>Радиус:</b> {state.get('radius', 'N/A')} км",
            f"<b>Страница:</b> {state.get('page', 'N/A')}",
            "",
            "<b>📊 Статистика по потокам:</b>",
            f"• found_by_stream: source={found_by_stream.get('source', 0)}, ai_parsed={found_by_stream.get('ai_parsed', 0)}, moments={found_by_stream.get('moments', 0)}",
            f"• kept_by_type: source={kept_by_type.get('source', 0)}, ai_parsed={kept_by_type.get('ai_parsed', 0)}, user={kept_by_type.get('user', 0)}",
            f"• dropped: {diag.get('dropped', 0)}, top_reasons={diag.get('reasons_top3', [])}",
            "",
        ]

        # Показываем первые 5 событий с детальной диагностикой согласно ТЗ
        if prepared:
            info_lines.extend(["", f"<b>📋 Последние {min(5, len(prepared))} карточек:</b>"])
            for i, event in enumerate(prepared[:5], 1):
                event_type = event.get("type", "unknown")
                title = html.escape(event.get("title", "Без названия"))
                when = event.get("when_str", "Не указано")

                # Определяем источник согласно ТЗ
                if event_type == "user":
                    # Для моментов показываем автора
                    author_username = event.get("creator_username")
                    source_info = f"автор-юзер @{author_username}" if author_username else "автор-юзер"
                else:
                    # Для источников и AI - домен источника
                    url = get_source_url(event)
                    if url:
                        try:
                            from urllib.parse import urlparse

                            domain = urlparse(url).netloc
                            source_info = f"домен {domain}"
                        except Exception:
                            source_info = "домен неизвестен"
                    else:
                        source_info = "без источника"

                # Определяем подтверждение локации
                venue = event.get("venue", {})
                if venue.get("name") or event.get("venue_name"):
                    location_info = "venue"
                elif venue.get("address") or event.get("address"):
                    location_info = "address"
                elif venue.get("lat") or event.get("lat"):
                    location_info = "coords"
                else:
                    location_info = "нет локации"

                info_lines.append(f"{i}) <b>{title}</b>")
                info_lines.append(
                    f"   тип: {event_type}, время: {when}, {source_info}, чем подтверждена локация: {location_info}"
                )

        # Добавляем информацию о моментах и лимитах
        from config import load_settings

        settings = load_settings()

        if settings.moments_enable:
            info_lines.extend(
                [
                    "",
                    "<b>⚡ Моменты:</b>",
                    f"• всего активных: {len([e for e in prepared if e.get('type') == 'user'])}",
                    f"• лимит на пользователя: {settings.moment_daily_limit}/день",
                    f"• TTL варианты: {', '.join(map(str, settings.moment_ttl_options))} мин",
                ]
            )

            # Показываем моменты с деталями
            moments = [e for e in prepared if e.get("type") == "user"]
            if moments:
                info_lines.extend(["", "<b>📋 Активные моменты:</b>"])
                for moment in moments[:3]:  # Показываем первые 3
                    author = moment.get("creator_username", "Аноним")
                    title = moment.get("title", "Момент")
                    expires = moment.get("expires_utc")
                    if expires:
                        try:
                            from datetime import datetime

                            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                            now = datetime.now(exp_dt.tzinfo)
                            remaining = exp_dt - now
                            hours = int(remaining.total_seconds() // 3600)
                            minutes = int((remaining.total_seconds() % 3600) // 60)
                            time_left = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
                        except Exception:
                            time_left = "неизвестно"
                    else:
                        time_left = "неизвестно"

                    lat = moment.get("lat", 0)
                    lng = moment.get("lng", 0)
                    info_lines.append(f'👤 @{author} | "{title}" | ещё {time_left} | ({lat:.4f}, {lng:.4f})')

        # Показываем первое отброшенное source событие для диагностики
        if diag.get("dropped", 0) > 0:
            info_lines.extend(["", "<b>🔍 Диагностика отброшенных событий:</b>"])
            # Здесь можно добавить логику для показа первого отброшенного события
            info_lines.append("• Проверьте логи для детальной информации об отброшенных событиях")

        text = "\n".join(info_lines)
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка в команде diag_last: {e}")
        await message.answer("Произошла ошибка при получении диагностики")


@dp.message(Command("diag_all"))
async def on_diag_all(message: types.Message):
    """Обработчик команды /diag_all для полной диагностики системы"""
    try:
        with get_session() as session:
            # Получаем статистику событий за последние 24 часа
            from datetime import UTC, datetime, timedelta

            now = datetime.now(UTC)
            yesterday = now - timedelta(hours=24)

            # События по типам за 24ч
            source_events = (
                session.query(Event).filter(Event.created_at_utc >= yesterday, Event.source.isnot(None)).count()
            )

            user_events = (
                session.query(Event)
                .filter(
                    Event.created_at_utc >= yesterday,
                    Event.source.is_(None),
                    Event.organizer_id.isnot(None),
                )
                .count()
            )

            ai_events = (
                session.query(Event).filter(Event.created_at_utc >= yesterday, Event.is_generated_by_ai is True).count()
            )

            # Активные моменты
            active_moments = session.query(Moment).filter(Moment.is_active is True, Moment.expires_at > now).count()

            # Истекшие моменты
            expired_moments = session.query(Moment).filter(Moment.is_active is True, Moment.expires_at <= now).count()

            # Общее количество событий
            total_events = session.query(Event).count()
            total_moments = session.query(Moment).count()

            # Получаем список активных источников
            sources = session.query(Event.source).filter(Event.source.isnot(None)).distinct().all()

            source_list = [s[0] for s in sources if s[0]]

            # Формируем диагностическую информацию
            info_lines = [
                "<b>🔍 Полная диагностика системы</b>",
                "",
                "<b>📊 События за последние 24ч:</b>",
                f"• Внешние источники: {source_events}",
                f"• Пользовательские: {user_events}",
                f"• AI-сгенерированные: {ai_events}",
                f"• Всего: {source_events + user_events + ai_events}",
                "",
                "<b>⚡ Моменты:</b>",
                f"• Активные: {active_moments}",
                f"• Истекшие (требуют очистки): {expired_moments}",
                f"• Всего в БД: {total_moments}",
                "",
                "<b>📈 Общая статистика:</b>",
                f"• Всего событий в БД: {total_events}",
                f"• Всего моментов в БД: {total_moments}",
                "",
                "<b>🔗 Активные источники:</b>",
            ]

            if source_list:
                for source in sorted(source_list)[:10]:  # Показываем первые 10
                    info_lines.append(f"• {source}")
                if len(source_list) > 10:
                    info_lines.append(f"• ... и еще {len(source_list) - 10}")
            else:
                info_lines.append("• Нет активных источников")

            # Добавляем информацию о конфигурации
            settings = load_settings()
            info_lines.extend(
                [
                    "",
                    "<b>⚙️ Конфигурация:</b>",
                    f"• Моменты включены: {'✅' if settings.moments_enable else '❌'}",
                    f"• AI парсинг: {'✅' if settings.ai_parse_enable else '❌'}",
                    f"• Meetup API: {'✅' if settings.enable_meetup_api else '❌'}",
                    f"• ICS календари: {'✅' if settings.enable_ics_feeds else '❌'}",
                    f"• Eventbrite API: {'✅' if settings.enable_eventbrite_api else '❌'}",
                    f"• Радиус по умолчанию: {settings.default_radius_km}км",
                    f"• Макс. радиус: {settings.max_radius_km}км",
                ]
            )

            await message.answer("\n".join(info_lines))

    except Exception as e:
        logger.error(f"Ошибка в команде diag_all: {e}")
        await message.answer("Произошла ошибка при получении диагностики")


@dp.message(Command("diag_search"))
async def on_diag_search(message: types.Message):
    """Обработчик команды /diag_search для диагностики поиска"""
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

        # Получаем информацию о пользователе
        lat = state.get("lat", "N/A")
        lng = state.get("lng", "N/A")
        radius = state.get("radius", "N/A")

        # Формируем информацию о найденных событиях
        kept_by_type = diag.get("kept_by_type", {})
        reasons_top3 = diag.get("reasons_top3", [])

        info_lines = [
            "<b>🔍 Диагностика поиска</b>",
            f"<b>user_point=</b>({lat}, {lng}) <b>radius_km=</b>{radius}",
            f"<b>found_total=</b>{diag.get('in', 0)}",
            f"<b>kept_by_type:</b> ai_parsed={kept_by_type.get('ai_parsed', 0)} user={kept_by_type.get('user', 0)} source={kept_by_type.get('source', 0)}",
            f"<b>dropped=</b>{diag.get('dropped', 0)} <b>reasons_top3=</b>{reasons_top3}",
            "",
            "<b>📊 Детали по типам:</b>",
            f"• AI события: {kept_by_type.get('ai_parsed', 0)}",
            f"• Пользовательские: {kept_by_type.get('user', 0)}",
            f"• Внешние источники: {kept_by_type.get('source', 0)}",
            "",
            "<b>📈 Итоговые счетчики:</b>",
            f"• Всего: {counts.get('all', 0)}",
            f"• Мгновенные: {counts.get('moments', 0)}",
            f"• Пользовательские: {counts.get('user', 0)}",
            f"• Внешние: {counts.get('sources', 0)}",
        ]

        # Добавляем информацию о причинах отбраковки
        if reasons_top3:
            info_lines.extend(
                [
                    "",
                    "<b>🚫 Топ причины отбраковки:</b>",
                ]
            )
            for reason in reasons_top3:
                info_lines.append(f"• {reason}")

        # Добавляем примеры отброшенных событий
        if prepared:
            info_lines.extend(
                [
                    "",
                    "<b>✅ Примеры сохраненных событий:</b>",
                ]
            )
            for i, event in enumerate(prepared[:3], 1):
                title = event.get("title", "Без названия")[:50]
                distance = event.get("distance_km", "N/A")
                info_lines.append(f"• {i}) {title} ({distance} км)")

        await message.answer("\n".join(info_lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в команде diag_search: {e}")
        await message.answer("Произошла ошибка при получении диагностики поиска")


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


# FSM обработчики для создания событий (должны быть ПЕРЕД общим обработчиком)
@dp.message(EventCreation.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    """Шаг 1: Обработка названия события"""
    title = message.text.strip()
    logger.info(f"process_title: получили название '{title}' от пользователя {message.from_user.id}")

    await state.update_data(title=title)
    await state.set_state(EventCreation.waiting_for_date)
    await message.answer(
        f"Название сохранено: *{title}* ✅\n\n📅 Теперь введите дату (например: 12.09.2025):", parse_mode="Markdown"
    )


@dp.message(EventCreation.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    """Шаг 2: Обработка даты события"""
    date = message.text.strip()
    logger.info(f"process_date: получили дату '{date}' от пользователя {message.from_user.id}")

    await state.update_data(date=date)
    await state.set_state(EventCreation.waiting_for_time)
    await message.answer(
        f"Дата сохранена: *{date}* ✅\n\n⏰ Теперь введите время (например: 17:30):", parse_mode="Markdown"
    )


@dp.message(EventCreation.waiting_for_time)
async def process_time(message: types.Message, state: FSMContext):
    """Шаг 3: Обработка времени события"""
    time = message.text.strip()
    logger.info(f"process_time: получили время '{time}' от пользователя {message.from_user.id}")

    await state.update_data(time=time)
    await state.set_state(EventCreation.waiting_for_location_type)

    # Создаем клавиатуру для выбора типа локации
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data="location_link")],
            [InlineKeyboardButton(text="🌍 Найти на карте", callback_data="location_map")],
        ]
    )

    await message.answer(
        f"Время сохранено: *{time}* ✅\n\n📍 Как укажем место?", parse_mode="Markdown", reply_markup=keyboard
    )


# Обработчики для выбора типа локации
@dp.callback_query(F.data == "location_link")
async def handle_location_link_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода готовой ссылки"""
    await state.set_state(EventCreation.waiting_for_location_link)
    await callback.message.answer("🔗 Вставьте сюда ссылку из Google Maps:")
    await callback.answer()


@dp.callback_query(F.data == "location_map")
async def handle_location_map_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор поиска на карте"""
    await state.set_state(EventCreation.waiting_for_location_link)

    # Создаем кнопку для открытия Google Maps
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🌍 Открыть Google Maps", url="https://www.google.com/maps")]]
    )

    await callback.message.answer("🌍 Открой карту, найди место и вставь ссылку сюда 👇", reply_markup=keyboard)
    await callback.answer()


@dp.message(EventCreation.waiting_for_location_link)
async def process_location_link(message: types.Message, state: FSMContext):
    """Обработка ссылки Google Maps"""
    link = message.text.strip()
    logger.info(f"process_location_link: получили ссылку от пользователя {message.from_user.id}")

    # Парсим ссылку
    from utils.geo_utils import parse_google_maps_link

    location_data = parse_google_maps_link(link)

    if not location_data:
        await message.answer(
            "❌ Не удалось распознать ссылку Google Maps.\n\n"
            "Попробуйте:\n"
            "• Скопировать ссылку из приложения Google Maps\n"
            "• Или ввести координаты в формате: широта,долгота"
        )
        return

    # Сохраняем данные локации
    await state.update_data(
        location_name=location_data.get("name", "Место на карте"),
        location_lat=location_data["lat"],
        location_lng=location_data["lng"],
        location_url=location_data["raw_link"],
    )

    # Показываем подтверждение
    location_name = location_data.get("name", "Место на карте")
    lat = location_data.get("lat")
    lng = location_data.get("lng")

    # Создаем кнопки подтверждения
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌍 Открыть на карте", url=link)],
            [
                InlineKeyboardButton(text="✅ Да", callback_data="location_confirm"),
                InlineKeyboardButton(text="❌ Изменить", callback_data="location_change"),
            ],
        ]
    )

    # Формируем сообщение в зависимости от наличия координат
    if lat is not None and lng is not None:
        location_text = f"📍 **Локация:** {location_name}\n🌍 Координаты: {lat:.6f}, {lng:.6f}\n\nВсё верно?"
    else:
        location_text = f"📍 **Локация:** {location_name}\n🌍 Ссылка на карту сохранена\n\nВсё верно?"

    await message.answer(
        location_text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# Обработчики подтверждения локации
@dp.callback_query(F.data == "location_confirm")
async def handle_location_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение локации"""
    await state.set_state(EventCreation.waiting_for_description)
    await callback.message.answer(
        "📍 Место сохранено! ✅\n\n📝 Теперь введите описание (например: Вечерняя прогулка у океана):",
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "location_change")
async def handle_location_change(callback: types.CallbackQuery, state: FSMContext):
    """Изменение локации"""
    await state.set_state(EventCreation.waiting_for_location_type)

    # Создаем клавиатуру для выбора типа локации
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data="location_link")],
            [InlineKeyboardButton(text="🌍 Найти на карте", callback_data="location_map")],
        ]
    )

    await callback.message.answer("📍 Как укажем место?", reply_markup=keyboard)
    await callback.answer()


@dp.message(EventCreation.waiting_for_location)
async def process_location(message: types.Message, state: FSMContext):
    """Шаг 4: Обработка места события"""
    location = message.text.strip()
    logger.info(f"process_location: получили место '{location}' от пользователя {message.from_user.id}")

    await state.update_data(location=location)
    await state.set_state(EventCreation.waiting_for_description)
    await message.answer(
        f"Место сохранено: *{location}* ✅\n\n📝 Теперь введите описание (например: Вечерняя прогулка у океана):",
        parse_mode="Markdown",
    )


@dp.message(EventCreation.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    """Шаг 5: Обработка описания события"""
    description = message.text.strip()
    logger.info(f"process_description: получили описание от пользователя {message.from_user.id}")

    await state.update_data(description=description)
    data = await state.get_data()
    await state.set_state(EventCreation.confirmation)

    # Показываем итог перед подтверждением
    location_text = data.get("location", "Не указано")
    if "location_name" in data:
        location_text = data["location_name"]
        if "location_url" in data:
            location_text += f"\n🌍 [Открыть на карте]({data['location_url']})"

    await message.answer(
        f"📌 **Проверьте данные мероприятия:**\n\n"
        f"**Название:** {data['title']}\n"
        f"**Дата:** {data['date']}\n"
        f"**Время:** {data['time']}\n"
        f"**Место:** {location_text}\n"
        f"**Описание:** {data['description']}\n\n"
        f"Если всё верно, нажмите ✅ Сохранить. Если нужно изменить — нажмите ❌ Отмена.",
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="✅ Сохранить", callback_data="event_confirm"),
                    types.InlineKeyboardButton(text="❌ Отмена", callback_data="event_cancel"),
                ]
            ]
        ),
    )


@dp.callback_query(F.data == "event_confirm")
async def confirm_event(callback: types.CallbackQuery, state: FSMContext):
    """Шаг 6: Подтверждение создания события"""
    data = await state.get_data()
    logger.info(f"confirm_event: подтверждение создания события от пользователя {callback.from_user.id}")

    # Создаём событие в БД
    with get_session() as session:
        # Сначала создаем пользователя, если его нет
        user = session.get(User, callback.from_user.id)
        if not user:
            user = User(
                id=callback.from_user.id,
                username=callback.from_user.username,
            )
            session.add(user)
            session.commit()

        # Объединяем дату и время
        time_local = f"{data['date']} {data['time']}"

        # Парсим дату и время для starts_at
        from datetime import datetime

        try:
            starts_at = datetime.strptime(time_local, "%d.%m.%Y %H:%M")
        except ValueError:
            starts_at = None

        # Определяем данные локации
        location_name = data.get("location_name", data.get("location", "Место не указано"))
        location_url = data.get("location_url")
        lat = data.get("location_lat")
        lng = data.get("location_lng")

        # Используем новую упрощенную архитектуру
        try:
            from database import get_engine
            from utils.simple_timezone import get_city_from_coordinates

            engine = get_engine()
            events_service = UnifiedEventsService(engine)

            # Определяем город по координатам
            city = get_city_from_coordinates(lat, lng) if lat and lng else "bali"

            # Создаем событие через упрощенный сервис
            event_id = events_service.create_user_event(
                organizer_id=callback.from_user.id,
                title=data["title"],
                description=data["description"],
                starts_at_utc=starts_at,
                city=city,
                lat=lat,
                lng=lng,
                location_name=location_name,
                location_url=location_url,
                max_participants=data.get("max_participants"),
                organizer_username=callback.from_user.username,
            )

            logger.info(f"✅ Событие создано с ID: {event_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка при создании события: {e}")
            # Fallback к старому методу
            event = Event(
                title=data["title"],
                description=data["description"],
                time_local=time_local,
                starts_at=starts_at,
                location_name=location_name,
                location_url=location_url,
                lat=lat,
                lng=lng,
                organizer_id=callback.from_user.id,
                organizer_username=callback.from_user.username,
                status="open",
                is_generated_by_ai=False,
            )
            session.add(event)
            session.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения события: {e}")
            raise

    await state.clear()
    await callback.message.edit_text(
        f"🎉 **Мероприятие сохранено!**\n\n"
        f"**Название:** {data['title']}\n"
        f"**Дата:** {data['date']}\n"
        f"**Время:** {data['time']}\n"
        f"**Место:** {location_name}\n"
        f"**Описание:** {data['description']}\n\n"
        f"Теперь другие пользователи смогут найти его через '📍 Что рядом'.",
        parse_mode="Markdown",
    )
    await callback.answer("Событие создано!")


@dp.callback_query(F.data == "event_cancel")
async def cancel_event_creation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания события"""
    await state.clear()
    await callback.message.edit_text("❌ Создание мероприятия отменено.")
    await callback.answer("Создание отменено")


@dp.message(~StateFilter(EventCreation, EventEditing))
async def echo_message(message: types.Message, state: FSMContext):
    """Обработчик всех остальных сообщений (кроме FSM состояний)"""
    current_state = await state.get_state()
    logger.info(
        f"echo_message: получили сообщение '{message.text}' от пользователя {message.from_user.id}, состояние: {current_state}"
    )
    logger.info("echo_message: отвечаем общим сообщением")
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
            logger.warning(f"Состояние не найдено для пользователя {callback.message.chat.id}")
            await callback.answer("Состояние не найдено. Отправьте новую геолокацию.")
            return

        prepared = state["prepared"]
        counts = state["counts"]
        current_radius = state.get("radius", 5)

        # Рендерим страницу
        page_html, total_pages = render_page(prepared, page, page_size=5)

        # Обновляем сообщение с защитой от ошибок
        try:
            await callback.message.edit_text(
                render_header(counts, radius_km=current_radius) + "\n\n" + page_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=kb_pager(page, total_pages, current_radius),
            )
        except TelegramBadRequest:
            await callback.message.answer(
                render_header(counts, radius_km=current_radius) + "\n\n" + page_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=kb_pager(page, total_pages, current_radius),
            )

        # Обновляем состояние
        state["page"] = page
        user_state[callback.message.chat.id] = state

        await callback.answer()

        # Возвращаем основное меню
        await send_main_menu(callback)

    except (ValueError, IndexError) as e:
        logger.error(f"❌ Ошибка обработки пагинации: {e}")
        await callback.answer("Ошибка обработки запроса")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в пагинации: {e}")
        await callback.answer("Произошла ошибка")


@dp.callback_query(F.data == "loading")
async def handle_loading_button(callback: types.CallbackQuery):
    """Обработчик кнопки загрузки - просто отвечаем, что работаем"""
    await callback.answer("🔍 Ищем события...", show_alert=False)


@dp.callback_query(F.data.startswith("rx:"))
async def handle_expand_radius(callback: types.CallbackQuery):
    """Обработчик расширения радиуса поиска"""

    try:
        # Извлекаем новый радиус из callback_data: rx:radius
        new_radius = int(callback.data.split(":")[1])

        # Получаем сохраненное состояние
        state = user_state.get(callback.message.chat.id)
        logger.info(f"🔍 Проверяем состояние для пользователя {callback.message.chat.id}: {state is not None}")
        if not state:
            logger.warning(f"Состояние не найдено для пользователя {callback.message.chat.id}")
            logger.info(f"Доступные состояния: {list(user_state.keys())}")
            await callback.answer("Состояние не найдено. Отправьте новую геолокацию.")
            return

        lat = state.get("lat")
        lng = state.get("lng")

        if not lat or not lng:
            logger.warning(f"Координаты не найдены в состоянии для пользователя {callback.message.chat.id}")
            await callback.answer("Координаты не найдены. Отправьте новую геолокацию.")
            return

        # Логируем параметры расширенного поиска
        logger.info(f"🔎 Расширенный поиск: координаты=({lat}, {lng}) радиус={new_radius}км источник=пользователь")
        logger.info(
            f"🔍 Расширяем поиск до {new_radius} км от ({lat}, {lng}) для пользователя {callback.message.chat.id}"
        )

        # Показываем индикатор загрузки
        loading_message = await callback.message.answer(
            "🔍 Ищу...",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔍", callback_data="loading")]]
            ),
        )

        # Ищем события с расширенным радиусом используя упрощенную архитектуру
        try:
            # Используем упрощенную архитектуру для поиска событий
            from database import get_engine
            from utils.simple_timezone import get_city_from_coordinates

            engine = get_engine()
            events_service = UnifiedEventsService(engine)

            # Определяем город по координатам
            city = get_city_from_coordinates(lat, lng)
            logger.info(f"🔍 Ищем события в городе {city} с радиусом {new_radius} км")

            # Ищем события через упрощенный сервис
            events = events_service.search_events_today(city=city, user_lat=lat, user_lng=lng, radius_km=new_radius)

            # Конвертируем в старый формат для совместимости
            converted_events = []
            for event in events:
                converted_event = {
                    "title": event.get("title", ""),
                    "description": event.get("description", ""),
                    "start_time": event.get("starts_at"),
                    "venue_name": event.get("location_name", ""),
                    "address": event.get("location_url", ""),
                    "lat": event.get("lat"),
                    "lng": event.get("lng"),
                    "source_url": event.get("event_url", ""),
                    "type": "source" if event.get("source_type") == "parser" else "user",
                    "source": event.get("source_type", "user_created"),
                }
                converted_events.append(converted_event)

            events = converted_events
            events = sort_events_by_time(events)

        except Exception as e:
            logger.error(f"❌ Ошибка при расширенном поиске: {e}")
            events = []
            await callback.answer("Ошибка при поиске событий")
            return

        if not events:
            # Удаляем сообщение загрузки если события не найдены
            try:
                await loading_message.delete()
            except Exception:
                pass
            await callback.answer("События не найдены даже в расширенном радиусе")
            return

        # Фильтруем и обогащаем события
        prepared, diag = prepare_events_for_feed(events, user_point=(lat, lng), radius_km=new_radius, with_diag=True)
        logger.info(f"prepared: kept={diag['kept']} dropped={diag['dropped']} reasons_top3={diag['reasons_top3']}")
        logger.info(
            f"kept_by_type: ai_parsed={diag['kept_by_type'].get('ai_parsed', 0)} user={diag['kept_by_type'].get('user', 0)} source={diag['kept_by_type'].get('source', 0)}"
        )

        for event in prepared:
            enrich_venue_name(event)

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
            "region": city,  # Сохраняем город
        }

        # Удаляем сообщение загрузки
        try:
            await loading_message.delete()
        except Exception:
            pass  # Игнорируем ошибки удаления

        # Рендерим первую страницу
        header_html = render_header(counts, radius_km=new_radius)
        page_html, total_pages = render_page(prepared, page=1, page_size=5)

        # Обновляем сообщение с защитой от ошибок
        try:
            await callback.message.edit_text(
                header_html + "\n\n" + page_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=kb_pager(1, total_pages, new_radius),
            )
        except TelegramBadRequest:
            # Если не удалось отредактировать (сообщение устарело/удалено), отправляем новое
            await callback.message.answer(
                header_html + "\n\n" + page_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=kb_pager(1, total_pages, new_radius),
            )

        await callback.answer(f"Радиус расширен до {new_radius} км")

        # Возвращаем основное меню
        await send_main_menu(callback)

    except (ValueError, IndexError) as e:
        logger.error(f"❌ Ошибка обработки расширения радиуса: {e}")
        await callback.answer("Ошибка обработки запроса")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в расширении радиуса: {e}")
        await callback.answer("Произошла ошибка")


@dp.callback_query(F.data == "create_event")
async def handle_create_event(callback: types.CallbackQuery):
    """Обработчик кнопки создания события"""
    try:
        # Отправляем сообщение с инструкциями по созданию события
        await callback.message.edit_text(
            "➕ <b>Создание события</b>\n\n"
            "Чтобы создать событие, используйте команду /create или нажмите кнопку '➕ Создать' в главном меню.\n\n"
            "Вы сможете указать:\n"
            "• Название события\n"
            "• Описание\n"
            "• Время проведения\n"
            "• Место проведения\n"
            "• Ссылку на событие",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Создать событие", callback_data="start_create")],
                    [InlineKeyboardButton(text="🔙 Назад к поиску", callback_data="back_to_search")],
                ]
            ),
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике создания события: {e}")
        await callback.answer("Произошла ошибка")


@dp.callback_query(F.data == "start_create")
async def handle_start_create(callback: types.CallbackQuery):
    """Обработчик начала создания события"""
    try:
        # Перенаправляем на команду создания события
        await callback.message.edit_text(
            "➕ <b>Создание события</b>\n\nИспользуйте команду /create для создания нового события.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_search")]]
            ),
        )
        await callback.answer("Используйте команду /create")

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике начала создания: {e}")
        await callback.answer("Произошла ошибка")


@dp.callback_query(F.data == "back_to_search")
async def handle_back_to_search(callback: types.CallbackQuery):
    """Обработчик возврата к поиску"""
    try:
        # Возвращаемся к главному меню
        await callback.message.edit_text(
            "🔍 <b>Поиск событий</b>\n\nОтправьте геолокацию, чтобы найти события рядом с вами.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике возврата к поиску: {e}")
        await callback.answer("Произошла ошибка")


# Обработчики для создания моментов
@dp.message(Command("moment"))
@dp.message(F.text == "⚡ Создать Момент")
async def start_moment_creation(message: types.Message, state: FSMContext):
    """Начало создания момента - Step 0"""
    from config import load_settings

    settings = load_settings()

    if not settings.moments_enable:
        await message.answer("Функция моментов отключена.", reply_markup=main_menu_kb())
        return

    # Создаем клавиатуру с шаблонами согласно UX
    keyboard = [
        [InlineKeyboardButton(text="☕ Кофе", callback_data="m:tpl:coffee")],
        [InlineKeyboardButton(text="🚶 Прогулка", callback_data="m:tpl:walk")],
        [InlineKeyboardButton(text="💬 Small talk", callback_data="m:tpl:talk")],
        [InlineKeyboardButton(text="🏐 Игра/спорт", callback_data="m:tpl:sport")],
        [InlineKeyboardButton(text="✏️ Свой вариант", callback_data="m:tpl:custom")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
    ]

    await message.answer(
        "**Создадим Момент — быструю встречу рядом.**\nВыбери шаблон или задай свой вариант.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
    )
    await state.set_state(MomentCreation.waiting_for_template)


@dp.callback_query(F.data.startswith("m:tpl:"))
async def handle_template_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора шаблона - Step 1"""
    template_data = callback.data[6:]  # убираем "m:tpl:"

    # Маппинг шаблонов
    template_map = {
        "coffee": "☕ Кофе",
        "walk": "🚶 Прогулка",
        "talk": "💬 Small talk",
        "sport": "🏐 Игра/спорт",
    }

    if template_data == "custom":
        await callback.message.edit_text(
            "Введи короткое название Момента (до 40 символов):\n*пример: «кофе у Marina», «пробежка в парке»*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")]]
            ),
        )
        await state.set_state(MomentCreation.waiting_for_custom_title)
    else:
        title = template_map.get(template_data, template_data)
        await state.update_data(title=title)

        # Переходим к локации
        await callback.message.edit_text(
            "Отправь геолокацию (📎 → Location)\nили напиши адрес: *«Jl. Danau Tamblingan 80, Sanur»*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📍 Использовать мою текущую гео", callback_data="m:loc:ask")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
                ]
            ),
        )
        await state.set_state(MomentCreation.waiting_for_location)

    await callback.answer()


@dp.message(MomentCreation.waiting_for_custom_title)
async def handle_custom_title(message: types.Message, state: FSMContext):
    """Обработка ввода кастомного названия - Step 1B"""
    title = message.text.strip()

    # Валидация согласно UX
    if not title or len(title) < 1:
        await message.answer(
            "❗ Слишком коротко. Введи название (1-40 символов).",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")]]
            ),
        )
        return

    if len(title) > 40:
        await message.answer(
            "❗ Слишком длинно. Сделай короче (до 40 символов).",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")]]
            ),
        )
        return

    # Проверка на спам/ссылки
    if any(word in title.lower() for word in ["http", "www", "@", "телефон", "звони"]):
        await message.answer(
            "❗ Не используй ссылки или контакты в названии.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")]]
            ),
        )
        return

    await state.update_data(title=title)

    # Переходим к локации
    await message.answer(
        "Отправь геолокацию (📎 → Location)\nили напиши адрес: *«Jl. Danau Tamblingan 80, Sanur»*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📍 Использовать мою текущую гео", callback_data="m:loc:ask")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
            ]
        ),
    )
    await state.set_state(MomentCreation.waiting_for_location)


@dp.callback_query(F.data == "m:loc:ask")
async def handle_location_help(callback: types.CallbackQuery, state: FSMContext):
    """Подсказка как отправить геолокацию"""
    await callback.message.edit_text(
        "📍 **Как отправить геолокацию:**\n\n"
        "1. Нажми кнопку 📎 (скрепка) рядом с полем ввода\n"
        "2. Выбери «Location» или «Местоположение»\n"
        "3. Выбери «Отправить мою геолокацию»\n\n"
        "Или просто напиши адрес текстом.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")]]
        ),
    )
    await callback.answer()


@dp.message(MomentCreation.waiting_for_location, F.location)
async def handle_moment_location(message: types.Message, state: FSMContext):
    """Обработка геолокации для момента - Step 2"""
    try:
        await state.get_data()
        lat = message.location.latitude
        lng = message.location.longitude

        # Сохраняем координаты
        await state.update_data(lat=lat, lng=lng, location_type="geo")

        # Показываем предпросмотр локации
        await message.answer(
            f"📍 **Локация принята:**\n({lat:.4f}, {lng:.4f})",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Дальше", callback_data="m:ok:loc")],
                    [InlineKeyboardButton(text="🔁 Изменить локацию", callback_data="m:loc:redo")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
                ]
            ),
        )
        await state.set_state(MomentCreation.location_confirmed)

    except Exception as e:
        logger.error(f"Ошибка обработки геолокации: {e}")
        await message.answer(
            "Произошла ошибка при обработке геолокации. Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")]]
            ),
        )


@dp.message(MomentCreation.waiting_for_location, F.text)
async def handle_moment_address(message: types.Message, state: FSMContext):
    """Обработка адреса для момента - Step 2"""
    try:
        from utils.geo_utils import geocode_address

        address = message.text.strip()

        if not address:
            await message.answer(
                "📍 Нужна локация. Отправь карту-пин или напиши адрес.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")]]
                ),
            )
            return

        coords = await geocode_address(address)

        if not coords:
            await message.answer(
                "😕 Не нашёл такой адрес. Отправь карта-пин (📎 → Location) или уточни адрес.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")]]
                ),
            )
            return

        lat, lng = coords

        # Сохраняем координаты и адрес
        await state.update_data(lat=lat, lng=lng, address=address, location_type="address")

        # Показываем предпросмотр локации
        await message.answer(
            f"📍 **Локация принята:**\n*{address}*\n({lat:.4f}, {lng:.4f})",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Дальше", callback_data="m:ok:loc")],
                    [InlineKeyboardButton(text="🔁 Изменить локацию", callback_data="m:loc:redo")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
                ]
            ),
        )
        await state.set_state(MomentCreation.location_confirmed)

    except Exception as e:
        logger.error(f"Ошибка обработки адреса: {e}")
        await message.answer(
            "Произошла ошибка при обработке адреса. Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")]]
            ),
        )


@dp.callback_query(F.data == "m:ok:loc")
async def handle_location_confirmed(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение локации - переход к TTL"""
    await callback.message.edit_text(
        "Выбери, сколько будет активен Момент:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⏳ 30 мин", callback_data="m:ttl:30")],
                [InlineKeyboardButton(text="⏰ 1 час", callback_data="m:ttl:60")],
                [InlineKeyboardButton(text="🕑 2 часа", callback_data="m:ttl:120")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="m:back:loc")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
            ]
        ),
    )
    await state.set_state(MomentCreation.waiting_for_ttl)
    await callback.answer()


@dp.callback_query(F.data == "m:loc:redo")
async def handle_location_redo(callback: types.CallbackQuery, state: FSMContext):
    """Повторный ввод локации"""
    await callback.message.edit_text(
        "Отправь геолокацию (📎 → Location)\nили напиши адрес: *«Jl. Danau Tamblingan 80, Sanur»*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📍 Использовать мою текущую гео", callback_data="m:loc:ask")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
            ]
        ),
    )
    await state.set_state(MomentCreation.waiting_for_location)
    await callback.answer()


@dp.callback_query(F.data.startswith("m:ttl:"))
async def handle_ttl_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора TTL - Step 3"""
    ttl_minutes = int(callback.data[7:])  # убираем "m:ttl:"

    # Валидация TTL - только разрешенные значения
    allowed_ttl = [30, 60, 120]
    if ttl_minutes not in allowed_ttl:
        await callback.answer("Выберите длительность из предложенных вариантов.", show_alert=True)
        return

    await state.update_data(ttl_minutes=ttl_minutes)

    # Получаем данные для предпросмотра
    data = await state.get_data()
    title = data.get("title", "Момент")
    lat = data.get("lat", 0)
    lng = data.get("lng", 0)
    address = data.get("address", "")

    # Форматируем TTL
    if ttl_minutes < 60:
        ttl_human = f"{ttl_minutes} мин"
    else:
        hours = ttl_minutes // 60
        minutes = ttl_minutes % 60
        if minutes == 0:
            ttl_human = f"{hours} час" if hours == 1 else f"{hours} часа"
        else:
            ttl_human = f"{hours}ч {minutes}м"

    # Форматируем адрес
    if address:
        short_address = address[:30] + "..." if len(address) > 30 else address
    else:
        short_address = f"({lat:.4f}, {lng:.4f})"

    await callback.message.edit_text(
        f"**Проверь:**\n✨ *{title}*\n📍 *{short_address}*\n⏳ *{ttl_human}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Создать", callback_data="m:create")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="m:back:ttl")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
            ]
        ),
    )
    await state.set_state(MomentCreation.preview_confirmed)
    await callback.answer()


@dp.callback_query(F.data == "m:back:loc")
async def handle_back_to_location(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору локации"""
    await callback.message.edit_text(
        "Отправь геолокацию (📎 → Location)\nили напиши адрес: *«Jl. Danau Tamblingan 80, Sanur»*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📍 Использовать мою текущую гео", callback_data="m:loc:ask")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
            ]
        ),
    )
    await state.set_state(MomentCreation.waiting_for_location)
    await callback.answer()


@dp.callback_query(F.data == "m:back:ttl")
async def handle_back_to_ttl(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору TTL"""
    await callback.message.edit_text(
        "Выбери, сколько будет активен Момент:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⏳ 30 мин", callback_data="m:ttl:30")],
                [InlineKeyboardButton(text="⏰ 1 час", callback_data="m:ttl:60")],
                [InlineKeyboardButton(text="🕑 2 часа", callback_data="m:ttl:120")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="m:back:loc")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="m:cancel")],
            ]
        ),
    )
    await state.set_state(MomentCreation.waiting_for_ttl)
    await callback.answer()


@dp.callback_query(F.data == "m:create")
async def handle_create_moment(callback: types.CallbackQuery, state: FSMContext):
    """Создание момента - финальный шаг"""
    try:
        data = await state.get_data()
        user_id = callback.from_user.id
        username = callback.from_user.username

        # Проверяем лимит перед созданием
        can_create, current_count = await check_daily_limit(user_id)
        if not can_create:
            await callback.message.edit_text(
                f"❌ Ты уже создал {current_count} Момента сегодня. Попробуй завтра.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="m:cancel")]]
                ),
            )
            await state.clear()
            await callback.answer()
            return

        # Создаем момент
        await create_moment(
            user_id=user_id,
            username=username or "Аноним",
            title=data["title"],
            lat=data["lat"],
            lng=data["lng"],
            ttl_minutes=data["ttl_minutes"],
        )

        # Обновляем пользователя с username если нужно
        if username:
            with get_session() as session:
                user = session.get(User, user_id)
                if user:
                    user.username = username
                    session.commit()

        # Форматируем TTL для отображения
        ttl_minutes = data["ttl_minutes"]
        if ttl_minutes < 60:
            ttl_human = f"{ttl_minutes} мин"
        else:
            hours = ttl_minutes // 60
            minutes = ttl_minutes % 60
            if minutes == 0:
                ttl_human = f"{hours} час" if hours == 1 else f"{hours} часа"
            else:
                ttl_human = f"{hours}ч {minutes}м"

        # Создаем ссылку на маршрут
        from utils.geo_utils import to_google_maps_link

        route_url = to_google_maps_link(data["lat"], data["lng"])

        await callback.message.edit_text(
            f"✅ **Момент создан!**\n\n"
            f"👤 Автор: @{username or 'Аноним'}\n"
            f"✨ *{data['title']}*\n"
            f"⏳ истечёт через *{ttl_human}*\n\n"
            f"🚗 [Маршрут]({route_url})",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="m:cancel")]]
            ),
        )

        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка создания момента: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при создании момента. Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="m:cancel")]]
            ),
        )
        await state.clear()
        await callback.answer()


@dp.callback_query(F.data == "m:cancel")
async def handle_cancel_moment(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания момента"""
    await callback.message.edit_text(
        "Ок, отменил создание Момента.\n(подсказка) В любой момент жми **➕ Момент**, чтобы попробовать снова.",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )
    await state.clear()
    await callback.answer()


# Обработчики для выбора радиуса
@dp.callback_query(F.data.startswith(CB_RADIUS_PREFIX))
async def on_radius_change(cb: types.CallbackQuery) -> None:
    """Обработчик выбора радиуса через новые кнопки"""
    try:
        km = int(cb.data.split(":", 1)[1])
    except Exception:
        await cb.answer("Некорректный радиус", show_alert=True)
        return

    if km not in RADIUS_OPTIONS:
        await cb.answer("Недоступный радиус", show_alert=True)
        return

    set_user_radius(cb.from_user.id, km)
    await cb.answer(f"Радиус: {km} км")

    # Обновляем клавиатуру с новым выбранным радиусом
    await cb.message.edit_reply_markup(reply_markup=kb_radius(km))


@dp.callback_query(F.data.startswith("radius:"))
async def handle_radius_selection(callback: types.CallbackQuery):
    """Обработчик выбора радиуса поиска"""
    try:
        if callback.data == "radius:cancel":
            try:
                await callback.message.edit_text("Настройки радиуса отменены.", reply_markup=main_menu_kb())
            except TelegramBadRequest:
                await callback.message.answer("Настройки радиуса отменены.", reply_markup=main_menu_kb())
            await callback.answer()
            return

        # Извлекаем радиус из callback_data: radius:5
        radius = int(callback.data.split(":")[1])
        user_id = callback.from_user.id

        # Сохраняем выбранный радиус в БД
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.default_radius_km = radius
                session.commit()
            else:
                # Создаем пользователя если его нет
                user = User(
                    id=user_id,
                    username=callback.from_user.username,
                    full_name=callback.from_user.full_name,
                    default_radius_km=radius,
                )
                session.add(user)
                session.commit()

        try:
            await callback.message.edit_text(
                f"✅ **Радиус поиска установлен: {radius} км**\n\n"
                f"Теперь при поиске событий будет использоваться радиус {radius} км.\n"
                f"Этот радиус также будет применяться для поиска моментов.",
                parse_mode="Markdown",
                reply_markup=main_menu_kb(),
            )
        except TelegramBadRequest:
            await callback.message.answer(
                f"✅ **Радиус поиска установлен: {radius} км**\n\n"
                f"Теперь при поиске событий будет использоваться радиус {radius} км.\n"
                f"Этот радиус также будет применяться для поиска моментов.",
                parse_mode="Markdown",
                reply_markup=main_menu_kb(),
            )
        await callback.answer(f"Радиус установлен: {radius} км")

    except Exception as e:
        logger.error(f"Ошибка при выборе радиуса: {e}")
        try:
            await callback.message.edit_text(
                "Произошла ошибка при сохранении настроек. Попробуйте еще раз.",
                reply_markup=main_menu_kb(),
            )
        except TelegramBadRequest:
            await callback.message.answer(
                "Произошла ошибка при сохранении настроек. Попробуйте еще раз.",
                reply_markup=main_menu_kb(),
            )
        await callback.answer("Произошла ошибка")


async def cleanup_moments_task():
    """Фоновая задача для очистки истекших моментов"""
    while True:
        try:
            count = await cleanup_expired_moments()
            if count > 0:
                logger.info(f"Очищено {count} истекших моментов")
        except Exception as e:
            logger.error(f"Ошибка очистки моментов: {e}")

        # Запускаем каждые 5 минут
        await asyncio.sleep(300)


async def main():
    """Главная функция"""
    logger.info("Запуск улучшенного EventBot (aiogram 3.x)...")

    # Запускаем фоновую задачу для очистки моментов
    from config import load_settings

    settings = load_settings()
    if settings.moments_enable:
        asyncio.create_task(cleanup_moments_task())
        logger.info("Запущена фоновая задача очистки моментов")

    # Читаем переменные окружения
    RUN_MODE = os.getenv("BOT_RUN_MODE", "webhook")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    int(os.getenv("PORT", "8000"))

    # Логируем конфигурацию
    logger.info(f"Режим запуска: {RUN_MODE}")
    if WEBHOOK_URL:
        logger.info(f"WEBHOOK_URL: {WEBHOOK_URL}")
    else:
        logger.info("WEBHOOK_URL не установлен")

    # Проверяем текущий webhook
    try:
        webhook_info = await bot.get_webhook_info()
        logger.info(f"Текущий webhook: {webhook_info.url or 'пустой'}")
        logger.info(f"Pending updates: {webhook_info.pending_update_count}")
    except Exception as e:
        logger.warning(f"Ошибка получения webhook info: {e}")

    # Устанавливаем команды бота для удобства пользователей
    try:
        commands = [
            types.BotCommand(command="start", description="🚀 Запустить бота и показать меню"),
            types.BotCommand(command="help", description="❓ Показать справку"),
            types.BotCommand(command="nearby", description="📍 Найти события рядом"),
            types.BotCommand(command="create", description="➕ Создать событие"),
        ]

        # Добавляем команду для моментов, если они включены
        if settings.moments_enable:
            commands.append(types.BotCommand(command="moment", description="⚡ Создать Момент"))

        commands.extend(
            [
                types.BotCommand(command="myevents", description="📋 Мои события"),
                types.BotCommand(command="share", description="🔗 Поделиться ботом"),
                types.BotCommand(command="admin_event", description="🔍 Диагностика события (админ)"),
                types.BotCommand(command="diag_last", description="📊 Диагностика последнего запроса"),
                types.BotCommand(command="diag_search", description="🔍 Диагностика поиска событий"),
                types.BotCommand(command="diag_webhook", description="🔗 Диагностика webhook"),
            ]
        )

        # Устанавливаем команды бота
        await bot.set_my_commands(commands)

        # Устанавливаем кнопку меню
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

        logger.info("Команды бота установлены")
    except Exception as e:
        logger.warning(f"Не удалось установить команды бота: {e}")

    # Определяем режим запуска
    RUN_MODE = os.getenv("BOT_RUN_MODE", "webhook")
    PORT = os.getenv("PORT", "8000")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")

    logger.info(f"Режим запуска: {RUN_MODE}")
    logger.info(f"Порт: {PORT}")
    logger.info(f"Webhook URL: {WEBHOOK_URL}")

    # Запускаем бота в зависимости от режима
    try:
        if RUN_MODE == "webhook":
            # Webhook режим для Railway
            if not WEBHOOK_URL:
                logger.error("WEBHOOK_URL не установлен для webhook режима")
                return

            # Гарантированно выключаем getUpdates на стороне Telegram
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Старый webhook удален")

            # Запускаем webhook сервер на отдельном порту
            from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
            from aiohttp import web

            # Создаем aiohttp приложение
            app = web.Application()

            # Настраиваем безопасный webhook handler
            webhook_path = "/webhook"

            # Создаем стандартный handler для справки
            webhook_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
            )

            # Создаем безопасный wrapper
            async def safe_webhook_handler(request):
                try:
                    # Проверяем, что это JSON
                    try:
                        data = await request.json()
                    except Exception:
                        logger.debug("Webhook: не JSON, игнорируем")
                        return web.Response(status=204)

                    # Простейшая проверка "похоже ли на Telegram Update"
                    if not isinstance(data, dict) or "update_id" not in data:
                        logger.debug("Webhook: не похоже на Telegram Update, игнорируем")
                        return web.Response(status=204)

                    # Передаем в стандартный handler
                    return await webhook_handler.handle(request)

                except Exception as e:
                    logger.debug(f"Webhook: ошибка обработки, игнорируем: {e}")
                    return web.Response(status=204)

            # Регистрируем безопасный handler
            app.router.add_post(webhook_path, safe_webhook_handler)

            # Настраиваем приложение
            setup_application(app, dp, bot=bot)

            # Добавляем health check endpoint в webhook сервер

            async def health_check(request):
                return web.json_response({"ok": True})

            app.router.add_get("/health", health_check)
            app.router.add_get("/", health_check)

            # Логируем зарегистрированные маршруты
            logger.info("Зарегистрированные маршруты:")
            for route in app.router.routes():
                logger.info(f"  {route.method} {route.resource.canonical}")

            # Запускаем объединенный сервер (webhook + health check)
            port = int(PORT)
            logger.info(f"Запуск объединенного сервера (webhook + health) на порту {port}")

            # Запускаем сервер в фоне
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            logger.info(f"Сервер запущен на http://0.0.0.0:{port}")

            # ТЕПЕРЬ устанавливаем webhook после запуска сервера
            try:
                await bot.set_webhook(url=WEBHOOK_URL)
                logger.info(f"Webhook установлен: {WEBHOOK_URL}")
            except Exception as e:
                logger.error(f"Ошибка установки webhook: {e}")
                # Не завершаем процесс, продолжаем работу

            logger.info("Webhook режим активирован")

            # Ждем бесконечно, чтобы сервер не завершился
            try:
                while True:
                    await asyncio.sleep(3600)  # Спим по часу
            except asyncio.CancelledError:
                logger.info("Получен сигнал завершения")
            finally:
                await runner.cleanup()

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


# Обработчики для управления статусами событий
@dp.callback_query(F.data.startswith("close_event_"))
async def handle_close_event(callback: types.CallbackQuery):
    """Завершение мероприятия"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    success = change_event_status(event_id, "closed", user_id)
    if success:
        # Получаем название события для сообщения
        events = get_user_events(user_id)
        event_name = "мероприятие"
        if events:
            event = next((e for e in events if e["id"] == event_id), None)
            if event:
                event_name = event["title"]

        await callback.answer(f"✅ Мероприятие '{event_name}' завершено!")

        # Обновляем сообщение
        if events:
            first_event = events[0]
            text = f"📋 **Ваши события:**\n\n{format_event_for_display(first_event)}"
            buttons = get_status_change_buttons(first_event["id"], first_event["status"])
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
                ]
            )
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await callback.answer("❌ Ошибка при завершении мероприятия")


@dp.callback_query(F.data.startswith("open_event_"))
async def handle_open_event(callback: types.CallbackQuery):
    """Возобновление мероприятия"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    success = change_event_status(event_id, "open", user_id)
    if success:
        # Получаем название события для сообщения
        events = get_user_events(user_id)
        event_name = "мероприятие"
        if events:
            event = next((e for e in events if e["id"] == event_id), None)
            if event:
                event_name = event["title"]

        await callback.answer(f"🔄 Мероприятие '{event_name}' снова активно!")

        # Обновляем сообщение
        if events:
            first_event = events[0]
            text = f"📋 **Ваши события:**\n\n{format_event_for_display(first_event)}"
            buttons = get_status_change_buttons(first_event["id"], first_event["status"])
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
                ]
            )
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await callback.answer("❌ Ошибка при возобновлении мероприятия")


@dp.callback_query(F.data.startswith("edit_event_"))
async def handle_edit_event(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования события"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    # Проверяем, что событие принадлежит пользователю
    events = get_user_events(user_id)
    event_exists = any(event["id"] == event_id for event in events)

    if not event_exists:
        await callback.answer("❌ Событие не найдено или не принадлежит вам")
        return

    # Сохраняем ID события в состоянии
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.choosing_field)

    # Показываем меню редактирования
    keyboard = edit_event_keyboard(event_id)
    await callback.message.answer(
        "✏️ **Редактирование события**\n\nВыберите, что хотите изменить:", parse_mode="Markdown", reply_markup=keyboard
    )
    await callback.answer()


# Обработчики для выбора полей редактирования
@dp.callback_query(F.data.startswith("edit_title_"))
async def handle_edit_title_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования названия"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    logging.info(f"handle_edit_title_choice: пользователь {user_id} выбрал редактирование названия события {event_id}")

    # Сохраняем ID события в состоянии
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.waiting_for_title)

    logging.info("handle_edit_title_choice: состояние установлено в EventEditing.waiting_for_title")

    await callback.message.answer("✍️ Введите новое название события:")
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_date_"))
async def handle_edit_date_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования даты"""
    await state.set_state(EventEditing.waiting_for_date)
    await callback.message.answer("📅 Введите новую дату в формате ДД.ММ.ГГГГ (например: 12.09.2025):")
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_time_"))
async def handle_edit_time_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования времени"""
    await state.set_state(EventEditing.waiting_for_time)
    await callback.message.answer("⏰ Введите новое время в формате ЧЧ:ММ (например: 18:30):")
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_location_"))
async def handle_edit_location_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования локации"""
    await state.set_state(EventEditing.waiting_for_location)
    await callback.message.answer("📍 Введите новое место проведения:")
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_description_"))
async def handle_edit_description_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования описания"""
    await state.set_state(EventEditing.waiting_for_description)
    await callback.message.answer("📝 Введите новое описание:")
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_finish_"))
async def handle_edit_finish(callback: types.CallbackQuery, state: FSMContext):
    """Завершение редактирования"""
    data = await state.get_data()
    event_id = data.get("event_id")

    if event_id:
        # Получаем обновленное событие
        events = get_user_events(callback.from_user.id)
        updated_event = next((event for event in events if event["id"] == event_id), None)

        if updated_event:
            text = f"✅ **Событие обновлено!**\n\n{format_event_for_display(updated_event)}"
            buttons = get_status_change_buttons(updated_event["id"], updated_event["status"])
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
                ]
            )
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

    await state.clear()
    await callback.answer("✅ Редактирование завершено!")


# Обработчики ввода данных для редактирования
@dp.message(EventEditing.waiting_for_title)
async def handle_title_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового названия"""
    data = await state.get_data()
    event_id = data.get("event_id")

    logging.info(
        f"handle_title_input: получен ввод '{message.text}' для события {event_id} от пользователя {message.from_user.id}"
    )

    if event_id and message.text:
        logging.info(f"handle_title_input: вызываем update_event_field для события {event_id}")
        success = update_event_field(event_id, "title", message.text.strip(), message.from_user.id)
        logging.info(f"handle_title_input: результат update_event_field: {success}")

        if success:
            await message.answer("✅ Название обновлено!")
            keyboard = edit_event_keyboard(event_id)
            await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
            await state.set_state(EventEditing.choosing_field)
        else:
            await message.answer("❌ Ошибка при обновлении названия")
    else:
        await message.answer("❌ Введите корректное название")


@dp.message(EventEditing.waiting_for_date)
async def handle_date_input(message: types.Message, state: FSMContext):
    """Обработка ввода новой даты"""
    data = await state.get_data()
    event_id = data.get("event_id")

    if event_id and message.text:
        success = update_event_field(event_id, "starts_at", message.text.strip(), message.from_user.id)
        if success:
            await message.answer("✅ Дата обновлена!")
            keyboard = edit_event_keyboard(event_id)
            await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
            await state.set_state(EventEditing.choosing_field)
        else:
            await message.answer("❌ Ошибка при обновлении даты. Проверьте формат (ДД.ММ.ГГГГ)")
    else:
        await message.answer("❌ Введите корректную дату")


@dp.message(EventEditing.waiting_for_time)
async def handle_time_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового времени"""
    data = await state.get_data()
    event_id = data.get("event_id")

    if event_id and message.text:
        # Для времени нужно получить текущую дату и объединить с новым временем
        try:
            from datetime import datetime

            # Получаем текущую дату события
            events = get_user_events(message.from_user.id)
            current_event = next((event for event in events if event["id"] == event_id), None)

            if current_event and current_event["starts_at"]:
                current_date = current_event["starts_at"].strftime("%d.%m.%Y")
                new_datetime = f"{current_date} {message.text.strip()}"
                success = update_event_field(event_id, "starts_at", new_datetime, message.from_user.id)
            else:
                # Если нет текущей даты, используем сегодняшнюю
                today = datetime.now().strftime("%d.%m.%Y")
                new_datetime = f"{today} {message.text.strip()}"
                success = update_event_field(event_id, "starts_at", new_datetime, message.from_user.id)

            if success:
                await message.answer("✅ Время обновлено!")
                keyboard = edit_event_keyboard(event_id)
                await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
                await state.set_state(EventEditing.choosing_field)
            else:
                await message.answer("❌ Ошибка при обновлении времени. Проверьте формат (ЧЧ:ММ)")
        except Exception:
            await message.answer("❌ Ошибка при обновлении времени. Проверьте формат (ЧЧ:ММ)")
    else:
        await message.answer("❌ Введите корректное время")


@dp.message(EventEditing.waiting_for_location)
async def handle_location_input(message: types.Message, state: FSMContext):
    """Обработка ввода новой локации"""
    data = await state.get_data()
    event_id = data.get("event_id")

    if event_id and message.text:
        success = update_event_field(event_id, "location_name", message.text.strip(), message.from_user.id)
        if success:
            await message.answer("✅ Локация обновлена!")
            keyboard = edit_event_keyboard(event_id)
            await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
            await state.set_state(EventEditing.choosing_field)
        else:
            await message.answer("❌ Ошибка при обновлении локации")
    else:
        await message.answer("❌ Введите корректную локацию")


@dp.message(EventEditing.waiting_for_description)
async def handle_description_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового описания"""
    data = await state.get_data()
    event_id = data.get("event_id")

    if event_id and message.text:
        success = update_event_field(event_id, "description", message.text.strip(), message.from_user.id)
        if success:
            await message.answer("✅ Описание обновлено!")
            keyboard = edit_event_keyboard(event_id)
            await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
            await state.set_state(EventEditing.choosing_field)
        else:
            await message.answer("❌ Ошибка при обновлении описания")
    else:
        await message.answer("❌ Введите корректное описание")


@dp.callback_query(F.data.startswith("next_event_"))
async def handle_next_event(callback: types.CallbackQuery):
    """Переход к следующему событию"""
    user_id = callback.from_user.id
    events = get_user_events(user_id)

    if len(events) > 1:
        # Показываем второе событие
        second_event = events[1]
        text = f"📋 **Ваши события:**\n\n{format_event_for_display(second_event)}"
        buttons = get_status_change_buttons(second_event["id"], second_event["status"])
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
            ]
        )

        # Добавляем кнопку "Предыдущее событие"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Предыдущее", callback_data="prev_event_0")])

        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()
    else:
        await callback.answer("Это единственное событие")


@dp.callback_query(F.data.startswith("back_to_main_"))
async def handle_back_to_main(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.answer("🏠 Вы вернулись в главное меню", reply_markup=main_menu_kb())
    await callback.answer("🏠 Возврат в главное меню")


@dp.callback_query(F.data.startswith("prev_event_"))
async def handle_prev_event(callback: types.CallbackQuery):
    """Возврат к предыдущему событию"""
    user_id = callback.from_user.id
    events = get_user_events(user_id)

    if events:
        # Показываем первое событие
        first_event = events[0]
        text = f"📋 **Ваши события:**\n\n{format_event_for_display(first_event)}"
        buttons = get_status_change_buttons(first_event["id"], first_event["status"])
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
            ]
        )

        # Добавляем кнопку "Следующее событие" если есть еще события
        if len(events) > 1:
            keyboard.inline_keyboard.append([InlineKeyboardButton(text="➡️ Следующее", callback_data="next_event_1")])

        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()


if __name__ == "__main__":
    asyncio.run(main())
