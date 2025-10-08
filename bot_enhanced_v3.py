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
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    ReplyKeyboardMarkup,
)

from config import load_settings
from database import Event, User, create_all, get_session, init_engine
from rockets_service import award_rockets_for_activity
from simple_status_manager import (
    auto_close_events,
    change_event_status,
    format_event_for_display,
    get_status_change_buttons,
    get_user_events,
)
from tasks_service import (
    accept_task,
    cancel_task,
    complete_task,
    get_daily_tasks,
    get_user_active_tasks,
)
from utils.geo_utils import haversine_km
from utils.static_map import build_static_map_url, fetch_static_map
from utils.unified_events_service import UnifiedEventsService


def get_user_display_name(user: types.User) -> str:
    """Получает отображаемое имя пользователя: username или first_name"""
    if user.username:
        return f"@{user.username}"
    elif user.first_name:
        return user.first_name
    else:
        return f"User {user.id}"


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
    }

    for event in events:
        event_type = event.get("type", "")
        event.get("source", "")

        if event_type == "user":
            groups["users"].append(event)
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
    Поддерживает три типа событий: source, user, ai_parsed
    """
    from config import load_settings
    from logging_helpers import DropStats
    from venue_enrich import enrich_venue_from_text

    settings = load_settings()
    drop = DropStats()
    kept = []
    kept_by_type = {"source": 0, "user": 0, "ai_parsed": 0}

    logger.info(f"🔍 PROCESSING {len(events)} events for filtering")
    for e in events:
        # 0) Сначала обогащаем локацию из текста
        e = enrich_venue_from_text(e)
        logger.info(
            f"🔍 EVENT: {e.get('title')}, coords: {e.get('lat')}, {e.get('lng')}, type: {e.get('type')}, source: {e.get('source')}"
        )

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

        # Для user URL не обязателен
        if event_type == "user" and not url:
            # Пользовательские события могут не иметь URL
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
                    drop.add("event_expired", title)
                    continue

            # Для пользовательских событий используем радиус пользователя
            user_radius = radius_km
            logger.info(f"🔍 FILTERING USER EVENTS: user_radius={user_radius}, user_point={user_point}")
            if user_point and user_radius is not None:
                # Получаем координаты события
                event_lat = None
                event_lng = None

                # Проверяем новую структуру venue
                venue = e.get("venue", {})
                if venue.get("lat") is not None and venue.get("lon") is not None:
                    event_lat = venue.get("lat")
                    event_lng = venue.get("lon")
                    logger.info(f"🔍 COORDS FROM VENUE: {event_lat}, {event_lng}")
                # Проверяем старую структуру
                elif e.get("lat") is not None and e.get("lng") is not None:
                    event_lat = e.get("lat")
                    event_lng = e.get("lng")
                    logger.info(f"🔍 COORDS FROM EVENT: {event_lat}, {event_lng}")

                if event_lat is not None and event_lng is not None:
                    # Вычисляем расстояние
                    from utils.geo_utils import haversine_km

                    distance = haversine_km(user_point[0], user_point[1], event_lat, event_lng)
                    logger.info(
                        f"🔍 FILTER CHECK: event='{title}', event_coords=({event_lat},{event_lng}), user_coords=({user_point[0]},{user_point[1]}), distance={distance:.2f}km, user_radius={user_radius}km"
                    )
                    if distance > user_radius:
                        logger.warning(
                            f"❌ FILTERED OUT: '{title}' - distance {distance:.2f}km > radius {user_radius}km"
                        )
                        drop.add("user_event_out_of_radius", title)
                        continue
                    else:
                        logger.info(f"✅ KEPT: '{title}' - distance {distance:.2f}km <= radius {user_radius}km")
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

        # Логируем пользовательские события
        if event_type == "user":
            logger.info(
                f"🔍 PREPARE: title='{title}', organizer_id={e.get('organizer_id')}, organizer_username='{e.get('organizer_username')}'"
            )

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
    user_count = sum(1 for e in events if e.get("type") == "user")

    summary_lines = [f"🗺 Найдено {len(events)} событий рядом!"]

    # Показываем только ненулевые счетчики
    if source_count > 0:
        summary_lines.append(f"• Из источников: {source_count}")
    if ai_parsed_count > 0:
        summary_lines.append(f"• AI-парсинг: {ai_parsed_count}")
    if user_count > 0:
        summary_lines.append(f"• От пользователей: {user_count}")

    return "\n".join(summary_lines)


async def send_compact_events_list_prepared(
    message: types.Message,
    prepared_events: list,
    user_lat: float,
    user_lng: float,
    page: int = 0,
    user_radius: float = None,
):
    """
    Отправляет компактный список уже подготовленных событий с пагинацией в HTML формате
    """
    from config import load_settings

    settings = load_settings()

    # Используем радиус пользователя или дефолтный
    radius = get_user_radius(message.from_user.id, settings.default_radius_km)

    # Обогащаем события названиями мест и расстояниями
    for event in prepared_events:
        enrich_venue_name(event)
        event["distance_km"] = haversine_km(user_lat, user_lng, event["lat"], event["lng"])

    # Группируем и считаем
    groups = group_by_type(prepared_events)
    counts = make_counts(groups)

    # Определяем регион пользователя
    region = "bali"  # По умолчанию Бали
    if 55.0 <= user_lat <= 60.0 and 35.0 <= user_lng <= 40.0:  # Москва
        region = "moscow"
    elif 59.0 <= user_lat <= 60.5 and 29.0 <= user_lng <= 31.0:  # СПб
        region = "spb"
    elif -9.0 <= user_lat <= -8.0 and 114.0 <= user_lng <= 116.0:  # Бали
        region = "bali"

    # Сохраняем состояние для пагинации и расширения радиуса
    user_state[message.chat.id] = {
        "prepared": prepared_events,
        "counts": counts,
        "lat": user_lat,
        "lng": user_lng,
        "radius": int(radius),
        "page": 1,
        "diag": {"kept": len(prepared_events), "dropped": 0, "reasons_top3": []},
        "region": region,
    }

    # Рендерим страницу
    header_html = render_header(counts, radius_km=int(radius))
    events_text, total_pages = render_page(prepared_events, page + 1, page_size=5)

    # Отладочная информация

    text = header_html + "\n\n" + events_text

    # Вычисляем total_pages для fallback
    total_pages = max(1, ceil(len(prepared_events) / 5))

    # Создаем клавиатуру с кнопками пагинации и расширения радиуса
    keyboard = kb_pager(page + 1, total_pages, int(radius))

    try:
        # Отправляем компактный список событий в HTML формате
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"✅ Страница {page + 1} событий отправлена (HTML)")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки страницы {page + 1}: {e}")
        # Fallback - отправляем без форматирования
        await message.answer(f"📋 События (страница {page + 1} из {total_pages}):\n\n{text}", reply_markup=keyboard)


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

    # 1) Сначала фильтруем и группируем (после всех проверок publishable)
    prepared, diag = prepare_events_for_feed(events, user_point=(user_lat, user_lng), with_diag=True)
    logger.info(f"prepared: kept={diag['kept']} dropped={diag['dropped']} reasons_top3={diag['reasons_top3']}")
    logger.info(
        f"found_by_stream: source={diag['found_by_stream']['source']} ai_parsed={diag['found_by_stream']['ai_parsed']} user={diag['found_by_stream']['user']}"
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

    # Главное меню будет отправлено в последнем сообщении со списком событий


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
        "user": [e for e in prepared if e["type"] == "user"],
        "source": [e for e in prepared if e["type"] == "source"],
    }
    counts = {
        "all": len(prepared),
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
    Отправляет детальный список событий отдельным сообщением

    DEPRECATED: Use send_compact_events_list directly
    """
    import warnings

    warnings.warn(
        "send_detailed_events_list is deprecated. Use send_compact_events_list directly.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Используем новую компактную функцию
    await send_compact_events_list(message, events, user_lat, user_lng, page=0)


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Эталонные функции для рендеринга ---


def build_maps_url(e: dict) -> str:
    """Создает URL для маршрута с приоритетом location_url > venue_name > address > coordinates"""
    # Для пользовательских событий приоритизируем location_url (ссылка, которую указал пользователь)
    if e.get("type") == "user" and e.get("location_url"):
        return e["location_url"]

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
    elif t == "user":
        # Для пользовательских событий URL не обязателен
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
    import logging

    logger = logging.getLogger(__name__)

    title = html.escape(e.get("title", "Событие"))
    when = e.get("when_str", "")

    logger.info(f"🕐 render_event_html: title={title}, when_str='{when}', starts_at={e.get('starts_at')}")

    # Если when_str пустое, используем новую функцию human_when
    if not when:
        region = e.get("city", "bali")
        when = human_when(e, region)
        logger.info(f"🕐 render_event_html: использовали human_when, получили when='{when}'")
    dist = f"{e['distance_km']:.1f} км" if e.get("distance_km") is not None else ""

    # Определяем тип события, если не установлен
    event_type = e.get("type")
    source = e.get("source", "")
    source_type = e.get("source_type", "")

    logger.info(f"🔍 DEBUG: event_type={event_type}, source={source}, source_type={source_type}")

    if not event_type:
        if source == "user" or source_type == "user":
            event_type = "user"
        else:
            event_type = "source"

    logger.info(f"🔍 FINAL: event_type={event_type} для события '{e.get('title', 'Без названия')[:20]}'")

    # Поддерживаем новую структуру venue и старую
    venue = e.get("venue", {})
    venue_name = venue.get("name") or e.get("location_name") or e.get("venue_name")
    venue_address = venue.get("address") or e.get("address") or e.get("location_url")

    logger.info(f"🔍 DEBUG VENUE: venue={venue}, venue_name='{venue_name}', venue_address='{venue_address}'")
    logger.info(
        f"🔍 DEBUG EVENT FIELDS: e.get('venue_name')='{e.get('venue_name')}', e.get('location_name')='{e.get('location_name')}', e.get('address')='{e.get('address')}'"
    )

    # Приоритет: venue_name → address → coords → description (для пользовательских событий)
    if venue_name:
        venue_display = html.escape(venue_name)
        logger.info(f"🔍 DEBUG: Используем venue_name: '{venue_display}'")
    elif venue_address:
        venue_display = html.escape(venue_address)
        logger.info(f"🔍 DEBUG: Используем venue_address: '{venue_display}'")
    elif e.get("lat") and e.get("lng"):
        venue_display = f"координаты ({e['lat']:.4f}, {e['lng']:.4f})"
        logger.info(f"🔍 DEBUG: Используем координаты: '{venue_display}'")
    elif event_type == "user" and e.get("description"):
        # Для пользовательских событий показываем описание вместо "Локация уточняется"
        description = e.get("description", "").strip()
        if description:
            # Ограничиваем длину описания для красоты
            if len(description) > 100:
                description = description[:97] + "..."
            venue_display = html.escape(description)
            logger.info(f"🔍 DEBUG: Используем описание: '{venue_display}'")
        else:
            venue_display = "📍 Локация уточняется"
            logger.info(f"🔍 DEBUG: Описание пустое, используем fallback: '{venue_display}'")
    else:
        venue_display = "📍 Локация уточняется"
        logger.info(f"🔍 DEBUG: Используем fallback: '{venue_display}'")

    # Источник/Автор - ТОЛЬКО из таблицы events
    if event_type == "user":
        organizer_id = e.get("organizer_id")
        organizer_username = e.get("organizer_username")  # Берем ТОЛЬКО из таблицы events

        logger.info(
            f"👤 Пользовательское событие: organizer_id={organizer_id}, organizer_username={organizer_username}"
        )

        # Используем единообразную функцию для отображения автора
        from utils.author_display import format_author_display

        src_part = format_author_display(organizer_id, organizer_username)
        logger.info(f"👤 Отображение автора: {src_part}")
        logger.info(
            f"👤 DEBUG: organizer_id={organizer_id}, organizer_username='{organizer_username}', src_part='{src_part}'"
        )
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

    # Добавляем таймер для пользовательских событий
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

    logger.info(f"🕐 render_event_html ИТОГ: title={title}, when='{when}', dist={dist}")
    logger.info(f"🔍 DEBUG: src_part='{src_part}', map_part='{map_part}'")

    # Формируем строку с автором
    author_line = f"{src_part}  " if src_part else ""
    logger.info(f"🔍 DEBUG: author_line='{author_line}', map_part='{map_part}'")

    # Добавляем описание для пользовательских событий
    description_part = ""
    if event_type == "user" and e.get("description"):
        description = e.get("description", "").strip()
        if description:
            # Ограничиваем длину описания для красоты
            if len(description) > 150:
                description = description[:147] + "..."
            description_part = f"\n📝 {html.escape(description)}"
            logger.info(f"🔍 DEBUG: Добавлено описание: '{description[:50]}...'")

    logger.info(f"🔍 DEBUG: ПЕРЕД final_html: venue_display='{venue_display}'")
    logger.info(f"🔍 DEBUG: venue_display repr: {repr(venue_display)}")
    logger.info(f"🔍 DEBUG: venue_display len: {len(venue_display)}")

    # Проверяем venue_display прямо в f-string
    test_venue = venue_display
    logger.info(f"🔍 DEBUG: test_venue='{test_venue}'")

    final_html = f"{idx}) <b>{title}</b> — {when} ({dist}){timer_part}\n📍 {test_venue}\n{author_line}{map_part}{description_part}\n"
    logger.info(f"🔍 DEBUG: ПОСЛЕ final_html: venue_display='{venue_display}'")
    logger.info(f"🔍 FINAL HTML: {final_html}")
    return final_html


def render_fallback(lat: float, lng: float) -> str:
    """Fallback страница при ошибках в пайплайне"""
    return (
        f"🗺 <b>Найдено рядом: 0</b>\n"
        f"• 👥 От пользователей: 0\n"
        f"• 🌐 Из источников: 0\n\n"
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
    import logging

    logger = logging.getLogger(__name__)

    if not events:
        return "Поблизости пока ничего не нашли.", 1

    total_pages = max(1, ceil(len(events) / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size

    parts = []
    for idx, e in enumerate(events[start:end], start=start + 1):
        logger.info(f"🕐 render_page: событие {idx} - starts_at={e.get('starts_at')}, title={e.get('title')}")
        try:
            html = render_event_html(e, idx)
            parts.append(html)
        except Exception as e_render:
            logger.error(f"❌ Ошибка рендеринга события {idx}: {e_render}")
            # Fallback для одного события
            title = e.get("title", "Без названия")
            parts.append(f"{idx}) {title}")

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

    # Добавляем кнопки расширения радиуса, используя фиксированные RADIUS_OPTIONS
    if current_radius is None:
        current_radius = int(settings.default_radius_km)

    # Находим следующие доступные радиусы из RADIUS_OPTIONS
    # Не предлагаем расширить до 5 км, если текущий радиус уже 5 км или больше
    for radius_option in RADIUS_OPTIONS:
        if radius_option > current_radius:
            # Не показываем кнопку "расширить до 5 км" - это минимальный радиус
            if radius_option == 5:
                continue
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🔍 Расширить до {radius_option} км",
                        callback_data=f"rx:{radius_option}",
                    )
                ]
            )

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
    counts = {
        "all": total,
        "user": len(groups.get("user", [])),  # Только пользовательские события
        "sources": len(groups.get("source", [])) + ai_count,  # AI события считаются как источники
    }
    logger.info(f"🔍 make_counts: groups={list(groups.keys())}, counts={counts}")
    return counts


def render_header(counts, radius_km: int = None) -> str:
    """Рендерит заголовок с счетчиками (только ненулевые)"""
    if radius_km:
        lines = [f"🗺 В радиусе {radius_km} км найдено: <b>{counts['all']}</b>"]
    else:
        lines = [f"🗺 Найдено рядом: <b>{counts['all']}</b>"]

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
    """Получает радиус пользователя из БД или возвращает дефолтный"""
    try:
        with get_session() as session:
            user = session.get(User, user_id)
            if user and user.default_radius_km:
                return int(user.default_radius_km)
    except Exception as e:
        logger.warning(f"Ошибка получения радиуса пользователя {user_id}: {e}")
    return default_km


def set_user_radius(user_id: int, radius_km: int, tg_user=None) -> None:
    """Устанавливает радиус пользователя в БД"""
    try:
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.default_radius_km = radius_km
                session.commit()
            else:
                # Создаем пользователя если его нет (требует объект tg_user)
                if tg_user:
                    user = User(
                        id=user_id,
                        username=tg_user.username,
                        full_name=get_user_display_name(tg_user),
                        default_radius_km=radius_km,
                    )
                    session.add(user)
                    session.commit()
                else:
                    logger.warning(f"Пользователь {user_id} не найден в БД и tg_user не передан, радиус не сохранен")
    except Exception as e:
        logger.error(f"Ошибка сохранения радиуса пользователя {user_id}: {e}")


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


# Инициализация базы данных
init_engine(settings.database_url)
create_all()

# Health check сервер будет запущен в main() вместе с webhook

# Создание бота и диспетчера
bot = Bot(token=settings.telegram_token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# BOT_ID для корректной фильтрации в групповых чатах
BOT_ID: int = None


# Состояния для FSM
class EventCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_location_type = State()  # Выбор типа локации
    waiting_for_location_link = State()  # Ввод ссылки Google Maps
    waiting_for_location = State()  # Legacy - для обратной совметимости
    waiting_for_description = State()
    confirmation = State()
    waiting_for_feedback = State()  # Ожидание фидбека для задания


# Отдельные FSM состояния для событий сообществ (групповых чатов)
class CommunityEventCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_city = State()  # Город события
    waiting_for_location_url = State()  # Ссылка на место
    waiting_for_description = State()
    confirmation = State()


class TaskFlow(StatesGroup):
    waiting_for_location = State()  # Ждем геолокацию для заданий
    waiting_for_category = State()  # Ждем выбор категории
    waiting_for_task_selection = State()  # Ждем выбор задания
    waiting_for_custom_location = State()  # Ждем ввод своей локации для задания


class EventSearch(StatesGroup):
    waiting_for_location = State()  # Ждем геолокацию для поиска событий


class EventEditing(StatesGroup):
    choosing_field = State()
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_location_type = State()  # Новое состояние для выбора типа локации
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
            elif field == "location_url":
                event.location_url = value
                logging.info(f"Обновлен URL локации события {event_id}: '{value}'")
            elif field == "lat":
                event.lat = float(value)
                logging.info(f"Обновлена широта события {event_id}: {value}")
            elif field == "lng":
                event.lng = float(value)
                logging.info(f"Обновлена долгота события {event_id}: {value}")
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


async def send_spinning_menu(message):
    """Отправляет анимированное меню с эпической ракетой"""
    import asyncio

    # Последовательность для эффекта эпического полета ракеты с взрывами
    rocket_frames = ["🚀", "🔥", "💥", "⚡", "🎯"]

    # Отправляем первый кадр
    menu_message = await message.answer(rocket_frames[0], reply_markup=main_menu_kb())

    # Анимируем эпический полет (динамичная анимация)
    try:
        for frame in rocket_frames[1:]:
            await asyncio.sleep(0.5)  # Пауза между кадрами для эффектности
            await menu_message.edit_text(frame, reply_markup=main_menu_kb())
    except Exception:
        # Если редактирование не удалось, просто оставляем мишень
        try:
            await menu_message.edit_text("🎯", reply_markup=main_menu_kb())
        except Exception:
            pass


def human_when(event: dict, region: str) -> str:
    """Возвращает '14:30' или пустую строку, если времени нет"""
    from datetime import datetime

    import pytz

    REGION_TZ = {
        "bali": "Asia/Makassar",
        "moscow": "Europe/Moscow",
        "spb": "Europe/Moscow",
    }

    dt_utc = event.get("starts_at") or event.get("start_time")  # подстраховка
    if not dt_utc:
        return ""

    if isinstance(dt_utc, str):
        # на всякий случай – ISO в БД могут прийти строкой
        try:
            dt_utc = datetime.fromisoformat(dt_utc.replace("Z", "+00:00"))
        except Exception:
            return ""

    try:
        tz = pytz.timezone(REGION_TZ.get(region, "UTC"))
        local = dt_utc.astimezone(tz)
        # если у источника была только дата без времени → не печатаем 00:00
        if not (local.hour == 0 and local.minute == 0):
            return local.strftime("%H:%M")
        return ""
    except Exception:
        return ""


def format_event_time(starts_at, city="bali") -> str:
    """Форматирует время события для отображения"""
    import logging

    logger = logging.getLogger(__name__)

    logger.info(f"🕐 format_event_time: starts_at={starts_at}, type={type(starts_at)}, city={city}")

    if not starts_at:
        logger.info("🕐 starts_at пустое, возвращаем 'время уточняется'")
        return "время уточняется"

    try:
        from datetime import datetime

        from utils.simple_timezone import get_city_timezone

        # Получаем часовой пояс города
        tz_name = get_city_timezone(city)

        # Если starts_at это строка, парсим её
        if isinstance(starts_at, str):
            # Пробуем разные форматы
            try:
                starts_at = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return "время уточняется"

        # Конвертируем в локальное время города
        import pytz

        utc = pytz.UTC
        local_tz = pytz.timezone(tz_name)

        if starts_at.tzinfo is None:
            starts_at = utc.localize(starts_at)

        local_time = starts_at.astimezone(local_tz)

        # Форматируем красиво
        now = datetime.now(local_tz)
        today = now.date()

        if local_time.date() == today:
            # Сегодня - показываем только время
            return f"сегодня в {local_time.strftime('%H:%M')}"
        else:
            # Другой день - показываем дату и время
            return f"{local_time.strftime('%d.%m в %H:%M')}"

    except Exception:
        # Если что-то пошло не так, возвращаем базовое значение
        return "время уточняется"


def get_user_display_name_by_id(user_id: int) -> str:
    """Получает отображаемое имя пользователя по ID"""
    try:
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                if user.username:
                    return f"@{user.username}"
                elif user.full_name:
                    return user.full_name
                else:
                    return "Пользователь"
            return "Пользователь"
    except Exception:
        return "Пользователь"


def get_example_date():
    """Возвращает пример даты (сегодня или завтра)"""
    from datetime import timedelta

    today = datetime.now()
    # Если уже поздно (после 18:00), предлагаем завтра
    if today.hour >= 18:
        example_date = today + timedelta(days=1)
    else:
        example_date = today
    return example_date.strftime("%d.%m.%Y")


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Создаёт главное меню"""
    from config import load_settings

    load_settings()

    keyboard = [
        [KeyboardButton(text="📍 Что рядом"), KeyboardButton(text="➕ Создать")],
        [KeyboardButton(text="🎯 Квесты на районе"), KeyboardButton(text="🏆 Мои квесты")],
    ]

    keyboard.extend(
        [
            [KeyboardButton(text="🔗 Поделиться"), KeyboardButton(text="📋 Мои события")],
            [KeyboardButton(text="💬 Написать отзыв Разработчику"), KeyboardButton(text="🚀 Старт")],
        ]
    )

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def ensure_user_exists(user_id: int, tg_user) -> None:
    """Создаёт пользователя в БД если его нет"""
    try:
        with get_session() as session:
            user = session.get(User, user_id)
            if not user and tg_user:
                user = User(
                    id=user_id,
                    username=tg_user.username,
                    full_name=get_user_display_name(tg_user),
                    default_radius_km=5,  # дефолтный радиус
                )
                session.add(user)
                session.commit()
                logger.info(f"Создан новый пользователь {user_id}")
    except Exception as e:
        logger.error(f"Ошибка создания пользователя {user_id}: {e}")


def kb_radius(current: int | None = None) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора радиуса поиска с выделением текущего"""
    buttons = []
    for km in RADIUS_OPTIONS:
        label = f"{'✅ ' if km == current else ''}{km} км"
        buttons.append(InlineKeyboardButton(text=label, callback_data=f"{CB_RADIUS_PREFIX}{km}"))
    # одна строка из 4 кнопок
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


# Удалена старая функция radius_selection_kb() - используем только kb_radius()


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
async def cmd_start(message: types.Message, state: FSMContext, command: CommandObject = None):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    chat_type = message.chat.type

    # Проверяем, есть ли параметр group_ (deep-link из группы)
    group_id = None
    if command and command.args and command.args.startswith("group_"):
        try:
            group_id = int(command.args.replace("group_", ""))
            logger.info(f"🔥 cmd_start: пользователь {user_id} перешёл из группы {group_id}")
        except ValueError:
            logger.warning(f"🔥 cmd_start: неверный параметр group_ {command.args}")

    # Если это переход из группы, запускаем FSM для создания группового события
    if group_id and chat_type == "private":
        await start_group_event_creation(message, group_id, state)
        return

    # Создаем пользователя если его нет
    ensure_user_exists(user_id, message.from_user)
    logger.info(f"cmd_start: пользователь {user_id}")

    # Разная логика для личных и групповых чатов
    if chat_type == "private":
        # Упрощенная логика - всегда показываем полное меню
        welcome_text = (
            "Привет! EventAroundBot твой цифровой помощник по активностям рядом.\n\n"
            "📍 Что рядом: находи события в радиусе 5–20 км\n"
            "🎯 Квесты на районе: автоматизированный подбор заданий с наградами 🚀\n\n"
            "➕ Создавать: организуй встречи и приглашай друзей\n"
            "🔗 Поделиться: добавь бота в чат — появится лента встреч и планов только для участников сообщества\n\n"
            "🚀 Начинай приключение"
        )
        await message.answer(welcome_text, reply_markup=main_menu_kb())
    else:
        # Групповой чат - упрощенный функционал для событий участников
        welcome_text = (
            "👋 **Привет! Я EventAroundBot для группового чата!**\n\n"
            "🎯 **В этом чате я помогаю:**\n"
            "• Создавать события участников чата\n"
            "• Показывать все события, созданные в этом чате\n"
            "• Переходить к полному боту для поиска по геолокации\n\n"
            "💡 **Выберите действие:**"
        )

        # Получаем username бота для создания ссылки
        bot_info = await bot.get_me()

        # Создаем inline кнопки для групповых чатов
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Создать событие", url=f"https://t.me/{bot_info.username}?start=group_{message.chat.id}"
                    )
                ],
                [InlineKeyboardButton(text="📋 События этого чата", callback_data="group_chat_events")],
                [InlineKeyboardButton(text="🚀 Полный бот (с геолокацией)", url=f"https://t.me/{bot_info.username}")],
                [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_bot")],
            ]
        )

        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")


async def start_group_event_creation(message: types.Message, group_id: int, state: FSMContext):
    """Запуск создания события для группы в ЛС"""
    logger.info(f"🔥 start_group_event_creation: запуск FSM для группы {group_id}, пользователь {message.from_user.id}")

    # Запускаем FSM для создания группового события
    await state.set_state(CommunityEventCreation.waiting_for_title)
    await state.update_data(group_id=group_id, creator_id=message.from_user.id, scope="group")

    welcome_text = (
        "🎉 **Создание события для группы**\n\n"
        "Вы перешли из группы для создания события. "
        "Давайте создадим интересное мероприятие!\n\n"
        "✍️ **Введите название события:**"
    )

    await message.answer(welcome_text, parse_mode="Markdown")


# Обработчики FSM для создания событий в ЛС (для групп)
@dp.message(CommunityEventCreation.waiting_for_title, F.chat.type == "private")
async def process_community_title_pm(message: types.Message, state: FSMContext):
    """Обработка названия события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_title_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n✍️ **Введите название события:**",
            parse_mode="Markdown",
        )
        return

    title = message.text.strip()
    logger.info(f"🔥 process_community_title_pm: получили название '{title}' от пользователя {message.from_user.id}")

    await state.update_data(title=title)
    await state.set_state(CommunityEventCreation.waiting_for_date)
    example_date = get_example_date()

    await message.answer(
        f"**Название сохранено:** *{title}* ✅\n\n📅 **Введите дату** (например: {example_date}):",
        parse_mode="Markdown",
    )


@dp.message(CommunityEventCreation.waiting_for_date, F.chat.type == "private")
async def process_community_date_pm(message: types.Message, state: FSMContext):
    """Обработка даты события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_date_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n📅 **Введите дату** (например: 15.12.2024):",
            parse_mode="Markdown",
        )
        return

    date = message.text.strip()
    logger.info(f"🔥 process_community_date_pm: получили дату '{date}' от пользователя {message.from_user.id}")

    await state.update_data(date=date)
    await state.set_state(CommunityEventCreation.waiting_for_time)

    await message.answer(
        f"**Дата сохранена:** {date} ✅\n\n⏰ **Введите время** (например: 19:00):", parse_mode="Markdown"
    )


@dp.message(CommunityEventCreation.waiting_for_time, F.chat.type == "private")
async def process_community_time_pm(message: types.Message, state: FSMContext):
    """Обработка времени события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_time_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n⏰ **Введите время** (например: 19:00):",
            parse_mode="Markdown",
        )
        return

    time = message.text.strip()
    logger.info(f"🔥 process_community_time_pm: получили время '{time}' от пользователя {message.from_user.id}")

    await state.update_data(time=time)
    await state.set_state(CommunityEventCreation.waiting_for_city)

    await message.answer(
        f"**Время сохранено:** {time} ✅\n\n🏙️ **Введите город** (например: Москва):", parse_mode="Markdown"
    )


@dp.message(CommunityEventCreation.waiting_for_city, F.chat.type == "private")
async def process_community_city_pm(message: types.Message, state: FSMContext):
    """Обработка города события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_city_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n🏙️ **Введите город** (например: Москва):",
            parse_mode="Markdown",
        )
        return

    city = message.text.strip()
    logger.info(f"🔥 process_community_city_pm: получили город '{city}' от пользователя {message.from_user.id}")

    await state.update_data(city=city)
    await state.set_state(CommunityEventCreation.waiting_for_location_url)

    await message.answer(
        f"**Город сохранен:** {city} ✅\n\n🔗 **Введите ссылку на место** (Google Maps или адрес):",
        parse_mode="Markdown",
    )


@dp.message(CommunityEventCreation.waiting_for_location_url, F.chat.type == "private")
async def process_community_location_url_pm(message: types.Message, state: FSMContext):
    """Обработка ссылки на место события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_location_url_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n🔗 **Введите ссылку на место** (Google Maps или адрес):",
            parse_mode="Markdown",
        )
        return

    location_url = message.text.strip()
    logger.info(f"🔥 process_community_location_url_pm: получили ссылку от пользователя {message.from_user.id}")

    # Автоматически определяем название места по ссылке
    location_name = "Место по ссылке"  # Базовое название
    try:
        # Пытаемся извлечь название из Google Maps ссылки
        if "maps.google.com" in location_url or "goo.gl" in location_url:
            # Для Google Maps ссылок можно попробовать извлечь название
            # Пока используем базовое название, но можно расширить логику
            location_name = "Место на карте"
        elif "yandex.ru/maps" in location_url:
            location_name = "Место на Яндекс.Картах"
        else:
            location_name = "Место по ссылке"
    except Exception as e:
        logger.warning(f"Не удалось определить название места: {e}")
        location_name = "Место по ссылке"

    await state.update_data(location_url=location_url, location_name=location_name)
    await state.set_state(CommunityEventCreation.waiting_for_description)

    await message.answer(
        f"**Ссылка сохранена** ✅\n📍 **Место:** {location_name}\n\n📝 **Введите описание события** (что будет происходить, кому интересно):",
        parse_mode="Markdown",
    )


@dp.message(CommunityEventCreation.waiting_for_description, F.chat.type == "private")
async def process_community_description_pm(message: types.Message, state: FSMContext):
    """Обработка описания события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_description_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n📝 **Введите описание события** (что будет происходить, кому интересно):",
            parse_mode="Markdown",
        )
        return

    description = message.text.strip()
    logger.info(f"🔥 process_community_description_pm: получили описание от пользователя {message.from_user.id}")

    await state.update_data(description=description)
    data = await state.get_data()
    await state.set_state(CommunityEventCreation.confirmation)

    # Логируем данные для отладки
    logger.info(f"🔥 process_community_description_pm: данные FSM: {data}")

    # Показываем итог перед подтверждением
    await message.answer(
        f"📌 **Проверьте данные события:**\n\n"
        f"**Название:** {data.get('title', 'НЕ УКАЗАНО')}\n"
        f"**Дата:** {data.get('date', 'НЕ УКАЗАНО')}\n"
        f"**Время:** {data.get('time', 'НЕ УКАЗАНО')}\n"
        f"**Город:** {data.get('city', 'НЕ УКАЗАНО')}\n"
        f"**Место:** {data.get('location_name', 'НЕ УКАЗАНО')}\n"
        f"**Ссылка:** {data.get('location_url', 'НЕ УКАЗАНО')}\n"
        f"**Описание:** {data.get('description', 'НЕ УКАЗАНО')}\n\n"
        f"Если всё верно, нажмите ✅ Сохранить. Если нужно изменить — нажмите ❌ Отмена.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Сохранить", callback_data="community_event_confirm_pm"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="community_event_cancel_pm"),
                ]
            ]
        ),
    )


# Обработчики для inline кнопок в групповых чатов
@dp.callback_query(F.data == "group_create_event")
async def handle_group_create_event(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Создать событие в чате' в групповых чатах"""
    logger.info(
        f"🔥 handle_group_create_event: пользователь {callback.from_user.id} нажал кнопку создания события в чате {callback.message.chat.id}"
    )

    # Антидребезг: предотвращаем двойной старт FSM
    from time import time

    from group_chat_handlers import LAST_START

    chat_id = callback.message.chat.id
    current_time = time()
    if current_time - LAST_START.get(chat_id, 0) < 2:
        logger.info(f"🔥 handle_group_create_event: игнорируем двойной клик в чате {chat_id}")
        await callback.answer("⏳ Подождите, создание события уже запущено...")
        return

    LAST_START[chat_id] = current_time

    # Импортируем GroupCreate FSM
    from group_chat_handlers import GroupCreate

    # Получаем thread_id для поддержки тредов в супергруппах
    thread_id = callback.message.message_thread_id

    # Устанавливаем FSM состояние
    await state.set_state(GroupCreate.waiting_for_title)
    logger.info(f"🔥 handle_group_create_event: FSM состояние установлено в waiting_for_title, thread_id={thread_id}")

    # Отправляем сообщение с ForceReply для следующего шага
    prompt = await bot.send_message(
        chat_id=callback.message.chat.id,
        text="✍️ **Введите название мероприятия:**",
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
        message_thread_id=thread_id,
    )

    # Сохраняем контекст для "жёсткой привязки"
    await state.update_data(
        initiator_id=callback.from_user.id,
        prompt_msg_id=prompt.message_id,
        group_id=callback.message.chat.id,
        thread_id=thread_id,
    )

    logger.info(
        f"🔥 handle_group_create_event: set wait_for_title, thread_id={thread_id}, prompt_msg_id={prompt.message_id}"
    )

    await callback.answer()


@dp.callback_query(F.data == "group_chat_events")
async def handle_group_chat_events(callback: types.CallbackQuery):
    """Обработчик кнопки 'События этого чата' в групповых чатах"""
    chat_id = callback.message.chat.id

    # Получаем события сообщества через новый сервис
    from utils.community_events_service import CommunityEventsService

    community_service = CommunityEventsService()

    events = community_service.get_community_events(group_id=chat_id, limit=10, include_past=False)

    if not events:
        text = (
            "📋 **События этого чата**\n\n"
            "В этом чате пока нет созданных событий.\n\n"
            "💡 Создайте первое событие, нажав кнопку '➕ Создать событие в чате'!"
        )
    else:
        text = f"📋 **События этого чата** ({len(events)} событий):\n\n"
        for i, event in enumerate(events, 1):
            text += f"**{i}. {event['title']}**\n"
            if event["description"]:
                text += f"   {event['description'][:100]}{'...' if len(event['description']) > 100 else ''}\n"
            text += f"   📅 {event['starts_at'].strftime('%d.%m.%Y %H:%M')}\n"
            text += f"   🏙️ {event['city']}\n"
            if event["location_url"]:
                location_name = event.get("location_name", "Место")
                text += f"   📍 [{location_name}]({event['location_url']})\n"
            elif event["location_name"]:
                text += f"   📍 {event['location_name']}\n"
            text += f"   👤 Создал: @{event['organizer_username'] or 'Неизвестно'}\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="group_back_to_start")]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "group_myevents")
async def handle_group_myevents(callback: types.CallbackQuery):
    """Обработчик кнопки 'Мои события' в групповых чатах"""
    user_id = callback.from_user.id

    # Получаем события пользователя
    events = get_user_events(user_id)

    if not events:
        text = "📋 **Мои события**\n\nУ вас пока нет созданных событий.\n\nИспользуйте команду `/create` для создания нового события!"
    else:
        # Показываем только активные события
        active_events = [e for e in events if e.get("status") == "open"]

        if not active_events:
            text = "📋 **Мои события**\n\nУ вас нет активных событий.\n\nИспользуйте команду `/create` для создания нового события!"
        else:
            text = "📋 **Ваши активные события:**\n\n"
            for i, event in enumerate(active_events[:5], 1):
                event_text = format_event_for_display(event)
                text += f"{i}) {event_text}\n\n"

    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "group_hide_bot")
async def handle_group_hide_bot(callback: types.CallbackQuery):
    """Обработчик кнопки 'Спрятать бота' в групповых чатах"""
    chat_id = callback.message.chat.id

    # Любой пользователь может скрыть бота (особенно полезно для создателей событий)
    # Подтверждение действия
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
            [InlineKeyboardButton(text="✅ Да, спрятать", callback_data=f"group_hide_confirm_{chat_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="group_back_to_start")],
        ]
    )

    await callback.message.edit_text(confirmation_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data.regexp(r"^group_hide_confirm_\d+$"))
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

        logger.info(f"✅ Бот скрыт в чате {chat_id} администратором {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при скрытии бота в чате {chat_id}: {e}")
        await callback.answer("❌ Произошла ошибка при скрытии бота", show_alert=True)


@dp.callback_query(F.data == "community_event_confirm_pm")
async def confirm_community_event_pm(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение создания события сообщества в ЛС"""
    logger.info(
        f"🔥 confirm_community_event_pm: пользователь {callback.from_user.id} подтверждает создание события в ЛС"
    )

    try:
        data = await state.get_data()
        logger.info(f"🔥 confirm_community_event_pm: данные события: {data}")

        # Парсим дату и время
        from datetime import datetime

        date_str = data["date"]
        time_str = data["time"]
        starts_at = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")

        # Импортируем сервис для событий сообществ
        from utils.community_events_service import CommunityEventsService

        community_service = CommunityEventsService()

        # Создаем событие в сообществе
        event_id = community_service.create_community_event(
            group_id=data["group_id"],
            creator_id=callback.from_user.id,
            creator_username=callback.from_user.username or callback.from_user.first_name,
            title=data["title"],
            date=starts_at,
            description=data["description"],
            city=data["city"],
            location_name=data.get("location_name", "Место по ссылке"),
            location_url=data.get("location_url"),
        )

        logger.info(f"✅ Событие сообщества создано с ID: {event_id}")

        # Публикуем событие в группу
        group_id = data["group_id"]
        event_text = (
            f"🎉 **Новое событие!**\n\n"
            f"**{data['title']}**\n"
            f"📅 {data['date']} в {data['time']}\n"
            f"🏙️ {data['city']}\n"
            f"📍 {data['location_name']}\n"
            f"🔗 {data['location_url']}\n\n"
            f"📝 {data['description']}\n\n"
            f"*Создано пользователем @{callback.from_user.username or callback.from_user.first_name}*"
        )

        try:
            group_message = await bot.send_message(chat_id=group_id, text=event_text, parse_mode="Markdown")

            # Показываем ссылку на опубликованное сообщение
            group_link = f"https://t.me/c/{str(group_id)[4:]}/{group_message.message_id}"

            await callback.message.edit_text(
                f"🎉 **Событие создано и опубликовано!**\n\n"
                f"**{data['title']}**\n"
                f"📅 {data['date']} в {data['time']}\n"
                f"🏙️ {data['city']}\n"
                f"📍 {data['location_name']}\n\n"
                f"✅ Событие опубликовано в группе!\n"
                f"🔗 [Ссылка на сообщение]({group_link})",
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Ошибка публикации в группу: {e}")
            await callback.message.edit_text(
                f"✅ **Событие создано!**\n\n"
                f"**{data['title']}**\n"
                f"📅 {data['date']} в {data['time']}\n"
                f"🏙️ {data['city']}\n"
                f"📍 {data['location_name']}\n\n"
                f"⚠️ Не удалось опубликовать в группу, но событие сохранено.",
                parse_mode="Markdown",
            )

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка создания события: {e}")
        await callback.message.edit_text(
            "❌ **Произошла ошибка при создании события.** Попробуйте еще раз.", parse_mode="Markdown"
        )

    await callback.answer()


@dp.callback_query(F.data == "community_event_cancel_pm")
async def cancel_community_event_pm(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания события сообщества в ЛС"""
    logger.info(f"🔥 cancel_community_event_pm: пользователь {callback.from_user.id} отменил создание события в ЛС")

    await state.clear()
    await callback.message.edit_text(
        "❌ **Создание события отменено.**\n\n" "Если хотите создать событие, нажмите /start", parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(F.data == "group_cancel_create")
async def handle_group_cancel_create(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик отмены создания события в групповых чатах"""
    await state.clear()

    text = "❌ Создание события отменено."
    await callback.message.edit_text(text)
    await callback.answer()


@dp.callback_query(F.data == "group_back_to_start")
async def handle_group_back_to_start(callback: types.CallbackQuery):
    """Обработчик возврата в главное меню группового чата"""
    welcome_text = (
        "👋 **Привет! Я EventAroundBot для группового чата!**\n\n"
        "🎯 **В этом чате я помогаю:**\n"
        "• Создавать события участников чата\n"
        "• Показывать все события, созданные в этом чате\n"
        "• Переходить к полному боту для поиска по геолокации\n\n"
        "💡 **Выберите действие:**"
    )

    # Получаем username бота для создания ссылки
    bot_info = await bot.get_me()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Создать событие",
                    url=f"https://t.me/{bot_info.username}?start=group_{callback.message.chat.id}",
                )
            ],
            [InlineKeyboardButton(text="📋 События этого чата", callback_data="group_chat_events")],
            [InlineKeyboardButton(text="🚀 Полный бот (с геолокацией)", url=f"https://t.me/{bot_info.username}")],
            [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_bot")],
        ]
    )

    await callback.message.edit_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@dp.message(Command("nearby"))
@dp.message(F.text == "📍 Что рядом")
async def on_what_nearby(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Что рядом'"""
    # Устанавливаем состояние для поиска событий
    await state.set_state(EventSearch.waiting_for_location)

    # Создаем клавиатуру с кнопкой геолокации и главным меню
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,  # Кнопка исчезнет после использования
    )

    await message.answer(
        "Отправь свежую геопозицию, чтобы я нашла события рядом ✨",
        reply_markup=location_keyboard,
    )


@dp.message(F.location, TaskFlow.waiting_for_location)
async def on_location_for_tasks(message: types.Message, state: FSMContext):
    """Обработчик геолокации для заданий"""
    user_id = message.from_user.id
    lat = message.location.latitude
    lng = message.location.longitude

    # Логируем состояние для отладки
    current_state = await state.get_state()
    logger.info(f"📍 [ЗАДАНИЯ] Получена геолокация от пользователя {user_id}: {lat}, {lng}, состояние: {current_state}")

    # Сохраняем координаты пользователя
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.last_lat = lat
            user.last_lng = lng
            user.last_geo_at_utc = datetime.now(UTC)
            session.commit()
            logger.info(f"📍 Координаты пользователя {user_id} обновлены")

    # Переходим в состояние ожидания выбора категории
    await state.set_state(TaskFlow.waiting_for_category)

    # Показываем выбор категории после получения геолокации
    keyboard = [
        [InlineKeyboardButton(text="💪 Тело", callback_data="task_category:body")],
        [InlineKeyboardButton(text="🧘 Дух", callback_data="task_category:spirit")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await message.answer(
        "✅ **Геолокация получена!**\n\n"
        "Выберите категорию для получения персонализированных заданий:\n\n"
        "💪 **Тело** - спорт, йога, прогулки\n"
        "🧘 **Дух** - медитация, храмы, природа",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

    logger.info(f"📍 [ЗАДАНИЯ] Показаны категории для пользователя {user_id}")


@dp.message(F.location)
async def on_location(message: types.Message, state: FSMContext):
    """Обработчик получения геолокации"""
    # Проверяем состояние - если это для заданий, не обрабатываем здесь
    current_state = await state.get_state()
    logger.info(f"📍 Обработчик событий: состояние={current_state}")

    if current_state == TaskFlow.waiting_for_location:
        logger.info("📍 Пропускаем - это для заданий")
        return  # Пропускаем - это для заданий

    # Проверяем, что это состояние для поиска событий
    if current_state != EventSearch.waiting_for_location:
        logger.info(f"📍 Неизвестное состояние для геолокации: {current_state}")
        return

    lat = message.location.latitude
    lng = message.location.longitude

    # Логируем получение геолокации
    logger.info(f"📍 Получена геолокация для событий: lat={lat} lon={lng} (источник=пользователь)")

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
            logger.info(f"🔍 SEARCH COORDS: lat={lat}, lng={lng}, radius={radius}")
            events = events_service.search_events_today(city=city, user_lat=lat, user_lng=lng, radius_km=int(radius))

            # Конвертируем в старый формат для совместимости
            formatted_events = []
            logger.info(f"🕐 Получили {len(events)} событий из UnifiedEventsService")
            for event in events:
                starts_at_value = event.get("starts_at")
                logger.info(
                    f"🕐 ДО конвертации: {event.get('title')} - starts_at: {starts_at_value} (тип: {type(starts_at_value)})"
                )

                formatted_event = {
                    "title": event["title"],
                    "description": event["description"],
                    "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
                    "starts_at": event["starts_at"],  # Добавляем поле starts_at!
                    "city": event.get("city", "bali"),  # Добавляем город для правильного форматирования времени
                    "location_name": event["location_name"],
                    "location_url": event["location_url"],
                    "lat": event["lat"],
                    "lng": event["lng"],
                    "source": event.get("source", ""),  # Сохраняем оригинальный source из БД
                    "source_type": event.get("source_type", ""),  # Добавляем source_type отдельно
                    "url": event.get("event_url", ""),
                    "community_name": "",
                    "community_link": "",
                    # Добавляем поля автора для пользовательских событий
                    "organizer_id": event.get("organizer_id"),
                    "organizer_username": event.get("organizer_username"),
                }

                logger.info(
                    f"🕐 ПОСЛЕ конвертации: {formatted_event.get('title')} - starts_at: {formatted_event.get('starts_at')}"
                )

                # Логируем конвертацию для пользовательских событий
                if event.get("source") == "user":
                    logger.info(
                        f"🔍 CONVERT USER EVENT: title='{event.get('title')}', "
                        f"organizer_id={event.get('organizer_id')} -> {formatted_event.get('organizer_id')}, "
                        f"organizer_username='{event.get('organizer_username')}' -> '{formatted_event.get('organizer_username')}'"
                    )
                formatted_events.append(formatted_event)

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

        # Ракеты за поиск убраны из системы

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

                # Создаем кнопки расширения радиуса, используя фиксированные RADIUS_OPTIONS
                keyboard_buttons = []
                current_radius = int(radius)

                # Находим следующие доступные радиусы из RADIUS_OPTIONS
                for radius_option in RADIUS_OPTIONS:
                    if radius_option > current_radius:
                        # Не показываем кнопку "расширить до 5 км" - это минимальный радиус
                        if radius_option == 5:
                            continue
                        keyboard_buttons.append(
                            [
                                InlineKeyboardButton(
                                    text=f"🔍 Расширить поиск до {radius_option} км",
                                    callback_data=f"rx:{radius_option}",
                                )
                            ]
                        )

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
                    f"💡 Попробуй расширить поиск до {next(iter([r for r in RADIUS_OPTIONS if r > current_radius and r != 5]), '20')} км\n"
                    f"➕ Или создай своё событие и собери свою компанию!",
                    reply_markup=inline_kb,
                )

                # Отправляем главное меню после сообщения о том, что события не найдены
                await send_spinning_menu(message)
                # Очищаем состояние FSM после завершения поиска
                await state.clear()
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
                next_radius = next(iter([r for r in RADIUS_OPTIONS if r > int(radius) and r != 5]), 20)
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

            # Всегда добавляем кнопки расширения радиуса для лучшего UX, используя фиксированные RADIUS_OPTIONS
            current_radius = int(settings.default_radius_km)

            # Находим следующие доступные радиусы из RADIUS_OPTIONS
            for radius_option in RADIUS_OPTIONS:
                if radius_option > current_radius:
                    # Не показываем кнопку "расширить до 5 км" - это минимальный радиус
                    if radius_option == 5:
                        continue
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(
                                text=f"🔍 Расширить до {radius_option} км",
                                callback_data=f"rx:{radius_option}",
                            )
                        ]
                    )

            inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            # Пробуем получить изображение карты (с circuit breaker)
            map_bytes = None
            if settings.google_maps_api_key and points:
                # Проверяем, находится ли пользователь в России для логирования
                is_russia = 41.0 <= lat <= 82.0 and 19.0 <= lng <= 180.0
                if is_russia:
                    logger.info(f"🇷🇺 Пользователь в России ({lat}, {lng}), пробуем загрузить карту...")

                # Конвертируем points в нужный формат для новой функции
                event_points = [(p[1], p[2]) for p in points]  # (lat, lng)
                map_bytes = await fetch_static_map(
                    build_static_map_url(lat, lng, event_points, settings.google_maps_api_key)
                )

                if is_russia:
                    if map_bytes:
                        logger.info("🇷🇺 Карта для пользователя в России загружена успешно")
                    else:
                        logger.warning("🇷🇺 Не удалось загрузить карту для пользователя в России - используем fallback")

            # Короткая подпись для карты/сообщения - используем отфильтрованные события
            caption = f"🗺️ **В радиусе {radius} км найдено: {len(prepared)}**\n"
            caption += f"• 👥 От пользователей: {counts.get('user', 0)}\n"
            caption += f"• 🌐 Из источников: {counts.get('sources', 0)}"

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

            except Exception as e:
                logger.error(f"❌ Ошибка отправки карты/заголовка: {e}")
                # Если не удалось отправить карту или заголовок, отправляем минимальное сообщение
                try:
                    await message.answer(
                        f"📋 Найдено {len(prepared)} событий в радиусе {radius} км",
                        reply_markup=inline_kb,
                        parse_mode="HTML",
                    )
                    logger.info("✅ Отправлен минимальный заголовок после ошибки карты")
                except Exception as e2:
                    logger.error(f"❌ Критическая ошибка отправки заголовка: {e2}")

            # ВСЕГДА отправляем компактный список событий, независимо от проблем с картой
            try:
                await send_compact_events_list_prepared(message, prepared, lat, lng, page=0, user_radius=radius)
                logger.info("✅ Компактный список событий отправлен")
                # Отправляем главное меню после списка событий
                await send_spinning_menu(message)
                # Очищаем состояние FSM после завершения поиска
                await state.clear()
            except Exception as e:
                logger.error(f"❌ Ошибка отправки компактного списка: {e}")
                # Fallback - отправляем простой список событий
                try:
                    event_titles = [f"• {event.get('title', 'Без названия')}" for event in prepared[:10]]
                    events_text = "\n".join(event_titles)
                    if len(prepared) > 10:
                        events_text += f"\n... и ещё {len(prepared) - 10} событий"

                    await message.answer(
                        f"📋 **Найдено {len(prepared)} событий:**\n\n{events_text}\n\n"
                        f"💡 Используйте кнопки выше для просмотра на карте!",
                        parse_mode="Markdown",
                        reply_markup=main_menu_kb(),
                    )
                    logger.info("✅ Отправлен fallback список событий")
                except Exception as e2:
                    logger.error(f"❌ Критическая ошибка fallback списка: {e2}")
                    # Последний fallback - просто сообщение о количестве
                    try:
                        await message.answer(
                            f"📋 Найдено {len(prepared)} событий в радиусе {radius} км", reply_markup=main_menu_kb()
                        )
                    except Exception as e3:
                        logger.error(f"❌ Финальная критическая ошибка: {e3}")

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
        "Создаём новое событие!\nНаграда 5 🚀\n\n✍ Введите название мероприятия (например: Прогулка):",
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
    logger.info(f"🔍 on_my_events: запрос от пользователя {user_id}")

    # Автомодерация: закрываем прошедшие события
    closed_count = auto_close_events()
    if closed_count > 0:
        await message.answer(f"🤖 Автоматически закрыто {closed_count} прошедших событий")

    # Получаем события пользователя
    events = get_user_events(user_id)
    logger.info(f"🔍 on_my_events: найдено {len(events) if events else 0} событий для пользователя {user_id}")

    # Получаем события с участием (все добавленные события)
    all_participations = []

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем текст сообщения
    text_parts = ["📋 **Мои события:**\n", f"**Баланс {rocket_balance} 🚀**\n"]

    # Созданные события
    if events:
        active_events = [e for e in events if e.get("status") == "open"]
        if active_events:
            text_parts.append("📝 **Созданные мной:**")
            for i, event in enumerate(active_events[:3], 1):
                title = event.get("title", "Без названия")
                event.get("starts_at")
                location = event.get("location_name", "Место уточняется")

                # Форматируем время проведения события (которое указал пользователь)
                starts_at = event.get("starts_at")
                if starts_at:
                    # Конвертируем UTC в местное время Бали
                    import pytz

                    tz_bali = pytz.timezone("Asia/Makassar")  # UTC+8
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = "Время уточняется"

                text_parts.append(f"{i}) **{title}**\n🕐 {time_str}\n📍 {location}\n")

            if len(active_events) > 3:
                text_parts.append(f"... и еще {len(active_events) - 3} событий")

    # Добавленные события
    if all_participations:
        text_parts.append(f"\n➕ **Добавленные ({len(all_participations)}):**")
        for i, event in enumerate(all_participations[:3], 1):
            title = event.get("title", "Без названия")
            starts_at = event.get("starts_at")
            if starts_at:
                # Конвертируем UTC в местное время Бали
                import pytz

                tz_bali = pytz.timezone("Asia/Makassar")  # UTC+8
                local_time = starts_at.astimezone(tz_bali)
                time_str = local_time.strftime("%H:%M")
            else:
                time_str = "Время уточняется"
            text_parts.append(f"{i}) **{title}** – {time_str}")

        if len(all_participations) > 3:
            text_parts.append(f"... и еще {len(all_participations) - 3} событий")

    # Если нет событий вообще
    if not events and not all_participations:
        # Получаем баланс ракет пользователя
        from rockets_service import get_user_rockets

        rocket_balance = get_user_rockets(user_id)

        text_parts = [
            "📋 **Мои события:**\n",
            "У вас пока нет событий.\n",
            f"**Баланс {rocket_balance} 🚀**",
        ]

    text = "\n".join(text_parts)

    # Создаем клавиатуру
    keyboard_buttons = []

    if events:
        keyboard_buttons.append([InlineKeyboardButton(text="🔧 Управление событиями", callback_data="manage_events")])

    if all_participations:
        keyboard_buttons.append(
            [InlineKeyboardButton(text="📋 Все добавленные события", callback_data="view_participations")]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else main_menu_kb()

    try:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        logger.info("✅ on_my_events: сообщение отправлено успешно")
    except Exception as e:
        logger.error(f"❌ on_my_events: ошибка отправки сообщения: {e}")
        # Fallback - отправляем простой список
        simple_text = (
            f"📋 Ваши события: созданных {len(events) if events else 0}, добавленных {len(all_participations)}"
        )
        await message.answer(simple_text, reply_markup=main_menu_kb())


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
            f"• found_by_stream: source={found_by_stream.get('source', 0)}, ai_parsed={found_by_stream.get('ai_parsed', 0)}, user={found_by_stream.get('user', 0)}",
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

        load_settings()

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

            # Общее количество событий
            total_events = session.query(Event).count()

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
                "",
                "<b>📈 Общая статистика:</b>",
                f"• Всего событий в БД: {total_events}",
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


@dp.message(F.text == "🎯 Квесты на районе")
async def on_tasks_goal(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Квесты на районе' - объяснение и запрос геолокации"""
    # Устанавливаем состояние для заданий
    await state.set_state(TaskFlow.waiting_for_location)

    # Создаем клавиатуру с кнопкой геолокации (one_time_keyboard=True - кнопка исчезнет)
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,  # Кнопка исчезнет после использования
    )

    await message.answer(
        "🎯 Квесты на районе\nНаграда 3 🚀\n\nСамое время развлечься и получить награды.\n\nНажмите кнопку **'📍 Отправить геолокацию'** чтобы начать!",
        parse_mode="Markdown",
        reply_markup=location_keyboard,
    )


@dp.message(F.text == "🏆 Мои квесты")
async def on_my_tasks(message: types.Message):
    """Обработчик кнопки 'Мои квесты'"""
    user_id = message.from_user.id

    # Автомодерация: помечаем истекшие задания
    from tasks_service import mark_tasks_as_expired

    try:
        expired_count = mark_tasks_as_expired()
        if expired_count > 0:
            await message.answer(f"🤖 Автоматически истекло {expired_count} просроченных заданий")
    except Exception as e:
        logger.error(f"Ошибка автомодерации заданий для пользователя {user_id}: {e}")

    # Получаем активные задания пользователя
    active_tasks = get_user_active_tasks(user_id)

    if not active_tasks:
        # Получаем баланс ракет пользователя
        from rockets_service import get_user_rockets

        rocket_balance = get_user_rockets(user_id)

        await message.answer(
            "🏆 **Мои квесты**\n\n"
            "У вас пока нет активных заданий.\n\n"
            f"**Баланс {rocket_balance} 🚀**\n\n"
            "🎯 Нажмите 'Квесты на районе' чтобы получить новые задания!",
            parse_mode="Markdown",
        )
        return

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем сообщение со списком активных заданий
    message_text = "📋 **Ваши активные задания:**\n\n"
    message_text += "Прохождение + 3 🚀\n"
    message_text += "⏰ Для мотивации даем 24 часа\n\n"
    message_text += f"**Баланс {rocket_balance} 🚀**\n\n"

    for i, task in enumerate(active_tasks, 1):
        # Вычисляем оставшееся время
        expires_at = task["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        time_left = expires_at - datetime.now(UTC)
        int(time_left.total_seconds() / 3600)

        category_emoji = "💪" if task["category"] == "body" else "🧘"
        # Форматируем время выполнения в компактном виде
        start_time = task["accepted_at"]
        end_time = expires_at
        time_period = f"{start_time.strftime('%d.%m.%Y %H:%M')} → {end_time.strftime('%d.%m.%Y %H:%M')}"

        message_text += f"{i}) {category_emoji} **{task['title']}**\n"
        message_text += f"⏰ **Время на выполнение:** {time_period}\n\n"

    # Добавляем кнопку управления заданиями
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔧 Управление заданиями", callback_data="manage_tasks")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
        ]
    )

    await message.answer(
        message_text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data == "manage_tasks")
async def handle_manage_tasks(callback: types.CallbackQuery):
    """Обработчик кнопки 'Управление заданиями'"""
    user_id = callback.from_user.id
    active_tasks = get_user_active_tasks(user_id)

    if not active_tasks:
        await callback.message.edit_text(
            "🏆 **Мои квесты**\n\n" "У вас нет активных заданий.",
            parse_mode="Markdown",
        )
        return

    # Показываем первое задание
    await show_task_detail(callback.message, active_tasks, 0, user_id)
    await callback.answer()


async def show_task_detail(message, tasks: list, task_index: int, user_id: int):
    """Показывает детальную информацию о задании"""
    task = tasks[task_index]

    # Вычисляем оставшееся время
    expires_at = task["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    time_left = expires_at - datetime.now(UTC)
    int(time_left.total_seconds() / 3600)

    category_emoji = "💪" if task["category"] == "body" else "🧘"
    category_name = "Тело" if task["category"] == "body" else "Дух"

    message_text = f"📋 **{task['title']}**\n\n"
    message_text += f"{category_emoji} **Категория:** {category_name}\n"
    message_text += f"📝 **Описание:** {task['description']}\n"
    # Форматируем время выполнения в компактном виде
    start_time = task["accepted_at"]
    end_time = expires_at

    message_text += (
        f"⏰ **Время на выполнение:** {start_time.strftime('%d.%m.%Y %H:%M')} → {end_time.strftime('%d.%m.%Y %H:%M')}\n"
    )

    if task.get("location_url"):
        message_text += f"📍 **Место:** [Открыть на карте]({task['location_url']})\n"

    # Создаем клавиатуру для навигации
    keyboard = []

    # Кнопки управления заданием
    keyboard.append(
        [
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"task_complete:{task['id']}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"task_cancel:{task['id']}"),
        ]
    )

    # Кнопки навигации
    nav_buttons = []
    if len(tasks) > 1:
        if task_index > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"task_nav:{task_index-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{task_index + 1}/{len(tasks)}", callback_data="noop"))
        if task_index < len(tasks) - 1:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"task_nav:{task_index+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопки возврата
    keyboard.append([InlineKeyboardButton(text="🔧 К списку заданий", callback_data="my_tasks_list")])
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await message.edit_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


@dp.callback_query(F.data.startswith("task_nav:"))
async def handle_task_navigation(callback: types.CallbackQuery):
    """Обработчик навигации по заданиям"""
    task_index = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    active_tasks = get_user_active_tasks(user_id)
    if not active_tasks or task_index >= len(active_tasks):
        await callback.answer("Задание не найдено")
        return

    await show_task_detail(callback.message, active_tasks, task_index, user_id)
    await callback.answer()


@dp.callback_query(F.data == "my_tasks_list")
async def handle_back_to_tasks_list(callback: types.CallbackQuery):
    """Возврат к списку заданий"""
    user_id = callback.from_user.id
    active_tasks = get_user_active_tasks(user_id)

    if not active_tasks:
        # Получаем баланс ракет пользователя
        from rockets_service import get_user_rockets

        rocket_balance = get_user_rockets(user_id)

        await callback.message.edit_text(
            "🏆 **Мои квесты**\n\n"
            "У вас пока нет активных заданий.\n\n"
            f"**Баланс {rocket_balance} 🚀**\n\n"
            "🎯 Нажмите 'Квесты на районе' чтобы получить новые задания!",
            parse_mode="Markdown",
        )
        return

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем сообщение со списком активных заданий
    message_text = "📋 **Ваши активные задания:**\n\n"
    message_text += "Прохождение + 3 🚀\n"
    message_text += "⏰ Для мотивации даем 24 часа\n\n"
    message_text += f"**Баланс {rocket_balance} 🚀**\n\n"

    for i, task in enumerate(active_tasks, 1):
        # Вычисляем оставшееся время
        expires_at = task["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        time_left = expires_at - datetime.now(UTC)
        int(time_left.total_seconds() / 3600)

        category_emoji = "💪" if task["category"] == "body" else "🧘"
        # Форматируем время выполнения в компактном виде
        start_time = task["accepted_at"]
        end_time = expires_at
        time_period = f"{start_time.strftime('%d.%m.%Y %H:%M')} → {end_time.strftime('%d.%m.%Y %H:%M')}"

        message_text += f"{i}) {category_emoji} **{task['title']}**\n"
        message_text += f"⏰ **Время на выполнение:** {time_period}\n\n"

    # Добавляем кнопку управления заданиями
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔧 Управление заданиями", callback_data="manage_tasks")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
        ]
    )

    await callback.message.edit_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    await callback.answer()


@dp.callback_query(F.data == "noop")
async def handle_noop(callback: types.CallbackQuery):
    """Заглушка для кнопок без действия"""
    await callback.answer()


@dp.callback_query(F.data.startswith("rx:"))
async def handle_expand_radius(callback: types.CallbackQuery):
    """Обработчик расширения радиуса поиска"""
    new_radius = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    logger.info(f"🔍 handle_expand_radius: пользователь {user_id} расширяет радиус до {new_radius} км")

    # Получаем сохраненное состояние
    state_data = user_state.get(chat_id)
    if not state_data:
        await callback.answer("❌ Данные поиска устарели. Отправьте геолокацию заново.")
        return

    lat = state_data.get("lat")
    lng = state_data.get("lng")
    region = state_data.get("region", "bali")

    if not lat or not lng:
        await callback.answer("❌ Геолокация не найдена. Отправьте геолокацию заново.")
        return

    # Показываем сообщение загрузки
    await callback.message.edit_text("🔍 Ищу события в расширенном радиусе...")

    # Выполняем поиск с новым радиусом
    from database import get_engine

    engine = get_engine()
    events_service = UnifiedEventsService(engine)

    events = events_service.search_events_today(
        city=region, user_lat=lat, user_lng=lng, radius_km=new_radius, message_id=f"{callback.message.message_id}"
    )

    # Конвертируем в старый формат для совместимости
    formatted_events = []
    for event in events:
        formatted_event = {
            "title": event["title"],
            "description": event["description"],
            "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
            "starts_at": event["starts_at"],
            "city": event.get("city", "bali"),
            "location_name": event["location_name"],
            "location_url": event["location_url"],
            "lat": event["lat"],
            "lng": event["lng"],
            "source": event.get("source", ""),
            "source_type": event.get("source_type", ""),
            "url": event.get("event_url", ""),
            "community_name": "",
            "community_link": "",
            "organizer_id": event.get("organizer_id"),
            "organizer_username": event.get("organizer_username"),
        }
        formatted_events.append(formatted_event)

    events = formatted_events

    # Сортируем события по времени
    events = sort_events_by_time(events)

    # Фильтруем и подготавливаем события
    prepared, diag = prepare_events_for_feed(events, user_point=(lat, lng), radius_km=int(new_radius), with_diag=True)

    # Если не найдено событий
    if not prepared:
        # Создаем кнопки расширения радиуса
        keyboard_buttons = []
        current_radius = new_radius

        # Находим следующие доступные радиусы из RADIUS_OPTIONS
        for radius_option in RADIUS_OPTIONS:
            if radius_option > current_radius:
                # Не показываем кнопку "расширить до 5 км" - это минимальный радиус
                if radius_option == 5:
                    continue
                keyboard_buttons.append(
                    [
                        InlineKeyboardButton(
                            text=f"🔍 Расширить поиск до {radius_option} км",
                            callback_data=f"rx:{radius_option}",
                        )
                    ]
                )

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

        await callback.message.edit_text(
            f"📅 В радиусе {current_radius} км событий на сегодня не найдено.\n\n"
            f"💡 Попробуй расширить поиск до {next(iter([r for r in RADIUS_OPTIONS if r > current_radius and r != 5]), '20')} км\n"
            f"➕ Или создай своё событие и собери свою компанию!",
            reply_markup=inline_kb,
        )

        await callback.answer()
        return

    # Если найдены события, отправляем их
    # Группируем и считаем
    groups = group_by_type(prepared)
    counts = make_counts(groups)

    # Обновляем состояние
    user_state[chat_id] = {
        "prepared": prepared,
        "counts": counts,
        "lat": lat,
        "lng": lng,
        "radius": new_radius,
        "page": 1,
        "diag": {"kept": len(prepared), "dropped": 0, "reasons_top3": []},
        "region": region,
    }

    # Рендерим страницу
    header_html = render_header(counts, radius_km=new_radius)
    events_text, total_pages = render_page(prepared, 1, page_size=5)

    text = header_html + "\n\n" + events_text

    # Создаем клавиатуру с кнопками пагинации и расширения радиуса
    keyboard = kb_pager(1, total_pages, new_radius)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    await callback.answer(f"✅ Радиус расширен до {new_radius} км")


@dp.callback_query(F.data.startswith("task_complete:"))
async def handle_task_complete(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик завершения задания"""
    user_task_id = int(callback.data.split(":")[1])

    # Переходим в состояние ожидания фидбека
    await state.set_state(EventCreation.waiting_for_feedback)
    await state.update_data(user_task_id=user_task_id)

    await callback.message.edit_text(
        "✅ **Задание выполнено!**\n\n"
        "Поделитесь своими впечатлениями:\n"
        "• Как прошло выполнение?\n"
        "• Что вы почувствовали?\n"
        "• Как это помогло вам?\n\n"
        "Напишите ваш отзыв:",
        parse_mode="Markdown",
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("task_cancel:"))
async def handle_task_cancel(callback: types.CallbackQuery):
    """Обработчик отмены задания"""
    user_task_id = int(callback.data.split(":")[1])

    # Отменяем задание
    success = cancel_task(user_task_id)

    if success:
        await callback.message.edit_text(
            "❌ **Задание отменено**\n\n" "Задание удалено из вашего списка активных заданий.",
            parse_mode="Markdown",
        )
    else:
        await callback.message.edit_text(
            "❌ **Ошибка отмены задания**\n\n" "Не удалось отменить задание. Попробуйте позже.",
            parse_mode="Markdown",
        )

    await callback.answer()


@dp.callback_query(F.data.startswith("task_category:"))
async def handle_task_category_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора категории задания"""
    category = callback.data.split(":")[1]
    user_id = callback.from_user.id

    # Получаем 3 задания на сегодня для выбранной категории
    tasks = get_daily_tasks(category)

    if not tasks:
        await callback.message.edit_text("❌ Задания для этой категории пока не готовы.")
        await callback.answer()
        return

    # Получаем активные задания пользователя для фильтрации
    active_tasks = get_user_active_tasks(user_id)
    active_task_ids = {active_task["task_id"] for active_task in active_tasks}

    # Фильтруем уже взятые задания
    available_tasks = [task for task in tasks if task.id not in active_task_ids]

    # Создаем клавиатуру с доступными заданиями
    keyboard = []
    for task in available_tasks:
        keyboard.append([InlineKeyboardButton(text=f"📋 {task.title}", callback_data=f"task_detail:{task.id}")])

    # Определяем названия категорий
    category_names = {"body": "💪 Тело", "spirit": "🧘 Дух"}
    category_name = category_names.get(category, category)

    # Если все задания взяты, показываем сообщение
    if not available_tasks:
        await callback.message.edit_text(
            f"🎯 **{category_name}**\n\n"
            "✅ Все задания этой категории уже взяты, завтра будут новые!\n\n"
            "📋 Перейдите в 'Мои квесты' чтобы посмотреть ваши активные задания.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Мои квесты", callback_data="my_tasks")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_tasks")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
                ]
            ),
        )
        await callback.answer()
        return

    # Добавляем кнопки управления
    keyboard.append(
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_tasks"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main"),
        ]
    )

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        f"🎯 **{category_name}**\n\n" "Выберите задание для получения подробной информации:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("task_detail:"))
async def handle_task_detail(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик просмотра деталей задания"""
    task_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    with get_session() as session:
        from database import Task

        task = session.query(Task).filter(Task.id == task_id).first()

        if not task:
            await callback.message.edit_text("❌ Задание не найдено.")
            await callback.answer()
            return

        # Проверяем, есть ли у пользователя уже это задание
        active_tasks = get_user_active_tasks(user_id)
        user_has_task = any(active_task["task_id"] == task_id for active_task in active_tasks)

        # Формируем сообщение с деталями задания
        message = f"📋 **{task.title}**\n\n"
        message += f"{task.description}\n\n"

        if task.location_url:
            message += "📍 **Предлагаемое место:**\n"
            message += f"[🌍 Открыть на карте]({task.location_url})\n\n"

        # Создаем клавиатуру
        keyboard = []

        if task.location_url and not user_has_task:
            keyboard.append(
                [InlineKeyboardButton(text="📍 Вставить свою локацию", callback_data=f"task_custom_location:{task_id}")]
            )

        # Показываем разные кнопки в зависимости от статуса задания
        if user_has_task:
            keyboard.extend(
                [
                    [InlineKeyboardButton(text="✅ Задание взято", callback_data=f"task_already_taken:{task_id}")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data=f"task_category:{task.category}")],
                ]
            )
        else:
            keyboard.extend(
                [
                    [InlineKeyboardButton(text="✅ Принять задание", callback_data=f"task_accept:{task_id}")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data=f"task_category:{task.category}")],
                ]
            )

        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await callback.message.edit_text(
            message, parse_mode="Markdown", reply_markup=reply_markup, disable_web_page_preview=True
        )
        await callback.answer()


@dp.callback_query(F.data.startswith("task_already_taken:"))
async def handle_task_already_taken(callback: types.CallbackQuery):
    """Обработчик кнопки 'Задание взято'"""
    await callback.message.edit_text(
        "✅ **Задание уже взято!**\n\n"
        "Вы уже выполняете это задание.\n\n"
        "📋 Перейдите в 'Мои квесты' чтобы посмотреть детали и управлять заданием.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📋 Мои квесты", callback_data="my_tasks")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
            ]
        ),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("task_accept:"))
async def handle_task_accept(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик принятия задания"""
    task_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Получаем координаты пользователя из БД
    with get_session() as session:
        user = session.get(User, user_id)
        user_lat = user.last_lat if user else None
        user_lng = user.last_lng if user else None

    # Принимаем задание с учетом часового пояса пользователя
    success = accept_task(user_id, task_id, user_lat, user_lng)

    if success:
        await callback.message.edit_text(
            "✅ **Задание принято!**\n\n"
            "⏰ У вас есть **24 часа** на выполнение.\n"
            "🏆 Задание добавлено в 'Мои квесты'.\n\n"
            "Удачи! 🚀",
            parse_mode="Markdown",
        )
        # Показываем главное меню
        await callback.message.answer("🚀", reply_markup=main_menu_kb())
    else:
        await callback.message.edit_text(
            "❌ **Не удалось принять задание**\n\n" "Возможно, у вас уже есть активное задание этого типа.",
            parse_mode="Markdown",
        )
        # Показываем главное меню
        await callback.message.answer("🚀", reply_markup=main_menu_kb())

    await callback.answer()


@dp.callback_query(F.data.startswith("task_custom_location:"))
async def handle_task_custom_location(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик ввода своей локации для задания"""
    task_id = int(callback.data.split(":")[1])

    await state.update_data(selected_task_id=task_id)
    await state.set_state(TaskFlow.waiting_for_custom_location)

    # Добавляем кнопки для выбора типа локации
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data="location_link")],
            [InlineKeyboardButton(text="🌍 Найти на карте", callback_data="location_map")],
            [InlineKeyboardButton(text="📍 Ввести координаты", callback_data="location_coords")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"task_detail:{task_id}")],
        ]
    )

    await callback.message.edit_text(
        "📍 **Введите свою локацию**\n\n"
        "Вы можете:\n"
        "• Отправить ссылку Google Maps\n"
        "• Ввести координаты (широта, долгота)\n"
        "• Найти место на карте\n\n"
        "Или выберите способ ниже:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("start_task:"))
async def handle_start_task(callback: types.CallbackQuery):
    """Обработчик начала выполнения задания"""
    try:
        # Парсим данные: start_task:template_id:place_id
        parts = callback.data.split(":")
        int(parts[1])
        int(parts[2])

        # Получаем данные задания и места
        # from tasks.task_service import TaskService
        # task_service = TaskService()

        # Здесь нужно получить полные данные задания и места
        # Пока заглушка
        await callback.message.edit_text(
            "🎯 **Задание начато!**\n\n"
            "Ваше задание добавлено в активные.\n"
            "Перейдите в '🏆 Мои квесты' для управления.\n\n"
            "🚀 Удачи в выполнении!",
            parse_mode="Markdown",
        )

        await callback.answer("✅ Задание добавлено в активные!")

    except Exception as e:
        logger.error(f"Ошибка начала задания: {e}")
        await callback.answer("❌ Ошибка при начале задания")


@dp.callback_query(F.data == "back_to_main")
async def handle_back_to_main_tasks(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик возврата в главное меню из заданий"""
    # Очищаем состояние FSM
    await state.clear()

    # Показываем анимацию ракеты с главным меню
    await send_spinning_menu(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "show_bot_commands")
async def handle_show_bot_commands(callback: types.CallbackQuery):
    """Обработчик показа команд бота"""
    commands_text = (
        "📋 **Команды бота:**\n\n"
        "🚀 /start - Запустить бота и показать меню\n"
        "❓ /help - Показать справку\n"
        "📍 /nearby - Найти события рядом\n"
        "➕ /create - Создать событие\n"
        "📋 /myevents - Мои события\n"
        "🔗 /share - Поделиться ботом\n\n"
        "💡 **Совет:** Используйте кнопки меню для удобной навигации!"
    )

    # Создаем клавиатуру с кнопкой возврата
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к заданиям", callback_data="back_to_tasks")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
        ]
    )

    await callback.message.edit_text(commands_text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data == "back_to_tasks")
async def handle_back_to_tasks(callback: types.CallbackQuery):
    """Обработчик возврата к выбору категории заданий"""
    # Показываем выбор категории
    keyboard = [
        [InlineKeyboardButton(text="💪 Тело", callback_data="task_category:body")],
        [InlineKeyboardButton(text="🧘 Дух", callback_data="task_category:spirit")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        "🎯 **Квесты на районе**\n\n" "Выберите категорию заданий:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("task_manage:"))
async def handle_task_manage(callback: types.CallbackQuery):
    """Обработчик управления заданием"""
    user_task_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Получаем информацию о задании
    active_tasks = get_user_active_tasks(user_id)
    task_info = None

    for task in active_tasks:
        if task["id"] == user_task_id:
            task_info = task
            break

    if not task_info:
        await callback.message.edit_text("❌ Задание не найдено.")
        await callback.answer()
        return

    # Проверяем, не истекло ли задание
    now = datetime.now(UTC)
    if now > task_info["expires_at"]:
        await callback.message.edit_text(
            "⏰ **Задание истекло**\n\n"
            "Время выполнения задания закончилось.\n"
            "Примите новое задание в '🎯 Цели на районе'!",
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    # Вычисляем оставшееся время
    time_left = task_info["expires_at"] - now
    hours_left = int(time_left.total_seconds() / 3600)
    minutes_left = int((time_left.total_seconds() % 3600) / 60)

    if hours_left > 0:
        time_text = f"⏰ До: {hours_left}ч {minutes_left}м"
    else:
        time_text = f"⏰ До: {minutes_left}м"

    category_emoji = "💪" if task_info["category"] == "body" else "🧘"

    message = f"{category_emoji} **{task_info['title']}**\n\n"
    message += f"{task_info['description']}\n\n"
    message += f"{time_text}\n\n"

    if task_info["location_url"]:
        message += f"📍 [🌍 Открыть на карте]({task_info['location_url']})\n\n"

    # Создаем клавиатуру
    keyboard = [
        [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"task_complete:{user_task_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"task_cancel:{user_task_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="my_tasks")],
    ]

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        message, parse_mode="Markdown", reply_markup=reply_markup, disable_web_page_preview=True
    )
    await callback.answer()


@dp.message(EventCreation.waiting_for_feedback)
async def process_feedback(message: types.Message, state: FSMContext):
    """Обработка фидбека для завершения задания"""
    feedback = message.text.strip()
    user_id = message.from_user.id

    # Получаем ID задания из состояния
    data = await state.get_data()
    completing_task_id = data.get("completing_task_id") or data.get("user_task_id")

    if not completing_task_id:
        await message.answer("❌ Ошибка: не найдено задание для завершения.")
        await state.clear()
        return

    # Завершаем задание с фидбеком
    success = complete_task(completing_task_id, feedback)

    if success:
        # Награждаем ракетами
        rockets_awarded = award_rockets_for_activity(user_id, "task_complete")

        await message.answer(
            f"🎉 **Задание завершено!**\n\n"
            f"📝 Спасибо за фидбек!\n"
            f"🚀 Получено ракет: **{rockets_awarded}**\n\n"
            f"Продолжайте в том же духе! 💪",
            parse_mode="Markdown",
        )

        # Отправляем ракету
        await message.answer("🚀")
    else:
        await message.answer(
            "❌ **Не удалось завершить задание**\n\n" "Возможно, время выполнения истекло или задание уже завершено.",
            parse_mode="Markdown",
        )

    await state.clear()


@dp.message(Command("help"))
@dp.message(F.text == "💬 Написать отзыв Разработчику")
async def on_help(message: types.Message):
    """Обработчик кнопки 'Написать отзыв Разработчику'"""
    feedback_text = (
        "💬 **Написать отзыв Разработчику**\n\n"
        "Спасибо за использование EventAroundBot! 🚀\n\n"
        "Если у вас есть предложения, замечания или просто хотите поблагодарить - "
        "напишите мне лично:\n\n"
        "👨‍💻 **@Fincontro**\n\n"
        "Я всегда рад обратной связи и готов помочь! 😊"
    )

    # Создаем inline кнопку для быстрого перехода к чату
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать @Fincontro", url="https://t.me/Fincontro")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
        ]
    )

    await message.answer(feedback_text, reply_markup=keyboard, parse_mode="Markdown")


# FSM обработчики для создания событий (должны быть ПЕРЕД общим обработчиком)
@dp.message(EventCreation.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    """Шаг 1: Обработка названия события"""
    title = message.text.strip()
    chat_id = message.chat.id
    chat_type = message.chat.type

    logger.info(
        f"process_title: получили название '{title}' от пользователя {message.from_user.id} в чате {chat_id} (тип: {chat_type})"
    )

    # Сохраняем chat_id для групповых чатов
    await state.update_data(title=title, chat_id=chat_id, chat_type=chat_type)
    await state.set_state(EventCreation.waiting_for_date)
    example_date = get_example_date()

    # Разные сообщения для личных и групповых чатов
    if chat_type == "private":
        await message.answer(
            f"Название сохранено: *{title}* ✅\n\n📅 Теперь введите дату (например: {example_date}):",
            parse_mode="Markdown",
        )
    else:
        # Для групповых чатов используем edit_text
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
        )
        await message.edit_text(
            f"**Название сохранено:** *{title}* ✅\n\n📅 **Теперь введите дату** (например: {example_date}):",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


@dp.message(EventCreation.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    """Шаг 2: Обработка даты события"""
    date = message.text.strip()
    logger.info(f"process_date: получили дату '{date}' от пользователя {message.from_user.id}")

    # Валидация формата даты DD.MM.YYYY
    import re

    if not re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", date):
        await message.answer(
            "❌ Неверный формат даты!\n\n"
            "Используйте формат **DD.MM.YYYY** (например: 02.10.2025, 25.12.2025)\n\n"
            "📅 Введите дату:",
            parse_mode="Markdown",
        )
        return

    # Дополнительная проверка: валидность даты
    try:
        day, month, year = map(int, date.split("."))
        from datetime import datetime

        datetime(year, month, day)  # Проверяем валидность даты
    except ValueError:
        await message.answer(
            "❌ Неверная дата!\n\n"
            "Проверьте правильность даты:\n"
            "• День: 1-31\n"
            "• Месяц: 1-12\n"
            "• Год: 2024-2030\n\n"
            "Например: 02.10.2025, 25.12.2025\n\n"
            "📅 Введите дату:",
            parse_mode="Markdown",
        )
        return

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

    # Валидация формата времени HH:MM
    import re

    if not re.match(r"^\d{1,2}:\d{2}$", time):
        await message.answer(
            "❌ Неверный формат времени!\n\n"
            "Используйте формат **HH:MM** (например: 17:30, 9:00)\n\n"
            "⏰ Введите время:",
            parse_mode="Markdown",
        )
        return

    # Дополнительная проверка: часы от 0 до 23, минуты от 0 до 59
    try:
        hours, minutes = map(int, time.split(":"))
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            raise ValueError("Invalid time range")
    except ValueError:
        await message.answer(
            "❌ Неверное время!\n\n"
            "Часы: 0-23, минуты: 0-59\n"
            "Например: 17:30, 9:00, 23:59\n\n"
            "⏰ Введите время:",
            parse_mode="Markdown",
        )
        return

    await state.update_data(time=time)
    await state.set_state(EventCreation.waiting_for_location_type)

    # Создаем клавиатуру для выбора типа локации
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data="location_link")],
            [InlineKeyboardButton(text="🌍 Найти на карте", callback_data="location_map")],
            [InlineKeyboardButton(text="📍 Ввести координаты", callback_data="location_coords")],
        ]
    )

    await message.answer(
        f"Время сохранено: *{time}* ✅\n\n📍 Как укажем место?\n\n" "Выберите один из способов:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@dp.message(EventCreation.waiting_for_location_type)
async def handle_location_type_text(message: types.Message, state: FSMContext):
    """Обработка текстовых сообщений в состоянии выбора типа локации"""
    text = message.text.strip()

    # Проверяем, является ли это Google Maps ссылкой
    if any(domain in text.lower() for domain in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl"]):
        # Пользователь отправил ссылку напрямую - обрабатываем как ссылку
        await state.set_state(EventCreation.waiting_for_location_link)
        await state.update_data(location_url=text)

        # Парсим ссылку
        from utils.geo_utils import parse_google_maps_link

        location_data = await parse_google_maps_link(text)

        if location_data:
            # Сохраняем данные локации
            await state.update_data(
                location_name=location_data.get("name", "Место на карте"),
                location_lat=location_data.get("lat"),
                location_lng=location_data.get("lng"),
            )

            # Переходим к описанию
            await state.set_state(EventCreation.waiting_for_description)
            await message.answer(
                f"📍 Место определено: *{location_data.get('name', 'Место на карте')}*\n\n"
                "📝 Теперь добавьте описание события:",
                parse_mode="Markdown",
            )
        else:
            await message.answer(
                "❌ Не удалось распознать ссылку Google Maps.\n\n"
                "Попробуйте:\n"
                "• Скопировать ссылку из приложения Google Maps\n"
                "• Или нажать кнопку '🔗 Вставить готовую ссылку'"
            )

    # Проверяем, являются ли это координаты (широта, долгота)
    elif "," in text and len(text.split(",")) == 2:
        try:
            lat_str, lng_str = text.split(",")
            lat = float(lat_str.strip())
            lng = float(lng_str.strip())

            # Проверяем валидность координат
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                # Сохраняем координаты
                await state.update_data(
                    location_name="Место по координатам",
                    location_lat=lat,
                    location_lng=lng,
                    location_url=text,
                )

                # Переходим к описанию
                await state.set_state(EventCreation.waiting_for_description)
                await message.answer(
                    f"📍 Место определено по координатам: *{lat}, {lng}*\n\n" "📝 Теперь добавьте описание события:",
                    parse_mode="Markdown",
                )
            else:
                raise ValueError("Invalid coordinates range")

        except ValueError:
            await message.answer(
                "❌ Неверный формат координат!\n\n"
                "Используйте формат: **широта, долгота**\n"
                "Например: 55.7558, 37.6176\n\n"
                "Диапазоны:\n"
                "• Широта: -90 до 90\n"
                "• Долгота: -180 до 180",
                parse_mode="Markdown",
            )
    else:
        # Не ссылка - напоминаем о кнопках
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data="location_link")],
                [InlineKeyboardButton(text="🌍 Найти на карте", callback_data="location_map")],
            ]
        )

        await message.answer(
            "❌ Пожалуйста, используйте кнопки ниже для указания места:\n\n"
            "• **🔗 Вставить готовую ссылку** - если у вас есть ссылка Google Maps\n"
            "• **🌍 Найти на карте** - чтобы найти место на карте\n"
            "• **📍 Ввести координаты** - если знаете широту и долготу",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


# Обработчики для выбора типа локации
@dp.callback_query(F.data == "location_link")
async def handle_location_link_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода готовой ссылки"""
    current_state = await state.get_state()

    if current_state == TaskFlow.waiting_for_custom_location:
        # Для заданий
        await callback.message.answer("🔗 Вставьте сюда ссылку из Google Maps:")
    else:
        # Для событий
        await state.set_state(EventCreation.waiting_for_location_link)
        await callback.message.answer("🔗 Вставьте сюда ссылку из Google Maps:")

    await callback.answer()


@dp.callback_query(F.data == "location_map")
async def handle_location_map_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор поиска на карте"""
    current_state = await state.get_state()

    # Создаем кнопку для открытия Google Maps
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🌍 Открыть Google Maps", url="https://www.google.com/maps")]]
    )

    if current_state == TaskFlow.waiting_for_custom_location:
        # Для заданий
        await callback.message.answer("🌍 Открой карту, найди место и вставь ссылку сюда 👇", reply_markup=keyboard)
    else:
        # Для событий
        await state.set_state(EventCreation.waiting_for_location_link)
        await callback.message.answer("🌍 Открой карту, найди место и вставь ссылку сюда 👇", reply_markup=keyboard)

    await callback.answer()


@dp.callback_query(F.data == "location_coords")
async def handle_location_coords_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода координат"""
    current_state = await state.get_state()

    if current_state == TaskFlow.waiting_for_custom_location:
        # Для заданий
        await callback.message.answer(
            "📍 Введите координаты в формате: **широта, долгота**\n\n"
            "Например: 55.7558, 37.6176\n"
            "Или: -8.67, 115.21",
            parse_mode="Markdown",
        )
    else:
        # Для событий
        await state.set_state(EventCreation.waiting_for_location_link)
        await callback.message.answer(
            "📍 Введите координаты в формате: **широта, долгота**\n\n"
            "Например: 55.7558, 37.6176\n"
            "Или: -8.67, 115.21",
            parse_mode="Markdown",
        )

    await callback.answer()


@dp.message(TaskFlow.waiting_for_custom_location)
async def process_task_custom_location(message: types.Message, state: FSMContext):
    """Обработка ввода своей локации для задания"""
    link = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"process_task_custom_location: получили ссылку от пользователя {user_id}")

    # Получаем ID задания из состояния
    data = await state.get_data()
    task_id = data.get("selected_task_id")

    if not task_id:
        await message.answer("❌ Ошибка: не найдено задание.")
        await state.clear()
        return

    # Проверяем, являются ли это координаты (широта, долгота)
    if "," in link and len(link.split(",")) == 2:
        try:
            lat_str, lng_str = link.split(",")
            lat = float(lat_str.strip())
            lng = float(lng_str.strip())

            # Проверяем валидность координат
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                # Сохраняем координаты пользователя
                with get_session() as session:
                    user = session.query(User).filter(User.id == user_id).first()
                    if user:
                        user.last_lat = lat
                        user.last_lng = lng
                        user.last_geo_at_utc = datetime.now(UTC)
                        session.commit()

                # Принимаем задание с кастомной локацией
                success = accept_task(user_id, task_id, lat, lng)

                if success:
                    await message.answer(
                        "✅ **Задание принято с вашей локацией!**\n\n"
                        f"📍 Место: {lat}, {lng}\n"
                        "⏰ У вас есть **24 часа** на выполнение.\n"
                        "🏆 Задание добавлено в 'Мои квесты'.\n\n"
                        "Удачи! 🚀",
                        parse_mode="Markdown",
                        reply_markup=main_menu_kb(),
                    )
                else:
                    await message.answer(
                        "❌ **Не удалось принять задание**\n\n" "Возможно, у вас уже есть активное задание этого типа.",
                        parse_mode="Markdown",
                        reply_markup=main_menu_kb(),
                    )

                # Очищаем состояние
                await state.clear()
                return
            else:
                await message.answer("❌ Неверные координаты. Широта должна быть от -90 до 90, долгота от -180 до 180.")
                return

        except ValueError:
            await message.answer("❌ Неверный формат координат. Используйте: широта, долгота")
            return

    # Проверяем, является ли это Google Maps ссылкой
    if any(domain in link.lower() for domain in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl"]):
        # Парсим ссылку
        from utils.geo_utils import parse_google_maps_link

        result = await parse_google_maps_link(link)

        if result.get("lat") and result.get("lng"):
            lat, lng = result["lat"], result["lng"]
            location_name = result.get("name", "Место по ссылке")

            # Сохраняем координаты пользователя
            with get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    user.last_lat = lat
                    user.last_lng = lng
                    user.last_geo_at_utc = datetime.now(UTC)
                    session.commit()

            # Принимаем задание с кастомной локацией
            success = accept_task(user_id, task_id, lat, lng)

            if success:
                await message.answer(
                    "✅ **Задание принято с вашей локацией!**\n\n"
                    f"📍 Место: {location_name}\n"
                    f"🌍 Координаты: {lat}, {lng}\n"
                    "⏰ У вас есть **24 часа** на выполнение.\n"
                    "🏆 Задание добавлено в 'Мои квесты'.\n\n"
                    "Удачи! 🚀",
                    parse_mode="Markdown",
                    reply_markup=main_menu_kb(),
                )
            else:
                await message.answer(
                    "❌ **Не удалось принять задание**\n\n" "Возможно, у вас уже есть активное задание этого типа.",
                    parse_mode="Markdown",
                    reply_markup=main_menu_kb(),
                )

            # Очищаем состояние
            await state.clear()
            return
        else:
            await message.answer("❌ Не удалось определить координаты по ссылке. Попробуйте ввести координаты вручную.")
            return

    # Если это не координаты и не ссылка
    await message.answer(
        "❌ Неверный формат.\n\n"
        "Введите:\n"
        "• Ссылку Google Maps\n"
        "• Координаты в формате: широта, долгота\n\n"
        "Например: -8.67, 115.21"
    )


@dp.message(EventCreation.waiting_for_location_link)
async def process_location_link(message: types.Message, state: FSMContext):
    """Обработка ссылки Google Maps или координат"""
    # Проверяем состояние - если это для заданий, не обрабатываем здесь
    current_state = await state.get_state()
    if current_state == TaskFlow.waiting_for_custom_location:
        logger.info("📍 Пропускаем - это для заданий")
        return  # Пропускаем - это для заданий

    link = message.text.strip()
    logger.info(f"process_location_link: получили ссылку от пользователя {message.from_user.id}")

    # Сначала проверяем, являются ли это координаты (широта, долгота)
    if "," in link and len(link.split(",")) == 2:
        try:
            lat_str, lng_str = link.split(",")
            lat = float(lat_str.strip())
            lng = float(lng_str.strip())

            # Проверяем валидность координат
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                # Сохраняем координаты
                await state.update_data(
                    location_name="Место по координатам",
                    location_lat=lat,
                    location_lng=lng,
                    location_url=link,
                )

                # Переходим к описанию
                await state.set_state(EventCreation.waiting_for_description)
                await message.answer(
                    f"📍 Место определено по координатам: *{lat}, {lng}*\n\n" "📝 Теперь добавьте описание события:",
                    parse_mode="Markdown",
                )
                return
            else:
                raise ValueError("Invalid coordinates range")

        except ValueError:
            await message.answer(
                "❌ Неверный формат координат!\n\n"
                "Используйте формат: **широта, долгота**\n"
                "Например: 55.7558, 37.6176\n\n"
                "Диапазоны:\n"
                "• Широта: -90 до 90\n"
                "• Долгота: -180 до 180",
                parse_mode="Markdown",
            )
            return

    # Если не координаты, пытаемся парсить как Google Maps ссылку
    from utils.geo_utils import parse_google_maps_link

    location_data = await parse_google_maps_link(link)
    logger.info(f"🔍 parse_google_maps_link результат: {location_data}")

    if not location_data:
        logger.warning(f"❌ Не удалось распознать ссылку: {link}")
        await message.answer(
            "❌ Не удалось распознать ссылку Google Maps.\n\n"
            "Попробуйте:\n"
            "• Скопировать ссылку из приложения Google Maps\n"
            "• Или ввести координаты в формате: широта,долгота"
        )
        return

    # Если координаты не найдены, пытаемся получить их через геокодирование
    lat = location_data.get("lat")
    lng = location_data.get("lng")

    if lat is None or lng is None:
        # Пытаемся получить координаты через геокодирование
        from utils.geo_utils import geocode_address

        # Используем название места или ссылку для геокодирования
        address = location_data.get("name") or location_data.get("raw_link", "")
        logger.info(f"🌍 Пытаемся геокодировать адрес: {address}")

        if address:
            coords = await geocode_address(address)
            if coords:
                lat, lng = coords
                logger.info(f"✅ Получили координаты через геокодирование: {lat}, {lng}")
            else:
                logger.warning(f"❌ Не удалось геокодировать адрес: {address}")
                await message.answer(
                    "❌ Не удалось определить координаты места.\n\n"
                    "Попробуйте:\n"
                    "• Ввести координаты в формате: широта,долгота\n"
                    "• Или выбрать другое место"
                )
                return
        else:
            logger.warning("❌ Нет адреса для геокодирования")
            await message.answer(
                "❌ Не удалось определить координаты места.\n\n"
                "Попробуйте:\n"
                "• Ввести координаты в формате: широта,долгота\n"
                "• Или выбрать другое место"
            )
            return

    # Сохраняем данные локации
    await state.update_data(
        location_name=location_data.get("name", "Место на карте"),
        location_lat=lat,
        location_lng=lng,
        location_url=location_data["raw_link"],
    )

    # Показываем подтверждение
    location_name = location_data.get("name", "Место на карте")

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
            [InlineKeyboardButton(text="📍 Ввести координаты", callback_data="location_coords")],
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


# ===== ОБРАБОТЧИКИ ДЛЯ СОБЫТИЙ СООБЩЕСТВ (ГРУППОВЫЕ ЧАТЫ) =====


# Убрали старый обработчик - теперь используем правильные FSM обработчики с фильтрами


# Функции для обработки каждого шага создания события
async def handle_community_title_step(message: types.Message, state: FSMContext):
    """Обработка названия события"""
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n"
            "✍ **Введите название мероприятия** (например: Встреча в кафе):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    title = message.text.strip()
    await state.update_data(title=title, step="date")

    example_date = get_example_date()
    await message.answer(
        f"**Название сохранено:** *{title}* ✅\n\n📅 **Введите дату** (например: {example_date}):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
        ),
    )


async def handle_community_date_step(message: types.Message, state: FSMContext):
    """Обработка даты события"""
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n" "📅 **Введите дату** (например: 15.12.2024):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    date = message.text.strip()
    import re

    if not re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", date):
        await message.answer(
            "❌ **Неверный формат даты!**\n\n" "📅 Введите дату в формате **ДД.ММ.ГГГГ**\n" "Например: 15.12.2024",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    await state.update_data(date=date, step="time")
    await message.answer(
        f"**Дата сохранена:** {date} ✅\n\n⏰ **Введите время** (например: 19:00):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
        ),
    )


async def handle_community_time_step(message: types.Message, state: FSMContext):
    """Обработка времени события"""
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n" "⏰ **Введите время** (например: 19:00):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    time = message.text.strip()
    import re

    if not re.match(r"^\d{1,2}:\d{2}$", time):
        await message.answer(
            "❌ **Неверный формат времени!**\n\n" "⏰ Введите время в формате **ЧЧ:ММ**\n" "Например: 19:00",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    await state.update_data(time=time, step="city")
    await message.answer(
        f"**Время сохранено:** {time} ✅\n\n🏙️ **Введите город** (например: Москва):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
        ),
    )


async def handle_community_city_step(message: types.Message, state: FSMContext):
    """Обработка города события"""
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n" "🏙️ **Введите город** (например: Москва):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    city = message.text.strip()
    await state.update_data(city=city, step="location_name")
    await message.answer(
        f"**Город сохранен:** {city} ✅\n\n📍 **Введите название места** (например: Кафе 'Уют'):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
        ),
    )


async def handle_community_location_name_step(message: types.Message, state: FSMContext):
    """Обработка названия места"""
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n"
            "📍 **Введите название места** (например: Кафе 'Уют'):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    location_name = message.text.strip()
    await state.update_data(location_name=location_name, step="location_url")
    await message.answer(
        f"**Место сохранено:** {location_name} ✅\n\n🔗 **Введите ссылку на место** (Google Maps или адрес):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
        ),
    )


async def handle_community_location_url_step(message: types.Message, state: FSMContext):
    """Обработка ссылки на место"""
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n"
            "🔗 **Введите ссылку на место** (Google Maps или адрес):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    location_url = message.text.strip()
    await state.update_data(location_url=location_url, step="description")
    await message.answer(
        "**Ссылка сохранена** ✅\n\n📝 **Введите описание события** (что будет происходить, кому интересно):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
        ),
    )


async def handle_community_description_step(message: types.Message, state: FSMContext):
    """Обработка описания события"""
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n"
            "📝 **Введите описание события** (что будет происходить, кому интересно):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    description = message.text.strip()
    data = await state.get_data()

    # Показываем итог перед подтверждением
    await message.answer(
        f"📌 **Проверьте данные события сообщества:**\n\n"
        f"**Название:** {data['title']}\n"
        f"**Дата:** {data['date']}\n"
        f"**Время:** {data['time']}\n"
        f"**Город:** {data['city']}\n"
        f"**Место:** {data['location_name']}\n"
        f"**Ссылка:** {data['location_url']}\n"
        f"**Описание:** {description}\n\n"
        f"Если всё верно, нажмите ✅ Сохранить. Если нужно изменить — нажмите ❌ Отмена.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Сохранить", callback_data="community_event_confirm"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create"),
                ]
            ]
        ),
    )

    # Сохраняем описание
    await state.update_data(description=description)


# Обработчики для групповых чатов с правильными фильтрами
@dp.message(CommunityEventCreation.waiting_for_title, F.chat.type.in_({"group", "supergroup"}))
async def process_community_title_group(message: types.Message, state: FSMContext):
    """Обработка названия события в групповых чатах"""
    logger.info(
        f"🔥 process_community_title_group: получено сообщение от пользователя {message.from_user.id} в чате {message.chat.id}, текст: '{message.text}'"
    )

    # Проверяем, что сообщение содержит текст
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n"
            "✍ **Введите название мероприятия** (например: Встреча в кафе):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    title = message.text.strip()
    chat_id = message.chat.id

    logger.info(
        f"🔥 process_community_title_group: получили название '{title}' от пользователя {message.from_user.id} в чате {chat_id}"
    )

    await state.update_data(title=title, chat_id=chat_id)
    await state.set_state(CommunityEventCreation.waiting_for_date)
    example_date = get_example_date()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
    )

    await message.answer(
        f"**Название сохранено:** *{title}* ✅\n\n📅 **Введите дату** (например: {example_date}):",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@dp.message(CommunityEventCreation.waiting_for_date, F.chat.type.in_({"group", "supergroup"}))
async def process_community_date_group(message: types.Message, state: FSMContext):
    """Обработка даты события в групповых чатах"""
    logger.info(
        f"🔥 process_community_date_group: получено сообщение от пользователя {message.from_user.id} в чате {message.chat.id}, текст: '{message.text}'"
    )

    # Проверяем, что сообщение содержит текст
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n" "📅 **Введите дату** (например: 15.12.2024):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    date = message.text.strip()
    logger.info(f"🔥 process_community_date_group: получили дату '{date}' от пользователя {message.from_user.id}")

    # Валидация формата даты DD.MM.YYYY
    import re

    if not re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", date):
        await message.answer(
            "❌ **Неверный формат даты!**\n\n" "📅 Введите дату в формате **ДД.ММ.ГГГГ**\n" "Например: 15.12.2024",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    await state.update_data(date=date)
    await state.set_state(CommunityEventCreation.waiting_for_time)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
    )

    await message.answer(
        f"**Дата сохранена:** {date} ✅\n\n⏰ **Введите время** (например: 19:00):",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@dp.message(CommunityEventCreation.waiting_for_time, F.chat.type.in_({"group", "supergroup"}))
async def process_community_time_group(message: types.Message, state: FSMContext):
    """Обработка времени события в групповых чатах"""
    logger.info(
        f"🔥 process_community_time_group: получено сообщение от пользователя {message.from_user.id} в чате {message.chat.id}, текст: '{message.text}'"
    )

    # Проверяем, что сообщение содержит текст
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n" "⏰ **Введите время** (например: 19:00):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    time = message.text.strip()
    logger.info(f"🔥 process_community_time_group: получили время '{time}' от пользователя {message.from_user.id}")

    # Валидация формата времени HH:MM
    import re

    if not re.match(r"^\d{1,2}:\d{2}$", time):
        await message.answer(
            "❌ **Неверный формат времени!**\n\n" "⏰ Введите время в формате **ЧЧ:ММ**\n" "Например: 19:00",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    await state.update_data(time=time)
    await state.set_state(CommunityEventCreation.waiting_for_city)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
    )

    await message.answer(
        f"**Время сохранено:** {time} ✅\n\n🏙️ **Введите город** (например: Москва):",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@dp.message(CommunityEventCreation.waiting_for_city, F.chat.type.in_({"group", "supergroup"}))
async def process_community_city_group(message: types.Message, state: FSMContext):
    """Обработка города события в групповых чатах"""
    logger.info(
        f"🔥 process_community_city_group: получено сообщение от пользователя {message.from_user.id} в чате {message.chat.id}, текст: '{message.text}'"
    )

    # Проверяем, что сообщение содержит текст
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n" "🏙️ **Введите город** (например: Москва):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    city = message.text.strip()
    logger.info(f"🔥 process_community_city_group: получили город '{city}' от пользователя {message.from_user.id}")

    await state.update_data(city=city)
    await state.set_state(CommunityEventCreation.waiting_for_location_url)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
    )

    await message.answer(
        f"**Город сохранен:** {city} ✅\n\n🔗 **Введите ссылку на место** (Google Maps или адрес):",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@dp.message(CommunityEventCreation.waiting_for_location_url, F.chat.type.in_({"group", "supergroup"}))
async def process_community_location_url_group(message: types.Message, state: FSMContext):
    """Обработка ссылки на место события в групповых чатах"""
    logger.info(
        f"🔥 process_community_location_url_group: получено сообщение от пользователя {message.from_user.id} в чате {message.chat.id}, текст: '{message.text}'"
    )

    # Проверяем, что сообщение содержит текст
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n"
            "🔗 **Введите ссылку на место** (Google Maps или адрес):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    location_url = message.text.strip()
    logger.info(f"🔥 process_community_location_url_group: получили ссылку от пользователя {message.from_user.id}")

    await state.update_data(location_url=location_url)
    await state.set_state(CommunityEventCreation.waiting_for_description)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
    )

    await message.answer(
        "**Ссылка сохранена** ✅\n\n📝 **Введите описание события** (что будет происходить, кому интересно):",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@dp.message(CommunityEventCreation.waiting_for_description, F.chat.type.in_({"group", "supergroup"}))
async def process_community_description_group(message: types.Message, state: FSMContext):
    """Обработка описания события в групповых чатах"""
    logger.info(
        f"🔥 process_community_description_group: получено сообщение от пользователя {message.from_user.id} в чате {message.chat.id}, текст: '{message.text}'"
    )

    # Проверяем, что сообщение содержит текст
    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n"
            "📝 **Введите описание события** (что будет происходить, кому интересно):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    description = message.text.strip()
    logger.info(f"🔥 process_community_description_group: получили описание от пользователя {message.from_user.id}")

    await state.update_data(description=description)
    data = await state.get_data()
    await state.set_state(CommunityEventCreation.confirmation)

    # Показываем итог перед подтверждением
    await message.answer(
        f"📌 **Проверьте данные события сообщества:**\n\n"
        f"**Название:** {data['title']}\n"
        f"**Дата:** {data['date']}\n"
        f"**Время:** {data['time']}\n"
        f"**Город:** {data['city']}\n"
        f"**Место:** {data['location_name']}\n"
        f"**Ссылка:** {data['location_url']}\n"
        f"**Описание:** {data['description']}\n\n"
        f"Если всё верно, нажмите ✅ Сохранить. Если нужно изменить — нажмите ❌ Отмена.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Сохранить", callback_data="community_event_confirm"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create"),
                ]
            ]
        ),
    )


# Старые обработчики для личных чатов (оставляем для совместимости)


@dp.callback_query(F.data == "community_event_confirm")
async def confirm_community_event(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение создания события сообщества"""
    logger.info(
        f"🔥 confirm_community_event: пользователь {callback.from_user.id} подтверждает создание события в чате {callback.message.chat.id}"
    )
    try:
        data = await state.get_data()
        logger.info(f"🔥 confirm_community_event: данные события: {data}")

        # Парсим дату и время
        from datetime import datetime

        date_str = data["date"]
        time_str = data["time"]

        # Создаем datetime объект
        starts_at = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")

        # Импортируем сервис для событий сообществ
        from utils.community_events_service import CommunityEventsService

        community_service = CommunityEventsService()

        # Создаем событие в сообществе
        event_id = community_service.create_community_event(
            group_id=data["chat_id"],
            creator_id=callback.from_user.id,
            creator_username=callback.from_user.username or callback.from_user.first_name,
            title=data["title"],
            date=starts_at,
            description=data["description"],
            city=data["city"],
            location_name=data.get("location_name", "Место по ссылке"),
            location_url=data.get("location_url"),
        )

        logger.info(f"✅ Событие сообщества создано с ID: {event_id}")

        await state.clear()
        await callback.message.edit_text(
            f"🎉 **Событие создано!**\n\n"
            f"**{data['title']}**\n"
            f"📅 {data['date']} в {data['time']}\n"
            f"🏙️ {data['city']}\n"
            f"📍 {data['location_name']}\n\n"
            f"Событие добавлено в список событий этого чата!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="group_back_to_start")]]
            ),
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"❌ Ошибка при создании события сообщества: {e}")
        await callback.message.edit_text(
            "❌ **Ошибка при создании события!**\n\n" "Попробуйте создать событие заново.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="group_back_to_start")]]
            ),
        )
        await callback.answer()


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
        logger.info(f"🔍 DATA: {data}")
        time_local = f"{data['date']} {data['time']}"
        logger.info(f"🔍 TIME_LOCAL: {time_local}")

        # Определяем предварительный город (для правильного часового пояса)
        # Позже будет уточнен по координатам
        preliminary_city = "bali"  # По умолчанию Бали

        # Парсим дату и время для starts_at с учетом часового пояса
        from datetime import datetime

        import pytz

        try:
            # Исправляем формат времени: заменяем точку на двоеточие в части времени
            # "02.10.2025 19.00" -> "02.10.2025 19:00"
            import re

            time_local_fixed = re.sub(r"(\d{2}\.\d{2}\.\d{4}) (\d{2})\.(\d{2})", r"\1 \2:\3", time_local)
            logger.info(f"🔍 TIME_LOCAL_FIXED: {time_local_fixed}")

            # Парсим время как локальное для региона
            naive_dt = datetime.strptime(time_local_fixed, "%d.%m.%Y %H:%M")

            # Определяем часовой пояс по городу
            if preliminary_city == "bali":
                tz = pytz.timezone("Asia/Makassar")
            elif preliminary_city in ["moscow", "spb"]:
                tz = pytz.timezone("Europe/Moscow")
            else:
                tz = pytz.UTC

            # Локализуем время и конвертируем в UTC
            local_dt = tz.localize(naive_dt)
            starts_at = local_dt.astimezone(pytz.UTC)

            logger.info(f"🕐 Время события: {time_local} ({preliminary_city}) → {starts_at} UTC")
        except ValueError as e:
            logger.error(f"❌ Ошибка парсинга времени: {e}, time_local: {time_local}")
            starts_at = None

        # Определяем данные локации
        location_name = data.get("location_name", data.get("location", "Место не указано"))
        location_url = data.get("location_url")
        lat = data.get("location_lat")
        lng = data.get("location_lng")

        # Если координаты не извлечены из ссылки, пробуем геокодирование
        if (not lat or not lng) and location_name and location_name != "Место не указано":
            logger.info(f"🌍 Координаты не найдены, пробуем геокодирование адреса: {location_name}")
            try:
                from utils.geo_utils import geocode_address

                coords = await geocode_address(location_name)
                if coords:
                    lat, lng = coords
                    logger.info(f"✅ Геокодирование успешно: lat={lat}, lng={lng}")
                else:
                    logger.warning(f"❌ Геокодирование не удалось для: {location_name}")
            except Exception as e:
                logger.error(f"❌ Ошибка геокодирования: {e}")

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
                chat_id=data.get("chat_id"),  # Добавляем chat_id для групповых чатов
                organizer_username=callback.from_user.username,
            )

            logger.info(f"✅ Событие создано с ID: {event_id}")

            # Награждаем ракетами за создание события
            rockets_earned = award_rockets_for_activity(callback.from_user.id, "event_create")
            if rockets_earned > 0:
                logger.info(
                    f"🚀 Пользователь {callback.from_user.id} получил {rockets_earned} ракет за создание события"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка при создании события: {e}")
            # НЕ используем fallback - события должны сохраняться только в events_user
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
        reply_markup=None,  # Убираем все кнопки после сохранения
    )
    await callback.answer("Событие создано!")

    # Показываем крутую анимацию после сохранения
    await send_spinning_menu(callback.message)


@dp.callback_query(F.data == "event_cancel")
async def cancel_event_creation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания события"""
    await state.clear()
    await callback.message.edit_text("❌ Создание мероприятия отменено.")
    await callback.answer("Создание отменено")


@dp.callback_query(F.data == "manage_events")
async def handle_manage_events(callback: types.CallbackQuery):
    """Обработчик кнопки Управление событиями"""
    user_id = callback.from_user.id
    events = get_user_events(user_id)
    active_events = [e for e in events if e.get("status") == "open"]

    if not active_events:
        await callback.message.edit_text("У вас нет активных событий для управления.", reply_markup=None)
        await callback.answer()
        return

    # Показываем первое событие с кнопками управления (старая логика)
    first_event = active_events[0]
    text = f"🔧 Управление событием:\n\n{format_event_for_display(first_event)}"

    # Создаем кнопки управления
    buttons = get_status_change_buttons(first_event["id"], first_event["status"])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
        ]
    )

    # Добавляем навигацию если есть еще события
    if len(active_events) > 1:
        keyboard.inline_keyboard.append(
            [
                InlineKeyboardButton(text="◀️ Предыдущее", callback_data="prev_event_0"),
                InlineKeyboardButton(text="▶️ Следующее", callback_data="next_event_1"),
            ]
        )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@dp.message(F.text == "🏠 Главное меню")
async def on_main_menu_button(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Главное меню' - очищает состояние и показывает анимацию ракеты"""
    # Очищаем состояние FSM
    await state.clear()

    # Показываем анимацию ракеты с главным меню
    await send_spinning_menu(message)


@dp.message(~StateFilter(EventCreation, EventEditing, TaskFlow))
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

        # Создаем клавиатуру пагинации
        combined_keyboard = kb_pager(page, total_pages, current_radius)

        # Обновляем сообщение с защитой от ошибок
        try:
            await callback.message.edit_text(
                render_header(counts, radius_km=current_radius) + "\n\n" + page_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=combined_keyboard,
            )
        except TelegramBadRequest:
            await callback.message.answer(
                render_header(counts, radius_km=current_radius) + "\n\n" + page_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=combined_keyboard,
            )

        # Обновляем состояние
        state["page"] = page
        user_state[callback.message.chat.id] = state

        await callback.answer()

        # Клавиатура главного меню уже есть у пользователя

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


@dp.callback_query(F.data == "create_event")
async def handle_create_event(callback: types.CallbackQuery):
    """Обработчик кнопки создания события"""
    try:
        # Закрываем предыдущее сообщение и отправляем главное меню
        try:
            await callback.message.delete()
        except Exception:
            pass

        # Отправляем сообщение с инструкциями и главным меню
        await callback.message.answer(
            "➕ <b>Создание события</b>\n\n"
            "Чтобы создать событие, нажмите кнопку <b>'➕ Создать'</b> в главном меню ниже.\n\n"
            "Вы сможете указать:\n"
            "• Название события\n"
            "• Описание\n"
            "• Время проведения\n"
            "• Место проведения\n"
            "• Ссылку на событие",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
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
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_search")]]
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


# ===== ОБРАБОТЧИКИ MOMENTS ОТКЛЮЧЕНЫ =====
# Все обработчики Moments закомментированы, так как функция отключена


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

    user_id = cb.from_user.id

    # Сохраняем выбранный радиус в БД
    try:
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.default_radius_km = km
                session.commit()
            else:
                # Создаем пользователя если его нет
                user = User(
                    id=user_id,
                    username=cb.from_user.username,
                    full_name=get_user_display_name(cb.from_user),
                    default_radius_km=km,
                )
                session.add(user)
                session.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения радиуса пользователя {user_id}: {e}")
        await cb.answer("Ошибка сохранения", show_alert=True)
        return

    await cb.answer(f"Радиус: {km} км")

    # Обновляем клавиатуру с новым выбранным радиусом
    await cb.message.edit_reply_markup(reply_markup=kb_radius(km))


# Удален старый обработчик handle_radius_selection() - используем только on_radius_change()


async def main():
    """Главная функция"""
    print("🔥 MAIN FUNCTION STARTED!")
    logger.info("🔥 MAIN FUNCTION STARTED!")
    logger.info("Запуск улучшенного EventBot (aiogram 3.x)...")

    # Инициализируем BOT_ID для корректной фильтрации в групповых чатах
    global BOT_ID
    BOT_ID = (await bot.me()).id
    logger.info(f"BOT_ID инициализирован: {BOT_ID}")

    # ИНТЕГРАЦИЯ ГРУППОВЫХ ЧАТОВ (ИЗОЛИРОВАННО)
    # ВНИМАНИЕ: Эта интеграция полностью изолирована от основного функционала
    logger.info("🔥 Начинаем интеграцию групповых чатов...")
    try:
        logger.info("🔥 Импортируем register_group_handlers...")
        from group_chat_handlers import register_group_handlers

        logger.info("✅ register_group_handlers импортирован успешно")

        logger.info(f"🔥 Регистрируем обработчики с BOT_ID={BOT_ID}")
        register_group_handlers(dp, BOT_ID)
        logger.info("✅ Обработчики групповых чатов успешно интегрированы")
    except Exception as e:
        logger.error(f"❌ Ошибка интеграции групповых чатов: {e}")
        import traceback

        logger.error(f"❌ Детали ошибки: {traceback.format_exc()}")
        # Не прерываем работу основного бота при ошибке

    # Запускаем фоновую задачу для очистки моментов
    from config import load_settings
    from tasks_service import mark_tasks_as_expired

    load_settings()

    # Очищаем просроченные задания при старте
    try:
        expired_count = mark_tasks_as_expired()
        if expired_count > 0:
            logger.info(f"При старте помечено как истекшие: {expired_count} заданий")
        else:
            logger.info("При старте просроченных заданий не найдено")
    except Exception as e:
        logger.error(f"Ошибка очистки просроченных заданий при старте: {e}")

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
        # АГРЕССИВНАЯ очистка всех команд для всех scope
        from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeDefault

        # Очищаем команды для всех типов чатов
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
        await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())

        # Ждем дольше, чтобы Telegram точно обработал удаление
        import asyncio

        await asyncio.sleep(3)

        from aiogram.types import BotCommandScopeChat, BotCommandScopeDefault

        # Публичные команды - только самое необходимое (без дублирования кнопок)
        public_commands = [
            types.BotCommand(command="start", description="🚀 Запустить бота и показать меню"),
            types.BotCommand(command="help", description="💬 Написать отзыв Разработчику"),
            types.BotCommand(command="share", description="🔗 Поделиться ботом"),
        ]

        # Админские команды - только для админа
        admin_commands = [
            types.BotCommand(command="admin_event", description="🔍 Диагностика события (админ)"),
            types.BotCommand(command="diag_last", description="📊 Диагностика последнего запроса"),
            types.BotCommand(command="diag_search", description="🔍 Диагностика поиска событий"),
            types.BotCommand(command="diag_webhook", description="🔗 Диагностика webhook"),
        ]

        # Команды для групповых чатов - только базовые
        group_commands = [
            types.BotCommand(command="start", description="🚀 Запустить бота"),
        ]

        # Устанавливаем команды для разных типов чатов
        await bot.set_my_commands(public_commands, scope=BotCommandScopeDefault())
        await bot.set_my_commands(public_commands, scope=BotCommandScopeAllPrivateChats())
        await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())

        # Устанавливаем админские команды для всех админов
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        if admin_ids_str:
            admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
            for admin_id in admin_ids:
                await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
                logger.info(f"Админские команды установлены для админа {admin_id}")
        else:
            # Fallback на старый способ
            admin_user_id = int(os.getenv("ADMIN_USER_ID", "123456789"))
            if admin_user_id != 123456789:
                await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_user_id))
                logger.info(f"Админские команды установлены для админа {admin_user_id}")

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
    example_date = get_example_date()
    await callback.message.answer(f"📅 Введите новую дату в формате ДД.ММ.ГГГГ (например: {example_date}):")
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_time_"))
async def handle_edit_time_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования времени"""
    await state.set_state(EventEditing.waiting_for_time)
    await callback.message.answer("⏰ Введите новое время в формате ЧЧ:ММ (например: 18:30):")
    await callback.answer()


@dp.callback_query(F.data.regexp(r"^edit_location_\d+$"))
async def handle_edit_location_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования локации - показываем меню выбора типа"""
    event_id = int(callback.data.split("_")[-1])

    # Сохраняем ID события в состоянии
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.waiting_for_location_type)

    # Создаем клавиатуру для выбора типа локации (как при создании)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data=f"edit_location_link_{event_id}")],
            [InlineKeyboardButton(text="🌍 Найти на карте", callback_data=f"edit_location_map_{event_id}")],
            [InlineKeyboardButton(text="📍 Ввести координаты", callback_data=f"edit_location_coords_{event_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"edit_event_{event_id}")],
        ]
    )

    await callback.message.answer(
        "📍 **Выберите способ указания локации:**\n\n"
        "🔗 **Готовая ссылка** - вставьте ссылку из Google Maps\n"
        "🌍 **Поиск на карте** - откроется Google Maps для поиска\n"
        "📍 **Координаты** - введите широту и долготу",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    await callback.answer()


# Обработчики для редактирования локации
@dp.callback_query(F.data.regexp(r"^edit_location_link_\d+$"))
async def handle_edit_location_link_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода готовой ссылки для редактирования"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.waiting_for_location)
    await callback.message.answer("🔗 Вставьте сюда ссылку из Google Maps:")
    await callback.answer()


@dp.callback_query(F.data.regexp(r"^edit_location_map_\d+$"))
async def handle_edit_location_map_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор поиска на карте для редактирования"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)

    # Создаем кнопку для открытия Google Maps
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🌍 Открыть Google Maps", url="https://www.google.com/maps")]]
    )

    await state.set_state(EventEditing.waiting_for_location)
    await callback.message.answer("🌍 Открой карту, найди место и вставь ссылку сюда 👇", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data.regexp(r"^edit_location_coords_\d+$"))
async def handle_edit_location_coords_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода координат для редактирования"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)

    await state.set_state(EventEditing.waiting_for_location)
    await callback.message.answer(
        "📍 Введите координаты в формате: **широта, долгота**\n\n" "Например: 55.7558, 37.6176\n" "Или: -8.67, 115.21",
        parse_mode="Markdown",
    )
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
    """Обработка ввода новой локации (ссылка, координаты или текст)"""
    data = await state.get_data()
    event_id = data.get("event_id")

    if not event_id or not message.text:
        await message.answer("❌ Введите корректную локацию")
        return

    location_input = message.text.strip()
    logger.info(f"handle_location_input: редактирование локации для события {event_id}, ввод: {location_input}")

    # Проверяем, является ли это Google Maps ссылкой
    if any(domain in location_input.lower() for domain in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl"]):
        # Парсим ссылку Google Maps
        from utils.geo_utils import parse_google_maps_link

        location_data = await parse_google_maps_link(location_input)

        if location_data:
            # Обновляем событие с данными из ссылки
            success = update_event_field(
                event_id, "location_name", location_data.get("name", "Место на карте"), message.from_user.id
            )
            if success:
                # Обновляем URL и координаты
                update_event_field(event_id, "location_url", location_input, message.from_user.id)
                if location_data.get("lat") and location_data.get("lng"):
                    update_event_field(event_id, "lat", location_data.get("lat"), message.from_user.id)
                    update_event_field(event_id, "lng", location_data.get("lng"), message.from_user.id)

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
                success = update_event_field(event_id, "location_name", "Место по координатам", message.from_user.id)
                if success:
                    update_event_field(event_id, "lat", lat, message.from_user.id)
                    update_event_field(event_id, "lng", lng, message.from_user.id)
                    update_event_field(event_id, "location_url", location_input, message.from_user.id)

                    await message.answer(f"✅ Локация обновлена: *{lat:.6f}, {lng:.6f}*", parse_mode="Markdown")
                else:
                    await message.answer("❌ Ошибка при обновлении локации")
            else:
                await message.answer("❌ Координаты вне допустимого диапазона")
        except ValueError:
            await message.answer("❌ Неверный формат координат. Используйте: широта, долгота")

    else:
        # Обычный текст - обновляем только название
        success = update_event_field(event_id, "location_name", location_input, message.from_user.id)
        if success:
            await message.answer(f"✅ Локация обновлена: *{location_input}*", parse_mode="Markdown")
        else:
            await message.answer("❌ Ошибка при обновлении локации")

    # Возвращаемся к меню редактирования
    keyboard = edit_event_keyboard(event_id)
    await message.answer("Выберите, что еще хотите изменить:", reply_markup=keyboard)
    await state.set_state(EventEditing.choosing_field)


@dp.message(EventEditing.waiting_for_description)
async def handle_description_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового описания"""
    description = message.text.strip()

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

    data = await state.get_data()
    event_id = data.get("event_id")

    if event_id and description:
        success = update_event_field(event_id, "description", description, message.from_user.id)
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
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="◀️ Предыдущее", callback_data="prev_event_0")])

        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()
    else:
        await callback.answer("Это единственное событие")


@dp.callback_query(F.data.startswith("back_to_main_"))
async def handle_back_to_main(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    # Показываем анимацию ракеты с главным меню
    await callback.answer("🎯 Возврат в главное меню")
    await send_spinning_menu(callback.message)


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
            keyboard.inline_keyboard.append([InlineKeyboardButton(text="▶️ Следующее", callback_data="next_event_1")])

        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()


if __name__ == "__main__":
    asyncio.run(main())
