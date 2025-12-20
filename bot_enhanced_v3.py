#!/usr/bin/env python3
"""
Улучшенная версия EventBot с расширенным поиском событий (aiogram 3.x)
"""

import asyncio
import html
import logging
import os
import re
import time
from datetime import UTC, datetime
from math import ceil
from urllib.parse import quote_plus, urlparse

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    ChatMemberUpdated,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from config import load_settings
from database import Event, User, create_all, get_session, init_engine
from rockets_service import award_rockets_for_activity
from simple_status_manager import (
    auto_close_events,
    change_event_status,
    format_event_for_display,
    get_event_by_id,
    get_status_change_buttons,
    get_user_events,
)
from tasks_service import (
    accept_task,
    cancel_task,
    complete_task,
    create_task_from_place,
    get_user_active_tasks,
)
from utils.geo_utils import get_timezone, haversine_km
from utils.static_map import build_static_map_url, fetch_static_map
from utils.unified_events_service import UnifiedEventsService
from utils.user_participation_analytics import UserParticipationAnalytics


def _build_tracking_url(click_type: str, event: dict, target_url: str, user_id: int | None) -> str:
    """
    Создает URL для отслеживания кликов через API endpoint.
    Если api_base_url не настроен или user_id отсутствует, возвращает оригинальный URL.
    """
    import logging
    from urllib.parse import quote

    logger = logging.getLogger(__name__)

    if not user_id:
        # Если user_id не указан, возвращаем оригинальный URL без отслеживания
        logger.debug("⚠️ _build_tracking_url: user_id отсутствует, используем прямой URL")
        return target_url

    settings = load_settings()
    if not settings.api_base_url:
        # Если API URL не настроен, возвращаем оригинальный URL
        logger.debug("⚠️ _build_tracking_url: API_BASE_URL не настроен, используем прямой URL")
        return target_url

    event_id = event.get("id")
    if not event_id:
        # Если нет event_id, возвращаем оригинальный URL
        logger.debug("⚠️ _build_tracking_url: event_id отсутствует в событии, используем прямой URL")
        return target_url

    # Формируем URL через API endpoint
    api_base = settings.api_base_url.rstrip("/")
    encoded_url = quote(target_url, safe="")
    tracking_url = (
        f"{api_base}/click?user_id={user_id}&event_id={event_id}&click_type={click_type}&target_url={encoded_url}"
    )

    logger.debug(f"✅ _build_tracking_url: создан URL отслеживания для {click_type}: event_id={event_id}")

    return tracking_url


def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown для безопасной вставки в текст"""
    if not text:
        return ""
    # Специальные символы Markdown (не V2), которые нужно экранировать
    # В обычном Markdown нужно экранировать: * _ ` [ и обратный слэш \
    # Обратный слэш экранируем первым, так как он используется для экранирования других символов
    special_chars = r"*_`["
    # Экранируем каждый специальный символ
    escaped = ""
    for char in text:
        if char == "\\":
            # Обратный слэш экранируем двойным обратным слэшем
            escaped += "\\\\"
        elif char in special_chars:
            escaped += "\\" + char
        else:
            escaped += char
    return escaped


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


def build_message_link(chat_id: int, message_id: int) -> str:
    """
    Возвращает корректную ссылку на сообщение в приватном чате/супергруппе.
    Для супергрупп Telegram использует внутренний идентификатор без префикса -100,
    для обычных групп – абсолютное значение chat_id.
    """
    chat_id_str = str(chat_id)
    if chat_id_str.startswith("-100"):
        internal_id = chat_id_str[4:]
    else:
        internal_id = chat_id_str.lstrip("-")

    return f"https://t.me/c/{internal_id}/{message_id}"


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
    НЕ извлекает из названия события - использует только данные из БД (геокодирование)
    """
    # Проверяем venue_name из БД (должен быть из геокодирования)
    if e.get("venue_name") and e.get("venue_name") not in [
        "",
        "Место проведения",
        "Место не указано",
    ]:
        return e

    # Проверяем location_name из БД (альтернативный источник)
    if e.get("location_name") and e.get("location_name") not in [
        "",
        "Место проведения",
        "Место не указано",
        "Место по ссылке",
    ]:
        e["venue_name"] = e.get("location_name")
        return e

    # Если всё ещё пустое, используем fallback
    # НЕ извлекаем из названия события - это неправильно!
    if not e.get("venue_name") or e.get("venue_name") in [
        "",
        "Место проведения",
        "Место не указано",
    ]:
        e["venue_name"] = "Локация"

    return e


def create_google_maps_url(event: dict) -> str:
    """
    Создает ссылку на Google Maps с названием места (устаревшая функция)
    """
    return build_maps_url(event)


def get_venue_name(event: dict) -> str:
    """
    Возвращает название места для события
    НЕ извлекает из названия/описания - использует только данные из БД (геокодирование)
    """
    # Приоритет: venue_name -> location_name -> address (все из БД/геокодирования)
    venue_name = event.get("venue_name") or event.get("location_name") or event.get("address") or ""

    # Фильтруем мусорные названия
    if venue_name in ["Место проведения", "Место не указано", "Локация", "", "Место по ссылке"]:
        venue_name = ""

    # НЕ извлекаем из описания - это неправильно!
    # Название места должно браться только из карты (геокодирование)

    # Если всё ещё пустое, используем fallback
    if not venue_name:
        venue_name = "Локация"

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
            # Все остальное считаем источниками
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
        if input_type == "user" or source in ["user_created", "user", "community"]:
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
    update_user_state_timestamp(message.chat.id)
    user_state[message.chat.id] = {
        "prepared": prepared_events,
        "counts": counts,
        "lat": user_lat,
        "lng": user_lng,
        "radius": int(radius),
        "page": 1,
        "date_filter": "today",  # По умолчанию показываем события на сегодня
        "diag": {"kept": len(prepared_events), "dropped": 0, "reasons_top3": []},
        "region": region,
    }

    # Рендерим страницу
    header_html = render_header(counts, radius_km=int(radius))
    # Обогащаем события reverse geocoding для названий локаций
    prepared_events = await enrich_events_with_reverse_geocoding(prepared_events)

    events_text, total_pages = render_page(prepared_events, page + 1, page_size=8, user_id=message.from_user.id)

    # Отладочная информация

    text = header_html + "\n\n" + events_text

    # Вычисляем total_pages для fallback
    total_pages = max(1, ceil(len(prepared_events) / 8))

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
    update_user_state_timestamp(message.chat.id)
    user_state[message.chat.id] = {
        "prepared": prepared,
        "counts": counts,
        "lat": user_lat,
        "lng": user_lng,
        "radius": int(radius),
        "page": 1,
        "date_filter": "today",  # По умолчанию показываем события на сегодня
        "diag": diag,
        "region": region,  # Добавляем регион
    }

    # 5) Обогащаем события reverse geocoding для названий локаций
    prepared = await enrich_events_with_reverse_geocoding(prepared)

    # 6) Рендерим страницу
    header_html = render_header(counts, radius_km=int(radius))
    page_html, total_pages = render_page(prepared, page=page + 1, page_size=8, user_id=message.from_user.id)
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
    events_per_page = 8
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
        event_html = render_event_html(event, idx, message.from_user.id)
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
    import logging

    logger = logging.getLogger(__name__)

    # Приоритизируем location_url для событий с валидным URL источника
    # Исключение: для ai_generated/ai_parsed без валидного URL источника не используем location_url
    # (так как это может быть небезопасно или неправильно)
    event_type = e.get("type", "")
    location_url = e.get("location_url", "").strip() if e.get("location_url") else ""

    if location_url and location_url.startswith(("http://", "https://", "www.")):
        # Для ai_generated/ai_parsed проверяем наличие валидного URL источника
        # (source_url, url, original_url), но НЕ location_url
        if event_type in ("ai_generated", "ai_parsed", "ai"):
            # Проверяем наличие валидного URL источника (не location_url)
            has_valid_source = bool(e.get("source_url") or e.get("url") or e.get("original_url"))
            if has_valid_source:
                # Есть валидный URL источника - можно использовать location_url
                logger.info(
                    f"🚗 Используем location_url для маршрута: '{location_url[:50]}...' для события '{e.get('title', 'Без названия')[:30]}'"
                )
                return location_url
            else:
                # Нет валидного URL источника - пропускаем location_url для безопасности
                logger.debug(
                    f"⚠️ Пропускаем location_url для ai-события без валидного URL источника: '{e.get('title', 'Без названия')[:30]}'"
                )
        else:
            # Для других типов событий (source, user) используем location_url
            logger.info(
                f"🚗 Используем location_url для маршрута: '{location_url[:50]}...' для события '{e.get('title', 'Без названия')[:30]}'"
            )
            return location_url

    # Поддерживаем новую структуру venue и старую
    # Приоритет: venue.name (из источника) > venue_name (из источника) > location_name (может быть из reverse geocoding)
    # Это важно, чтобы названия из источника имели приоритет над адресами
    venue = e.get("venue", {})
    name = (venue.get("name") or e.get("venue_name") or e.get("location_name") or "").strip()
    addr = (venue.get("address") or e.get("address") or "").strip()
    lat = venue.get("lat") or e.get("lat")
    lng = venue.get("lon") or e.get("lng")

    # Пропускаем generic названия мест
    generic_venues = ["Локация", "📍 Локация уточняется", "Место проведения", "Место не указано", "", "None"]

    # Проверяем, что name не содержит временные/календарные слова (не название места)
    time_patterns = [
        "по понедельникам",
        "по вторникам",
        "по средам",
        "по четвергам",
        "по пятницам",
        "по субботам",
        "по воскресеньям",
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
        "ежедневно",
        "еженедельно",
        "каждый день",
        "каждую неделю",
    ]

    # Проверяем, что name похож на название места (не слишком короткий, не содержит временные слова)
    name_is_valid = (
        name
        and name not in generic_venues
        and len(name) > 3  # Минимум 4 символа для названия места
        and not any(pattern in name.lower() for pattern in time_patterns)
    )

    if name_is_valid:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(name)}"
    if addr and addr not in generic_venues:
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
                # Если есть реферальный код, добавляем его к URL
                referral_code = e.get("referral_code")
                if referral_code:
                    from utils.referral_url import add_referral_to_url

                    referral_param = e.get("referral_param", "ref")
                    return add_referral_to_url(sanitized, referral_code, referral_param)
                return sanitized
    return None  # нет реального источника — лучше не показывать ссылку


def truncate_html_safely(html_text: str, max_length: int) -> str:
    """
    Безопасно обрезает HTML-текст, используя BeautifulSoup для правильной обработки тегов
    Учитывает байты (Telegram считает по байтам, а не по символам)

    Args:
        html_text: HTML-текст для обрезки
        max_length: Максимальная длина в байтах (включая "...")

    Returns:
        Обрезанный HTML-текст с закрытыми тегами
    """
    import logging

    from bs4 import BeautifulSoup

    logger = logging.getLogger(__name__)

    # Проверяем длину в байтах
    html_bytes = html_text.encode("utf-8")
    if len(html_bytes) <= max_length:
        return html_text

    # Оставляем место для "..." (примерно 10 байт)
    target_bytes = max_length - 10

    # Простой и надежный подход: находим последний полный тег в байтовой строке
    html_bytes_trunc = html_bytes[:target_bytes]

    # Пытаемся декодировать
    try:
        html_partial = html_bytes_trunc.decode("utf-8")
    except UnicodeDecodeError:
        # Уменьшаем позицию до последнего полного символа
        for i in range(target_bytes, max(0, target_bytes - 10), -1):
            try:
                html_partial = html_bytes[:i].decode("utf-8")
                break
            except UnicodeDecodeError:
                continue
        else:
            html_partial = html_bytes[: target_bytes - 50].decode("utf-8", errors="ignore")

    # Находим последний полный тег (от < до > без других < между ними)
    last_tag_end = -1
    i = len(html_partial) - 1
    while i >= 0:
        if html_partial[i] == ">":
            # Нашли закрывающий символ тега
            tag_start = html_partial.rfind("<", 0, i + 1)
            if tag_start >= 0:
                # Проверяем, что между < и > нет других < (значит тег полный)
                if "<" not in html_partial[tag_start + 1 : i]:
                    last_tag_end = i + 1
                    break
        i -= 1

    if last_tag_end > 0:
        # Обрезаем после последнего полного тега
        safe_pos = len(html_partial[:last_tag_end].encode("utf-8"))
        truncated_html = html_text[:safe_pos] + "..."
    else:
        # Если не нашли полный тег, обрезаем и удаляем незакрытые теги
        truncated_html = html_partial
        # Удаляем незакрытые теги с конца
        while truncated_html and "<" in truncated_html:
            last_open = truncated_html.rfind("<")
            if last_open >= 0:
                # Проверяем, есть ли закрывающий > после этого <
                if ">" not in truncated_html[last_open:]:
                    # Незакрытый тег, удаляем его
                    truncated_html = truncated_html[:last_open]
                else:
                    break
            else:
                break
        truncated_html += "..."

    # Валидируем через BeautifulSoup и исправляем если нужно
    try:
        soup = BeautifulSoup(truncated_html, "html.parser")
        # BeautifulSoup автоматически закроет незакрытые теги
        validated_html = str(soup)

        # Проверяем длину после валидации
        validated_bytes = validated_html.encode("utf-8")
        if len(validated_bytes) <= max_length:
            return validated_html
        else:
            # Если после валидации стало длиннее, обрезаем еще раз рекурсивно
            return truncate_html_safely(validated_html, max_length)

    except Exception as e:
        logger.warning(f"Ошибка валидации HTML через BeautifulSoup: {e}, возвращаем как есть")
        # Возвращаем обрезанный HTML без валидации
        final_bytes = truncated_html.encode("utf-8")
        if len(final_bytes) > max_length:
            # Если все еще слишком длинно, обрезаем еще больше
            return html_text[: max_length - 10] + "..."
        return truncated_html


def render_event_html(e: dict, idx: int, user_id: int = None, is_caption: bool = False) -> str:
    """Рендерит одну карточку события в HTML согласно ТЗ"""
    import logging

    logger = logging.getLogger(__name__)

    title = html.escape(e.get("title", "Событие"))
    when = e.get("when_str", "")

    logger.info(f"🕐 render_event_html: title={title}, when_str='{when}', starts_at={e.get('starts_at')}")

    # Если when_str пустое, используем функцию human_when с учетом часового пояса пользователя
    if not when:
        when = human_when(e, user_id=user_id)
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
    # Приоритет: venue.name (из источника) > venue_name (из источника) > location_name (может быть из reverse geocoding)
    # Это важно, чтобы названия из источника (например "Valle Canggu") имели приоритет над адресами из reverse geocoding
    venue = e.get("venue", {})
    # НЕ включаем location_name в venue_name, так как location_name может быть обогащен через reverse geocoding позже
    venue_name = venue.get("name") or e.get("venue_name")
    venue_address = venue.get("address") or e.get("address") or e.get("location_url")

    logger.info(f"🔍 DEBUG VENUE: venue={venue}, venue_name='{venue_name}', venue_address='{venue_address}'")
    logger.info(
        f"🔍 DEBUG EVENT FIELDS: e.get('venue_name')='{e.get('venue_name')}', e.get('location_name')='{e.get('location_name')}', e.get('address')='{e.get('address')}'"
    )

    # Проверяем, что venue_name не содержит временные/календарные слова
    time_patterns = [
        "по понедельникам",
        "по вторникам",
        "по средам",
        "по четвергам",
        "по пятницам",
        "по субботам",
        "по воскресеньям",
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
        "ежедневно",
        "еженедельно",
        "каждый день",
        "каждую неделю",
    ]

    # Проверяем generic названия
    generic_venues = ["Локация", "📍 Локация уточняется", "Место проведения", "Место не указано", "", "None"]

    # Если venue_name содержит временные слова или generic, считаем его невалидным
    if venue_name and (venue_name in generic_venues or any(pattern in venue_name.lower() for pattern in time_patterns)):
        logger.warning(f"🔍 DEBUG: venue_name невалидное: '{venue_name}', пропускаем")
        venue_name = None

    # Приоритет: venue_name → address → location_name (может быть из reverse geocoding) → coords → description
    # Проверяем location_name из события (может быть обогащено через reverse geocoding)
    location_name_from_event = e.get("location_name", "").strip() if e.get("location_name") else ""

    logger.info(
        f"🔍 DEBUG LOCATION: venue_name='{venue_name}', venue_address='{venue_address}', "
        f"location_name_from_event='{location_name_from_event}', lat={e.get('lat')}, lng={e.get('lng')}"
    )

    if venue_name:
        venue_display = html.escape(venue_name)
        logger.info(f"🔍 DEBUG: Используем venue_name: '{venue_display}'")
    elif venue_address and venue_address not in generic_venues:
        venue_display = html.escape(venue_address)
        logger.info(f"🔍 DEBUG: Используем venue_address: '{venue_display}'")
    elif location_name_from_event and location_name_from_event not in generic_venues:
        # Используем location_name (может быть из reverse geocoding или из БД)
        venue_display = html.escape(location_name_from_event)
        logger.info(f"🔍 DEBUG: Используем location_name: '{venue_display}'")
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
            # Если нет описания, проверяем location_name перед координатами
            if location_name_from_event and location_name_from_event not in generic_venues:
                venue_display = html.escape(location_name_from_event)
                logger.info(f"🔍 DEBUG: Описание пустое, используем location_name: '{venue_display}'")
            elif e.get("lat") and e.get("lng"):
                venue_display = f"координаты ({e['lat']:.4f}, {e['lng']:.4f})"
                logger.info(f"🔍 DEBUG: Описание пустое, используем координаты: '{venue_display}'")
            else:
                venue_display = "Локация"
                logger.info(f"🔍 DEBUG: Описание пустое, используем fallback: '{venue_display}'")
    else:
        # Для событий от парсеров: проверяем location_name перед координатами
        if location_name_from_event and location_name_from_event not in generic_venues:
            venue_display = html.escape(location_name_from_event)
            logger.info(f"🔍 DEBUG: Используем location_name как fallback: '{venue_display}'")
        elif e.get("lat") and e.get("lng"):
            venue_display = f"координаты ({e['lat']:.4f}, {e['lng']:.4f})"
            logger.info(f"🔍 DEBUG: Используем координаты как fallback: '{venue_display}'")
        else:
            venue_display = "Локация"
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
            # Используем API endpoint для отслеживания кликов
            tracking_url = _build_tracking_url("source", e, src, user_id)
            src_part = f'🔗 <a href="{html.escape(tracking_url)}">Источник</a>'
        else:
            src_part = "ℹ️ Источник не указан"

    # Маршрут с приоритетом venue_name → address → coords
    maps_url = build_maps_url(e)
    map_part = f'🚗 <a href="{_build_tracking_url("route", e, maps_url, user_id)}">Маршрут</a>'

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
        f"📍 Локация\n"
        f'ℹ️ Источник не указан  🚗 <a href="https://www.google.com/maps/search/?api=1&query={lat},{lng}">Маршрут</a>\n\n'
        f"2) <b>Создайте своё событие</b> — (0.0 км)\n"
        f"📍 Локация\n"
        f'ℹ️ Источник не указан  🚗 <a href="https://www.google.com/maps/search/?api=1&query={lat},{lng}">Маршрут</a>\n\n'
        f"3) <b>Проверьте позже</b> — (0.0 км)\n"
        f"📍 Локация\n"
        f'ℹ️ Источник не указан  🚗 <a href="https://www.google.com/maps/search/?api=1&query={lat},{lng}">Маршрут</a>'
    )


async def enrich_events_with_reverse_geocoding(events: list[dict]) -> list[dict]:
    """
    Обогащает события обратным геокодированием для получения названий локаций из координат
    (как для пользовательских событий)
    """
    import logging

    logger = logging.getLogger(__name__)

    # Временные/календарные паттерны, которые не являются названиями мест
    time_patterns = [
        "по понедельникам",
        "по вторникам",
        "по средам",
        "по четвергам",
        "по пятницам",
        "по субботам",
        "по воскресеньям",
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
        "ежедневно",
        "еженедельно",
        "каждый день",
        "каждую неделю",
    ]

    generic_venues = ["Локация", "📍 Локация уточняется", "Место проведения", "Место не указано", "", "None"]

    async def enrich_single_event(event: dict) -> dict:
        """Обогащает одно событие"""
        # Проверяем все возможные источники названия места (приоритет источника)
        venue = event.get("venue", {})
        venue_name_from_source = venue.get("name") or event.get("venue_name")
        location_name_current = event.get("location_name", "")

        # Если есть валидное название из источника, НЕ перезаписываем его reverse geocoding
        has_valid_source_name = (
            venue_name_from_source
            and venue_name_from_source not in generic_venues
            and len(venue_name_from_source) > 3
            and not any(pattern in venue_name_from_source.lower() for pattern in time_patterns)
            # Проверяем, что это не адрес (не начинается с "Jl.", "ул.", "Street" и т.д.)
            and not venue_name_from_source.strip().startswith(
                ("Jl.", "ул.", "Street", "st.", "avenue", "проспект", "проспект")
            )
        )

        lat = event.get("lat")
        lng = event.get("lng")

        # Обогащаем ТОЛЬКО если:
        # 1. Нет валидного названия из источника
        # 2. И текущий location_name пустой или generic
        # 3. И есть координаты
        needs_enrichment = (
            not has_valid_source_name
            and lat
            and lng
            and (
                not location_name_current
                or location_name_current in generic_venues
                or any(pattern in location_name_current.lower() for pattern in time_patterns)
            )
        )

        if needs_enrichment:
            try:
                from utils.geo_utils import reverse_geocode

                reverse_name = await reverse_geocode(lat, lng)
                if reverse_name:
                    # Проверяем, что reverse geocoding не вернул адрес (улицу)
                    # Адреса обычно начинаются с "Jl.", содержат "No." или слишком длинные
                    is_address = (
                        reverse_name.startswith(("Jl.", "ул.", "Street", "st.", "avenue"))
                        or "No." in reverse_name
                        or len(reverse_name) > 50  # Слишком длинное для названия места
                    )

                    if not is_address:
                        event["location_name"] = reverse_name
                        logger.info(
                            f"✅ Обогащено через reverse geocoding: location_name={reverse_name} для события '{event.get('title', 'Без названия')[:30]}'"
                        )
                    else:
                        logger.debug(f"⚠️ Reverse geocoding вернул адрес, пропускаем: {reverse_name}")
            except Exception as e:
                logger.debug(f"⚠️ Ошибка reverse geocoding: {e}")

        return event

    # Выполняем обогащение параллельно для всех событий (быстрее чем последовательно)
    import asyncio

    logger.info(f"🔄 Начинаем обогащение {len(events)} событий через reverse geocoding")
    enriched_events = await asyncio.gather(*[enrich_single_event(event) for event in events])

    # Логируем результаты обогащения
    enriched_count = sum(
        1 for e in enriched_events if e.get("location_name") and e.get("location_name") not in generic_venues
    )
    logger.info(f"✅ Обогащение завершено: {enriched_count} из {len(events)} событий получили location_name")

    return list(enriched_events)


def render_page(
    events: list[dict],
    page: int,
    page_size: int = 8,
    user_id: int = None,
    is_caption: bool = False,
    first_page_was_photo: bool = False,
) -> tuple[str, int]:
    """
    Рендерит страницу событий
    events — уже отфильтрованные prepared (publishable) и отсортированные по distance/time
    page    — 1..N
    is_caption — если True, обрезаем описания более агрессивно (для caption с лимитом 1024 байта)
    return: (html_text, total_pages)
    """
    import logging

    logger = logging.getLogger(__name__)

    if not events:
        return "Поблизости пока ничего не нашли.", 1

    # ВАЖНО: Правильный расчет total_pages с учетом смешанного размера страниц
    # Первая страница (с картой) имеет page_size=1, остальные - page_size=8
    # Если page_size=1 (первая страница с картой), то total_pages рассчитывается так:
    # - Первая страница: 1 событие
    # - Остальные страницы: по 8 событий
    if page_size == 1:
        # Первая страница с картой: 1 событие на первой странице, остальные по 8
        if len(events) <= 1:
            total_pages = 1
        else:
            # 1 событие на первой странице + остальные по 8
            total_pages = 1 + ceil((len(events) - 1) / 8)
    else:
        # Обычные страницы: все по page_size
        total_pages = max(1, ceil(len(events) / page_size))

    page = max(1, min(page, total_pages))

    # Правильный расчет start/end с учетом смешанного размера страниц
    if page == 1:
        if page_size == 1:
            # Первая страница с картой: только первое событие
            start = 0
            end = 1
        else:
            # Первая страница без карты: обычная логика
            start = 0
            end = page_size
    else:
        # Страницы 2+: учитываем, была ли первая страница с картой
        if first_page_was_photo:
            # Первая страница была с картой (1 событие), остальные по 8
            start = 1 + (page - 2) * 8
            end = start + 8
        else:
            # Обычная пагинация: все страницы по page_size
            start = (page - 1) * page_size
            end = start + page_size

    parts = []
    for idx, e in enumerate(events[start:end], start=start + 1):
        logger.info(f"🕐 render_page: событие {idx} - starts_at={e.get('starts_at')}, title={e.get('title')}")
        try:
            # Для caption (первая страница с картой) обрезаем описания более агрессивно
            html = render_event_html(e, idx, user_id, is_caption=is_caption)
            parts.append(html)
        except Exception as e_render:
            logger.error(f"❌ Ошибка рендеринга события {idx}: {e_render}")
            # Fallback для одного события
            title = e.get("title", "Без названия")
            parts.append(f"{idx}) {title}")

    return "\n".join(parts).strip(), total_pages


def kb_pager(page: int, total: int, current_radius: int = None, date_filter: str = "today") -> InlineKeyboardMarkup:
    """Создает клавиатуру пагинации с кнопками расширения радиуса и фильтрации даты"""
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

    # Добавляем кнопки фильтрации даты (Сегодня/Завтра)
    if date_filter == "today":
        buttons.append(
            [
                InlineKeyboardButton(text="📅 Сегодня ✅", callback_data="date_filter:today"),
                InlineKeyboardButton(text="📅 Завтра", callback_data="date_filter:tomorrow"),
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(text="📅 Сегодня", callback_data="date_filter:today"),
                InlineKeyboardButton(text="📅 Завтра ✅", callback_data="date_filter:tomorrow"),
            ]
        )

    # Добавляем кнопки расширения радиуса, используя фиксированные RADIUS_OPTIONS
    if current_radius is None:
        current_radius = int(settings.default_radius_km)

    # Добавляем кнопки изменения радиуса
    buttons.extend(build_radius_inline_buttons(current_radius))

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
# ВАЖНО: Очищаем старые записи для предотвращения утечек памяти
user_state = {}
_user_state_timestamps = {}  # Время последнего использования для каждого chat_id
USER_STATE_MAX_SIZE = 500  # Максимальное количество пользователей в памяти (уменьшено для экономии памяти)
USER_STATE_TTL_SECONDS = 1800  # Время жизни состояния: 30 минут (уменьшено для более агрессивной очистки)


def cleanup_user_state():
    """Очищает старые записи из user_state для предотвращения утечек памяти"""
    global user_state, _user_state_timestamps
    current_time = time.time()
    expired_chat_ids = []

    # Находим устаревшие записи
    for chat_id, timestamp in _user_state_timestamps.items():
        if current_time - timestamp > USER_STATE_TTL_SECONDS:
            expired_chat_ids.append(chat_id)

    # Удаляем устаревшие записи
    for chat_id in expired_chat_ids:
        user_state.pop(chat_id, None)
        _user_state_timestamps.pop(chat_id, None)

    # Если все еще слишком много записей, удаляем самые старые
    if len(user_state) > USER_STATE_MAX_SIZE:
        # Сортируем по времени последнего использования
        sorted_chats = sorted(_user_state_timestamps.items(), key=lambda x: x[1])
        # Удаляем самые старые
        to_remove = len(user_state) - USER_STATE_MAX_SIZE
        for chat_id, _ in sorted_chats[:to_remove]:
            user_state.pop(chat_id, None)
            _user_state_timestamps.pop(chat_id, None)

    if expired_chat_ids or len(user_state) > USER_STATE_MAX_SIZE:
        logger.debug(
            f"🧹 Очистка user_state: удалено {len(expired_chat_ids)} устаревших, осталось {len(user_state)} записей"
        )


def update_user_state_timestamp(chat_id: int):
    """Обновляет время последнего использования для chat_id"""
    _user_state_timestamps[chat_id] = time.time()
    # Периодически очищаем старые записи (каждые 100 обновлений)
    if len(_user_state_timestamps) % 100 == 0:
        cleanup_user_state()


def cleanup_large_prepared_events():
    """Очищает большие списки prepared_events из user_state для экономии памяти"""
    global user_state
    MAX_PREPARED_EVENTS = 50  # Максимальное количество событий в prepared

    for chat_id, state in list(user_state.items()):
        if "prepared" in state and isinstance(state["prepared"], list):
            if len(state["prepared"]) > MAX_PREPARED_EVENTS:
                # Оставляем только последние MAX_PREPARED_EVENTS событий
                original_count = len(state["prepared"])
                state["prepared"] = state["prepared"][-MAX_PREPARED_EVENTS:]
                logger.debug(
                    f"🧹 Очищены prepared_events для chat_id {chat_id}: "
                    f"оставлено {MAX_PREPARED_EVENTS} из {original_count}"
                )


async def periodic_cleanup_user_state():
    """Периодическая очистка user_state каждые 15 минут (более агрессивная очистка)"""
    while True:
        await asyncio.sleep(900)  # 15 минут (уменьшено для более частой очистки)
        try:
            cleanup_user_state()
            # Также очищаем большие prepared_events списки для экономии памяти
            cleanup_large_prepared_events()
            logger.debug("🧹 Периодическая очистка user_state выполнена")
        except Exception as e:
            logger.error(f"Ошибка при периодической очистке user_state: {e}")


# ---------- Радиус поиска ----------
RADIUS_OPTIONS = (5, 10, 15, 20)
CB_RADIUS_PREFIX = "rx:"  # callback_data вроде "rx:10"
RADIUS_KEY = "radius_km"

TEST_LOCATIONS = {
    "moscow_center": {
        "lat": 55.751244,
        "lng": 37.618423,
        "label": "Москва · Красная площадь",
    },
    "spb_center": {
        "lat": 59.93863,
        "lng": 30.31413,
        "label": "Санкт-Петербург · Невский проспект",
    },
    "bali_canggu": {
        "lat": -8.647817,
        "lng": 115.138519,
        "label": "Бали · Чангу",
    },
}


def build_radius_inline_buttons(current_radius: int) -> list[list[InlineKeyboardButton]]:
    """Формирует список кнопок для изменения радиуса поиска."""
    buttons_row = []
    for radius_option in RADIUS_OPTIONS:
        if radius_option == current_radius:
            continue
        buttons_row.append(
            InlineKeyboardButton(
                text=f"{radius_option} км",
                callback_data=f"{CB_RADIUS_PREFIX}{radius_option}",
            )
        )
    return [buttons_row] if buttons_row else []


def build_test_locations_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с предустановленными тестовыми локациями для админов."""
    buttons = [
        [
            InlineKeyboardButton(
                text="🇷🇺 Москва (тест)",
                callback_data="test_location:moscow_center",
            )
        ],
        [
            InlineKeyboardButton(
                text="🇷🇺 Санкт-Петербург (тест)",
                callback_data="test_location:spb_center",
            )
        ],
        [
            InlineKeyboardButton(
                text="🇮🇩 Бали (тест)",
                callback_data="test_location:bali_canggu",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def perform_nearby_search(
    message: types.Message,
    state: FSMContext,
    lat: float,
    lng: float,
    source: str,
) -> None:
    """Универсальный обработчик поиска событий рядом по координатам."""
    user_id = message.from_user.id
    logger.info(f"📍 perform_nearby_search: user_id={user_id}, lat={lat}, lng={lng}, source={source}")

    loading_message = await message.answer(
        "🔍 Ищу события рядом...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍", callback_data="loading")]]),
    )

    try:
        radius = get_user_radius(user_id, settings.default_radius_km)
        with get_session() as session:
            user_row = session.get(User, user_id)
            if user_row:
                user_row.last_lat = lat
                user_row.last_lng = lng
                user_row.last_geo_at_utc = datetime.now(UTC)
                try:
                    tz_name = await get_timezone(lat, lng)
                    if tz_name:
                        user_row.user_tz = tz_name
                        logger.info(f"🕒 Timezone обновлен для пользователя {user_id}: {tz_name}")
                    else:
                        logger.warning(f"⚠️ Не удалось получить timezone для координат ({lat}, {lng})")
                except Exception as e:
                    logger.error(f"❌ Ошибка при получении timezone: {e}")
                session.commit()

        logger.info(f"🔎 Поиск с координатами=({lat}, {lng}) радиус={radius}км источник={source}")

        try:
            from database import get_engine
            from utils.simple_timezone import get_city_from_coordinates

            engine = get_engine()
            events_service = UnifiedEventsService(engine)

            city = get_city_from_coordinates(lat, lng)
            if not city:
                logger.info(f"ℹ️ Регион не определен по координатам ({lat}, {lng}), используем UTC для временных границ")

            logger.info(
                f"🌍 Поиск событий: координаты=({lat}, {lng}), радиус={radius}км, регион для временных границ={city}"
            )

            events = events_service.search_events_today(city=city, user_lat=lat, user_lng=lng, radius_km=int(radius))

            formatted_events = []
            logger.info(f"🕐 Получили {len(events)} событий из UnifiedEventsService")
            for event in events:
                formatted_event = {
                    "id": event.get("id"),
                    "title": event["title"],
                    "description": event["description"],
                    "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
                    "starts_at": event["starts_at"],
                    "city": event.get("city"),
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

            events = sort_events_by_time(formatted_events)
            logger.info("📅 События отсортированы по времени")
        except Exception:
            logger.exception("❌ Ошибка при поиске событий")
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

        try:
            prepared, diag = prepare_events_for_feed(
                events, user_point=(lat, lng), radius_km=int(radius), with_diag=True
            )

            for event in prepared:
                enrich_venue_name(event)

            groups = group_by_type(prepared)
            counts = make_counts(groups)

            if not prepared:
                logger.info("📭 События не найдены после фильтрации")
                current_radius = int(radius)

                # Получаем date_filter из состояния пользователя (по умолчанию "today")
                date_filter_state = user_state.get(message.chat.id, {}).get("date_filter", "today")

                keyboard_buttons = []

                # Добавляем кнопки фильтрации даты (Сегодня/Завтра)
                if date_filter_state == "today":
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(text="📅 Сегодня ✅", callback_data="date_filter:today"),
                            InlineKeyboardButton(text="📅 Завтра", callback_data="date_filter:tomorrow"),
                        ]
                    )
                else:
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(text="📅 Сегодня", callback_data="date_filter:today"),
                            InlineKeyboardButton(text="📅 Завтра ✅", callback_data="date_filter:tomorrow"),
                        ]
                    )

                # Добавляем кнопки радиуса
                keyboard_buttons.extend(build_radius_inline_buttons(current_radius))

                # Добавляем кнопку создания события
                keyboard_buttons.append([InlineKeyboardButton(text="➕ Создать событие", callback_data="create_event")])
                inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

                try:
                    await loading_message.delete()
                except Exception:
                    pass

                region = "bali"
                if 55.0 <= lat <= 60.0 and 35.0 <= lng <= 40.0:
                    region = "moscow"
                elif 59.0 <= lat <= 60.5 and 29.0 <= lng <= 31.0:
                    region = "spb"
                elif -9.0 <= lat <= -8.0 and 114.0 <= lng <= 116.0:
                    region = "bali"

                user_state[message.chat.id] = {
                    "prepared": [],
                    "counts": {},
                    "lat": lat,
                    "lng": lng,
                    "radius": current_radius,
                    "page": 1,
                    "date_filter": date_filter_state,
                    "diag": diag,
                    "region": region,
                }

                higher_options = [r for r in RADIUS_OPTIONS if r > current_radius]
                suggested_radius = (
                    higher_options[0]
                    if higher_options
                    else next((r for r in RADIUS_OPTIONS if r < current_radius), current_radius)
                )
                suggestion_line = (
                    f"💡 Попробуй изменить радиус до {suggested_radius} км\n"
                    if suggested_radius != current_radius
                    else "💡 Попробуй изменить радиус и повторить поиск\n"
                )

                # Формируем текст сообщения в зависимости от фильтра даты
                date_text = "на сегодня" if date_filter_state == "today" else "на завтра"

                await message.answer(
                    f"📅 В радиусе {current_radius} км событий {date_text} не найдено.\n\n"
                    f"{suggestion_line}"
                    f"➕ Или создай своё событие и собери свою компанию!",
                    reply_markup=inline_kb,
                )

                await send_spinning_menu(message)
                await state.clear()
                return

            update_user_state_timestamp(message.chat.id)
            user_state[message.chat.id] = {
                "prepared": prepared,
                "counts": counts,
                "lat": lat,
                "lng": lng,
                "radius": int(radius),
                "page": 1,
                "date_filter": "today",
                "diag": diag,
            }

            header_html = render_header(counts, radius_km=int(radius))
            prepared = await enrich_events_with_reverse_geocoding(prepared)
            # Обновлено: теперь показываем 8 событий (карта отдельно)
            page_html, _ = render_page(prepared, page=1, page_size=8, user_id=user_id)
            short_caption = header_html + "\n\n" + page_html
            if len(prepared) > 8:
                short_caption += f"\n\n... и еще {len(prepared) - 8} событий"

            if counts["all"] < 5:
                next_radius = next(iter([r for r in RADIUS_OPTIONS if r > int(radius) and r != 5]), 20)
                short_caption += f"\n🔍 <i>Можно расширить поиск до {next_radius} км</i>"

            points = []
            for i, event in enumerate(prepared[:12], 1):
                event_lat = event.get("lat")
                event_lng = event.get("lng")
                if event_lat is not None and event_lng is not None:
                    if -90 <= event_lat <= 90 and -180 <= event_lng <= 180:
                        points.append((str(i), event_lat, event_lng))

            map_bytes = None
            if settings.google_maps_api_key and points:
                event_points = [(p[1], p[2]) for p in points]
                map_bytes = await fetch_static_map(
                    build_static_map_url(lat, lng, event_points, settings.google_maps_api_key)
                )

            try:
                await loading_message.delete()
            except Exception:
                pass

            engine = get_engine()
            participation_analytics = UserParticipationAnalytics(engine)

            group_chat_id = None
            if message.chat.type != "private":
                group_chat_id = message.chat.id

            shown_events = prepared[:5]
            for event in shown_events:
                event_id = event.get("id")
                if not event_id:
                    logger.warning(f"⚠️ У события нет id для логирования: {event.get('title', 'Без названия')[:30]}")
                    continue

                logger.info(
                    f"📊 Логируем list_view: user_id={user_id}, event_id={event_id}, group_chat_id={group_chat_id}"
                )
                participation_analytics.record_list_view(
                    user_id=user_id,
                    event_id=event_id,
                    group_chat_id=group_chat_id,
                )

            total_pages = max(1, ceil(len(prepared) / 8))
            date_filter_state = user_state.get(message.chat.id, {}).get("date_filter", "today")
            combined_keyboard = kb_pager(1, total_pages, int(radius), date_filter=date_filter_state)

            # ИСПРАВЛЕНИЕ: Отправляем карту и список событий отдельными сообщениями
            if map_bytes:
                # Отправляем карту отдельным сообщением
                map_file = BufferedInputFile(map_bytes, filename="map.jpg")
                map_caption = "📍 Карта событий"  # Единая подпись без указания радиуса
                map_message = await message.answer_photo(
                    map_file,
                    caption=map_caption,
                    parse_mode="HTML",
                )
                logger.info("✅ Карта отправлена отдельным сообщением (send_compact_events_list)")

                # Сохраняем message_id карты в состоянии для последующего редактирования
                if message.chat.id in user_state:
                    update_user_state_timestamp(message.chat.id)
                    user_state[message.chat.id]["map_message_id"] = map_message.message_id

                # Отправляем список событий отдельным текстовым сообщением
                list_message = await message.answer(
                    short_caption,
                    parse_mode="HTML",
                    reply_markup=combined_keyboard,
                )
                logger.info("✅ Список событий отправлен отдельным сообщением (send_compact_events_list)")

                # Сохраняем message_id списка событий в состоянии для последующего редактирования
                if message.chat.id in user_state:
                    update_user_state_timestamp(message.chat.id)
                    user_state[message.chat.id]["list_message_id"] = list_message.message_id
            else:
                await message.answer(
                    short_caption,
                    parse_mode="HTML",
                    reply_markup=combined_keyboard,
                )

            await send_spinning_menu(message)
        finally:
            await state.clear()
    finally:
        try:
            await loading_message.delete()
        except Exception:
            pass


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

# Кеш для bot_info (не меняется часто, можно кешировать)
_bot_info_cache: types.User | None = None

# === MIDDLEWARE ДЛЯ СЕССИЙ ===
from collections.abc import Awaitable, Callable  # noqa: E402
from typing import Any  # noqa: E402

from aiogram import BaseMiddleware  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402


class DuplicateCallbackMiddleware(BaseMiddleware):
    """Middleware для защиты от дублирования обработки callback_query"""

    def __init__(self):
        # Храним обработанные callback_query ID (очищаем старые периодически)
        self._processed_callbacks: set[str] = set()
        self._max_size = 10000  # Максимальное количество хранимых ID

    async def __call__(
        self, handler: Callable[[Any, dict[str, Any]], Awaitable[Any]], event: Any, data: dict[str, Any]
    ) -> Any:
        # Проверяем только callback_query
        if isinstance(event, types.CallbackQuery):
            callback_id = event.id
            if callback_id in self._processed_callbacks:
                # Этот callback уже обработан - игнорируем
                logger.warning(f"⚠️ Дублирование callback_query {callback_id}, пропускаем")
                try:
                    await event.answer("⏳ Уже обрабатывается...", show_alert=False)
                except Exception:
                    pass  # Игнорируем ошибки ответа
                return  # Прерываем обработку

            # Помечаем как обработанный
            self._processed_callbacks.add(callback_id)

            # Очищаем старые записи, если слишком много (более эффективно)
            if len(self._processed_callbacks) > self._max_size:
                # Удаляем первые 5000 элементов (старые записи)
                # Используем более эффективный способ без создания списка
                items_to_remove = list(self._processed_callbacks)[:5000]
                for item in items_to_remove:
                    self._processed_callbacks.discard(item)

        return await handler(event, data)


class BanCheckMiddleware(BaseMiddleware):
    """Middleware для проверки бана пользователей"""

    async def __call__(
        self, handler: Callable[[Any, dict[str, Any]], Awaitable[Any]], event: Any, data: dict[str, Any]
    ) -> Any:
        # Получаем user_id из события
        user_id = None
        if hasattr(event, "from_user") and event.from_user:
            user_id = event.from_user.id
        elif hasattr(event, "message") and event.message and event.message.from_user:
            user_id = event.message.from_user.id

        # Проверяем бан только для обычных пользователей (не админов)
        if user_id:
            from config import load_settings

            settings = load_settings()
            # Админы не проверяются на бан
            if user_id not in settings.admin_ids:
                from database import get_engine
                from utils.ban_service import BanService

                engine = get_engine()
                ban_service = BanService(engine)
                if ban_service.is_banned(user_id):
                    # Пользователь забанен - не обрабатываем сообщение
                    logger.info(f"🚫 Забаненный пользователь {user_id} попытался использовать бота")
                    # Пытаемся отправить сообщение (если это возможно)
                    try:
                        if hasattr(event, "answer"):
                            await event.answer("🚫 Вы заблокированы в этом боте")
                        elif hasattr(event, "message") and event.message:
                            await event.message.answer("🚫 Вы заблокированы в этом боте")
                    except Exception:
                        pass  # Игнорируем ошибки отправки
                    return  # Прерываем обработку

        return await handler(event, data)


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_maker: async_sessionmaker):
        self.session_maker = session_maker

    async def __call__(
        self, handler: Callable[[Any, dict[str, Any]], Awaitable[Any]], event: Any, data: dict[str, Any]
    ) -> Any:
        async with self.session_maker() as session:
            data["session"] = session
            return await handler(event, data)


# Подключаем middleware для всех типов событий (если доступен async_session_maker)
from database import async_session_maker  # noqa: E402

# Подключаем middleware для проверки бана (должен быть первым)
# Защита от дублирования callback_query (должен быть первым)
duplicate_callback_middleware = DuplicateCallbackMiddleware()
dp.update.middleware(duplicate_callback_middleware)
dp.callback_query.middleware(duplicate_callback_middleware)

# Проверка бана пользователей
dp.update.middleware(BanCheckMiddleware())
dp.message.middleware(BanCheckMiddleware())
dp.callback_query.middleware(BanCheckMiddleware())
logging.info("✅ Ban check middleware подключен")

if async_session_maker is not None:
    dp.update.middleware(DbSessionMiddleware(async_session_maker))
    dp.message.middleware(DbSessionMiddleware(async_session_maker))
    dp.callback_query.middleware(DbSessionMiddleware(async_session_maker))
    logging.info("✅ Async session middleware подключен")
else:
    # Для тестов создаем заглушку middleware
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CI"):
        logging.warning("⚠️ Тестовый режим - создаем заглушку middleware")

        class MockSessionMiddleware(BaseMiddleware):
            async def __call__(
                self, handler: Callable[[Any, dict[str, Any]], Awaitable[Any]], event: Any, data: dict[str, Any]
            ) -> Any:
                # Для тестов передаем None как session
                data["session"] = None
                return await handler(event, data)

        dp.update.middleware(MockSessionMiddleware())
        dp.message.middleware(MockSessionMiddleware())
        dp.callback_query.middleware(MockSessionMiddleware())
        logging.info("✅ Mock session middleware подключен (для тестов)")
    else:
        logging.error("❌ Async session middleware недоступен - требуется PostgreSQL и asyncpg")
        raise RuntimeError("PostgreSQL и asyncpg обязательны для работы бота")

# BOT_ID для корректной фильтрации в групповых чатах
BOT_ID: int = None

# === СОЗДАНИЕ ОСНОВНОГО РОУТЕРА С ФИЛЬТРОМ ===
# Основной роутер работает ТОЛЬКО в приватных чатах
from aiogram import Router  # noqa: E402

main_router = Router()
main_router.message.filter(F.chat.type == "private")
main_router.callback_query.filter(F.message.chat.type == "private")

# === ПОДКЛЮЧЕНИЕ ИЗОЛИРОВАННОГО ГРУППОВОГО РОУТЕРА ===
# Импортируем роутер для групп (полностью изолирован от основного бота)
from debug_test_router import diag_router  # noqa: E402
from diagnostic_router import diag  # noqa: E402
from group_router import group_router  # noqa: E402


# Middleware для логирования всех обновлений (для отладки MacBook)
@dp.update.outer_middleware()
async def log_location_updates_middleware(handler, event, data):
    """Middleware для логирования всех обновлений с геолокацией и всех message обновлений"""
    # Логируем все message обновления для отладки
    if hasattr(event, "message") and event.message:
        user_id = event.message.from_user.id if event.message.from_user else None
        message_type = "unknown"
        if event.message.location:
            message_type = "location"
            lat = event.message.location.latitude
            lng = event.message.location.longitude
            logger.info(
                f"📍 [MIDDLEWARE] Обнаружена геолокация в update: user_id={user_id}, lat={lat}, lng={lng}, message_id={event.message.message_id}"
            )
        elif event.message.text:
            message_type = "text"
            logger.info(
                f"📍 [MIDDLEWARE] Обнаружено текстовое сообщение: user_id={user_id}, text={event.message.text[:50]}, message_id={event.message.message_id}"
            )
        elif event.message.photo:
            message_type = "photo"
            logger.info(f"📍 [MIDDLEWARE] Обнаружено фото: user_id={user_id}, message_id={event.message.message_id}")
        else:
            # Логируем все остальные типы сообщений
            content_type = getattr(event.message, "content_type", "unknown")
            logger.info(
                f"📍 [MIDDLEWARE] Обнаружено сообщение типа {message_type}: user_id={user_id}, message_id={event.message.message_id}, content_type={content_type}"
            )

    return await handler(event, data)


dp.include_router(group_router)  # Групповой роутер (только группы) - ПЕРВЫМ!
dp.include_router(diag_router)  # Временный роутер для диагностики
dp.include_router(diag)  # Диагностические команды для трекинга
dp.include_router(main_router)  # Основной роутер (только приватные чаты) - ПОСЛЕДНИМ!


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
    waiting_for_location_type = State()  # Выбор типа локации (ссылка/карта/координаты)
    waiting_for_location_url = State()  # Ссылка на место
    waiting_for_description = State()
    confirmation = State()


class CommunityEventEditing(StatesGroup):
    """FSM состояния для редактирования Community событий в приватном чате"""

    choosing_field = State()
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_location = State()
    waiting_for_description = State()


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
                # Для даты/времени нужно парсить и правильно конвертировать в UTC
                try:
                    import pytz

                    from utils.simple_timezone import get_city_timezone

                    # Получаем часовой пояс пользователя
                    user = session.query(User).filter(User.id == user_id).first()
                    user_tz_name = user.user_tz if user and user.user_tz else "Asia/Makassar"  # По умолчанию Бали

                    # Если у события есть координаты, определяем часовой пояс по городу
                    if event.lat and event.lng:
                        from utils.simple_timezone import get_city_from_coordinates

                        city = get_city_from_coordinates(event.lat, event.lng)
                        if city:
                            tz_name = get_city_timezone(city)
                        else:
                            tz_name = user_tz_name
                    else:
                        tz_name = user_tz_name

                    tz = pytz.timezone(tz_name)

                    if " " in value:
                        # Полная дата и время - парсим как локальное время
                        naive_dt = datetime.strptime(value, "%d.%m.%Y %H:%M")
                        # Локализуем время и конвертируем в UTC
                        local_dt = tz.localize(naive_dt)
                        event.starts_at = local_dt.astimezone(pytz.UTC)
                    else:
                        # Только дата - сохраняем существующее время
                        new_date = datetime.strptime(value, "%d.%m.%Y")
                        if event.starts_at:
                            # Сохраняем существующее время, но конвертируем правильно
                            existing_time = event.starts_at.astimezone(tz).time()
                            naive_dt = new_date.replace(
                                hour=existing_time.hour, minute=existing_time.minute, second=existing_time.second
                            )
                            local_dt = tz.localize(naive_dt)
                            event.starts_at = local_dt.astimezone(pytz.UTC)
                        else:
                            # Если времени не было, устанавливаем 00:00
                            naive_dt = new_date.replace(hour=0, minute=0, second=0)
                            local_dt = tz.localize(naive_dt)
                            event.starts_at = local_dt.astimezone(pytz.UTC)

                    logging.info(
                        f"Обновлена дата события {event_id}: '{value}' (локальное время {tz_name}) → {event.starts_at} UTC"
                    )
                except ValueError as ve:
                    logging.error(f"Ошибка парсинга даты '{value}': {ve}")
                    return False
                except Exception as e:
                    logging.error(f"Ошибка конвертации времени для события {event_id}: {e}")
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


def human_when(event: dict, region: str = None, user_id: int = None) -> str:
    """Возвращает время в формате 'HH:MM' в локальном времени события (определяется по координатам события)"""
    from datetime import datetime

    import pytz

    from utils.simple_timezone import get_city_from_coordinates, get_city_timezone

    dt_utc = event.get("starts_at") or event.get("start_time")
    if not dt_utc:
        return ""

    if isinstance(dt_utc, str):
        try:
            dt_utc = datetime.fromisoformat(dt_utc.replace("Z", "+00:00"))
        except Exception:
            return ""

    try:
        # Определяем timezone события
        # Приоритет: 1) city из события (если это известный город), 2) координаты, 3) region, 4) UTC
        event_tz = "UTC"

        # 1. Используем city из события (если это известный город)
        event_city = event.get("city")
        if event_city:
            # Проверяем, что это известный город, а не название заведения
            known_cities = ["bali", "moscow", "spb", "jakarta"]
            if event_city.lower() in known_cities:
                event_tz = get_city_timezone(event_city)

        # 2. Если timezone еще не определен, определяем по координатам события
        if event_tz == "UTC" and event.get("lat") and event.get("lng"):
            city = get_city_from_coordinates(event["lat"], event["lng"])
            if city:
                event_tz = get_city_timezone(city)

        # 3. Fallback на регион (если передан)
        if event_tz == "UTC" and region:
            region_tz_map = {
                "bali": "Asia/Makassar",
                "moscow": "Europe/Moscow",
                "spb": "Europe/Moscow",
                "jakarta": "Asia/Jakarta",
            }
            event_tz = region_tz_map.get(region, "UTC")

        # Конвертируем время в часовой пояс события
        utc = pytz.UTC
        event_timezone = pytz.timezone(event_tz)

        if dt_utc.tzinfo is None:
            dt_utc = utc.localize(dt_utc)

        local_time = dt_utc.astimezone(event_timezone)

        if not (local_time.hour == 0 and local_time.minute == 0):
            return local_time.strftime("%H:%M")
        return ""
    except Exception:
        return ""


def format_event_time(starts_at, event_tz="UTC") -> str:
    """
    Форматирует время события для отображения в timezone события

    Args:
        starts_at: Время события (datetime в UTC или naive)
        event_tz: Timezone события в формате IANA (например, "Europe/Madrid")
                   Определяется по координатам события
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.info(f"🕐 format_event_time: starts_at={starts_at}, type={type(starts_at)}, event_tz={event_tz}")

    if not starts_at:
        logger.info("🕐 starts_at пустое, возвращаем 'время уточняется'")
        return "время уточняется"

    try:
        from datetime import datetime

        # Если starts_at это строка, парсим её
        if isinstance(starts_at, str):
            # Пробуем разные форматы
            try:
                starts_at = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return "время уточняется"

        # Конвертируем в timezone события
        import pytz

        utc = pytz.UTC
        event_timezone = pytz.timezone(event_tz)

        if starts_at.tzinfo is None:
            starts_at = utc.localize(starts_at)

        local_time = starts_at.astimezone(event_timezone)

        # Форматируем красиво
        now = datetime.now(event_timezone)
        today = now.date()

        if local_time.date() == today:
            # Сегодня - показываем только время
            return f"сегодня в {local_time.strftime('%H:%M')}"
        else:
            # Другой день - показываем дату и время
            return f"{local_time.strftime('%d.%m в %H:%M')}"

    except Exception as e:
        logger.error(f"❌ Ошибка форматирования времени: {e}")
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
        [KeyboardButton(text="🎯 Чем заняться"), KeyboardButton(text="🏆 Мои квесты")],
        [KeyboardButton(text="🔗 Добавить бота в чат"), KeyboardButton(text="📋 Мои события")],
        [KeyboardButton(text="🚀 Старт")],
    ]

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


async def setup_bot_commands():
    """ЭТАЛОН: Устанавливает команды бота для всех языков и скоупов"""
    try:
        from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeDefault

        # Команды для групповых чатов - только /start в режиме Community
        group_commands = [
            types.BotCommand(command="start", description="🎉 События чата"),
        ]

        # Публичные команды для личных чатов (полный набор)
        public_commands = [
            types.BotCommand(command="start", description="🚀 Запустить бота и показать меню"),
            types.BotCommand(command="nearby", description="📍 Что рядом - найти события поблизости"),
            types.BotCommand(command="create", description="➕ Создать новое событие"),
            types.BotCommand(command="myevents", description="📋 Мои события - просмотр созданных событий"),
            types.BotCommand(command="tasks", description="🎯 Чем заняться - найти задания поблизости"),
            types.BotCommand(command="mytasks", description="🏆 Мои квесты - просмотр выполненных заданий"),
            types.BotCommand(command="share", description="🔗 Добавить бота в чат"),
            types.BotCommand(command="help", description="💬 Написать отзыв Разработчику"),
        ]

        # Сначала очищаем все команды, чтобы избежать конфликтов
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
        await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())

        # Очищаем команды для всех локалей
        for lang in ["ru", "en"]:
            await bot.delete_my_commands(scope=BotCommandScopeDefault(), language_code=lang)
            await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats(), language_code=lang)
            await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats(), language_code=lang)

        # Ждем немного, чтобы Telegram обработал удаление
        import asyncio

        await asyncio.sleep(1)

        # Устанавливаем команды для всех скоупов и языков
        scopes = [
            (BotCommandScopeDefault(), public_commands),
            (BotCommandScopeAllPrivateChats(), public_commands),
            (BotCommandScopeAllGroupChats(), group_commands),
        ]

        languages = [None, "ru", "en"]  # None = default, ru = русский, en = английский

        for scope, commands in scopes:
            for lang in languages:
                try:
                    await bot.set_my_commands(commands, scope=scope, language_code=lang)
                    logger.info(f"✅ Команды установлены: {scope.__class__.__name__} {lang or 'default'}")
                except Exception as e:
                    logger.error(f"❌ Ошибка установки команд {scope.__class__.__name__} {lang}: {e}")

        # Принудительно показываем меню команд в ЛС
        try:
            from aiogram.types import MenuButtonCommands

            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.info("✅ Menu Button установлен для принудительного показа команд")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось установить Menu Button: {e}")

        logger.info("✅ Команды бота установлены для всех языков и скоупов")

    except Exception as e:
        logger.error(f"❌ Ошибка установки команд бота: {e}")


async def ensure_group_commands(bot):
    """СТОРОЖ КОМАНД ДЛЯ ГРУПП: проверяет и восстанавливает команды в группах"""
    try:
        from contextlib import suppress

        from aiogram.types import BotCommandScopeAllGroupChats

        # Команды для групп - только /start в режиме Community
        GROUP_CMDS = [types.BotCommand(command="start", description="🎉 События чата")]
        LANGS = (None, "ru", "en")  # default + ru + en

        # Проверяем группы - есть ли /start
        ok = True
        for lang in LANGS:
            with suppress(Exception):
                cmds = await bot.get_my_commands(scope=BotCommandScopeAllGroupChats(), language_code=lang)
                if not any(c.command == "start" for c in cmds):
                    ok = False
                    logger.warning(f"❌ /start отсутствует в группах для языка {lang or 'default'}")
                    break

        if not ok:
            logger.warning("🔄 Восстанавливаем команды для групп...")
            for lang in LANGS:
                with suppress(Exception):
                    await bot.set_my_commands(GROUP_CMDS, scope=BotCommandScopeAllGroupChats(), language_code=lang)
            logger.info("✅ Команды для групп восстановлены")
        else:
            logger.info("✅ Команды для групп в порядке")

    except Exception as e:
        logger.error(f"❌ Ошибка сторожа команд для групп: {e}")


async def ensure_commands(bot):
    """СТОРОЖ КОМАНД: idempotent auto-heal - проверяет и восстанавливает команды"""
    try:
        from contextlib import suppress

        # Команды для групп - только /start в режиме Community
        GROUP_CMDS = [types.BotCommand(command="start", description="🎉 События чата")]

        # Команды для личных чатов - полный набор
        PRIVATE_CMDS = [
            types.BotCommand(command="start", description="🚀 Запустить бота и показать меню"),
            types.BotCommand(command="nearby", description="📍 Что рядом - найти события поблизости"),
            types.BotCommand(command="create", description="➕ Создать новое событие"),
            types.BotCommand(command="myevents", description="📋 Мои события - просмотр созданных событий"),
            types.BotCommand(command="tasks", description="🎯 Чем заняться - найти задания поблизости"),
            types.BotCommand(command="mytasks", description="🏆 Мои квесты - просмотр выполненных заданий"),
            types.BotCommand(command="share", description="🔗 Добавить бота в чат"),
            types.BotCommand(command="help", description="💬 Написать отзыв Разработчику"),
        ]

        LANGS = [None, "ru", "en"]  # расширяй при необходимости

        async def _set(scope, cmds):
            """Устанавливает команды для всех языков"""
            for lang in LANGS:
                with suppress(Exception):
                    await bot.set_my_commands(cmds, scope=scope, language_code=lang)

        # Проверяем группы - есть ли /start
        ok = True
        for lang in LANGS:
            with suppress(Exception):
                cmds = await bot.get_my_commands(scope=types.BotCommandScopeAllGroupChats(), language_code=lang)
                if not any(c.command == "start" for c in cmds):
                    ok = False
                    logger.warning(f"❌ /start отсутствует в группах для языка {lang or 'default'}")
                    break

        if not ok:
            logger.warning("🔄 Восстанавливаем команды...")
            await _set(types.BotCommandScopeDefault(), PRIVATE_CMDS)
            await _set(types.BotCommandScopeAllPrivateChats(), PRIVATE_CMDS)
            await _set(types.BotCommandScopeAllGroupChats(), GROUP_CMDS)
            logger.info("✅ Команды восстановлены")
        else:
            logger.info("✅ Команды в порядке")

        # Опционально лог-хелсчек
        with suppress(Exception):
            dump = []
            for scope in (
                types.BotCommandScopeDefault(),
                types.BotCommandScopeAllPrivateChats(),
                types.BotCommandScopeAllGroupChats(),
            ):
                for lang in LANGS:
                    c = await bot.get_my_commands(scope=scope, language_code=lang)
                    dump.append((scope.__class__.__name__, lang, [x.command for x in c]))
            logger.info(f"COMMANDS_HEALTH: {dump}")

    except Exception as e:
        logger.error(f"❌ Ошибка сторожа команд: {e}")


async def dump_commands_healthcheck(bot):
    """Runtime-healthcheck: проверяет команды по всем скоупам и языкам"""
    try:
        from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeDefault

        # Команды для групп - только /start в режиме Community
        group_commands = [
            types.BotCommand(command="start", description="🎉 События чата"),
        ]

        # Публичные команды для личных чатов (полный набор)
        public_commands = [
            types.BotCommand(command="start", description="🚀 Запустить бота и показать меню"),
            types.BotCommand(command="nearby", description="📍 Что рядом - найти события поблизости"),
            types.BotCommand(command="create", description="➕ Создать новое событие"),
            types.BotCommand(command="myevents", description="📋 Мои события - просмотр созданных событий"),
            types.BotCommand(command="tasks", description="🎯 Чем заняться - найти задания поблизости"),
            types.BotCommand(command="mytasks", description="🏆 Мои квесты - просмотр выполненных заданий"),
            types.BotCommand(command="share", description="🔗 Добавить бота в чат"),
            types.BotCommand(command="help", description="💬 Написать отзыв Разработчику"),
        ]

        scopes = [
            BotCommandScopeDefault(),
            BotCommandScopeAllPrivateChats(),
            BotCommandScopeAllGroupChats(),
        ]

        logger.info("🔍 HEALTHCHECK: Проверяем команды бота...")

        for lang in (None, "ru", "en"):
            for scope in scopes:
                try:
                    cmds = await bot.get_my_commands(scope=scope, language_code=lang)
                    scope_name = scope.__class__.__name__
                    lang_name = lang or "default"
                    cmd_list = [c.command for c in cmds]

                    logger.info(f"HEALTHCHECK: {scope_name} {lang_name} => {cmd_list}")

                    # Проверяем, что start есть (без слэша, т.к. cmd_list содержит только имена команд)
                    if "start" not in cmd_list:
                        logger.error(f"❌ КРИТИЧНО: /start отсутствует в {scope_name} {lang_name}!")
                        # Автоматически восстанавливаем команды
                        try:
                            if scope_name == "BotCommandScopeAllGroupChats":
                                restore_cmds = group_commands
                            else:
                                restore_cmds = public_commands
                            await bot.set_my_commands(restore_cmds, scope=scope, language_code=lang)
                            logger.info(f"🔄 Восстановлены команды для {scope_name} {lang_name}")
                        except Exception as restore_error:
                            logger.error(
                                f"❌ Не удалось восстановить команды для {scope_name} {lang_name}: {restore_error}"
                            )
                    else:
                        logger.info(f"✅ /start найден в {scope_name} {lang_name}")

                except Exception as e:
                    logger.error(f"❌ Ошибка проверки {scope.__class__.__name__} {lang}: {e}")

        logger.info("✅ HEALTHCHECK завершен")

    except Exception as e:
        logger.error(f"❌ Ошибка healthcheck команд: {e}")


async def periodic_commands_update():
    """СТОРОЖ КОМАНД: проверяет и восстанавливает команды каждые 15 минут"""
    while True:
        try:
            await asyncio.sleep(900)  # 15 минут
            logger.info("🔄 Сторож команд: проверяем состояние...")
            await ensure_commands(bot)
            await ensure_group_commands(bot)  # Дополнительная проверка для групп
            logger.info("✅ Сторож команд завершен")
        except Exception as e:
            logger.error(f"❌ Ошибка сторожа команд: {e}")
            await asyncio.sleep(300)  # При ошибке ждем 5 минут


def _ensure_user_exists_sync(user_id: int, tg_user) -> None:
    """Синхронная версия создания пользователя (для выполнения в отдельном потоке)"""
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


async def ensure_user_exists(user_id: int, tg_user) -> None:
    """Создаёт пользователя в БД если его нет (выполняется в отдельном потоке)"""
    await asyncio.to_thread(_ensure_user_exists_sync, user_id, tg_user)


def kb_radius(current: int | None = None) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора радиуса поиска с выделением текущего"""
    buttons = []
    for km in RADIUS_OPTIONS:
        label = f"{'✅ ' if km == current else ''}{km} км"
        buttons.append(InlineKeyboardButton(text=label, callback_data=f"{CB_RADIUS_PREFIX}{km}"))
    # одна строка из 4 кнопок
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


# Удалена старая функция radius_selection_kb() - используем только kb_radius()


@main_router.message(F.text == "🔧 Настройки радиуса")
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


async def get_bot_info_cached() -> types.User:
    """Получает информацию о боте с кешированием"""
    global _bot_info_cache
    if _bot_info_cache is None:
        _bot_info_cache = await bot.get_me()
    return _bot_info_cache


@main_router.message(Command("start"))
@main_router.message(F.text == "🚀 Старт")
async def cmd_start(message: types.Message, state: FSMContext, command: CommandObject = None):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    chat_type = message.chat.type

    # Проверяем, есть ли параметр group_ (deep-link из группы для создания)
    group_id = None
    if command and command.args and command.args.startswith("group_"):
        try:
            group_id = int(command.args.replace("group_", ""))
            logger.info(f"🔥 cmd_start: пользователь {user_id} перешёл из группы {group_id}")
        except ValueError:
            logger.warning(f"🔥 cmd_start: неверный параметр group_ {command.args}")

    # Проверяем, есть ли параметр edit_group_ (deep-link из группы для редактирования)
    edit_params = None
    if command and command.args and command.args.startswith("edit_group_"):
        try:
            # Формат: edit_group_{event_id}_{chat_id}
            parts = command.args.replace("edit_group_", "").split("_")
            if len(parts) == 2:
                event_id = int(parts[0])
                chat_id = int(parts[1])
                edit_params = {"event_id": event_id, "chat_id": chat_id}
                logger.info(
                    f"🔥 cmd_start: пользователь {user_id} перешёл для редактирования события {event_id} из группы {chat_id}"
                )
        except (ValueError, IndexError) as e:
            logger.warning(f"🔥 cmd_start: неверный параметр edit_group_ {command.args}: {e}")

    # Проверяем, есть ли параметр add_quest_ (deep-link для добавления места в квесты)
    # Оставляем поддержку deep link для обратной совместимости, но теперь используем callback
    if command and command.args and command.args.startswith("add_quest_"):
        try:
            place_id = int(command.args.replace("add_quest_", ""))
            logger.info(f"🎯 cmd_start: пользователь {user_id} добавляет место {place_id} в квесты через deep link")

            # Получаем координаты пользователя из БД
            with get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                user_lat = user.last_lat if user else None
                user_lng = user.last_lng if user else None

            # Создаем задание из места
            from tasks_service import create_task_from_place

            success, message_text = create_task_from_place(user_id, place_id, user_lat, user_lng)

            # Показываем сообщение с результатом
            await message.answer(message_text, reply_markup=main_menu_kb())
            return
        except (ValueError, Exception) as e:
            logger.warning(f"🎯 cmd_start: неверный параметр add_quest_ {command.args}: {e}")

    # Если это переход из группы для редактирования, запускаем FSM для редактирования
    if edit_params and chat_type == "private":
        await start_group_event_editing(message, edit_params["event_id"], edit_params["chat_id"], state)
        return

    # Если это переход из группы, запускаем FSM для создания группового события
    if group_id and chat_type == "private":
        await start_group_event_creation(message, group_id, state)
        return

    # Создаем пользователя если его нет (в фоне, не ждём)
    asyncio.create_task(ensure_user_exists(user_id, message.from_user))

    # Увеличиваем счетчик сессий (в фоне, не ждём)
    async def _update_analytics():
        from utils.user_analytics import UserAnalytics

        try:
            if chat_type == "private":
                UserAnalytics.increment_sessions_world(user_id)
            else:
                UserAnalytics.increment_sessions_community(user_id)
        except Exception:
            UserAnalytics.increment_sessions(user_id)

    asyncio.create_task(_update_analytics())

    logger.info(f"cmd_start: пользователь {user_id}")

    # Восстанавливаем команды бота в фоне (не ждём завершения)
    asyncio.create_task(setup_bot_commands())

    # Разная логика для личных и групповых чатов
    if chat_type == "private":
        # Упрощенная логика - всегда показываем полное меню
        welcome_text = (
            'Привет! @EventAroundBot версия "World" - твой цифровой помощник по активностям.\n\n'
            "📍 Что рядом: находи события в радиусе 5–20 км\n"
            "🎯 Чем заняться: автоматизированный подбор заданий с наградами 🚀\n\n"
            "➕ Создать: организуй встречи и приглашай друзей\n"
            '🔗 Добавить бота в чат: добавь бота версия "Community" в чат — появится лента встреч и планов только для участников сообщества.\n\n'
            "🚀 Начинай приключение"
        )
        await message.answer(welcome_text, reply_markup=main_menu_kb())
    else:
        # Групповой чат - упрощенный функционал для событий участников
        welcome_text = (
            '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
            "🎯 **В этом чате я помогаю:**\n"
            "• Создавать события участников чата\n"
            "• Показывать все события, созданные в этом чате\n"
            "• Переходить к полному боту для поиска по геолокации\n\n"
            "💡 **Выберите действие:**"
        )

        # Получаем username бота для создания ссылки (с кешированием)
        bot_info = await get_bot_info_cached()

        # Создаем inline кнопки для групповых чатов
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Создать событие", url=f"https://t.me/{bot_info.username}?start=group_{message.chat.id}"
                    )
                ],
                [InlineKeyboardButton(text="📋 События этого чата", callback_data="group_chat_events")],
                [InlineKeyboardButton(text='🚀 Расширенная версия "World"', url=f"https://t.me/{bot_info.username}")],
                [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_bot")],
            ]
        )

        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")


def get_community_cancel_kb() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой отмены для группового события"""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить создание", callback_data="community_cancel")]]
    )


async def start_group_event_creation(message: types.Message, group_id: int, state: FSMContext):
    """Запуск создания события для группы в ЛС"""
    logger.info(f"🔥 start_group_event_creation: запуск FSM для группы {group_id}, пользователь {message.from_user.id}")

    # Запускаем FSM для создания группового события
    await state.set_state(CommunityEventCreation.waiting_for_title)
    await state.update_data(group_id=group_id, creator_id=message.from_user.id, scope="group")

    welcome_text = (
        '➕ **Создать событие "Community"**\n\n'
        "- Это событие будет добавлено в группу, из которой вы перешли.\n\n"
        "👀 Видно только участникам вашего чата.\n\n"
        "**Введите название события:**"
    )

    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_community_cancel_kb())


async def start_group_event_editing(message: types.Message, event_id: int, chat_id: int, state: FSMContext):
    """Запуск редактирования Community события в ЛС"""
    from database import CommunityEvent, get_session

    logger.info(
        f"🔥 start_group_event_editing: запуск редактирования события {event_id} из группы {chat_id}, "
        f"пользователь {message.from_user.id}"
    )

    # Загружаем событие из БД (используем синхронную сессию для простоты)
    user_id = message.from_user.id
    try:
        with get_session() as session:
            event = (
                session.query(CommunityEvent)
                .filter(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
                .first()
            )

            if not event:
                await message.answer("❌ Событие не найдено")
                return

            # Проверяем права доступа
            can_edit = event.organizer_id == user_id
            if not can_edit:
                await message.answer("❌ У вас нет прав для редактирования этого события")
                return

            # Форматируем дату и время для отображения
            date_str = event.starts_at.strftime("%d.%m.%Y") if event.starts_at else "Не указано"
            time_str = event.starts_at.strftime("%H:%M") if event.starts_at else "Не указано"

            # Показываем информацию о событии и меню редактирования
            event_info = (
                f"✏️ **Редактирование события**\n\n"
                f"**Текущие данные:**\n"
                f"📌 Название: {event.title}\n"
                f"📅 Дата: {date_str}\n"
                f"⏰ Время: {time_str}\n"
                f"📍 Локация: {event.location_name or 'Не указано'}\n"
                f"📝 Описание: {event.description or 'Не указано'}\n\n"
                f"**Выберите, что хотите изменить:**"
            )

            # Создаем клавиатуру для редактирования
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📌 Название", callback_data=f"pm_edit_title_{event_id}_{chat_id}")],
                    [InlineKeyboardButton(text="📅 Дата", callback_data=f"pm_edit_date_{event_id}_{chat_id}")],
                    [InlineKeyboardButton(text="⏰ Время", callback_data=f"pm_edit_time_{event_id}_{chat_id}")],
                    [InlineKeyboardButton(text="📍 Локация", callback_data=f"pm_edit_location_{event_id}_{chat_id}")],
                    [
                        InlineKeyboardButton(
                            text="📝 Описание", callback_data=f"pm_edit_description_{event_id}_{chat_id}"
                        )
                    ],
                    [InlineKeyboardButton(text="✅ Завершить", callback_data=f"pm_edit_finish_{event_id}_{chat_id}")],
                ]
            )

            # Сохраняем данные в состоянии
            await state.update_data(
                event_id=event_id,
                chat_id=chat_id,
                editing_community_event=True,
                original_title=event.title,
                original_date=date_str,
                original_time=time_str,
                original_location=event.location_name,
                original_description=event.description,
                edit_menu_msg_id=None,  # Будет установлено при первом создании
            )

            # Проверяем, есть ли уже сообщение с меню редактирования
            data = await state.get_data()
            edit_menu_msg_id = data.get("edit_menu_msg_id")

            if edit_menu_msg_id:
                # Редактируем существующее сообщение
                try:
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=edit_menu_msg_id,
                        text=event_info,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
                    return
                except Exception as e:
                    logger.warning(f"Не удалось отредактировать сообщение {edit_menu_msg_id}: {e}")
                    # Если не удалось отредактировать, создаем новое

            # Создаем новое сообщение
            sent_message = await message.answer(event_info, parse_mode="Markdown", reply_markup=keyboard)
            await state.update_data(edit_menu_msg_id=sent_message.message_id)
    except Exception as e:
        logger.error(f"Ошибка при загрузке события для редактирования: {e}")
        await message.answer("❌ Ошибка при загрузке события")


async def update_community_event_field_pm(event_id: int, field: str, value: str, user_id: int, chat_id: int) -> bool:
    """Обновляет поле Community события в базе данных (для приватного чата)"""
    from database import CommunityEvent, get_session

    try:
        with get_session() as session:
            # Проверяем права доступа
            event = (
                session.query(CommunityEvent)
                .filter(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
                .first()
            )

            if not event:
                logger.warning(f"Событие {event_id} не найдено")
                return False

            can_edit = event.organizer_id == user_id
            if not can_edit:
                logger.warning(f"Пользователь {user_id} не имеет прав для редактирования события {event_id}")
                return False

            # Обновляем поле
            if field == "title":
                event.title = value
                logger.info(f"Обновлено название события {event_id}: '{value}'")
            elif field == "starts_at":
                # Для Community событий starts_at - это TIMESTAMP WITHOUT TIME ZONE (naive datetime)
                # Парсим дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ
                try:
                    # Парсим дату и время (используем глобальный datetime из импортов)
                    dt = datetime.strptime(value.strip(), "%d.%m.%Y %H:%M")
                    event.starts_at = dt  # Сохраняем как naive datetime
                    logger.info(f"Обновлена дата/время события {event_id}: {dt}")
                except ValueError:
                    logger.error(f"Неверный формат даты/времени для события {event_id}: {value}")
                    return False
            elif field == "location_name":
                event.location_name = value
                logger.info(f"Обновлена локация события {event_id}: '{value}'")
            elif field == "description":
                event.description = value
                logger.info(f"Обновлено описание события {event_id}: '{value}'")
            elif field == "location_url":
                event.location_url = value
                logger.info(f"Обновлен URL локации события {event_id}: '{value}'")
            else:
                logger.error(f"Неизвестное поле для обновления: {field}")
                return False

            # Обновляем updated_at
            event.updated_at = datetime.now(UTC)
            session.commit()
            logger.info(f"Событие {event_id} успешно обновлено в БД")
            return True

    except Exception as e:
        logger.error(f"Ошибка обновления события {event_id}: {e}")
        return False


# === ОБРАБОТЧИКИ РЕДАКТИРОВАНИЯ COMMUNITY СОБЫТИЙ В ПРИВАТНОМ ЧАТЕ ===
@main_router.callback_query(F.data.startswith("pm_edit_title_"))
async def pm_edit_title_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования названия Community события"""
    try:
        # Формат: pm_edit_title_{event_id}_{chat_id}
        parts = callback.data.replace("pm_edit_title_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_title)
            await callback.message.answer("✍️ Введите новое название события:")
            await callback.answer()
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_title_: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_date_"))
async def pm_edit_date_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования даты Community события"""
    try:
        parts = callback.data.replace("pm_edit_date_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_date)
            await callback.message.answer("📅 Введите новую дату в формате ДД.ММ.ГГГГ:")
            await callback.answer()
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_date_: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_time_"))
async def pm_edit_time_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования времени Community события"""
    try:
        parts = callback.data.replace("pm_edit_time_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_time)
            await callback.message.answer("⏰ Введите новое время в формате ЧЧ:ММ:")
            await callback.answer()
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_time_: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@main_router.callback_query(
    F.data.startswith("pm_edit_location_")
    & ~F.data.startswith("pm_edit_location_link_")
    & ~F.data.startswith("pm_edit_location_map_")
    & ~F.data.startswith("pm_edit_location_coords_")
)
async def pm_edit_location_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования локации Community события - показываем 3 кнопки"""
    try:
        # Формат: pm_edit_location_{event_id}_{chat_id}
        parts = callback.data.replace("pm_edit_location_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_location)

            # Создаем клавиатуру с 3 кнопками для выбора способа ввода локации
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔗 Вставить готовую ссылку",
                            callback_data=f"pm_edit_location_link_{event_id}_{chat_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🌍 Найти на карте", callback_data=f"pm_edit_location_map_{event_id}_{chat_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📍 Ввести координаты", callback_data=f"pm_edit_location_coords_{event_id}_{chat_id}"
                        )
                    ],
                ]
            )

            await callback.message.answer(
                "📍 **Как укажем место?**\n\nВыберите один из способов:",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            await callback.answer()
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_location_: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_location_link_"))
async def pm_edit_location_link_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода ссылки Google Maps для редактирования локации"""
    try:
        parts = callback.data.replace("pm_edit_location_link_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_location)
            await callback.message.answer(
                "🔗 Вставьте ссылку Google Maps:\n\n" "Скопируйте ссылку из приложения Google Maps и отправьте её сюда."
            )
            await callback.answer()
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_location_link_: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_location_map_"))
async def pm_edit_location_map_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор поиска на карте для редактирования локации"""
    try:
        parts = callback.data.replace("pm_edit_location_map_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_location)

            # Показываем кнопку с картой
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🌍 Найти на карте", url="https://www.google.com/maps")],
                ]
            )

            await callback.message.answer(
                "🌍 **Найдите место на карте**\n\n"
                "1. Нажмите кнопку ниже, чтобы открыть Google Maps\n"
                "2. Найдите нужное место\n"
                "3. Скопируйте ссылку и отправьте её сюда",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            await callback.answer()
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_location_map_: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_location_coords_"))
async def pm_edit_location_coords_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода координат для редактирования локации"""
    try:
        parts = callback.data.replace("pm_edit_location_coords_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_location)
            await callback.message.answer(
                "📍 Введите координаты в формате: **широта, долгота**\n\n"
                "Например: 55.7558, 37.6176\n"
                "Или: -8.67, 115.21",
                parse_mode="Markdown",
            )
            await callback.answer()
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_location_coords_: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_description_"))
async def pm_edit_description_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования описания Community события"""
    try:
        parts = callback.data.replace("pm_edit_description_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_description)
            await callback.message.answer("📝 Введите новое описание:")
            await callback.answer()
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_description_: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_finish_"))
async def pm_edit_finish(callback: types.CallbackQuery, state: FSMContext):
    """Завершение редактирования Community события"""
    try:
        parts = callback.data.replace("pm_edit_finish_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])

            # Загружаем обновленное событие
            from database import CommunityEvent, get_session

            with get_session() as session:
                event = (
                    session.query(CommunityEvent)
                    .filter(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
                    .first()
                )

                if event:
                    # Форматируем дату и время
                    date_str = event.starts_at.strftime("%d.%m.%Y") if event.starts_at else "Не указано"
                    time_str = event.starts_at.strftime("%H:%M") if event.starts_at else "Не указано"

                    text = (
                        f"✅ **Событие обновлено!**\n\n"
                        f"📌 Название: {event.title}\n"
                        f"📅 Дата: {date_str}\n"
                        f"⏰ Время: {time_str}\n"
                        f"📍 Локация: {event.location_name or 'Не указано'}\n"
                        f"📝 Описание: {event.description or 'Не указано'}\n\n"
                        f"Событие обновлено в группе!"
                    )
                    await callback.message.edit_text(text, parse_mode="Markdown")
                    await callback.answer("✅ Событие обновлено!")
                else:
                    await callback.answer("❌ Событие не найдено", show_alert=True)

            await state.clear()
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_finish_: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# === ОБРАБОТЧИКИ ВВОДА ДАННЫХ ДЛЯ РЕДАКТИРОВАНИЯ COMMUNITY СОБЫТИЙ ===
@main_router.message(CommunityEventEditing.waiting_for_title)
async def pm_handle_title_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового названия Community события"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id

    if event_id and chat_id and message.text:
        success = await update_community_event_field_pm(event_id, "title", message.text.strip(), user_id, chat_id)
        if success:
            await message.answer("✅ Название обновлено!")
            # Показываем меню редактирования снова
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer("❌ Ошибка при обновлении названия")
    else:
        await message.answer("❌ Введите корректное название")


@main_router.message(CommunityEventEditing.waiting_for_date)
async def pm_handle_date_input(message: types.Message, state: FSMContext):
    """Обработка ввода новой даты Community события"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id

    if event_id and chat_id and message.text:
        # Получаем текущее событие для получения времени
        from database import CommunityEvent, get_session

        with get_session() as session:
            event = (
                session.query(CommunityEvent)
                .filter(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
                .first()
            )

            if event and event.starts_at:
                # Сохраняем текущее время и обновляем только дату
                current_time = event.starts_at.strftime("%H:%M")
                new_datetime = f"{message.text.strip()} {current_time}"
            else:
                # Если нет текущей даты, используем время по умолчанию
                new_datetime = f"{message.text.strip()} 12:00"

        success = await update_community_event_field_pm(event_id, "starts_at", new_datetime, user_id, chat_id)
        if success:
            await message.answer("✅ Дата обновлена!")
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer("❌ Ошибка при обновлении даты. Проверьте формат (ДД.ММ.ГГГГ)")
    else:
        await message.answer("❌ Введите корректную дату")


@main_router.message(CommunityEventEditing.waiting_for_time)
async def pm_handle_time_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового времени Community события"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id

    if event_id and chat_id and message.text:
        # Получаем текущее событие для получения даты
        from database import CommunityEvent, get_session

        with get_session() as session:
            event = (
                session.query(CommunityEvent)
                .filter(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
                .first()
            )

            if event and event.starts_at:
                # Сохраняем текущую дату и обновляем только время
                current_date = event.starts_at.strftime("%d.%m.%Y")
                new_datetime = f"{current_date} {message.text.strip()}"
            else:
                # Если нет текущей даты, используем сегодняшнюю
                today = datetime.now().strftime("%d.%m.%Y")
                new_datetime = f"{today} {message.text.strip()}"

        success = await update_community_event_field_pm(event_id, "starts_at", new_datetime, user_id, chat_id)
        if success:
            await message.answer("✅ Время обновлено!")
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer("❌ Ошибка при обновлении времени. Проверьте формат (ЧЧ:ММ)")
    else:
        await message.answer("❌ Введите корректное время")


@main_router.message(CommunityEventEditing.waiting_for_location)
async def pm_handle_location_input(message: types.Message, state: FSMContext):
    """Обработка ввода новой локации Community события"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id

    if not event_id or not chat_id or not message.text:
        await message.answer("❌ Введите корректную локацию")
        return

    location_input = message.text.strip()
    logger.info(f"pm_handle_location_input: редактирование локации для события {event_id}, ввод: {location_input}")

    # Проверяем, является ли это Google Maps ссылкой
    if any(domain in location_input.lower() for domain in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl"]):
        # Парсим ссылку Google Maps
        from utils.geo_utils import parse_google_maps_link

        location_data = await parse_google_maps_link(location_input)

        if location_data:
            # Обновляем событие с данными из ссылки
            success = await update_community_event_field_pm(
                event_id, "location_name", location_data.get("name", "Место на карте"), user_id, chat_id
            )
            if success:
                # Обновляем URL
                await update_community_event_field_pm(event_id, "location_url", location_input, user_id, chat_id)
                await message.answer(
                    f"✅ Локация обновлена: *{location_data.get('name', 'Место на карте')}*", parse_mode="Markdown"
                )
                await start_group_event_editing(message, event_id, chat_id, state)
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
                success = await update_community_event_field_pm(
                    event_id, "location_name", "Место по координатам", user_id, chat_id
                )
                if success:
                    await update_community_event_field_pm(event_id, "location_url", location_input, user_id, chat_id)
                    await message.answer(f"✅ Локация обновлена: *{lat:.6f}, {lng:.6f}*", parse_mode="Markdown")
                    await start_group_event_editing(message, event_id, chat_id, state)
                else:
                    await message.answer("❌ Ошибка при обновлении локации")
            else:
                await message.answer("❌ Координаты вне допустимого диапазона")
        except ValueError:
            await message.answer("❌ Неверный формат координат. Используйте: широта, долгота")

    else:
        # Обычный текст - обновляем только название
        success = await update_community_event_field_pm(event_id, "location_name", location_input, user_id, chat_id)
        if success:
            await message.answer(f"✅ Локация обновлена: *{location_input}*", parse_mode="Markdown")
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer("❌ Ошибка при обновлении локации")


@main_router.message(CommunityEventEditing.waiting_for_description)
async def pm_handle_description_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового описания Community события"""
    description = message.text.strip()
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id

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

    if event_id and chat_id and description:
        success = await update_community_event_field_pm(event_id, "description", description, user_id, chat_id)
        if success:
            await message.answer("✅ Описание обновлено!")
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer("❌ Ошибка при обновлении описания")
    else:
        await message.answer("❌ Введите корректное описание")


# Обработчики FSM для создания событий в ЛС (для групп)
@main_router.message(CommunityEventCreation.waiting_for_title)
async def process_community_title_pm(message: types.Message, state: FSMContext):
    """Обработка названия события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_title_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n✍️ **Введите название события:**",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    title = message.text.strip()
    logger.info(f"🔥 process_community_title_pm: получили название '{title}' от пользователя {message.from_user.id}")

    # Проверяем на спам-индикаторы в названии
    spam_indicators = [
        "http://",
        "https://",
        "www.",
        ".com",
        ".ru",
        ".org",
        "instagram.com",
        "vk.com",
        "facebook.com",
        "youtube.com",
        "t.me",
        "@",
        "tg://",
        "bit.ly",
        "goo.gl",
    ]

    # Проверяем на команды (символ / в начале)
    if title.startswith("/"):
        await message.answer(
            "❌ В названии нельзя указывать команды (символ / в начале)!\n\n"
            "📝 Пожалуйста, придумайте краткое название события:\n"
            "• Что будет происходить\n"
            "• Где будет проходить\n"
            "• Для кого предназначено\n\n"
            "✍️ **Введите название события:**",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    title_lower = title.lower()
    if any(indicator in title_lower for indicator in spam_indicators):
        await message.answer(
            "❌ В названии нельзя указывать ссылки и контакты!\n\n"
            "📝 Пожалуйста, придумайте краткое название события:\n"
            "• Что будет происходить\n"
            "• Где будет проходить\n"
            "• Для кого предназначено\n\n"
            "✍️ **Введите название события:**",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    await state.update_data(title=title)
    await state.set_state(CommunityEventCreation.waiting_for_date)
    example_date = get_example_date()

    await message.answer(
        f"**Название сохранено:** *{title}* ✅\n\n📅 **Введите дату** (например: {example_date}):",
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(),
    )


@main_router.message(CommunityEventCreation.waiting_for_date)
async def process_community_date_pm(message: types.Message, state: FSMContext):
    """Обработка даты события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_date_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n📅 **Введите дату** (например: 15.12.2024):",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    date = message.text.strip()
    logger.info(f"🔥 process_community_date_pm: получили дату '{date}' от пользователя {message.from_user.id}")

    # Валидация формата даты DD.MM.YYYY

    if not re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", date):
        await message.answer(
            "❌ **Неверный формат даты!**\n\n📅 Введите дату в формате **ДД.ММ.ГГГГ**\nНапример: 15.12.2024",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    # Дополнительная проверка: валидность даты и проверка на прошлое
    try:
        day, month, year = map(int, date.split("."))
        from datetime import datetime

        import pytz

        event_date = datetime(year, month, day)  # Проверяем валидность даты

        # Проверяем, что дата не в прошлом
        tz_bali = pytz.timezone("Asia/Makassar")  # UTC+8 для Бали
        now_bali = datetime.now(tz_bali)
        today_bali = now_bali.date()
        event_date_only = event_date.date()

        logger.info(
            f"🔍 Проверка даты: event_date_only={event_date_only}, today_bali={today_bali}, "
            f"сравнение: {event_date_only < today_bali}"
        )

        if event_date_only < today_bali:
            logger.warning(f"⚠️ Пользователь {message.from_user.id} пытается создать событие с прошлой датой: {date}")
            await message.answer(
                f"⚠️ Внимание! Дата *{date}* уже прошла (сегодня {today_bali.strftime('%d.%m.%Y')}).\n\n"
                "📅 Введите дату:",
                parse_mode="Markdown",
                reply_markup=get_community_cancel_kb(),
            )
            return
    except ValueError:
        await message.answer(
            "❌ **Неверная дата!**\n\n"
            "Проверьте правильность даты:\n"
            "• День: 1-31\n"
            "• Месяц: 1-12\n"
            "• Год: 2024-2030\n\n"
            "Например: 15.12.2024\n\n"
            "📅 **Введите дату** (например: 15.12.2024):",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    await state.update_data(date=date)
    await state.set_state(CommunityEventCreation.waiting_for_time)

    await message.answer(
        f"**Дата сохранена:** {date} ✅\n\n⏰ **Введите время** (например: 19:00):",
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(),
    )


@main_router.message(CommunityEventCreation.waiting_for_time)
async def process_community_time_pm(message: types.Message, state: FSMContext):
    """Обработка времени события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_time_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n⏰ **Введите время** (например: 19:00):",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    time = message.text.strip()
    logger.info(f"🔥 process_community_time_pm: получили время '{time}' от пользователя {message.from_user.id}")

    # Валидация формата времени HH:MM

    if not re.match(r"^\d{1,2}:\d{2}$", time):
        await message.answer(
            "❌ **Неверный формат времени!**\n\n⏰ Введите время в формате **ЧЧ:ММ**\nНапример: 19:00",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    await state.update_data(time=time)
    await state.set_state(CommunityEventCreation.waiting_for_city)

    await message.answer(
        f"**Время сохранено:** {time} ✅\n\n🏙️ **Введите город** (например: Москва):",
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(),
    )


@main_router.message(CommunityEventCreation.waiting_for_city)
async def process_community_city_pm(message: types.Message, state: FSMContext):
    """Обработка города события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_city_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n🏙️ **Введите город** (например: Москва):",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    city = message.text.strip()
    logger.info(f"🔥 process_community_city_pm: получили город '{city}' от пользователя {message.from_user.id}")

    await state.update_data(city=city)
    await state.set_state(CommunityEventCreation.waiting_for_location_type)

    # Создаем клавиатуру для выбора типа локации (как в World режиме)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data="community_location_link")],
            [InlineKeyboardButton(text="🌍 Найти на карте", callback_data="community_location_map")],
            [InlineKeyboardButton(text="📍 Ввести координаты", callback_data="community_location_coords")],
        ]
    )

    await message.answer(
        f"**Город сохранен:** {city} ✅\n\n📍 **Как укажем место?**\n\nВыберите один из способов:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@main_router.message(CommunityEventCreation.waiting_for_location_type)
async def handle_community_location_type_text(message: types.Message, state: FSMContext):
    """Обработка текстовых сообщений в состоянии выбора типа локации в Community режиме"""
    text = message.text.strip()

    # Проверяем, является ли это Google Maps ссылкой
    if any(domain in text.lower() for domain in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl"]):
        # Пользователь отправил ссылку напрямую - обрабатываем как ссылку
        await state.set_state(CommunityEventCreation.waiting_for_location_url)
        # Имитируем обработку через process_community_location_url_pm
        from aiogram import Bot

        from database import async_session_maker

        bot = Bot.get_current()
        async with async_session_maker() as session:
            await process_community_location_url_pm(message, state, bot, session)
        return

    # Проверяем, являются ли это координаты (широта, долгота)
    if "," in text and len(text.split(",")) == 2:
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
                await state.set_state(CommunityEventCreation.waiting_for_description)
                await message.answer(
                    f"📍 **Место определено по координатам:** {lat}, {lng} ✅\n\n"
                    "📝 **Введите описание события** (что будет происходить, кому интересно):",
                    parse_mode="Markdown",
                    reply_markup=get_community_cancel_kb(),
                )
                return
            else:
                raise ValueError("Invalid coordinates range")
        except (ValueError, TypeError):
            await message.answer(
                "❌ **Неверный формат координат!**\n\n"
                "Используйте формат: **широта, долгота**\n"
                "Например: 55.7558, 37.6176\n\n"
                "Диапазоны:\n"
                "• Широта: -90 до 90\n"
                "• Долгота: -180 до 180",
                parse_mode="Markdown",
                reply_markup=get_community_cancel_kb(),
            )
            return

    # Если не распознали, показываем подсказку
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data="community_location_link")],
            [InlineKeyboardButton(text="🌍 Найти на карте", callback_data="community_location_map")],
            [InlineKeyboardButton(text="📍 Ввести координаты", callback_data="community_location_coords")],
        ]
    )
    await message.answer(
        "📍 **Как укажем место?**\n\nВыберите один из способов:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@main_router.message(CommunityEventCreation.waiting_for_location_url)
async def process_community_location_url_pm(message: types.Message, state: FSMContext, bot: Bot, session: AsyncSession):
    """Обработка ссылки на место события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_location_url_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n🔗 **Введите ссылку на место** (Google Maps или адрес):",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
        )
        return

    location_input = message.text.strip()
    logger.info(f"🔥 process_community_location_url_pm: получили ввод от пользователя {message.from_user.id}")

    # Определяем название места по ссылке и пробуем достать координаты
    location_name = "Место по ссылке"  # Базовое название
    location_lat = None
    location_lng = None
    location_url = None

    # Проверяем, являются ли это координаты (широта, долгота)
    if "," in location_input and len(location_input.split(",")) == 2:
        try:
            lat_str, lng_str = location_input.split(",")
            lat = float(lat_str.strip())
            lng = float(lng_str.strip())

            # Проверяем валидность координат
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                location_name = "Место по координатам"
                location_lat = lat
                location_lng = lng
                location_url = location_input  # Сохраняем координаты как строку
            else:
                raise ValueError("Invalid coordinates range")
        except (ValueError, TypeError):
            await message.answer(
                "❌ **Неверный формат координат!**\n\n"
                "Используйте формат: **широта, долгота**\n"
                "Например: 55.7558, 37.6176\n\n"
                "Диапазоны:\n"
                "• Широта: -90 до 90\n"
                "• Долгота: -180 до 180",
                parse_mode="Markdown",
                reply_markup=get_community_cancel_kb(),
            )
            return
    else:
        # Это ссылка
        location_url = location_input
        try:
            if "maps.google.com" in location_url or "goo.gl" in location_url or "maps.app.goo.gl" in location_url:
                from utils.geo_utils import parse_google_maps_link

                location_data = await parse_google_maps_link(location_url)
                logger.info(f"🌍 parse_google_maps_link (community) ответ: {location_data}")
                if location_data:
                    location_name = location_data.get("name") or "Место на карте"
                    location_lat = location_data.get("lat")
                    location_lng = location_data.get("lng")
                else:
                    location_name = "Место на карте"
            elif "yandex.ru/maps" in location_url:
                location_name = "Место на Яндекс.Картах"
            else:
                location_name = "Место по ссылке"
        except Exception as e:
            logger.warning(f"Не удалось распарсить ссылку для community события: {e}")
            location_name = "Место по ссылке"

    await state.update_data(
        location_url=location_url,
        location_name=location_name,
        location_lat=location_lat,
        location_lng=location_lng,
    )
    await state.set_state(CommunityEventCreation.waiting_for_description)

    if location_lat and location_lng:
        location_text = f"📍 **Место:** {location_name}\n**Координаты:** {location_lat}, {location_lng}"
    else:
        location_text = f"📍 **Место:** {location_name}"

    await message.answer(
        f"**Место сохранено** ✅\n{location_text}\n\n📝 **Введите описание события** (что будет происходить, кому интересно):",
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(),
    )


@main_router.message(CommunityEventCreation.waiting_for_description)
async def process_community_description_pm(message: types.Message, state: FSMContext):
    """Обработка описания события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_description_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n📝 **Введите описание события** (что будет происходить, кому интересно):",
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(),
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
    city_info = f"\n🏙️ **Город:** {data.get('city', 'НЕ УКАЗАНО')}" if data.get("city") else ""
    await message.answer(
        f"📌 **Проверьте данные события для группы:**\n\n"
        f"**Название:** {data.get('title', 'НЕ УКАЗАНО')}\n"
        f"**Дата:** {data.get('date', 'НЕ УКАЗАНО')}\n"
        f"**Время:** {data.get('time', 'НЕ УКАЗАНО')}{city_info}\n"
        f"**Место:** {data.get('location_name', 'НЕ УКАЗАНО')}\n"
        f"**Ссылка:** {data.get('location_url', 'НЕ УКАЗАНО')}\n"
        f"**Описание:** {data.get('description', 'НЕ УКАЗАНО')}\n\n"
        f"✅ **Все данные корректны?**\n"
        f"Выберите, где опубликовать событие.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Только чат", callback_data="community_event_confirm_chat"),
                    InlineKeyboardButton(text="🌍 Чат + World", callback_data="community_event_confirm_world"),
                ],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="community_event_cancel_pm")],
            ]
        ),
    )


# Обработчики для inline кнопок в групповых чатов
@main_router.callback_query(F.data == "group_create_event")
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

    # Получаем thread_id для поддержки тредов в супергруппах
    thread_id = callback.message.message_thread_id

    # Устанавливаем FSM состояние (используем новый FSM)
    await state.set_state(CommunityEventCreation.waiting_for_title)
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


@main_router.callback_query(F.data == "group_chat_events")
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
            "В этом чате пока нет активных событий.\n\n"
            "💡 Создайте первое событие, нажав кнопку '➕ Создать событие в чате'!"
        )
    else:
        text = f"📋 **События этого чата** ({len(events)} событий):\n\n"
        from utils.simple_timezone import get_city_from_coordinates, get_city_timezone

        for i, event in enumerate(events, 1):
            text += f"**{i}. {event['title']}**\n"
            if event["description"]:
                text += f"   {event['description'][:100]}{'...' if len(event['description']) > 100 else ''}\n"
            # Определяем timezone события по его координатам
            event_tz = "UTC"
            if event.get("lat") and event.get("lng"):
                city = get_city_from_coordinates(event["lat"], event["lng"])
                event_tz = get_city_timezone(city)
            # Форматируем время в timezone события
            time_str = format_event_time(event["starts_at"], event_tz=event_tz)
            text += f"   📅 {time_str}\n"
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


@main_router.callback_query(F.data == "group_myevents")
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


@main_router.callback_query(F.data == "group_hide_bot")
async def handle_group_hide_bot(callback: types.CallbackQuery, bot: Bot, session):
    """Обработчик кнопки 'Спрятать бота' в групповых чатах"""
    from sqlalchemy.ext.asyncio import AsyncSession

    from group_router import ensure_group_start_command
    from utils.messaging_utils import delete_all_tracked

    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    # Получаем thread_id для форумов
    is_forum = getattr(callback.message.chat, "is_forum", False)
    thread_id = getattr(callback.message, "message_thread_id", None)

    logger.info(
        f"🔥 handle_group_hide_bot: пользователь {user_id} скрывает бота в чате {chat_id}, thread_id={thread_id}"
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

    # Используем асинхронную версию delete_all_tracked для удаления всех трекированных сообщений
    try:
        if isinstance(session, AsyncSession):
            deleted = await delete_all_tracked(bot, session, chat_id=chat_id)
        else:
            # Fallback для синхронной сессии (не должно происходить, но на всякий случай)
            from utils.messaging_utils import delete_all_tracked_sync

            deleted = delete_all_tracked_sync(bot, session, chat_id=chat_id)
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
        await asyncio.sleep(5)
        await note.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления уведомления

    logger.info(f"✅ Бот скрыт в чате {chat_id} пользователем {user_id}, удалено сообщений: {deleted}")


@main_router.callback_query(F.data.regexp(r"^delete_message_\d+$"))
async def handle_delete_message(callback: types.CallbackQuery):
    """Обработчик кнопки удаления сообщения"""
    try:
        await callback.message.delete()
        await callback.answer("✅ Сообщение удалено")
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении сообщения: {e}")
        await callback.answer("❌ Не удалось удалить сообщение")


@main_router.callback_query(F.data.in_({"community_event_confirm_chat", "community_event_confirm_world"}))
async def confirm_community_event_pm(callback: types.CallbackQuery, state: FSMContext, bot: Bot, session: AsyncSession):
    """Подтверждение создания события сообщества в ЛС"""
    logger.info(
        f"🔥 confirm_community_event_pm: пользователь {callback.from_user.id} подтверждает создание события в ЛС"
    )
    publish_world = callback.data == "community_event_confirm_world"

    # Антидребезг: предотвращаем двойное создание события
    user_id = callback.from_user.id
    from time import time

    # Используем глобальный словарь для отслеживания обработки
    if not hasattr(confirm_community_event_pm, "_processing"):
        confirm_community_event_pm._processing = {}

    current_time = time()
    last_processing = confirm_community_event_pm._processing.get(user_id, 0)

    if current_time - last_processing < 3:  # 3 секунды защиты от двойного клика
        logger.warning(f"⚠️ confirm_community_event_pm: игнорируем двойной клик от пользователя {user_id}")
        await callback.answer("⏳ Подождите, событие уже создается...", show_alert=False)
        return

    confirm_community_event_pm._processing[user_id] = current_time

    try:
        data = await state.get_data()
        logger.info(f"🔥 confirm_community_event_pm: данные события: {data}")

        # Парсим дату и время с учетом города
        from datetime import datetime

        from utils.simple_timezone import get_city_from_coordinates

        date_str = data["date"]
        time_str = data["time"]
        location_lat = data.get("location_lat")
        location_lng = data.get("location_lng")

        normalized_city = None
        try:
            if location_lat is not None and location_lng is not None:
                normalized_city = get_city_from_coordinates(float(location_lat), float(location_lng))
        except (TypeError, ValueError):
            logger.warning(
                f"⚠️ Не удалось преобразовать координаты community события: lat={location_lat}, lng={location_lng}"
            )

        # В Community режиме сохраняем время как указал пользователь, БЕЗ конвертации в UTC
        # Пользователь сам указал город и время, значит он уже учел свой часовой пояс
        # Сохраняем как naive datetime (без timezone), т.к. колонка в БД TIMESTAMP WITHOUT TIME ZONE
        starts_at = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        logger.info(
            f"🕐 Community событие: время={time_str}, дата={date_str}, starts_at={starts_at} (naive, без timezone)"
        )

        # Импортируем сервис для событий сообществ
        from utils.community_events_service import CommunityEventsService

        community_service = CommunityEventsService()

        # Получаем ID всех админов группы с кэшированием
        print(f"🔥🔥🔥 bot_enhanced_v3: ВЫЗОВ get_cached_admin_ids для группы {data['group_id']}")
        admin_ids = await community_service.get_cached_admin_ids(bot, data["group_id"])
        print(f"🔥🔥🔥 bot_enhanced_v3: РЕЗУЛЬТАТ get_cached_admin_ids: {admin_ids}")

        # FALLBACK: если админы не получены, оставляем пустой список
        if not admin_ids:
            print("🚨🚨🚨 FALLBACK: admin_ids пустой, оставляем пустой список")
            print("🚨🚨🚨 FALLBACK: Система будет работать с пустыми админами")

        admin_id = admin_ids[0] if admin_ids else None  # LEGACY для обратной совместимости

        logger.info(f"🔥 Создание события: получены админы группы {data['group_id']}: {admin_ids}")
        logger.info(f"🔥 LEGACY admin_id: {admin_id}")

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
            admin_id=admin_id,  # LEGACY
            admin_ids=admin_ids,  # Новый подход
        )

        logger.info(f"✅ Событие сообщества создано с ID: {event_id}")

        world_publish_status = None
        if publish_world:
            world_publish_status = await publish_community_event_to_world(
                event_data=data,
                starts_at=starts_at,
                organizer_id=callback.from_user.id,
                organizer_username=callback.from_user.username or callback.from_user.first_name,
                community_event_id=event_id,
                normalized_city=normalized_city or (data.get("city") or None),
            )
            logger.info(f"🌍 publish_community_event_to_world результат: {world_publish_status}")

        # Публикуем событие в группу
        group_id = data["group_id"]
        # Экранируем все поля для безопасной вставки в Markdown
        safe_title = escape_markdown(data.get("title", ""))
        safe_date = escape_markdown(data.get("date", ""))
        safe_time = escape_markdown(data.get("time", ""))
        safe_city = escape_markdown(data.get("city", ""))
        safe_location_name = escape_markdown(data.get("location_name", "Место по ссылке"))
        safe_description = escape_markdown(data.get("description", ""))
        safe_username = escape_markdown(callback.from_user.username or callback.from_user.first_name or "Пользователь")

        event_text = (
            f"🎉 **Новое событие!**\n\n"
            f"**{safe_title}**\n"
            f"📅 {safe_date} в {safe_time}\n"
            f"🏙️ {safe_city}\n"
            f"📍 {safe_location_name}\n"
        )
        if data.get("location_url"):
            # URL не экранируем, так как он должен быть кликабельным
            event_text += f"🔗 {data['location_url']}\n"
        event_text += (
            "\n"
            f"📝 {safe_description}\n\n"
            f"*Создано пользователем @{safe_username}*\n\n"
            f"💡 **Создавай через команду /start**"
        )

        try:
            # Отправляем через send_tracked с тегом "notification" (не удаляется автоматически)
            from utils.messaging_utils import send_tracked

            group_message = await send_tracked(
                bot, session, chat_id=group_id, text=event_text, tag="notification", parse_mode="Markdown"
            )

            # Показываем ссылку на опубликованное сообщение (только для супергрупп с chat_id, начинающимся на -100)
            is_supergroup = str(group_id).startswith("-100")
            group_link = build_message_link(group_id, group_message.message_id) if is_supergroup else None

            # Сообщение об успешном создании (используем уже экранированные значения)
            success_text_parts = [
                "🎉 **Событие создано и опубликовано!**\n",
                f"**{safe_title}**\n",
                f"📅 {safe_date} в {safe_time}\n",
                f"🏙️ {safe_city}\n",
                f"📍 {safe_location_name}\n",
            ]
            if data.get("location_url"):
                success_text_parts.append(f"🔗 {data['location_url']}\n")
            if group_link:
                success_text_parts.extend(
                    [
                        "\n",
                        "✅ Событие опубликовано в группе!\n",
                        f"🔗 [Ссылка на сообщение]({group_link})\n\n",
                    ]
                )
            if publish_world:
                if world_publish_status and world_publish_status.get("success"):
                    success_text_parts.append("\n🌍 Событие также доступно в World-версии!\n")
                else:
                    success_text_parts.append("\n⚠️ Не смогли создать событие в World версии, создайте вручную.\n")

            success_text_parts.append("\n🚀")
            success_text = "".join(success_text_parts)

            # Отправляем новое сообщение с ReplyKeyboardMarkup вместо edit_text
            await callback.message.answer(success_text, parse_mode="Markdown", reply_markup=main_menu_kb())

            # Восстанавливаем команды бота после создания события
            await setup_bot_commands()

        except Exception as e:
            logger.error(f"Ошибка публикации в группу: {e}")
            # Используем экранированные значения для сообщения об ошибке
            await callback.message.edit_text(
                f"✅ **Событие создано!**\n\n"
                f"**{safe_title}**\n"
                f"📅 {safe_date} в {safe_time}\n"
                f"🏙️ {safe_city}\n"
                f"📍 {safe_location_name}\n\n"
                f"⚠️ Не удалось опубликовать в группу, но событие сохранено.",
                parse_mode="Markdown",
            )

        await state.clear()

        # Очищаем флаг обработки после успешного создания
        if hasattr(confirm_community_event_pm, "_processing"):
            confirm_community_event_pm._processing.pop(user_id, None)

    except Exception as e:
        logger.error(f"Ошибка создания события: {e}")
        await callback.message.edit_text(
            "❌ **Произошла ошибка при создании события.** Попробуйте еще раз.", parse_mode="Markdown"
        )

        # Очищаем флаг обработки даже при ошибке
        if hasattr(confirm_community_event_pm, "_processing"):
            confirm_community_event_pm._processing.pop(user_id, None)

    await callback.answer()


async def publish_community_event_to_world(
    event_data: dict,
    starts_at: datetime,
    organizer_id: int,
    organizer_username: str | None,
    community_event_id: int,
    normalized_city: str | None,
) -> dict:
    """
    Публикует событие из Community в основную таблицу events.

    Args:
        starts_at: naive datetime (без timezone) - время как указал пользователь в Community режиме
        normalized_city: нормализованный город для определения часового пояса

    Returns:
        dict: {"success": bool, "world_event_id": int | None, "reason": str | None}
    """

    lat = event_data.get("location_lat")
    lng = event_data.get("location_lng")

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        logger.warning(
            "⚠️ publish_community_event_to_world: отсутствуют координаты, World версия недоступна",
        )
        return {"success": False, "reason": "missing_coordinates"}

    try:
        from datetime import UTC

        import pytz

        from database import get_engine
        from utils.simple_timezone import get_city_timezone
        from utils.unified_events_service import UnifiedEventsService

        # В World режиме нужно конвертировать время в UTC с учетом часового пояса города
        # starts_at приходит как naive datetime (время как указал пользователь)
        # Определяем часовой пояс города и конвертируем в UTC
        city = normalized_city or event_data.get("city")
        tz_name = get_city_timezone(city)
        local_tz = pytz.timezone(tz_name)
        # Локализуем naive datetime в часовой пояс города и конвертируем в UTC
        local_dt = local_tz.localize(starts_at)
        starts_at_utc = local_dt.astimezone(UTC)

        logger.info(
            f"🌍 Публикация в World: время={starts_at} (naive), город={city}, tz={tz_name}, UTC={starts_at_utc}"
        )

        engine = get_engine()
        events_service = UnifiedEventsService(engine)

        location_name = event_data.get("location_name") or "Место на карте"
        location_url = event_data.get("location_url")
        chat_id = event_data.get("group_id")

        external_id = f"community:{chat_id}:{community_event_id}"

        world_event_id = events_service.create_user_event(
            organizer_id=organizer_id,
            title=event_data["title"],
            description=event_data["description"],
            starts_at_utc=starts_at_utc,  # Конвертированное время в UTC для World режима
            city=city,
            lat=lat,
            lng=lng,
            location_name=location_name,
            location_url=location_url,
            max_participants=None,
            chat_id=chat_id,
            organizer_username=organizer_username,
            source="community",
            external_id=external_id,
        )

        return {"success": True, "world_event_id": world_event_id}
    except Exception as e:
        logger.error(
            f"❌ publish_community_event_to_world: ошибка при сохранении события community_id={community_event_id}: {e}",
            exc_info=True,
        )
        return {"success": False, "reason": "exception", "error": str(e)}


@main_router.callback_query(F.data == "community_event_cancel_pm")
async def cancel_community_event_pm(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания события сообщества в ЛС"""
    logger.info(f"🔥 cancel_community_event_pm: пользователь {callback.from_user.id} отменил создание события в ЛС")

    await state.clear()
    await callback.message.edit_text(
        "❌ **Создание события отменено.**\n\n" "Если хотите создать событие, нажмите /start", parse_mode="Markdown"
    )
    await callback.answer()


@main_router.callback_query(F.data == "community_cancel")
async def cancel_community_event(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания события сообщества (универсальная кнопка отмены)"""
    logger.info(f"🔥 cancel_community_event: пользователь {callback.from_user.id} отменил создание группового события")

    # Получаем данные для информативного сообщения
    data = await state.get_data()
    group_id = data.get("group_id")

    await state.clear()

    cancel_text = "❌ **Создание группового события отменено.**\n\n"
    if group_id:
        cancel_text += "Вы можете вернуться в группу или остаться в боте:"

        # Создаем кнопки "Что рядом" и "Старт (все функции)"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📍 Что рядом", callback_data="nearby_events"),
                    InlineKeyboardButton(text="🚀 Старт", callback_data="start_menu"),
                ]
            ]
        )

        await callback.message.edit_text(cancel_text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        cancel_text += "Если хотите создать событие, нажмите /start"
        await callback.message.edit_text(cancel_text, parse_mode="Markdown")
    await callback.answer("Создание отменено", show_alert=False)


@main_router.callback_query(F.data == "group_cancel_create")
async def handle_group_cancel_create(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик отмены создания события в групповых чатах"""
    await state.clear()

    text = "❌ Создание события отменено."
    await callback.message.edit_text(text)
    await callback.answer()


@main_router.callback_query(F.data == "group_back_to_start")
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

    # Получаем username бота для создания ссылки (с кешированием)
    bot_info = await get_bot_info_cached()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Создать событие",
                    url=f"https://t.me/{bot_info.username}?start=group_{callback.message.chat.id}",
                )
            ],
            [InlineKeyboardButton(text="📋 События этого чата", callback_data="group_chat_events")],
            [InlineKeyboardButton(text='🚀 Расширенная версия "World"', url=f"https://t.me/{bot_info.username}")],
            [InlineKeyboardButton(text="👁️‍🗨️ Спрятать бота", callback_data="group_hide_bot")],
        ]
    )

    await callback.message.edit_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@main_router.callback_query(F.data == "start_menu")
async def on_start_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Старт' из callback"""
    await callback.answer()

    # Запускаем главное меню (аналогично команде /start)
    user_id = callback.from_user.id

    # Создаем пользователя если его нет (в фоне, не ждём)
    asyncio.create_task(ensure_user_exists(user_id, callback.from_user))

    # Показываем приветственное сообщение с главным меню
    welcome_text = (
        'Привет! @EventAroundBot версия "World" - твой цифровой помощник по активностям.\n\n'
        "📍 Что рядом: находи события в радиусе 5–20 км\n"
        "🎯 Чем заняться: автоматизированный подбор заданий с наградами 🚀\n\n"
        "➕ Создать: организуй встречи и приглашай друзей\n"
        '🔗 Поделиться: добавь бота версия "Community" в чат — появится лента встреч и планов только для участников сообщества.\n\n'
        "🚀 Начинай приключение"
    )

    await callback.message.answer(welcome_text, reply_markup=main_menu_kb())


@main_router.callback_query(F.data == "nearby_events")
async def on_nearby_events_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Что рядом' из callback"""
    await callback.answer()

    # Устанавливаем состояние для поиска событий
    await state.set_state(EventSearch.waiting_for_location)

    # Создаем клавиатуру с кнопкой геолокации и главным меню
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="🌍 Найти на карте")],
            [KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    # Отправляем новое сообщение с ReplyKeyboardMarkup
    await callback.message.answer(
        "Нажмите кнопку '📍 Отправить геолокацию' чтобы начать!\n\n"
        "💡 Если кнопка не работает :\n\n"
        "• Жми '🌍 Найти на карте' \n"
        "и вставь ссылку \n\n"
        "• Или отправь координаты\n"
        "пример: -8.4095, 115.1889",
        reply_markup=location_keyboard,
        parse_mode="Markdown",
    )

    if callback.from_user.id in settings.admin_ids:
        await callback.message.answer(
            "Для теста можно выбрать готовую точку геолокации:",
            reply_markup=build_test_locations_keyboard(),
        )


@main_router.callback_query(F.data.startswith("test_location:"))
async def on_test_location(callback: types.CallbackQuery, state: FSMContext):
    """Быстрый выбор тестовой локации (доступно только администраторам)."""
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Доступ запрещён")
        return

    key = callback.data.split(":", maxsplit=1)[1]
    location = TEST_LOCATIONS.get(key)
    if not location:
        await callback.answer("Локация не найдена")
        return

    await callback.answer(f"📍 {location['label']}")
    await state.set_state(EventSearch.waiting_for_location)
    await perform_nearby_search(
        message=callback.message,
        state=state,
        lat=location["lat"],
        lng=location["lng"],
        source=f"admin_test:{key}",
    )


@main_router.message(Command("nearby"))
@main_router.message(F.text == "📍 Что рядом")
async def on_what_nearby(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Что рядом'"""
    user_id = message.from_user.id
    logger.info(f"📍 [DEBUG] Команда /nearby от пользователя {user_id}")

    # Инкрементируем сессию World (с проверкой времени)
    if message.chat.type == "private":
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(message.from_user.id, min_interval_minutes=6)

    # Устанавливаем состояние для поиска событий
    await state.set_state(EventSearch.waiting_for_location)
    current_state = await state.get_state()
    logger.info(f"📍 [DEBUG] Состояние установлено: {current_state} для пользователя {user_id}")

    # Создаем клавиатуру с кнопкой геолокации и главным меню
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="🌍 Найти на карте")],
            [KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,  # Изменено на False, чтобы кнопка не исчезала на MacBook
    )

    await message.answer(
        "Нажмите кнопку '📍 Отправить геолокацию' чтобы начать!\n\n"
        "💡 Если кнопка не работает :\n\n"
        "• Жми '🌍 Найти на карте' \n"
        "и вставь ссылку \n\n"
        "• Или отправь координаты\n"
        "пример: -8.4095, 115.1889",
        reply_markup=location_keyboard,
        parse_mode="Markdown",
    )

    if message.from_user.id in settings.admin_ids:
        await message.answer(
            "Для теста можно выбрать предустановленную локацию:",
            reply_markup=build_test_locations_keyboard(),
        )


@main_router.message(F.location, TaskFlow.waiting_for_location)
async def on_location_for_tasks(message: types.Message, state: FSMContext):
    """Обработчик геолокации для заданий"""
    user_id = message.from_user.id
    lat = message.location.latitude
    lng = message.location.longitude

    # Логируем состояние для отладки
    current_state = await state.get_state()
    logger.info(f"📍 [ЗАДАНИЯ] Получена геолокация от пользователя {user_id}: {lat}, {lng}, состояние: {current_state}")

    # Сохраняем координаты пользователя и обновляем timezone
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.last_lat = lat
            user.last_lng = lng
            user.last_geo_at_utc = datetime.now(UTC)

            # Получаем timezone по координатам и сохраняем
            try:
                tz_name = await get_timezone(lat, lng)
                if tz_name:
                    user.user_tz = tz_name
                    logger.info(f"🕒 Timezone обновлен для пользователя {user_id}: {tz_name}")
                else:
                    logger.warning(f"⚠️ Не удалось получить timezone для координат ({lat}, {lng})")
            except Exception as e:
                logger.error(f"❌ Ошибка при получении timezone: {e}")

            session.commit()
            logger.info(f"📍 Координаты пользователя {user_id} обновлены")

    # Переходим в состояние ожидания выбора категории
    await state.set_state(TaskFlow.waiting_for_category)

    # Показываем выбор категории после получения геолокации
    keyboard = [
        [InlineKeyboardButton(text="🍔 Еда", callback_data="task_category:food")],
        [InlineKeyboardButton(text="💪 Здоровье", callback_data="task_category:health")],
        [InlineKeyboardButton(text="🌟 Интересные места", callback_data="task_category:places")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await message.answer(
        "✅ **Геолокация получена!**\n\n"
        "Выберите категорию для получения персонализированных заданий:\n\n"
        "🍔 **Еда** - кафе, рестораны, уличная еда\n"
        "💪 **Здоровье** - спорт, йога, спа, клиники\n"
        "🌟 **Интересные места** - парки, выставки, храмы",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

    logger.info(f"📍 [ЗАДАНИЯ] Показаны категории для пользователя {user_id}")


# Обработчик для текстовых сообщений в состоянии ожидания геолокации (для MacBook)
@main_router.message(EventSearch.waiting_for_location, F.text)
async def on_location_text_input(message: types.Message, state: FSMContext):
    """Обработчик текстового ввода координат или ссылки Google Maps для MacBook"""
    user_id = message.from_user.id
    text = message.text.strip()
    logger.info(f"📍 [TEXT_INPUT] Получен текст в состоянии waiting_for_location: user_id={user_id}, text={text[:100]}")

    # Если пользователь нажал "Главное меню", вызываем соответствующий обработчик
    if text == "🏠 Главное меню":
        logger.info(f"📍 [TEXT_INPUT] Обнаружена кнопка 'Главное меню', возвращаем в меню для пользователя {user_id}")
        # Очищаем состояние FSM
        await state.clear()
        # Показываем анимацию ракеты с главным меню
        await send_spinning_menu(message)
        return

    # Если пользователь нажал "🌍 Найти на карте", показываем inline-кнопку с картой
    if text == "🌍 Найти на карте":
        logger.info(f"📍 [TEXT_INPUT] Обнаружена кнопка '🌍 Найти на карте' от пользователя {user_id}")
        # Создаем inline-кнопку для открытия Google Maps
        maps_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🌍 Найти на карте", url="https://www.google.com/maps")],
            ]
        )
        await message.answer(
            "🌍 Открой карту, найди место и вставь ссылку сюда 👇",
            reply_markup=maps_keyboard,
        )
        return

    # Специальная обработка для MacBook: если пользователь нажал кнопку "📍 Что рядом" повторно
    if text == "📍 Что рядом":
        logger.info(f"📍 [TEXT_INPUT] Обнаружен повторный запрос '📍 Что рядом' от пользователя {user_id} (MacBook)")
        # Создаем inline-кнопку для открытия Google Maps (для MacBook)
        maps_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🌍 Найти на карте", url="https://www.google.com/maps")],
            ]
        )
        await message.answer(
            "Нажмите кнопку '📍 Отправить геолокацию' чтобы начать!\n\n"
            "💡 Если кнопка не работает :\n\n"
            "• Жми '🌍 Найти на карте' \n"
            "и вставь ссылку \n\n"
            "• Или отправь координаты\n"
            "пример: -8.4095, 115.1889",
            parse_mode="Markdown",
            reply_markup=maps_keyboard,
        )
        return

    # Проверяем, является ли это ссылкой Google Maps
    if any(
        domain in text.lower() for domain in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl", "google.com/maps"]
    ):
        logger.info("📍 [TEXT_INPUT] Обнаружена ссылка Google Maps, парсим...")
        from utils.geo_utils import parse_google_maps_link

        location_data = await parse_google_maps_link(text)
        if location_data and location_data.get("lat") and location_data.get("lng"):
            lat = location_data["lat"]
            lng = location_data["lng"]
            logger.info(f"📍 [TEXT_INPUT] Извлечены координаты из Google Maps: lat={lat}, lng={lng}")

            # Вызываем функцию поиска напрямую с координатами
            await perform_nearby_search(
                message=message,
                state=state,
                lat=lat,
                lng=lng,
                source="google_maps_link",
            )
            return
        else:
            maps_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🌍 Найти на карте", url="https://www.google.com/maps")],
                ]
            )
            await message.answer(
                "❌ Не удалось извлечь координаты из ссылки Google Maps.\n\n"
                "💡 Если кнопка не работает :\n\n"
                "• Жми '🌍 Найти на карте' \n"
                "и вставь ссылку \n\n"
                "• Или отправь координаты\n"
                "пример: -8.4095, 115.1889",
                reply_markup=maps_keyboard,
            )
            return

    # Пробуем распарсить координаты в формате "широта, долгота"
    try:
        text_clean = text.replace("(", "").replace(")", "").strip()
        parts = [p.strip() for p in text_clean.split(",")]

        if len(parts) == 2:
            lat = float(parts[0])
            lng = float(parts[1])

            # Проверяем, что координаты в разумных пределах
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                logger.info(f"📍 [TEXT_INPUT] Распарсены координаты: lat={lat}, lng={lng}")
                # Вызываем функцию поиска напрямую с координатами
                await perform_nearby_search(
                    message=message,
                    state=state,
                    lat=lat,
                    lng=lng,
                    source="manual_coordinates",
                )
                return
            else:
                await message.answer("❌ Координаты вне допустимого диапазона. Широта: -90 до 90, долгота: -180 до 180")
                return
    except ValueError:
        # Не координаты, возможно это другой текст - пропускаем
        logger.info("📍 [TEXT_INPUT] Текст не является координатами или ссылкой, пропускаем")
        pass

    # Если это не координаты и не ссылка, показываем подсказку
    # Создаем inline-кнопку для открытия Google Maps (для MacBook)
    maps_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌍 Найти на карте", url="https://www.google.com/maps")],
        ]
    )
    await message.answer(
        "Нажмите кнопку '📍 Отправить геолокацию' чтобы начать!\n\n"
        "💡 Если кнопка не работает :\n\n"
        "• Жми '🌍 Найти на карте' \n"
        "и вставь ссылку \n\n"
        "• Или отправь координаты\n"
        "пример: -8.4095, 115.1889",
        parse_mode="Markdown",
        reply_markup=maps_keyboard,
    )


# Обработчик для текстовых сообщений в состоянии ожидания геолокации для заданий (для MacBook)
@main_router.message(TaskFlow.waiting_for_location, F.text)
async def on_location_text_input_tasks(message: types.Message, state: FSMContext):
    """Обработчик текстового ввода координат или ссылки Google Maps для заданий (MacBook)"""
    user_id = message.from_user.id
    text = message.text.strip()
    logger.info(
        f"📍 [TEXT_INPUT_TASKS] Получен текст в состоянии TaskFlow.waiting_for_location: user_id={user_id}, text={text[:100]}"
    )

    # Если пользователь нажал "Главное меню", вызываем соответствующий обработчик
    if text == "🏠 Главное меню":
        logger.info(
            f"📍 [TEXT_INPUT_TASKS] Обнаружена кнопка 'Главное меню', возвращаем в меню для пользователя {user_id}"
        )
        # Очищаем состояние FSM
        await state.clear()
        # Показываем анимацию ракеты с главным меню
        await send_spinning_menu(message)
        return

    # Если пользователь нажал "🌍 Найти на карте", показываем inline-кнопку с картой
    if text == "🌍 Найти на карте":
        logger.info(f"📍 [TEXT_INPUT_TASKS] Обнаружена кнопка '🌍 Найти на карте' от пользователя {user_id}")
        # Создаем inline-кнопку для открытия Google Maps
        maps_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🌍 Найти на карте", url="https://www.google.com/maps")],
            ]
        )
        await message.answer(
            "🌍 Открой карту, найди место и вставь ссылку сюда 👇",
            reply_markup=maps_keyboard,
        )
        return

    # Специальная обработка для MacBook: если пользователь нажал кнопку "🎯 Чем заняться" повторно
    if text == "🎯 Чем заняться":
        logger.info(
            f"📍 [TEXT_INPUT_TASKS] Обнаружен повторный запрос '🎯 Чем заняться' от пользователя {user_id} (MacBook)"
        )
        # Создаем inline-кнопку для открытия Google Maps (для MacBook)
        maps_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🌍 Найти на карте", url="https://www.google.com/maps")],
            ]
        )
        await message.answer(
            "Нажмите кнопку '📍 Отправить геолокацию' чтобы начать!\n\n"
            "💡 Если кнопка не работает :\n\n"
            "• Жми '🌍 Найти на карте' \n"
            "и вставь ссылку \n\n"
            "• Или отправь координаты\n"
            "пример: -8.4095, 115.1889",
            parse_mode="Markdown",
            reply_markup=maps_keyboard,
        )
        return

    # Проверяем, является ли это ссылкой Google Maps
    if any(
        domain in text.lower() for domain in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl", "google.com/maps"]
    ):
        logger.info("📍 [TEXT_INPUT_TASKS] Обнаружена ссылка Google Maps, парсим...")
        from utils.geo_utils import parse_google_maps_link

        location_data = await parse_google_maps_link(text)
        if location_data and location_data.get("lat") and location_data.get("lng"):
            lat = location_data["lat"]
            lng = location_data["lng"]
            logger.info(f"📍 [TEXT_INPUT_TASKS] Извлечены координаты из Google Maps: lat={lat}, lng={lng}")

            # Обрабатываем координаты для заданий (аналогично on_location_for_tasks)
            await process_task_location(message, state, lat, lng)
            return
        else:
            # Создаем inline-кнопку для открытия Google Maps (для MacBook)
            maps_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🌍 Найти на карте", url="https://www.google.com/maps")],
                ]
            )
            await message.answer(
                "❌ Не удалось извлечь координаты из ссылки Google Maps.\n\n"
                "💡 Если кнопка не работает :\n\n"
                "• Жми '🌍 Найти на карте' \n"
                "и вставь ссылку \n\n"
                "• Или отправь координаты\n"
                "пример: -8.4095, 115.1889",
                reply_markup=maps_keyboard,
            )
            return

    # Пробуем распарсить координаты в формате "широта, долгота"
    try:
        text_clean = text.replace("(", "").replace(")", "").strip()
        parts = [p.strip() for p in text_clean.split(",")]

        if len(parts) == 2:
            lat = float(parts[0])
            lng = float(parts[1])

            # Проверяем, что координаты в разумных пределах
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                logger.info(f"📍 [TEXT_INPUT_TASKS] Распарсены координаты: lat={lat}, lng={lng}")
                # Обрабатываем координаты для заданий (аналогично on_location_for_tasks)
                await process_task_location(message, state, lat, lng)
                return
            else:
                await message.answer("❌ Координаты вне допустимого диапазона. Широта: -90 до 90, долгота: -180 до 180")
                return
    except ValueError:
        # Не координаты, возможно это другой текст - пропускаем
        logger.info("📍 [TEXT_INPUT_TASKS] Текст не является координатами или ссылкой, пропускаем")
        pass

    # Если это не координаты и не ссылка, показываем подсказку
    # Создаем inline-кнопку для открытия Google Maps (для MacBook)
    maps_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌍 Найти на карте", url="https://www.google.com/maps")],
        ]
    )
    await message.answer(
        "Нажмите кнопку '📍 Отправить геолокацию' чтобы начать!\n\n"
        "💡 Если кнопка не работает :\n\n"
        "• Жми '🌍 Найти на карте' \n"
        "и вставь ссылку \n\n"
        "• Или отправь координаты\n"
        "пример: -8.4095, 115.1889",
        parse_mode="Markdown",
        reply_markup=maps_keyboard,
    )


async def process_task_location(message: types.Message, state: FSMContext, lat: float, lng: float):
    """Вспомогательная функция для обработки координат для заданий"""
    user_id = message.from_user.id
    logger.info(f"📍 [TASKS] Обработка координат для заданий: user_id={user_id}, lat={lat}, lng={lng}")

    # Сохраняем координаты пользователя и обновляем timezone (аналогично on_location_for_tasks)
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.last_lat = lat
            user.last_lng = lng
            user.last_geo_at_utc = datetime.now(UTC)

            # Получаем timezone по координатам и сохраняем
            try:
                tz_name = await get_timezone(lat, lng)
                if tz_name:
                    user.user_tz = tz_name
                    logger.info(f"🕒 Timezone обновлен для пользователя {user_id}: {tz_name}")
                else:
                    logger.warning(f"⚠️ Не удалось получить timezone для координат ({lat}, {lng})")
            except Exception as e:
                logger.error(f"❌ Ошибка при получении timezone: {e}")

            session.commit()
            logger.info(f"📍 Координаты пользователя {user_id} обновлены")

    # Переходим в состояние ожидания выбора категории
    await state.set_state(TaskFlow.waiting_for_category)

    # Показываем выбор категории после получения геолокации
    keyboard = [
        [InlineKeyboardButton(text="🍔 Еда", callback_data="task_category:food")],
        [InlineKeyboardButton(text="💪 Здоровье", callback_data="task_category:health")],
        [InlineKeyboardButton(text="🌟 Интересные места", callback_data="task_category:places")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await message.answer(
        "✅ **Геолокация получена!**\n\n"
        "Выберите категорию для получения персонализированных заданий:\n\n"
        "🍔 **Еда** - кафе, рестораны, уличная еда\n"
        "💪 **Здоровье** - спорт, йога, спа, клиники\n"
        "🌟 **Интересные места** - парки, выставки, храмы",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

    logger.info(f"📍 [ЗАДАНИЯ] Показаны категории для пользователя {user_id}")


@main_router.message(F.location)
async def on_location(message: types.Message, state: FSMContext):
    """Обработчик получения геолокации"""
    # Логируем все входящие геолокации для отладки
    user_id = message.from_user.id
    lat = message.location.latitude if message.location else None
    lng = message.location.longitude if message.location else None
    logger.info(f"📍 [DEBUG] Получена геолокация от пользователя {user_id}: lat={lat}, lng={lng}")

    # Проверяем состояние - если это для заданий, не обрабатываем здесь
    current_state = await state.get_state()
    logger.info(f"📍 [DEBUG] Обработчик событий: состояние={current_state}, user_id={user_id}")

    if current_state == TaskFlow.waiting_for_location:
        logger.info("📍 Пропускаем - это для заданий")
        return  # Пропускаем - это для заданий

    # Проверяем, что это состояние для поиска событий
    # Если состояние не установлено, но пользователь отправил геолокацию, устанавливаем состояние автоматически
    # Это особенно важно для MacBook, где состояние может не сохраняться правильно
    if current_state != EventSearch.waiting_for_location:
        logger.warning(
            f"📍 [WARNING] Состояние не EventSearch.waiting_for_location: {current_state}, но обрабатываем геолокацию"
        )
        # Устанавливаем состояние автоматически для удобства пользователя
        await state.set_state(EventSearch.waiting_for_location)
        logger.info(
            f"📍 [DEBUG] Состояние автоматически установлено в EventSearch.waiting_for_location для пользователя {user_id}"
        )

    if not message.location:
        logger.error(f"📍 [ERROR] message.location is None для пользователя {user_id}")
        await message.answer("❌ Ошибка: не удалось получить геолокацию. Попробуйте отправить геолокацию еще раз.")
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

                # Получаем timezone по координатам и сохраняем
                try:
                    tz_name = await get_timezone(lat, lng)
                    if tz_name:
                        user.user_tz = tz_name
                        logger.info(f"🕒 Timezone обновлен для пользователя {message.from_user.id}: {tz_name}")
                    else:
                        logger.warning(f"⚠️ Не удалось получить timezone для координат ({lat}, {lng})")
                except Exception as e:
                    logger.error(f"❌ Ошибка при получении timezone: {e}")

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

            # Определяем город по координатам (для временных границ)
            # Если город не определен, используем UTC для временных границ
            # Поиск все равно идет по радиусу (координатам), независимо от региона
            city = get_city_from_coordinates(lat, lng)
            if not city:
                logger.info(f"ℹ️ Регион не определен по координатам ({lat}, {lng}), используем UTC для временных границ")
                # city останется None, get_city_timezone вернет UTC

            logger.info(
                f"🌍 Поиск событий: координаты=({lat}, {lng}), радиус={radius}км, регион для временных границ={city}"
            )

            # Ищем события (поиск идет по радиусу, независимо от региона)
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
                    "id": event.get("id"),  # Добавляем id для отслеживания кликов
                    "title": event["title"],
                    "description": event["description"],
                    "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
                    "starts_at": event["starts_at"],  # Добавляем поле starts_at!
                    "city": event.get("city"),  # Город события (может быть None)
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
                current_radius = int(radius)

                # Получаем date_filter из состояния пользователя (по умолчанию "today")
                date_filter_state = user_state.get(message.chat.id, {}).get("date_filter", "today")

                keyboard_buttons = []

                # Добавляем кнопки фильтрации даты (Сегодня/Завтра)
                if date_filter_state == "today":
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(text="📅 Сегодня ✅", callback_data="date_filter:today"),
                            InlineKeyboardButton(text="📅 Завтра", callback_data="date_filter:tomorrow"),
                        ]
                    )
                else:
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(text="📅 Сегодня", callback_data="date_filter:today"),
                            InlineKeyboardButton(text="📅 Завтра ✅", callback_data="date_filter:tomorrow"),
                        ]
                    )

                # Добавляем кнопки радиуса
                keyboard_buttons.extend(build_radius_inline_buttons(current_radius))

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
                    "date_filter": date_filter_state,  # Используем date_filter из состояния
                    "diag": diag,
                    "region": region,
                }
                logger.info(
                    f"💾 Состояние сохранено для пользователя {message.chat.id}: lat={lat}, lng={lng}, radius={current_radius}, region={region}, date_filter={date_filter_state}"
                )

                higher_options = [r for r in RADIUS_OPTIONS if r > current_radius]
                suggested_radius = (
                    higher_options[0]
                    if higher_options
                    else next((r for r in RADIUS_OPTIONS if r < current_radius), current_radius)
                )
                suggestion_line = (
                    f"💡 Попробуй изменить радиус до {suggested_radius} км\n"
                    if suggested_radius != current_radius
                    else "💡 Попробуй изменить радиус и повторить поиск\n"
                )

                # Формируем текст сообщения в зависимости от фильтра даты
                date_text = "на сегодня" if date_filter_state == "today" else "на завтра"

                await message.answer(
                    f"📅 В радиусе {current_radius} км событий {date_text} не найдено.\n\n"
                    f"{suggestion_line}"
                    f"➕ Или создай своё событие и собери свою компанию!",
                    reply_markup=inline_kb,
                )

                # Отправляем главное меню после сообщения о том, что события не найдены
                await send_spinning_menu(message)
                # Очищаем состояние FSM после завершения поиска
                await state.clear()
                return

            # Сохраняем состояние для пагинации и расширения радиуса
            # map_message_id будет добавлен после отправки карты
            state_dict = {
                "prepared": prepared,
                "counts": counts,
                "lat": lat,
                "lng": lng,
                "radius": int(radius),
                "page": 1,
                "date_filter": "today",  # По умолчанию показываем события на сегодня
                "diag": diag,
            }
            user_state[message.chat.id] = state_dict
            logger.info(
                f"💾 Состояние сохранено для пользователя {message.chat.id}: lat={lat}, lng={lng}, radius={radius}"
            )

            # 4) Формируем заголовок с правильным отчётом
            header_html = render_header(counts, radius_km=int(radius))

            # 5) Обогащаем события reverse geocoding для названий локаций
            prepared = await enrich_events_with_reverse_geocoding(prepared)

            # Логируем результаты обогащения для отладки
            for i, event in enumerate(prepared[:3], 1):
                logger.info(
                    f"🔍 После обогащения событие {i}: '{event.get('title', 'Без названия')[:30]}' - "
                    f"location_name='{event.get('location_name')}', lat={event.get('lat')}, lng={event.get('lng')}"
                )

            # 6) Рендерим события для первой страницы (теперь 8 событий, так как карта отдельно)
            page_html, total_pages = render_page(prepared, page=1, page_size=8, user_id=message.from_user.id)
            short_caption = header_html + "\n\n" + page_html

            if len(prepared) > 8:
                short_caption += f"\n\n... и еще {len(prepared) - 8} событий"

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
            # maps_url = create_enhanced_google_maps_url(lat, lng, prepared[:12])  # Не используется в объединенном сообщении

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

            # Короткая подпись больше не нужна - используем полный текст с событиями

            # Удаляем сообщение загрузки
            try:
                await loading_message.delete()
            except Exception:
                pass

            # ИСПРАВЛЕНИЕ: Отправляем карту и список событий ОТДЕЛЬНЫМИ сообщениями
            try:
                # Создаем полный текст с событиями (как в send_compact_events_list_prepared)
                # 1) Обогащаем события названиями мест и расстояниями
                for event in prepared:
                    enrich_venue_name(event)
                    event["distance_km"] = round(haversine_km(lat, lng, event.get("lat"), event.get("lng")), 1)

                # 2) Подсчитываем события по типам для сводки
                groups = group_by_type(prepared)
                counts = make_counts(groups)

                # 3) Создаем заголовок с событиями
                header_html = render_header(counts, radius_km=int(radius))

                # 4) Обогащаем события reverse geocoding для названий локаций
                prepared = await enrich_events_with_reverse_geocoding(prepared)

                # 5) Рендерим события для первой страницы
                # ИСПРАВЛЕНИЕ: Теперь карта и список событий отправляются отдельными сообщениями
                # Это позволяет показывать больше событий сразу (без ограничения 1024 байта для caption)
                page_size = 8  # Показываем 8 событий на первой странице (как и на остальных)
                page_html, total_pages = render_page(
                    prepared, page=1, page_size=page_size, user_id=message.from_user.id, is_caption=False
                )
                events_text = header_html + "\n\n" + page_html
                logger.info(f"🔍 page_size для первой страницы: {page_size} событий (карта и список разделены)")

                # 4.5) Логируем показ событий в списке (list_view)
                from database import get_engine

                engine = get_engine()
                participation_analytics = UserParticipationAnalytics(engine)

                # Определяем group_chat_id (NULL для World, значение для Community)
                group_chat_id = None
                if message.chat.type != "private":
                    group_chat_id = message.chat.id

                # Логируем каждое показанное событие на первой странице
                shown_events = prepared[:5]  # Первые 5 событий на странице
                for event in shown_events:
                    event_id = event.get("id")
                    if event_id:
                        logger.info(
                            f"📊 Логируем list_view: user_id={message.from_user.id}, event_id={event_id}, group_chat_id={group_chat_id}"
                        )
                        participation_analytics.record_list_view(
                            user_id=message.from_user.id,
                            event_id=event_id,
                            group_chat_id=group_chat_id,
                        )
                    else:
                        logger.warning(f"⚠️ У события нет id для логирования: {event.get('title', 'Без названия')[:30]}")

                # 5) Правильный расчет total_pages (теперь все страницы по 8 событий, так как карта отдельно)
                total_pages = max(1, ceil(len(prepared) / page_size))
                if total_pages > 1:
                    events_text += f"\n\n📄 Страница 1 из {total_pages}"

                # 6) Создаем клавиатуру с пагинацией И расширением радиуса
                # Используем date_filter из состояния (по умолчанию "today")
                date_filter_state = user_state.get(message.chat.id, {}).get("date_filter", "today")
                combined_keyboard = kb_pager(1, total_pages, int(radius), date_filter=date_filter_state)

                # 7) НОВАЯ ЛОГИКА: Отправляем карту и список событий ОТДЕЛЬНЫМИ сообщениями
                # Это решает проблему с лимитом 1024 байта для caption и позволяет показывать больше событий
                if map_bytes:
                    # 7.1) Отправляем карту отдельным сообщением (без caption или с минимальным текстом)
                    from aiogram.types import BufferedInputFile

                    map_file = BufferedInputFile(map_bytes, filename="map.png")
                    map_caption = "📍 Карта событий"  # Единая подпись без указания радиуса
                    map_message = await message.answer_photo(
                        map_file,
                        caption=map_caption,
                        parse_mode="HTML",
                    )
                    logger.info("✅ Карта отправлена отдельным сообщением")

                    # Сохраняем message_id карты в состоянии для последующего редактирования
                    if message.chat.id in user_state:
                        user_state[message.chat.id]["map_message_id"] = map_message.message_id
                        logger.info(
                            f"🗺️ [ПЕРВЫЙ ПОИСК] map_message_id={map_message.message_id} сохранен в существующем состоянии"
                        )
                    else:
                        # Если состояния еще нет, создаем его
                        user_state[message.chat.id] = {"map_message_id": map_message.message_id}
                        logger.info(
                            f"🗺️ [ПЕРВЫЙ ПОИСК] map_message_id={map_message.message_id} сохранен в новом состоянии"
                        )

                    # 7.2) Отправляем список событий отдельным текстовым сообщением
                    list_message = await message.answer(
                        events_text,
                        reply_markup=combined_keyboard,
                        parse_mode="HTML",
                    )
                    logger.info("✅ Список событий отправлен отдельным сообщением")

                    # Сохраняем message_id списка событий в состоянии для последующего редактирования
                    if message.chat.id in user_state:
                        user_state[message.chat.id]["list_message_id"] = list_message.message_id
                        logger.info(
                            f"📋 [ПЕРВЫЙ ПОИСК] list_message_id={list_message.message_id} сохранен в существующем состоянии"
                        )
                    else:
                        # Если состояния еще нет, создаем его
                        if not user_state.get(message.chat.id):
                            user_state[message.chat.id] = {}
                        user_state[message.chat.id]["list_message_id"] = list_message.message_id
                        logger.info(
                            f"📋 [ПЕРВЫЙ ПОИСК] list_message_id={list_message.message_id} сохранен в новом состоянии"
                        )
                else:
                    # Отправляем без карты, но с полным списком событий
                    list_message = await message.answer(
                        events_text,
                        reply_markup=combined_keyboard,
                        parse_mode="HTML",
                    )
                    logger.info("✅ События отправлены в одном сообщении без карты")

                    # Сохраняем message_id списка событий в состоянии для последующего редактирования
                    if message.chat.id in user_state:
                        user_state[message.chat.id]["list_message_id"] = list_message.message_id
                        logger.info(f"📋 [ПЕРВЫЙ ПОИСК БЕЗ КАРТЫ] list_message_id={list_message.message_id} сохранен")
                    else:
                        if not user_state.get(message.chat.id):
                            user_state[message.chat.id] = {}
                        user_state[message.chat.id]["list_message_id"] = list_message.message_id
                        logger.info(
                            f"📋 [ПЕРВЫЙ ПОИСК БЕЗ КАРТЫ] list_message_id={list_message.message_id} сохранен в новом состоянии"
                        )

                # Отправляем главное меню после объединенного сообщения
                await send_spinning_menu(message)
                # Очищаем состояние FSM после завершения поиска
                await state.clear()

            except Exception as e:
                logger.error(f"❌ Ошибка отправки объединенного сообщения: {e}")
                # Fallback - отправляем простое сообщение как раньше
                try:
                    await message.answer(
                        f"📋 Найдено {len(prepared)} событий в радиусе {radius} км",
                        reply_markup=main_menu_kb(),
                        parse_mode="HTML",
                    )
                    logger.info("✅ Отправлен fallback после ошибки объединения")
                except Exception as e2:
                    logger.error(f"❌ Критическая ошибка fallback: {e2}")

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


@main_router.message(Command("create"))
@main_router.message(F.text == "➕ Создать")
async def on_create(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Создать'"""
    # Инкрементируем сессию World (с проверкой времени)
    if message.chat.type == "private":
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(message.from_user.id, min_interval_minutes=6)

    await state.set_state(EventCreation.waiting_for_title)
    await message.answer(
        '➕ **Создаём событие "World"**\n\n'
        "- Будет видно для всех игроков бота.\n\n"
        "Награда 5 🚀\n\n"
        "**Введите название мероприятия** (например: Прогулка):",
        parse_mode="Markdown",
        reply_markup=types.ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True),
    )


@main_router.message(F.text == "❌ Отмена")
async def cancel_creation(message: types.Message, state: FSMContext):
    """Отмена создания события"""
    await state.clear()
    await message.answer("Создание отменено.", reply_markup=main_menu_kb())


@main_router.message(Command("myevents"))
@main_router.message(F.text == "📋 Мои события")
async def on_my_events(message: types.Message):
    """Обработчик кнопки 'Мои события' с управлением статусами"""
    user_id = message.from_user.id
    logger.info(f"🔍 on_my_events: запрос от пользователя {user_id}")

    # Инкрементируем сессию World (с проверкой времени)
    if message.chat.type == "private":
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(user_id, min_interval_minutes=6)

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

        # Показываем также недавно закрытые события (за последние 24 часа)
        from datetime import datetime, timedelta

        import pytz

        tz_bali = pytz.timezone("Asia/Makassar")
        now_bali = datetime.now(tz_bali)
        day_ago = now_bali - timedelta(hours=24)

        recent_closed_events = []
        for e in events:
            if e.get("status") == "closed":
                # Проверяем дату закрытия (updated_at_utc), а не дату начала события
                updated_at = e.get("updated_at_utc")
                if updated_at:
                    # Конвертируем UTC в местное время Бали для сравнения
                    local_time = updated_at.astimezone(tz_bali)
                    # Проверяем, что событие было закрыто недавно (в пределах 24 часов)
                    if local_time >= day_ago:
                        recent_closed_events.append(e)

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
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = "Время уточняется"

                # Экранируем специальные символы Markdown (сначала \, потом остальные)
                escaped_title = (
                    title.replace("\\", "\\\\")
                    .replace("*", "\\*")
                    .replace("_", "\\_")
                    .replace("`", "\\`")
                    .replace("[", "\\[")
                )
                escaped_location = (
                    location.replace("\\", "\\\\")
                    .replace("*", "\\*")
                    .replace("_", "\\_")
                    .replace("`", "\\`")
                    .replace("[", "\\[")
                )

                text_parts.append(f"{i}) {escaped_title}\n🕐 {time_str}\n📍 {escaped_location}\n")

            if len(active_events) > 3:
                text_parts.append(f"... и еще {len(active_events) - 3} событий")

        # Показываем недавно закрытые события
        if recent_closed_events:
            text_parts.append(f"\n🔴 **Недавно закрытые ({len(recent_closed_events)}):**")
            for i, event in enumerate(recent_closed_events[:3], 1):
                title = event.get("title", "Без названия")
                location = event.get("location_name", "Место уточняется")
                starts_at = event.get("starts_at")

                if starts_at:
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = "Время уточняется"

                escaped_title = (
                    title.replace("\\", "\\\\")
                    .replace("*", "\\*")
                    .replace("_", "\\_")
                    .replace("`", "\\`")
                    .replace("[", "\\[")
                )
                escaped_location = (
                    location.replace("\\", "\\\\")
                    .replace("*", "\\*")
                    .replace("_", "\\_")
                    .replace("`", "\\`")
                    .replace("[", "\\[")
                )

                text_parts.append(f"{i}) {escaped_title}\n🕐 {time_str}\n📍 {escaped_location} (закрыто)\n")

            if len(recent_closed_events) > 3:
                text_parts.append(f"... и еще {len(recent_closed_events) - 3} закрытых событий")

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
            # Экранируем специальные символы Markdown (сначала \, потом остальные)
            escaped_title = (
                title.replace("\\", "\\\\")
                .replace("*", "\\*")
                .replace("_", "\\_")
                .replace("`", "\\`")
                .replace("[", "\\[")
            )
            text_parts.append(f"{i}) {escaped_title} – {time_str}")

        if len(all_participations) > 3:
            text_parts.append(f"... и еще {len(all_participations) - 3} событий")

    # Добавляем информацию о раздельном удалении событий в конце
    if events or all_participations:
        text_parts.append("\nℹ️ События в версии Community и World удаляются отдельно")

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

    # Пытаемся отправить с изображением (всегда, независимо от наличия событий)
    import os
    from pathlib import Path

    # Используем изображение my_events.png
    photo_path = Path(__file__).parent / "images" / "my_events.png"

    logger.info(f"🖼️ Проверяем наличие изображения: {photo_path}, exists={os.path.exists(photo_path)}")

    if os.path.exists(photo_path):
        try:
            from aiogram.types import FSInputFile

            photo = FSInputFile(photo_path)
            logger.info(f"✅ Отправляем изображение для 'Мои события': {photo_path}")
            await message.answer_photo(photo, caption=text, reply_markup=keyboard, parse_mode="Markdown")
            logger.info("✅ on_my_events: сообщение с изображением отправлено успешно")
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото для 'Мои события': {e}", exc_info=True)
            # Продолжаем отправку текста
    else:
        logger.warning(f"⚠️ Изображение не найдено: {photo_path}")

    # Fallback: отправляем только текст
    try:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        logger.info("✅ on_my_events: сообщение отправлено успешно")
    except Exception as e:
        logger.error(f"❌ on_my_events: ошибка отправки сообщения: {e}")
        # Fallback - отправляем то же сообщение без Markdown
        await message.answer(text, reply_markup=keyboard)


@main_router.message(Command("share"))
@main_router.message(F.text == "🔗 Добавить бота в чат")
async def on_share(message: types.Message):
    """Обработчик кнопки 'Добавить бота в чат'"""
    bot_info = await get_bot_info_cached()
    text = (
        '🤝Версия "Community"- наведет структуру и порядок событий в вашем чате.\n\n'
        "🚀 **Награда: За добавление бота в чат 150 ракет !!!** 🚀\n\n"
        "Инструкция:\n\n"
        "Для супергрупп !!!\n"
        "Заходите с Web 💻\n"
        "Сможете добавить в конкретную Тему\n\n"
        "1) Нажми на ссылку и выбери чат\n"
        f"t.me/{bot_info.username}?startgroup=true\n\n"
        "2) Предоставьте права админ\n\n"
        "3) Разрешите удалять сообщения\n\n"
        "Бот автоматически\n"
        "чистит свои сообщения в чате\n\n"
        "Теперь все события в одном месте ❤"
    )

    # Пытаемся отправить фото, если оно есть (поддерживаем разные форматы)
    photo_paths = [
        "images/community_instruction.jpg",
        "images/community_instruction.png",
        "images/community_instruction.webp",
        "images/community_instruction.jpeg",
    ]

    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            try:
                from aiogram.types import FSInputFile

                photo = FSInputFile(photo_path)
                await message.answer_photo(photo, caption=text, reply_markup=main_menu_kb())
                return
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить фото инструкции: {e}, отправляем только текст")
                break

    # Если фото нет или произошла ошибка, отправляем только текст
    await message.answer(text, reply_markup=main_menu_kb())


def is_admin_user(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    from config import load_settings

    settings = load_settings()
    return user_id in settings.admin_ids


@main_router.message(Command("ban"))
async def on_ban(message: types.Message):
    """Команда для бана пользователя (только для админов)"""
    if not is_admin_user(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return

    try:
        command_parts = message.text.split(maxsplit=2)
        if len(command_parts) < 2:
            await message.answer(
                "Использование: /ban <user_id> [дни] [причина]\n\n"
                "Примеры:\n"
                "/ban 123456789 - забанить навсегда\n"
                "/ban 123456789 7 - забанить на 7 дней\n"
                "/ban 123456789 30 Спам - забанить на 30 дней с причиной"
            )
            return

        user_id_to_ban = int(command_parts[1])
        days = None
        reason = None

        if len(command_parts) >= 3:
            # Пытаемся распарсить дни
            try:
                days = int(command_parts[2])
            except ValueError:
                # Если не число, значит это причина
                reason = command_parts[2]

        if len(command_parts) >= 4:
            reason = command_parts[3]

        # Получаем информацию о пользователе (если есть в сообщении)
        username = None
        first_name = None
        if message.reply_to_message:
            replied_user = message.reply_to_message.from_user
            username = replied_user.username
            first_name = replied_user.first_name
            user_id_to_ban = replied_user.id

        from database import get_engine
        from utils.ban_service import BanService

        engine = get_engine()
        ban_service = BanService(engine)

        success = ban_service.ban_user(
            user_id=user_id_to_ban,
            banned_by=message.from_user.id,
            reason=reason,
            username=username,
            first_name=first_name,
            days=days,
        )

        if success:
            ban_text = f"🚫 Пользователь {user_id_to_ban}"
            if username:
                ban_text += f" (@{username})"
            if days:
                ban_text += f" забанен на {days} дней"
            else:
                ban_text += " забанен навсегда"
            if reason:
                ban_text += f"\nПричина: {reason}"
            await message.answer(ban_text)
        else:
            await message.answer("❌ Ошибка при бане пользователя")

    except ValueError:
        await message.answer("❌ ID пользователя должен быть числом")
    except Exception as e:
        logger.error(f"Ошибка в команде ban: {e}")
        await message.answer(f"❌ Произошла ошибка: {e}")


@main_router.message(Command("unban"))
async def on_unban(message: types.Message):
    """Команда для разбана пользователя (только для админов)"""
    if not is_admin_user(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return

    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.answer(
                "Использование: /unban <user_id>\n\n" "Или ответьте на сообщение пользователя командой /unban"
            )
            return

        user_id_to_unban = int(command_parts[1])

        # Если это ответ на сообщение, берем ID из сообщения
        if message.reply_to_message:
            user_id_to_unban = message.reply_to_message.from_user.id

        from database import get_engine
        from utils.ban_service import BanService

        engine = get_engine()
        ban_service = BanService(engine)

        success = ban_service.unban_user(user_id_to_unban)

        if success:
            await message.answer(f"✅ Пользователь {user_id_to_unban} разбанен")
        else:
            await message.answer(f"⚠️ Пользователь {user_id_to_unban} не найден в списке банов")

    except ValueError:
        await message.answer("❌ ID пользователя должен быть числом")
    except Exception as e:
        logger.error(f"Ошибка в команде unban: {e}")
        await message.answer(f"❌ Произошла ошибка: {e}")


@main_router.message(Command("banlist"))
async def on_banlist(message: types.Message):
    """Команда для просмотра списка забаненных пользователей (только для админов)"""
    if not is_admin_user(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return

    try:
        from database import get_engine
        from utils.ban_service import BanService

        engine = get_engine()
        ban_service = BanService(engine)

        banned_users = ban_service.get_banned_users(limit=20)

        if not banned_users:
            await message.answer("📋 Список забаненных пользователей пуст")
            return

        text_lines = ["🚫 <b>Забаненные пользователи:</b>\n"]
        for ban in banned_users:
            user_info = f"ID: {ban['user_id']}"
            if ban["username"]:
                user_info += f" (@{ban['username']})"
            if ban["first_name"]:
                user_info += f" - {ban['first_name']}"

            text_lines.append(f"• {user_info}")
            if ban["reason"]:
                text_lines.append(f"  Причина: {ban['reason']}")
            if ban["expires_at"]:
                expires_str = ban["expires_at"].strftime("%d.%m.%Y %H:%M")
                text_lines.append(f"  До: {expires_str}")
            else:
                text_lines.append("  Навсегда")
            text_lines.append("")

        text = "\n".join(text_lines)
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в команде banlist: {e}")
        await message.answer(f"❌ Произошла ошибка: {e}")


@main_router.message(Command("admin_event"))
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


@main_router.message(Command("diag_webhook"))
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


@main_router.message(Command("diag_commands"))
async def on_diag_commands(message: types.Message):
    """Диагностика команд бота"""
    try:
        from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeDefault

        info_lines = ["🔧 <b>Диагностика команд бота</b>", ""]

        # Проверяем Menu Button
        try:
            menu_button = await bot.get_chat_menu_button()
            info_lines.append(f"📱 <b>Menu Button:</b> {menu_button}")
            if hasattr(menu_button, "type"):
                info_lines.append(f"   <b>Тип:</b> {menu_button.type}")
        except Exception as e:
            info_lines.append(f"❌ <b>Ошибка получения Menu Button:</b> {e}")

        info_lines.append("")

        # Проверяем команды по scope'ам
        for scope_name, scope in [
            ("Default", BotCommandScopeDefault()),
            ("PrivateChats", BotCommandScopeAllPrivateChats()),
            ("GroupChats", BotCommandScopeAllGroupChats()),
        ]:
            info_lines.append(f"<b>{scope_name}:</b>")

            # Без языка
            try:
                commands = await bot.get_my_commands(scope=scope)
                info_lines.append(f"  <b>EN:</b> {len(commands)} команд")
                for cmd in commands:
                    info_lines.append(f"    - /{cmd.command}: {cmd.description}")
            except Exception as e:
                info_lines.append(f"  <b>EN:</b> ❌ {e}")

            # Русская локаль
            try:
                commands_ru = await bot.get_my_commands(scope=scope, language_code="ru")
                info_lines.append(f"  <b>RU:</b> {len(commands_ru)} команд")
                for cmd in commands_ru:
                    info_lines.append(f"    - /{cmd.command}: {cmd.description}")
            except Exception as e:
                info_lines.append(f"  <b>RU:</b> ❌ {e}")

            info_lines.append("")

        await message.answer("\n".join(info_lines), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в диагностике команд: {e}")
        await message.answer(f"❌ Ошибка диагностики команд: {e}")


@main_router.message(Command("diag_last"))
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


@main_router.message(Command("diag_all"))
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


@main_router.message(Command("diag_search"))
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


@main_router.message(F.text == "🎯 Чем заняться")
async def on_tasks_goal(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Чем заняться' - объяснение и запрос геолокации"""
    # Устанавливаем состояние для заданий
    await state.set_state(TaskFlow.waiting_for_location)

    # Создаем клавиатуру с кнопкой геолокации (one_time_keyboard=False - кнопка не исчезнет на MacBook)
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="🌍 Найти на карте")],
            [KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,  # Изменено на False, чтобы кнопка не исчезала на MacBook
    )

    quest_text = (
        "🎯 Чем заняться\nНаграда 3 🚀\n\n"
        "Самое время развлечься и получить награды.\n\n"
        "Нажмите кнопку '📍 Отправить геолокацию' чтобы начать!\n\n"
        "💡 Если кнопка не работает :\n\n"
        "• Жми '🌍 Найти на карте' \n"
        "и вставь ссылку \n\n"
        "• Или отправь координаты\n"
        "пример: -8.4095, 115.1889"
    )

    # Пытаемся отправить фото, если оно есть (поддерживаем разные форматы)
    photo_paths = [
        "images/quests_instruction.jpg",
        "images/quests_instruction.png",
        "images/quests_instruction.webp",
        "images/quests_instruction.jpeg",
    ]

    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            try:
                from aiogram.types import FSInputFile

                photo = FSInputFile(photo_path)
                await message.answer_photo(
                    photo, caption=quest_text, parse_mode="Markdown", reply_markup=location_keyboard
                )
                return
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить фото квестов: {e}, отправляем только текст")
                break

    # Если фото нет или произошла ошибка, отправляем только текст
    await message.answer(quest_text, parse_mode="Markdown", reply_markup=location_keyboard)


@main_router.message(F.text == "🏆 Мои квесты")
async def on_my_tasks(message: types.Message):
    """Обработчик кнопки 'Мои квесты'"""
    user_id = message.from_user.id

    # Автомодерация: помечаем истекшие задания (отключено - ограничение по времени снято)
    # from tasks_service import mark_tasks_as_expired
    # try:
    #     expired_count = mark_tasks_as_expired()
    #     if expired_count > 0:
    #         await message.answer(f"🤖 Автоматически истекло {expired_count} просроченных заданий")
    # except Exception as e:
    #     logger.error(f"Ошибка автомодерации заданий для пользователя {user_id}: {e}")

    # Получаем активные задания пользователя
    active_tasks = get_user_active_tasks(user_id)

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем текст сообщения
    if not active_tasks:
        message_text = (
            "🏆 **Мои квесты**\n\n"
            "У вас пока нет активных заданий.\n\n"
            f"**Баланс {rocket_balance} 🚀**\n\n"
            "🎯 Нажмите 'Чем заняться' чтобы получить новые задания!"
        )
        # Клавиатура не нужна, когда нет заданий
        keyboard = None
    else:
        # Формируем сообщение со списком активных заданий
        message_text = "📋 **Ваши активные задания:**\n\n"
        message_text += "Прохождение + 3 🚀\n\n"
        message_text += f"**Баланс {rocket_balance} 🚀**\n\n"

        for i, task in enumerate(active_tasks, 1):
            # Время выполнения больше не показываем - ограничение по времени снято

            category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
            category_emoji = category_emojis.get(task["category"], "📋")

            message_text += f"{i}) {category_emoji} **{task['title']}**\n"

            # Показываем локацию, если есть
            if task.get("place_name") or task.get("place_url"):
                place_name = task.get("place_name", "Место на карте")
                place_url = task.get("place_url")
                distance = task.get("distance_km")

                if place_url:
                    if distance:
                        message_text += f"📍 **Место:** [{place_name} ({distance:.1f} км)]({place_url})\n"
                    else:
                        message_text += f"📍 **Место:** [{place_name}]({place_url})\n"
                else:
                    if distance:
                        message_text += f"📍 **Место:** {place_name} ({distance:.1f} км)\n"
                    else:
                        message_text += f"📍 **Место:** {place_name}\n"

            # Показываем промокод, если есть
            if task.get("promo_code"):
                message_text += f"🎁 **Промокод:** `{task['promo_code']}`\n"

            message_text += "\n"

        # Добавляем кнопку управления заданиями
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔧 Управление заданиями", callback_data="manage_tasks")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
            ]
        )

    # Пытаемся отправить с изображением (всегда, независимо от наличия заданий)
    import os
    from pathlib import Path

    # Используем одно имя файла
    photo_path = Path(__file__).parent / "images" / "my_quests.png"

    logger.info(f"🖼️ Проверяем наличие изображения: {photo_path}, exists={os.path.exists(photo_path)}")

    if os.path.exists(photo_path):
        try:
            from aiogram.types import FSInputFile

            photo = FSInputFile(photo_path)
            logger.info(f"✅ Отправляем изображение для 'Мои квесты': {photo_path}")
            if keyboard:
                await message.answer_photo(photo, caption=message_text, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await message.answer_photo(photo, caption=message_text, parse_mode="Markdown")
            logger.info("✅ on_my_tasks: сообщение с изображением отправлено успешно")
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото для 'Мои квесты': {e}", exc_info=True)
            # Продолжаем отправку текста
    else:
        logger.warning(f"⚠️ Изображение не найдено: {photo_path}")

    # Fallback: отправляем только текст
    if keyboard:
        await message.answer(message_text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await message.answer(message_text, parse_mode="Markdown")


@main_router.message(Command("tasks"))
async def cmd_tasks(message: types.Message, state: FSMContext):
    """Обработчик команды /tasks - Чем заняться"""
    # Инкрементируем сессию World (с проверкой времени)
    if message.chat.type == "private":
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(message.from_user.id, min_interval_minutes=6)

    # Устанавливаем состояние для заданий
    await state.set_state(TaskFlow.waiting_for_location)

    # Создаем клавиатуру с кнопкой геолокации
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="🌍 Найти на карте")],
            [KeyboardButton(text="🏠 Главное меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    quest_text = "🎯 Чем заняться\nНаграда 3 🚀\n\nСамое время развлечься и получить награды.\n\nНажмите кнопку **'📍 Отправить геолокацию'** чтобы начать!"

    # Пытаемся отправить фото, если оно есть (поддерживаем разные форматы)
    photo_paths = [
        "images/quests_instruction.jpg",
        "images/quests_instruction.png",
        "images/quests_instruction.webp",
        "images/quests_instruction.jpeg",
    ]

    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            try:
                from aiogram.types import FSInputFile

                photo = FSInputFile(photo_path)
                await message.answer_photo(
                    photo, caption=quest_text, parse_mode="Markdown", reply_markup=location_keyboard
                )
                return
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить фото квестов: {e}, отправляем только текст")
                break

    # Если фото нет или произошла ошибка, отправляем только текст
    await message.answer(quest_text, parse_mode="Markdown", reply_markup=location_keyboard)


@main_router.message(Command("mytasks"))
async def cmd_mytasks(message: types.Message):
    """Обработчик команды /mytasks - Мои квесты"""
    user_id = message.from_user.id

    # Инкрементируем сессию World (с проверкой времени)
    if message.chat.type == "private":
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(user_id, min_interval_minutes=6)

    # Автомодерация: помечаем истекшие задания (отключено - ограничение по времени снято)
    # from tasks_service import mark_tasks_as_expired
    # try:
    #     expired_count = mark_tasks_as_expired()
    #     if expired_count > 0:
    #         await message.answer(f"🤖 Автоматически истекло {expired_count} просроченных заданий")
    # except Exception as e:
    #     logger.error(f"Ошибка автомодерации заданий для пользователя {user_id}: {e}")

    # Получаем активные задания пользователя
    active_tasks = get_user_active_tasks(user_id)

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем текст сообщения
    if not active_tasks:
        message_text = (
            "🏆 **Мои квесты**\n\n"
            "У вас пока нет активных заданий.\n\n"
            f"**Баланс {rocket_balance} 🚀**\n\n"
            "🎯 Нажмите 'Чем заняться' чтобы получить новые задания!"
        )
        # Клавиатура не нужна, когда нет заданий
        keyboard = None
    else:
        # Формируем сообщение со списком активных заданий
        message_text = "📋 **Ваши активные задания:**\n\n"
        message_text += "Прохождение + 3 🚀\n\n"
        message_text += f"**Баланс {rocket_balance} 🚀**\n\n"

        for i, task in enumerate(active_tasks, 1):
            # Время выполнения больше не показываем - ограничение по времени снято

            category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
            category_emoji = category_emojis.get(task["category"], "📋")

            message_text += f"{i}) {category_emoji} **{task['title']}**\n"

            # Показываем локацию, если есть
            if task.get("place_name") or task.get("place_url"):
                place_name = task.get("place_name", "Место на карте")
                place_url = task.get("place_url")
                distance = task.get("distance_km")

                if place_url:
                    if distance:
                        message_text += f"📍 **Место:** [{place_name} ({distance:.1f} км)]({place_url})\n"
                    else:
                        message_text += f"📍 **Место:** [{place_name}]({place_url})\n"
                else:
                    if distance:
                        message_text += f"📍 **Место:** {place_name} ({distance:.1f} км)\n"
                    else:
                        message_text += f"📍 **Место:** {place_name}\n"

            # Показываем промокод, если есть
            if task.get("promo_code"):
                message_text += f"🎁 **Промокод:** `{task['promo_code']}`\n"

            message_text += "\n"

        # Добавляем кнопку управления заданиями
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔧 Управление заданиями", callback_data="manage_tasks")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
            ]
        )

    # Пытаемся отправить с изображением (всегда, независимо от наличия заданий)
    import os
    from pathlib import Path

    # Используем одно имя файла
    photo_path = Path(__file__).parent / "images" / "my_quests.png"

    logger.info(f"🖼️ Проверяем наличие изображения: {photo_path}, exists={os.path.exists(photo_path)}")

    if os.path.exists(photo_path):
        try:
            from aiogram.types import FSInputFile

            photo = FSInputFile(photo_path)
            logger.info(f"✅ Отправляем изображение для 'Мои квесты': {photo_path}")
            if keyboard:
                await message.answer_photo(photo, caption=message_text, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await message.answer_photo(photo, caption=message_text, parse_mode="Markdown")
            logger.info("✅ cmd_mytasks: сообщение с изображением отправлено успешно")
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото для 'Мои квесты': {e}", exc_info=True)
            # Продолжаем отправку текста
    else:
        logger.warning(f"⚠️ Изображение не найдено: {photo_path}")

    # Fallback: отправляем только текст
    if keyboard:
        await message.answer(message_text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await message.answer(message_text, parse_mode="Markdown")


@main_router.callback_query(F.data == "manage_tasks")
async def handle_manage_tasks(callback: types.CallbackQuery):
    """Обработчик кнопки 'Управление заданиями'"""
    user_id = callback.from_user.id
    active_tasks = get_user_active_tasks(user_id)

    if not active_tasks:
        # Проверяем, содержит ли сообщение фото
        if callback.message.photo:
            try:
                chat_id = callback.message.chat.id
                bot = callback.bot
                await callback.message.delete()
                await bot.send_message(
                    chat_id=chat_id,
                    text="🏆 **Мои квесты**\n\n" "У вас нет активных заданий.",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении сообщения с фото: {e}", exc_info=True)
                # Fallback: отправляем новое сообщение
                chat_id = callback.message.chat.id
                bot = callback.bot
                await bot.send_message(
                    chat_id=chat_id,
                    text="🏆 **Мои квесты**\n\n" "У вас нет активных заданий.",
                    parse_mode="Markdown",
                )
        else:
            try:
                await callback.message.edit_text(
                    "🏆 **Мои квесты**\n\n" "У вас нет активных заданий.",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при редактировании сообщения: {e}", exc_info=True)
                # Fallback: отправляем новое сообщение
                chat_id = callback.message.chat.id
                bot = callback.bot
                await bot.send_message(
                    chat_id=chat_id,
                    text="🏆 **Мои квесты**\n\n" "У вас нет активных заданий.",
                    parse_mode="Markdown",
                )
        await callback.answer()
        return

    # Показываем первое задание
    await show_task_detail(callback, active_tasks, 0, user_id)
    await callback.answer()


async def show_task_detail(callback_or_message, tasks: list, task_index: int, user_id: int):
    """Показывает детальную информацию о задании

    Args:
        callback_or_message: Может быть либо CallbackQuery, либо Message объект
        tasks: Список заданий
        task_index: Индекс текущего задания
        user_id: ID пользователя
    """
    task = tasks[task_index]

    # Вычисляем оставшееся время
    expires_at = task["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    time_left = expires_at - datetime.now(UTC)
    int(time_left.total_seconds() / 3600)

    category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
    category_emoji = category_emojis.get(task["category"], "📋")
    category_names = {"food": "Еда", "health": "Здоровье", "places": "Интересные места"}
    category_name = category_names.get(task["category"], task["category"])

    message_text = f"📋 **{task['title']}**\n\n"
    message_text += f"{category_emoji} **Категория:** {category_name}\n"
    message_text += f"📝 **Описание:** {task['description']}\n"
    # Время выполнения больше не показываем - ограничение по времени снято

    # Показываем локацию, если есть
    if task.get("place_name") or task.get("place_url"):
        place_name = task.get("place_name", "Место на карте")
        place_url = task.get("place_url")
        distance = task.get("distance_km")

        if place_url:
            if distance:
                message_text += f"📍 **Место:** [{place_name} ({distance:.1f} км)]({place_url})\n"
            else:
                message_text += f"📍 **Место:** [{place_name}]({place_url})\n"
        else:
            if distance:
                message_text += f"📍 **Место:** {place_name} ({distance:.1f} км)\n"
            else:
                message_text += f"📍 **Место:** {place_name}\n"

    # Показываем промокод, если есть
    if task.get("promo_code"):
        message_text += f"🎁 **Промокод:** `{task['promo_code']}`\n"

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

    # Определяем, является ли это callback или message
    if hasattr(callback_or_message, "message"):
        # Это CallbackQuery
        callback = callback_or_message
        message = callback.message

        # Проверяем, содержит ли сообщение фото (нельзя редактировать сообщения с фото)
        if message.photo:
            # Удаляем старое сообщение с фото и отправляем новое текстовое
            try:
                chat_id = message.chat.id
                bot = callback.bot
                await message.delete()
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении сообщения с фото и отправке нового: {e}", exc_info=True)
                # Fallback: отправляем новое сообщение без удаления старого
                chat_id = message.chat.id
                bot = callback.bot
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
        else:
            # Обычное текстовое сообщение, можно редактировать
            try:
                await message.edit_text(
                    message_text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при редактировании сообщения: {e}", exc_info=True)
                # Fallback: отправляем новое сообщение
                chat_id = message.chat.id
                bot = callback.bot
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
    else:
        # Это Message объект (старый способ вызова для обратной совместимости)
        message = callback_or_message
        try:
            await message.edit_text(
                message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        except Exception as e:
            logger.error(f"❌ Ошибка при редактировании сообщения: {e}", exc_info=True)
            # Fallback: отправляем новое сообщение
            await message.answer(
                message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )


@main_router.callback_query(F.data.startswith("task_nav:"))
async def handle_task_navigation(callback: types.CallbackQuery):
    """Обработчик навигации по заданиям"""
    task_index = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    active_tasks = get_user_active_tasks(user_id)
    if not active_tasks or task_index >= len(active_tasks):
        await callback.answer("Задание не найдено")
        return

    await show_task_detail(callback, active_tasks, task_index, user_id)
    await callback.answer()


@main_router.callback_query(F.data == "my_tasks_list")
async def handle_back_to_tasks_list(callback: types.CallbackQuery):
    """Возврат к списку заданий"""
    user_id = callback.from_user.id
    active_tasks = get_user_active_tasks(user_id)

    if not active_tasks:
        # Получаем баланс ракет пользователя
        from rockets_service import get_user_rockets

        rocket_balance = get_user_rockets(user_id)

        text = (
            "🏆 **Мои квесты**\n\n"
            "У вас пока нет активных заданий.\n\n"
            f"**Баланс {rocket_balance} 🚀**\n\n"
            "🎯 Нажмите 'Чем заняться' чтобы получить новые задания!"
        )

        # Для callback используем edit_text, но можно отправить новое сообщение с фото
        # Пытаемся отправить с изображением
        import os
        from pathlib import Path

        # Используем одно имя файла
        photo_path = Path(__file__).parent / "images" / "my_quests.png"

        logger.info(f"🖼️ Проверяем наличие изображения (callback): {photo_path}, exists={os.path.exists(photo_path)}")

        if os.path.exists(photo_path):
            try:
                from aiogram.types import FSInputFile

                photo = FSInputFile(photo_path)
                logger.info(f"✅ Отправляем изображение для 'Мои квесты' (callback): {photo_path}")
                # Удаляем старое сообщение и отправляем новое с фото
                await callback.message.delete()
                await callback.message.answer_photo(photo, caption=text, parse_mode="Markdown")
                await callback.answer()
                return
            except Exception as e:
                logger.error(f"❌ Ошибка отправки фото для 'Мои квесты' (callback): {e}", exc_info=True)
                # Продолжаем с edit_text
        else:
            logger.warning(f"⚠️ Изображение не найдено (callback): {photo_path}")

        # Fallback: редактируем текст
        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer()
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

        category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
        category_emoji = category_emojis.get(task["category"], "📋")
        # Форматируем время выполнения в компактном виде
        start_time = task["accepted_at"]
        end_time = expires_at
        time_period = f"{start_time.strftime('%d.%m.%Y %H:%M')} → {end_time.strftime('%d.%m.%Y %H:%M')}"

        message_text += f"{i}) {category_emoji} **{task['title']}**\n"
        message_text += f"⏰ **Время на выполнение:** {time_period}\n"

        # Показываем локацию, если есть
        if task.get("place_name") or task.get("place_url"):
            place_name = task.get("place_name", "Место на карте")
            place_url = task.get("place_url")
            distance = task.get("distance_km")

            if place_url:
                if distance:
                    message_text += f"📍 **Место:** [{place_name} ({distance:.1f} км)]({place_url})\n"
                else:
                    message_text += f"📍 **Место:** [{place_name}]({place_url})\n"
            else:
                if distance:
                    message_text += f"📍 **Место:** {place_name} ({distance:.1f} км)\n"
                else:
                    message_text += f"📍 **Место:** {place_name}\n"

        # Показываем промокод, если есть
        if task.get("promo_code"):
            message_text += f"🎁 **Промокод:** `{task['promo_code']}`\n"

        message_text += "\n"

    # Добавляем кнопку управления заданиями
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔧 Управление заданиями", callback_data="manage_tasks")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
        ]
    )

    # Пытаемся отправить с изображением (для callback удаляем старое сообщение)
    import os
    from pathlib import Path

    photo_path = Path(__file__).parent / "images" / "my_quests.png"

    logger.info(
        f"🖼️ Проверяем наличие изображения (callback с заданиями): {photo_path}, exists={os.path.exists(photo_path)}"
    )

    if os.path.exists(photo_path):
        try:
            from aiogram.types import FSInputFile

            photo = FSInputFile(photo_path)
            logger.info(f"✅ Отправляем изображение для 'Мои квесты' (callback с заданиями): {photo_path}")
            # Удаляем старое сообщение и отправляем новое с фото
            await callback.message.delete()
            await callback.message.answer_photo(
                photo, caption=message_text, reply_markup=keyboard, parse_mode="Markdown"
            )
            await callback.answer()
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото для 'Мои квесты' (callback с заданиями): {e}", exc_info=True)
            # Продолжаем с edit_text
    else:
        logger.warning(f"⚠️ Изображение не найдено (callback с заданиями): {photo_path}")

    # Fallback: редактируем текст
    await callback.message.edit_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    await callback.answer()


@main_router.callback_query(F.data == "noop")
async def handle_noop(callback: types.CallbackQuery):
    """Заглушка для кнопок без действия"""
    await callback.answer()


@main_router.callback_query(F.data.startswith("rx:"))
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

    # Определяем city по координатам (как при первом запросе)
    from utils.simple_timezone import get_city_from_coordinates

    city = get_city_from_coordinates(lat, lng)
    if not city:
        # Если город не определен по координатам, используем region из состояния
        city = region
        logger.info(
            f"ℹ️ Регион не определен по координатам ({lat}, {lng}), используем region={region} для временных границ"
        )
    else:
        logger.info(f"🌍 Определен city={city} по координатам ({lat}, {lng}) для временных границ")

    # НЕ показываем сообщение загрузки - сразу редактируем карту и отправляем список
    # Это убирает лишнее сообщение между картой и списком
    current_message = callback.message  # Сохраняем ссылку на текущее сообщение

    # Выполняем поиск с новым радиусом
    from database import get_engine

    engine = get_engine()
    events_service = UnifiedEventsService(engine)

    # Получаем date_filter из состояния (по умолчанию "today")
    date_filter = state_data.get("date_filter", "today")
    date_offset = 0 if date_filter == "today" else 1

    logger.info(f"🔍 РАСШИРЕНИЕ РАДИУСА: radius={new_radius} км, date_filter={date_filter}, date_offset={date_offset}")

    events = events_service.search_events_today(
        city=city,
        user_lat=lat,
        user_lng=lng,
        radius_km=new_radius,
        date_offset=date_offset,
        message_id=f"{callback.message.message_id}",
    )

    # Конвертируем в старый формат для совместимости
    formatted_events = []
    for event in events:
        formatted_event = {
            "title": event["title"],
            "description": event["description"],
            "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
            "starts_at": event["starts_at"],
            "city": event.get("city"),  # Город события (может быть None)
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
        current_radius = new_radius
        keyboard_buttons = []

        # Добавляем кнопки фильтрации даты (Сегодня/Завтра)
        if date_filter == "today":
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(text="📅 Сегодня ✅", callback_data="date_filter:today"),
                    InlineKeyboardButton(text="📅 Завтра", callback_data="date_filter:tomorrow"),
                ]
            )
        else:
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(text="📅 Сегодня", callback_data="date_filter:today"),
                    InlineKeyboardButton(text="📅 Завтра ✅", callback_data="date_filter:tomorrow"),
                ]
            )

        # Добавляем кнопки радиуса
        keyboard_buttons.extend(build_radius_inline_buttons(current_radius))

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

        higher_options = [r for r in RADIUS_OPTIONS if r > current_radius]
        suggested_radius = (
            higher_options[0]
            if higher_options
            else next((r for r in RADIUS_OPTIONS if r < current_radius), current_radius)
        )
        suggestion_line = (
            f"💡 Попробуй изменить радиус до {suggested_radius} км\n"
            if suggested_radius != current_radius
            else "💡 Попробуй изменить радиус и повторить поиск\n"
        )

        # Формируем текст сообщения в зависимости от фильтра даты
        date_text = "на сегодня" if date_filter == "today" else "на завтра"

        await callback.message.edit_text(
            f"📅 В радиусе {current_radius} км событий {date_text} не найдено.\n\n"
            f"{suggestion_line}"
            f"➕ Или создай своё событие и собери свою компанию!",
            reply_markup=inline_kb,
        )

        await callback.answer()
        return

    # Если найдены события, отправляем их
    # Группируем и считаем
    groups = group_by_type(prepared)
    counts = make_counts(groups)

    # Сохраняем map_message_id и list_message_id ДО обновления состояния, чтобы использовать их для редактирования
    map_message_id = state_data.get("map_message_id")
    list_message_id = state_data.get("list_message_id")
    logger.info(
        f"🗺️ [РАСШИРЕНИЕ РАДИУСА] map_message_id из состояния: {map_message_id}, list_message_id: {list_message_id}"
    )

    # Обновляем состояние (сохраняем map_message_id и list_message_id для редактирования)
    update_user_state_timestamp(chat_id)
    user_state[chat_id] = {
        "prepared": prepared,
        "counts": counts,
        "lat": lat,
        "lng": lng,
        "radius": new_radius,
        "page": 1,
        "date_filter": date_filter,  # Сохраняем текущий фильтр даты
        "diag": {"kept": len(prepared), "dropped": 0, "reasons_top3": []},
        "region": region,
        "map_message_id": map_message_id,  # Сохраняем message_id карты для редактирования
        "list_message_id": list_message_id,  # Сохраняем message_id списка событий для редактирования
    }
    logger.info(
        f"✅ РАДИУС РАСШИРЕН: новый радиус={new_radius} км, найдено событий={len(prepared)}, "
        f"date_filter={date_filter}, map_message_id={map_message_id} сохранен в состоянии"
    )

    # Обогащаем события reverse geocoding для названий локаций
    prepared = await enrich_events_with_reverse_geocoding(prepared)

    # Рендерим страницу
    header_html = render_header(counts, radius_km=new_radius)
    events_text, total_pages = render_page(prepared, 1, page_size=8, user_id=user_id)

    text = header_html + "\n\n" + events_text

    # Создаем клавиатуру с кнопками пагинации и расширения радиуса
    keyboard = kb_pager(1, total_pages, new_radius, date_filter=date_filter)

    # Отправляем результаты с картой (как в основном поиске)
    try:
        # Сначала пытаемся создать карту (как в основном коде)
        from config import load_settings
        from utils.static_map import build_static_map_url, fetch_static_map

        settings = load_settings()
        map_bytes = None
        try:
            # Создаем точки событий для карты
            points = []
            for event in prepared[:12]:  # Максимум 12 событий на карте
                if event.get("lat") and event.get("lng"):
                    # Определяем тип события для иконки
                    event_type = event.get("type", "source")
                    if event_type == "user":
                        icon = "👤"
                    elif event_type in ["ai", "ai_parsed", "ai_generated"]:
                        icon = "🤖"
                    else:
                        icon = "📌"

                    points.append((icon, event["lat"], event["lng"], event.get("title", "")))

            # Добавляем точку пользователя
            points.append(("📍", lat, lng, "Вы здесь"))

            # Создаем карту
            event_points = [(p[1], p[2]) for p in points]  # (lat, lng)
            map_bytes = await fetch_static_map(
                build_static_map_url(lat, lng, event_points, settings.google_maps_api_key)
            )
        except Exception as map_error:
            logger.warning(f"⚠️ Не удалось создать карту: {map_error}")

        # ИСПРАВЛЕНИЕ: Редактируем существующее сообщение с картой вместо создания нового
        if map_bytes:
            from aiogram.types import BufferedInputFile, InputMediaPhoto

            map_file = BufferedInputFile(map_bytes, filename="map.png")
            map_caption = "📍 Карта событий"

            # Используем сохраненный map_message_id (получен ДО обновления состояния)
            # map_message_id уже получен выше, перед обновлением user_state
            logger.info(
                f"🗺️ [РЕДАКТИРОВАНИЕ КАРТЫ] map_message_id={map_message_id}, chat_id={chat_id}, map_bytes={'есть' if map_bytes else 'нет'}"
            )

            if map_message_id:
                # Редактируем существующее сообщение с картой
                try:
                    # Используем bot из callback для редактирования
                    bot = callback.bot
                    logger.info(
                        f"🗺️ [РЕДАКТИРОВАНИЕ] Пытаемся отредактировать карту message_id={map_message_id} в chat_id={chat_id}"
                    )

                    await bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=map_message_id,
                        media=InputMediaPhoto(media=map_file, caption=map_caption, parse_mode="HTML"),
                    )
                    logger.info(f"✅ Карта отредактирована на месте (message_id={map_message_id})")
                except Exception as edit_error:
                    logger.warning(f"⚠️ Не удалось отредактировать карту: {edit_error}, создаем новую")
                    # Если не удалось отредактировать, создаем новое сообщение
                    new_map_msg = await callback.message.answer_photo(
                        map_file,
                        caption=map_caption,
                        parse_mode="HTML",
                    )
                    # Обновляем message_id в состоянии
                    user_state[chat_id]["map_message_id"] = new_map_msg.message_id
                    logger.info("✅ Создана новая карта (не удалось отредактировать)")
            else:
                # Если карты еще не было, создаем новое сообщение
                new_map_msg = await callback.message.answer_photo(
                    map_file,
                    caption=map_caption,
                    parse_mode="HTML",
                )
                # Сохраняем message_id карты в состоянии
                user_state[chat_id]["map_message_id"] = new_map_msg.message_id
                logger.info("✅ Карта создана (первый раз)")

            # Редактируем существующее сообщение со списком событий или создаем новое
            if list_message_id:
                # Редактируем существующее сообщение со списком событий
                try:
                    bot = callback.bot
                    logger.info(
                        f"📋 [РЕДАКТИРОВАНИЕ СПИСКА] Пытаемся отредактировать список message_id={list_message_id} в chat_id={chat_id}"
                    )

                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=list_message_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    logger.info(f"✅ Список событий отредактирован на месте (message_id={list_message_id})")
                    current_message = callback.message  # Используем исходное сообщение для дальнейших операций
                except Exception as edit_error:
                    logger.warning(f"⚠️ Не удалось отредактировать список событий: {edit_error}, создаем новое")
                    # Если не удалось отредактировать, создаем новое сообщение
                    new_msg = await callback.message.answer(
                        text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                    )
                    # Обновляем message_id в состоянии
                    update_user_state_timestamp(chat_id)
                    user_state[chat_id]["list_message_id"] = new_msg.message_id
                    logger.info("✅ Создан новый список событий (не удалось отредактировать)")
                    current_message = new_msg
            else:
                # Если списка еще не было, создаем новое сообщение
                new_msg = await callback.message.answer(
                    text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                # Сохраняем message_id списка в состоянии
                user_state[chat_id]["list_message_id"] = new_msg.message_id
                logger.info("✅ Список событий создан (первый раз)")
                current_message = new_msg
        else:
            # Отправляем без карты - редактируем существующее сообщение со списком или создаем новое
            if list_message_id:
                # Редактируем существующее сообщение со списком событий
                try:
                    bot = callback.bot
                    logger.info(
                        f"📋 [РЕДАКТИРОВАНИЕ СПИСКА БЕЗ КАРТЫ] Пытаемся отредактировать список message_id={list_message_id} в chat_id={chat_id}"
                    )

                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=list_message_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    logger.info(f"✅ Список событий отредактирован на месте (message_id={list_message_id})")
                except Exception as edit_error:
                    logger.warning(f"⚠️ Не удалось отредактировать список событий: {edit_error}, создаем новое")
                    # Если не удалось отредактировать, создаем новое сообщение
                    new_msg = await callback.message.answer(
                        text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                    )
                    # Обновляем message_id в состоянии
                    update_user_state_timestamp(chat_id)
                    user_state[chat_id]["list_message_id"] = new_msg.message_id
                    logger.info("✅ Создан новый список событий (не удалось отредактировать)")
            else:
                # Если списка еще не было, создаем новое сообщение
                new_msg = await callback.message.answer(
                    text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                # Сохраняем message_id списка в состоянии
                user_state[chat_id]["list_message_id"] = new_msg.message_id
                logger.info("✅ Список событий создан (первый раз, без карты)")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки результатов расширенного поиска: {e}")
        # Fallback - простое текстовое сообщение
        try:
            await current_message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e2:
            logger.error(f"❌ Критическая ошибка fallback: {e2}")
            # Последний fallback - новое сообщение
            await current_message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

    await callback.answer(f"✅ Радиус расширен до {new_radius} км")


@main_router.callback_query(F.data.startswith("task_complete:"))
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
        "📸 **Отправьте фото места** где вы были\n"
        "или **напишите ваш отзыв** текстом:",
        parse_mode="Markdown",
    )

    await callback.answer()


@main_router.callback_query(F.data.startswith("task_cancel:"))
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


async def show_tasks_for_category(
    message_or_callback, category: str, user_id: int, user_lat: float, user_lng: float, state: FSMContext, page: int = 1
):
    """
    Показывает места для категории списком (8 на страницу)

    Args:
        message_or_callback: Сообщение или callback для редактирования
        category: Категория заданий ('food', 'health' или 'places')
        user_id: ID пользователя
        user_lat: Широта пользователя
        user_lng: Долгота пользователя
        state: FSM состояние
        page: Номер страницы (начинается с 1)
    """
    # Определяем тип региона пользователя и соответствующий тип задания
    from tasks_location_service import get_all_places_for_category, get_task_type_for_region, get_user_region_type

    region_type = get_user_region_type(user_lat, user_lng)
    task_type = get_task_type_for_region(region_type)

    logger.info(
        f"Показ мест для категории {category}, регион: {region_type}, тип задания: {task_type}, страница {page}"
    )

    # Получаем все доступные места для категории
    try:
        all_places = get_all_places_for_category(category, user_id, user_lat, user_lng, task_type=task_type, limit=100)
        logger.info(f"show_tasks_for_category: Получено {len(all_places)} мест для категории {category}")
    except Exception as e:
        logger.error(f"Ошибка получения мест: {e}", exc_info=True)
        all_places = []

    # Определяем названия категорий
    category_names = {"food": "🍔 Еда", "health": "💪 Здоровье", "places": "🌟 Интересные места"}
    category_name = category_names.get(category, category)

    # Если мест нет
    if not all_places:
        text = f"🎯 **{category_name}**\n\n" "❌ Места для этой категории пока не добавлены."
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_tasks")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
            ]
        )
        if hasattr(message_or_callback, "edit_text"):
            await message_or_callback.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await message_or_callback.answer(text, parse_mode="Markdown", reply_markup=reply_markup)
        return

    # Пагинация: 8 мест на страницу
    places_per_page = 8
    total_pages = (len(all_places) + places_per_page - 1) // places_per_page
    page = max(1, min(page, total_pages))

    # Получаем места для текущей страницы
    start_idx = (page - 1) * places_per_page
    end_idx = min(start_idx + places_per_page, len(all_places))
    page_places = all_places[start_idx:end_idx]

    # Формируем текст сообщения
    text = f"🎯 **{category_name}**\n\n"
    text += f"📍 Найдено мест: {len(all_places)}\n\n"

    # Получаем username бота для создания deep links
    bot_info = await message_or_callback.bot.get_me() if hasattr(message_or_callback, "bot") else None
    bot_username = bot_info.username if bot_info else "EventAroundBot"

    # Добавляем каждое место с ссылкой "Забрать квест" в тексте
    for idx, place in enumerate(page_places, start=start_idx + 1):
        # Название места (кликабельная ссылка на Google Maps, если есть)
        if place.google_maps_url:
            # В Markdown ссылки: [текст](url)
            # Экранируем специальные символы в названии для Markdown
            escaped_name = place.name.replace("[", "\\[").replace("]", "\\]").replace("(", "\\(").replace(")", "\\)")
            text += f"**{idx}. [{escaped_name}]({place.google_maps_url})**\n"
        else:
            text += f"**{idx}. {place.name}**\n"

        # Расстояние
        if hasattr(place, "distance_km") and place.distance_km:
            text += f"📍 {place.distance_km:.1f} км от вас\n"

        # Промокод
        if place.promo_code:
            text += f"🎁 Промокод: `{place.promo_code}`\n"

        # Короткое задание (task_hint)
        if place.task_hint:
            text += f"💡 {place.task_hint}\n"

        # Добавляем скрытую ссылку "Забрать квест" под каждым местом в тексте
        # Используем deep link (будет показывать /start, но это особенность Telegram)
        deep_link = f"https://t.me/{bot_username}?start=add_quest_{place.id}"
        text += f"[🎯 Забрать квест]({deep_link})\n"

        text += "\n"

    # Создаем клавиатуру только с кнопками пагинации (без кнопок мест)
    keyboard = []

    # Кнопки пагинации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"places_page:{category}:{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"places_page:{category}:{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    # Информация о странице
    if total_pages > 1:
        keyboard.append([InlineKeyboardButton(text=f"Стр. {page}/{total_pages}", callback_data="places_page:noop")])

    # Кнопки управления
    keyboard.append(
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_tasks"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main"),
        ]
    )

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if hasattr(message_or_callback, "edit_text"):
        await message_or_callback.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await message_or_callback.answer(text, parse_mode="Markdown", reply_markup=reply_markup)


@main_router.callback_query(F.data.startswith("task_category:"))
async def handle_task_category_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора категории задания"""
    category = callback.data.split(":")[1]
    user_id = callback.from_user.id

    # Получаем координаты пользователя из БД
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        user_lat = user.last_lat if user else None
        user_lng = user.last_lng if user else None

    # Если координаты отсутствуют, просим отправить геолокацию
    if not user_lat or not user_lng:
        await callback.message.edit_text(
            "📍 **Требуется геолокация**\n\n"
            "Для получения персонализированных заданий с локациями рядом с вами, "
            "пожалуйста, отправьте вашу геолокацию.\n\n"
            "Нажмите кнопку '📍 Отправить геолокацию' в меню.",
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    # Используем общую функцию для показа мест (страница 1)
    await show_tasks_for_category(callback.message, category, user_id, user_lat, user_lng, state, page=1)
    await callback.answer()


@main_router.callback_query(F.data.startswith("task_detail:"))
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

        # Получаем информацию о месте из состояния (если есть)
        data = await state.get_data()
        places_info = data.get("task_places_info", {})
        place_info = places_info.get(task_id)

        # Если нет места в состоянии, пытаемся найти его в базе (для известных регионов)
        if not place_info:
            from database import User
            from tasks_location_service import (
                find_nearest_available_place,
                generate_search_query_url,
                get_user_region,
                get_user_region_type,
            )

            user = session.query(User).filter(User.id == user_id).first()
            if user and user.last_lat is not None and user.last_lng is not None:
                region = get_user_region(user.last_lat, user.last_lng)
                region_type = get_user_region_type(user.last_lat, user.last_lng)
                task_type = task.task_type or "urban"

                # Для известных регионов ищем место в базе
                if region != "unknown":
                    category_place_types = {
                        "food": ["cafe", "restaurant", "street_food", "market", "bakery"],
                        "health": ["gym", "spa", "lab", "clinic", "nature"],
                        "places": [
                            "park",
                            "exhibition",
                            "temple",
                            "trail",
                            "viewpoint",
                            "beach",
                            "cliff",
                            "beach_club",
                            "culture",
                        ],
                    }
                    place_types = category_place_types.get(task.category, ["park"])

                    place = None
                    for place_type in place_types:
                        place = find_nearest_available_place(
                            category=task.category,
                            place_type=place_type,
                            task_type=task_type,
                            user_lat=user.last_lat,
                            user_lng=user.last_lng,
                            user_id=user_id,
                            exclude_days=0,  # Не исключаем места для просмотра деталей
                        )
                        if place:
                            break

                    if place:
                        place_info = {
                            "name": place.name,
                            "url": place.google_maps_url,
                            "distance_km": getattr(place, "distance_km", None),
                            "promo_code": place.promo_code,
                        }
                else:
                    # Для unknown регионов генерируем поисковый запрос
                    category_place_types = {
                        "food": ["cafe", "restaurant", "street_food", "market", "bakery"],
                        "health": ["gym", "spa", "lab", "clinic", "nature"],
                        "places": [
                            "park",
                            "exhibition",
                            "temple",
                            "trail",
                            "viewpoint",
                            "beach",
                            "cliff",
                            "beach_club",
                            "culture",
                        ],
                    }
                    place_types = category_place_types.get(task.category, ["park"])
                    place_type = place_types[0]

                    search_url = generate_search_query_url(
                        place_type=place_type,
                        user_lat=user.last_lat,
                        user_lng=user.last_lng,
                        region_type=region_type,
                    )
                    place_info = {
                        "name": "Ближайшее место",
                        "url": search_url,
                        "distance_km": None,
                        "promo_code": None,
                    }

        # Формируем сообщение с деталями задания
        message = f"📋 **{task.title}**\n\n"
        message += f"{task.description}\n\n"

        # Показываем локацию из базы (если есть)
        location_url = None
        location_name = None

        if place_info:
            # Используем место из базы
            location_name = place_info.get("name", "Место")
            location_url = place_info.get("url")
            distance = place_info.get("distance_km")
            promo_code = place_info.get("promo_code")

            message += "📍 **Предлагаемое место:**\n"
            if distance:
                message += f"🏃 {location_name} ({distance:.1f} км)\n"
            else:
                message += f"🏃 {location_name}\n"
            if location_url:
                message += f"[🌍 Открыть на карте]({location_url})\n"
            if promo_code:
                message += f"🎁 **Промокод:** `{promo_code}`\n"
            message += "\n"

        # Создаем клавиатуру
        keyboard = []

        if (location_url or place_info) and not user_has_task:
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


@main_router.callback_query(F.data.startswith("task_already_taken:"))
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


@main_router.callback_query(F.data.startswith("task_accept:"))
async def handle_task_accept(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик принятия задания"""
    task_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Получаем координаты пользователя и категорию задания из БД
    with get_session() as session:
        from database import Task

        user = session.get(User, user_id)
        user_lat = user.last_lat if user else None
        user_lng = user.last_lng if user else None

        # Получаем категорию задания для показа обновленного списка
        task = session.query(Task).filter(Task.id == task_id).first()
        category = task.category if task else None

    # Принимаем задание с учетом часового пояса пользователя
    success = accept_task(user_id, task_id, user_lat, user_lng)

    if success:
        # Показываем краткое сообщение об успехе
        await callback.answer("✅ Задание принято!", show_alert=False)

        # Если есть категория и координаты, показываем обновленный список мест
        if category and user_lat and user_lng:
            await show_tasks_for_category(callback.message, category, user_id, user_lat, user_lng, state, page=1)
        else:
            # Если нет категории или координат, показываем обычное сообщение
            await callback.message.edit_text(
                "✅ **Задание принято!**\n\n" "🏆 Задание добавлено в 'Мои квесты'.\n\n" "Удачи! 🚀",
                parse_mode="Markdown",
            )
            await callback.message.answer("🚀", reply_markup=main_menu_kb())
    else:
        await callback.message.edit_text(
            "❌ **Не удалось принять задание**\n\n" "Возможно, у вас уже есть активное задание этого типа.",
            parse_mode="Markdown",
        )
        # Показываем главное меню
        await callback.message.answer("🚀", reply_markup=main_menu_kb())

    await callback.answer()


@main_router.callback_query(F.data.startswith("task_custom_location:"))
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


@main_router.callback_query(F.data.startswith("start_task:"))
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


@main_router.callback_query(F.data == "back_to_main")
async def handle_back_to_main_tasks(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик возврата в главное меню из заданий"""
    # Очищаем состояние FSM
    await state.clear()

    # Показываем анимацию ракеты с главным меню
    await send_spinning_menu(callback.message)
    await callback.answer()


@main_router.callback_query(F.data == "show_bot_commands")
async def handle_show_bot_commands(callback: types.CallbackQuery):
    """Обработчик показа команд бота"""
    commands_text = (
        "📋 **Команды бота:**\n\n"
        "🚀 /start - Запустить бота и показать меню\n"
        "❓ /help - Показать справку\n"
        "📍 /nearby - Найти события рядом\n"
        "➕ /create - Создать событие\n"
        "📋 /myevents - Мои события\n"
        "🔗 /share - Добавить бота в чат\n\n"
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


@main_router.callback_query(F.data == "back_to_tasks")
async def handle_back_to_tasks(callback: types.CallbackQuery):
    """Обработчик возврата к выбору категории заданий"""
    # Показываем выбор категории
    keyboard = [
        [InlineKeyboardButton(text="🍔 Еда", callback_data="task_category:food")],
        [InlineKeyboardButton(text="💪 Здоровье", callback_data="task_category:health")],
        [InlineKeyboardButton(text="🌟 Интересные места", callback_data="task_category:places")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        "🎯 **Чем заняться**\n\n"
        "Выберите категорию заданий:\n\n"
        "🍔 **Еда** - кафе, рестораны, уличная еда\n"
        "💪 **Здоровье** - спорт, йога, спа, клиники\n"
        "🌟 **Интересные места** - парки, выставки, храмы",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    await callback.answer()


@main_router.callback_query(F.data.startswith("places_page:"))
async def handle_places_page(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик пагинации мест"""
    parts = callback.data.split(":")
    if len(parts) < 3 or parts[2] == "noop":
        await callback.answer("Это крайняя страница")
        return

    category = parts[1]
    page = int(parts[2])
    user_id = callback.from_user.id

    # Получаем координаты пользователя из БД
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        user_lat = user.last_lat if user else None
        user_lng = user.last_lng if user else None

    if not user_lat or not user_lng:
        await callback.answer("📍 Требуется геолокация")
        return

    # Показываем страницу мест
    await show_tasks_for_category(callback.message, category, user_id, user_lat, user_lng, state, page=page)
    await callback.answer()


@main_router.callback_query(F.data.startswith("add_place_to_quests:"))
async def handle_add_place_to_quests(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик добавления места в квесты"""
    place_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Получаем координаты пользователя из БД
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        user_lat = user.last_lat if user else None
        user_lng = user.last_lng if user else None

    # Создаем задание из места
    success, message_text = create_task_from_place(user_id, place_id, user_lat, user_lng)

    # Показываем уведомление с результатом
    # Если квест уже добавлен (success=False), показываем alert, иначе просто toast
    await callback.answer(message_text, show_alert=not success)


@main_router.callback_query(F.data.startswith("task_manage:"))
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

    # Проверка на истечение отключена - задания доступны всегда
    # Время истечения больше не показываем, так как ограничение снято

    category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
    category_emoji = category_emojis.get(task_info["category"], "📋")

    message = f"{category_emoji} **{task_info['title']}**\n\n"
    message += f"{task_info['description']}\n\n"

    # Показываем локацию, если есть
    if task_info.get("place_name") or task_info.get("place_url"):
        place_name = task_info.get("place_name", "Место на карте")
        place_url = task_info.get("place_url")
        distance = task_info.get("distance_km")

        if place_url:
            if distance:
                message += f"📍 **Место:** [{place_name} ({distance:.1f} км)]({place_url})\n"
            else:
                message += f"📍 **Место:** [{place_name}]({place_url})\n"
        else:
            if distance:
                message += f"📍 **Место:** {place_name} ({distance:.1f} км)\n"
            else:
                message += f"📍 **Место:** {place_name}\n"
        message += "\n"

    # Показываем промокод, если есть
    if task_info.get("promo_code"):
        message += f"🎁 **Промокод:** `{task_info['promo_code']}`\n\n"

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


@main_router.message(EventCreation.waiting_for_feedback)
async def process_feedback(message: types.Message, state: FSMContext):
    """Обработка фидбека для завершения задания (принимает фото или текст)"""
    user_id = message.from_user.id

    # Получаем ID задания из состояния
    data = await state.get_data()
    completing_task_id = data.get("completing_task_id") or data.get("user_task_id")

    if not completing_task_id:
        await message.answer("❌ Ошибка: не найдено задание для завершения.")
        await state.clear()
        return

    # Проверяем, что пользователь отправил (фото или текст)
    feedback_text = None
    photo_file_id = None

    # Если есть фото
    if message.photo:
        # Берём самое большое фото (последнее в списке)
        photo_file_id = message.photo[-1].file_id
        # Если есть подпись к фото, используем её как текст
        if message.caption:
            feedback_text = message.caption.strip()
        else:
            feedback_text = "📸 Фото места выполнения задания"

        # Сохраняем file_id в формате "PHOTO:file_id|текст" или просто file_id
        feedback = f"PHOTO:{photo_file_id}"
        if feedback_text and feedback_text != "📸 Фото места выполнения задания":
            feedback += f"|{feedback_text}"
    elif message.text:
        # Если только текст
        feedback_text = message.text.strip()
        feedback = feedback_text
    else:
        await message.answer(
            "❌ Пожалуйста, отправьте **фото места** где вы были или **напишите отзыв** текстом.",
            parse_mode="Markdown",
        )
        return

    # Завершаем задание с фидбеком
    success = complete_task(completing_task_id, feedback)

    if success:
        # Награждаем ракетами
        rockets_awarded = award_rockets_for_activity(user_id, "task_complete")

        # Формируем сообщение в зависимости от типа фидбека
        if photo_file_id:
            success_message = (
                f"🎉 **Задание завершено!**\n\n"
                f"📸 Спасибо за фото места!\n"
                f"🚀 Получено ракет: **{rockets_awarded}**\n\n"
                f"Продолжайте в том же духе! 💪"
            )
        else:
            success_message = (
                f"🎉 **Задание завершено!**\n\n"
                f"📝 Спасибо за фидбек!\n"
                f"🚀 Получено ракет: **{rockets_awarded}**\n\n"
                f"Продолжайте в том же духе! 💪"
            )

        await message.answer(success_message, parse_mode="Markdown")

        # Отправляем ракету
        await message.answer("🚀")
    else:
        await message.answer(
            "❌ **Не удалось завершить задание**\n\n" "Возможно, время выполнения истекло или задание уже завершено.",
            parse_mode="Markdown",
        )

    await state.clear()


@main_router.message(Command("help"))
@main_router.message(F.text == "💬 Написать отзыв Разработчику")
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
@main_router.message(EventCreation.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    """Шаг 1: Обработка названия события"""
    title = message.text.strip()
    chat_id = message.chat.id
    chat_type = message.chat.type

    logger.info(
        f"process_title: получили название '{title}' от пользователя {message.from_user.id} в чате {chat_id} (тип: {chat_type})"
    )

    # Проверяем на спам-индикаторы в названии
    spam_indicators = [
        "http://",
        "https://",
        "www.",
        ".com",
        ".ru",
        ".org",
        "instagram.com",
        "vk.com",
        "facebook.com",
        "youtube.com",
        "t.me",
        "@",
        "tg://",
        "bit.ly",
        "goo.gl",
    ]

    # Проверяем на команды (символ / в начале)
    if title.startswith("/"):
        await message.answer(
            "❌ В названии нельзя указывать команды (символ / в начале)!\n\n"
            "📝 Пожалуйста, придумайте краткое название события:\n"
            "• Что будет происходить\n"
            "• Где будет проходить\n"
            "• Для кого предназначено\n\n"
            "**Введите название мероприятия** (например: Прогулка):"
        )
        return

    title_lower = title.lower()
    if any(indicator in title_lower for indicator in spam_indicators):
        await message.answer(
            "❌ В названии нельзя указывать ссылки и контакты!\n\n"
            "📝 Пожалуйста, придумайте краткое название события:\n"
            "• Что будет происходить\n"
            "• Где будет проходить\n"
            "• Для кого предназначено\n\n"
            "**Введите название мероприятия** (например: Прогулка):"
        )
        return

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


@main_router.message(EventCreation.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    """Шаг 2: Обработка даты события"""
    date = message.text.strip()
    logger.info(f"process_date: получили дату '{date}' от пользователя {message.from_user.id}")

    # Валидация формата даты DD.MM.YYYY

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

        import pytz

        event_date = datetime(year, month, day)  # Проверяем валидность даты

        # Проверяем, что дата не в прошлом
        tz_bali = pytz.timezone("Asia/Makassar")  # UTC+8 для Бали
        now_bali = datetime.now(tz_bali)
        today_bali = now_bali.date()
        event_date_only = event_date.date()

        if event_date_only < today_bali:
            await message.answer(
                f"⚠️ Внимание! Дата *{date}* уже прошла (сегодня {today_bali.strftime('%d.%m.%Y')}).\n\n"
                "📅 Введите дату:",
                parse_mode="Markdown",
            )
            return
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


@main_router.message(EventCreation.waiting_for_time)
async def process_time(message: types.Message, state: FSMContext):
    """Шаг 3: Обработка времени события"""
    time = message.text.strip()
    logger.info(f"process_time: получили время '{time}' от пользователя {message.from_user.id}")

    # Валидация формата времени HH:MM

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


@main_router.message(EventCreation.waiting_for_location_type)
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
@main_router.callback_query(F.data == "location_link")
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


@main_router.callback_query(F.data == "location_map")
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


@main_router.callback_query(F.data == "location_coords")
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


# Обработчики для выбора типа локации в Community режиме
@main_router.callback_query(F.data == "community_location_link")
async def handle_community_location_link_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода готовой ссылки в Community режиме"""
    await state.set_state(CommunityEventCreation.waiting_for_location_url)
    await callback.message.answer("🔗 Вставьте сюда ссылку из Google Maps:", reply_markup=get_community_cancel_kb())
    await callback.answer()


@main_router.callback_query(F.data == "community_location_map")
async def handle_community_location_map_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор поиска на карте в Community режиме"""
    # Создаем кнопку для открытия Google Maps
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🌍 Открыть Google Maps", url="https://www.google.com/maps")]]
    )
    await state.set_state(CommunityEventCreation.waiting_for_location_url)
    await callback.message.answer("🌍 Открой карту, найди место и вставь ссылку сюда 👇", reply_markup=keyboard)
    await callback.answer()


@main_router.callback_query(F.data == "community_location_coords")
async def handle_community_location_coords_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода координат в Community режиме"""
    await state.set_state(CommunityEventCreation.waiting_for_location_url)
    await callback.message.answer(
        "📍 Введите координаты в формате: **широта, долгота**\n\n" "Например: 55.7558, 37.6176\n" "Или: -8.67, 115.21",
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(),
    )
    await callback.answer()


@main_router.message(TaskFlow.waiting_for_custom_location)
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


@main_router.message(EventCreation.waiting_for_location_link)
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
@main_router.callback_query(F.data == "location_confirm")
async def handle_location_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение локации"""
    await state.set_state(EventCreation.waiting_for_description)
    await callback.message.answer(
        "📍 Место сохранено! ✅\n\n📝 Теперь введите описание (например: Вечерняя прогулка у океана):",
        parse_mode="Markdown",
    )
    await callback.answer()


@main_router.callback_query(F.data == "location_change")
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


@main_router.message(EventCreation.waiting_for_location)
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


@main_router.message(EventCreation.waiting_for_description)
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

    # Проверяем, что все необходимые данные есть в FSM
    required_fields = ["title", "date", "time", "description"]
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        logger.warning(f"process_description: отсутствуют поля в FSM данных: {missing_fields}")
        await message.answer(
            "❌ **Ошибка:** Не все данные события сохранены.\n\n"
            "🔄 Начните создание события заново, нажав кнопку **➕ Создать**."
        )
        await state.clear()
        return

    # Показываем итог перед подтверждением
    location_text = data.get("location", "Не указано")
    if "location_name" in data and data["location_name"]:
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
@main_router.message(CommunityEventCreation.waiting_for_title, F.chat.type.in_({"group", "supergroup"}))
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

    # Проверяем на спам-индикаторы в названии
    spam_indicators = [
        "http://",
        "https://",
        "www.",
        ".com",
        ".ru",
        ".org",
        "instagram.com",
        "vk.com",
        "facebook.com",
        "youtube.com",
        "t.me",
        "@",
        "tg://",
        "bit.ly",
        "goo.gl",
    ]

    # Проверяем на команды (символ / в начале)
    if title.startswith("/"):
        await message.answer(
            "❌ В названии нельзя указывать команды (символ / в начале)!\n\n"
            "📝 Пожалуйста, придумайте краткое название события:\n"
            "• Что будет происходить\n"
            "• Где будет проходить\n"
            "• Для кого предназначено\n\n"
            "✍ **Введите название мероприятия** (например: Встреча в кафе):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    title_lower = title.lower()
    if any(indicator in title_lower for indicator in spam_indicators):
        await message.answer(
            "❌ В названии нельзя указывать ссылки и контакты!\n\n"
            "📝 Пожалуйста, придумайте краткое название события:\n"
            "• Что будет происходить\n"
            "• Где будет проходить\n"
            "• Для кого предназначено\n\n"
            "✍ **Введите название мероприятия** (например: Встреча в кафе):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    await state.update_data(title=title, chat_id=chat_id)
    await state.set_state(CommunityEventCreation.waiting_for_date)
    example_date = get_example_date()

    await message.answer(
        f"**Название сохранено:** *{title}* ✅\n\n📅 **Введите дату** (например: {example_date}):",
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
    )


@main_router.message(
    CommunityEventCreation.waiting_for_date,
    F.chat.type.in_({"group", "supergroup"}),
    F.reply_to_message,
    F.reply_to_message.from_user.id == BOT_ID,
)
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

    if not re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", date):
        await message.answer(
            "❌ **Неверный формат даты!**\n\n" "📅 Введите дату в формате **ДД.ММ.ГГГГ**\n" "Например: 15.12.2024",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    # Дополнительная проверка: валидность даты и проверка на прошлое
    try:
        day, month, year = map(int, date.split("."))
        from datetime import datetime

        import pytz

        event_date = datetime(year, month, day)  # Проверяем валидность даты

        # Проверяем, что дата не в прошлом
        tz_bali = pytz.timezone("Asia/Makassar")  # UTC+8 для Бали
        now_bali = datetime.now(tz_bali)
        today_bali = now_bali.date()
        event_date_only = event_date.date()

        if event_date_only < today_bali:
            await message.answer(
                f"⚠️ Внимание! Дата *{date}* уже прошла (сегодня {today_bali.strftime('%d.%m.%Y')}).\n\n"
                "📅 Введите дату:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
                ),
            )
            return
    except ValueError:
        await message.answer(
            "❌ **Неверная дата!**\n\n"
            "Проверьте правильность даты:\n"
            "• День: 1-31\n"
            "• Месяц: 1-12\n"
            "• Год: 2024-2030\n\n"
            "Например: 15.12.2024\n\n"
            "📅 **Введите дату** (например: 15.12.2024):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    await state.update_data(date=date)
    await state.set_state(CommunityEventCreation.waiting_for_time)

    await message.answer(
        f"**Дата сохранена:** {date} ✅\n\n⏰ **Введите время** (например: 19:00):",
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
    )


@main_router.message(
    CommunityEventCreation.waiting_for_time,
    F.chat.type.in_({"group", "supergroup"}),
    F.reply_to_message,
    F.reply_to_message.from_user.id == BOT_ID,
)
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

    await message.answer(
        f"**Время сохранено:** {time} ✅\n\n🏙️ **Введите город** (например: Москва):",
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
    )


@main_router.message(
    CommunityEventCreation.waiting_for_city,
    F.chat.type.in_({"group", "supergroup"}),
    F.reply_to_message,
    F.reply_to_message.from_user.id == BOT_ID,
)
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
    await state.set_state(CommunityEventCreation.waiting_for_location_type)

    # Создаем клавиатуру для выбора типа локации (как в World режиме)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data="community_location_link")],
            [InlineKeyboardButton(text="🌍 Найти на карте", callback_data="community_location_map")],
            [InlineKeyboardButton(text="📍 Ввести координаты", callback_data="community_location_coords")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")],
        ]
    )

    await message.answer(
        f"**Город сохранен:** {city} ✅\n\n📍 **Как укажем место?**\n\nВыберите один из способов:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@main_router.message(
    CommunityEventCreation.waiting_for_location_type,
    F.chat.type.in_({"group", "supergroup"}),
)
async def handle_community_location_type_text_group(message: types.Message, state: FSMContext):
    """Обработка текстовых сообщений в состоянии выбора типа локации в Community режиме (групповые чаты)"""
    text = message.text.strip()

    # Проверяем, является ли это Google Maps ссылкой
    if any(domain in text.lower() for domain in ["maps.google.com", "goo.gl/maps", "maps.app.goo.gl"]):
        # Пользователь отправил ссылку напрямую - обрабатываем как ссылку
        await state.set_state(CommunityEventCreation.waiting_for_location_url)
        await process_community_location_url_group(message, state)
        return

    # Проверяем, являются ли это координаты (широта, долгота)
    if "," in text and len(text.split(",")) == 2:
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
                await state.set_state(CommunityEventCreation.waiting_for_description)
                await message.answer(
                    f"📍 **Место определено по координатам:** {lat}, {lng} ✅\n\n"
                    "📝 **Введите описание события** (что будет происходить, кому интересно):",
                    parse_mode="Markdown",
                    reply_markup=ForceReply(selective=True),
                )
                return
            else:
                raise ValueError("Invalid coordinates range")
        except (ValueError, TypeError):
            await message.answer(
                "❌ **Неверный формат координат!**\n\n"
                "Используйте формат: **широта, долгота**\n"
                "Например: 55.7558, 37.6176\n\n"
                "Диапазоны:\n"
                "• Широта: -90 до 90\n"
                "• Долгота: -180 до 180",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
                ),
            )
            return

    # Если не распознали, показываем подсказку
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вставить готовую ссылку", callback_data="community_location_link")],
            [InlineKeyboardButton(text="🌍 Найти на карте", callback_data="community_location_map")],
            [InlineKeyboardButton(text="📍 Ввести координаты", callback_data="community_location_coords")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")],
        ]
    )
    await message.answer(
        "📍 **Как укажем место?**\n\nВыберите один из способов:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@main_router.message(
    CommunityEventCreation.waiting_for_location_url,
    F.chat.type.in_({"group", "supergroup"}),
    F.reply_to_message,
    F.reply_to_message.from_user.id == BOT_ID,
)
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

    location_input = message.text.strip()
    logger.info(f"🔥 process_community_location_url_group: получили ввод от пользователя {message.from_user.id}")

    # Определяем название места по ссылке и пробуем достать координаты
    location_name = "Место по ссылке"  # Базовое название
    location_lat = None
    location_lng = None
    location_url = None

    # Проверяем, являются ли это координаты (широта, долгота)
    if "," in location_input and len(location_input.split(",")) == 2:
        try:
            lat_str, lng_str = location_input.split(",")
            lat = float(lat_str.strip())
            lng = float(lng_str.strip())

            # Проверяем валидность координат
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                location_name = "Место по координатам"
                location_lat = lat
                location_lng = lng
                location_url = location_input  # Сохраняем координаты как строку
            else:
                raise ValueError("Invalid coordinates range")
        except (ValueError, TypeError):
            await message.answer(
                "❌ **Неверный формат координат!**\n\n"
                "Используйте формат: **широта, долгота**\n"
                "Например: 55.7558, 37.6176\n\n"
                "Диапазоны:\n"
                "• Широта: -90 до 90\n"
                "• Долгота: -180 до 180",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
                ),
            )
            return
    else:
        # Это ссылка
        location_url = location_input
        try:
            if "maps.google.com" in location_url or "goo.gl" in location_url or "maps.app.goo.gl" in location_url:
                from utils.geo_utils import parse_google_maps_link

                location_data = await parse_google_maps_link(location_url)
                logger.info(f"🌍 parse_google_maps_link (community group) ответ: {location_data}")
                if location_data:
                    location_name = location_data.get("name") or "Место на карте"
                    location_lat = location_data.get("lat")
                    location_lng = location_data.get("lng")
                else:
                    location_name = "Место на карте"
            elif "yandex.ru/maps" in location_url:
                location_name = "Место на Яндекс.Картах"
            else:
                location_name = "Место по ссылке"
        except Exception as e:
            logger.warning(f"Не удалось распарсить ссылку для community события: {e}")
            location_name = "Место по ссылке"

    await state.update_data(
        location_url=location_url,
        location_name=location_name,
        location_lat=location_lat,
        location_lng=location_lng,
    )
    await state.set_state(CommunityEventCreation.waiting_for_description)

    if location_lat and location_lng:
        location_text = f"📍 **Место:** {location_name}\n**Координаты:** {location_lat}, {location_lng}"
    else:
        location_text = f"📍 **Место:** {location_name}"

    await message.answer(
        f"**Место сохранено** ✅\n{location_text}\n\n📝 **Введите описание события** (что будет происходить, кому интересно):",
        parse_mode="Markdown",
        reply_markup=ForceReply(selective=True),
    )


@main_router.message(
    CommunityEventCreation.waiting_for_description,
    F.chat.type.in_({"group", "supergroup"}),
    F.reply_to_message,
    F.reply_to_message.from_user.id == BOT_ID,
)
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


@main_router.callback_query(F.data == "community_event_confirm")
async def confirm_community_event(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение создания события сообщества"""
    logger.info(
        f"🔥 confirm_community_event: пользователь {callback.from_user.id} подтверждает создание события в чате {callback.message.chat.id}"
    )

    # Антидребезг: предотвращаем двойное создание события
    user_id = callback.from_user.id
    from time import time

    # Используем глобальный словарь для отслеживания обработки
    if not hasattr(confirm_community_event, "_processing"):
        confirm_community_event._processing = {}

    current_time = time()
    last_processing = confirm_community_event._processing.get(user_id, 0)

    if current_time - last_processing < 3:  # 3 секунды защиты от двойного клика
        logger.warning(f"⚠️ confirm_community_event: игнорируем двойной клик от пользователя {user_id}")
        await callback.answer("⏳ Подождите, событие уже создается...", show_alert=False)
        return

    confirm_community_event._processing[user_id] = current_time

    try:
        data = await state.get_data()
        logger.info(f"🔥 confirm_community_event: данные события: {data}")

        # Парсим дату и время с учетом указанного города
        from datetime import datetime

        date_str = data["date"]
        time_str = data["time"]

        # В Community режиме сохраняем время как указал пользователь, БЕЗ конвертации в UTC
        # Пользователь сам указал город и время, значит он уже учел свой часовой пояс
        # Сохраняем как naive datetime (без timezone), т.к. колонка в БД TIMESTAMP WITHOUT TIME ZONE
        starts_at = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")

        # Импортируем сервис для событий сообществ
        from utils.community_events_service import CommunityEventsService

        community_service = CommunityEventsService()

        # Получаем ID всех админов группы
        chat_id = callback.message.chat.id
        creator_id = callback.from_user.id

        print("🚨🚨🚨 НОВАЯ ВЕРСИЯ BOT_ENHANCED_V3 ЗАПУЩЕНА! 🚨🚨🚨")
        print("🚨🚨🚨 НОВАЯ ВЕРСИЯ BOT_ENHANCED_V3 ЗАПУЩЕНА! 🚨🚨🚨")
        print(f"🔥🔥🔥 confirm_community_event: ВЫЗОВ get_group_admin_ids для группы {chat_id}")

        # ПРОБУЕМ получить админов группы с кэшированием
        try:
            admin_ids = await community_service.get_cached_admin_ids(bot, chat_id)
            print(f"🔥🔥🔥 confirm_community_event: РЕЗУЛЬТАТ get_cached_admin_ids: {admin_ids}")

            # Если админы не получены из-за SSL ошибок, используем создателя
            if not admin_ids:
                admin_ids = [creator_id]
                print(f"🔥🔥🔥 FALLBACK: админы группы не получены, используем создателя: {admin_ids}")
            else:
                print(f"🔥🔥🔥 УСПЕХ: получены админы группы: {admin_ids}")
        except Exception as e:
            print(f"🔥🔥🔥 ОШИБКА получения админов: {e}")
            admin_ids = [creator_id]
            print(f"🔥🔥🔥 FALLBACK: ошибка получения админов, используем создателя: {admin_ids}")

        admin_id = admin_ids[0] if admin_ids else creator_id
        print(f"🔥🔥🔥 confirm_community_event: chat_id={chat_id}, admin_ids={admin_ids}, admin_id={admin_id}")
        print(
            f"🔥🔥🔥 СТАТУС: {'Админы группы получены' if len(admin_ids) > 1 or (len(admin_ids) == 1 and admin_ids[0] != creator_id) else 'Используется создатель как админ'}"
        )

        # Создаем событие в сообществе
        event_id = community_service.create_community_event(
            group_id=chat_id,
            creator_id=callback.from_user.id,
            creator_username=callback.from_user.username or callback.from_user.first_name,
            title=data["title"],
            date=starts_at,
            description=data["description"],
            city=data["city"],
            location_name=data.get("location_name", "Место по ссылке"),
            location_url=data.get("location_url"),
            admin_id=admin_id,  # LEGACY
            admin_ids=admin_ids,  # Новый подход
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


@main_router.callback_query(F.data == "event_confirm")
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
        from utils.simple_timezone import get_city_from_coordinates, get_city_timezone

        preliminary_city = None  # По умолчанию None (будет UTC)

        # Пробуем определить город по региону из состояния
        preliminary_city = data.get("region")  # Может быть None

        # Если координаты есть в data, используем их для определения города
        event_lat = data.get("location_lat")
        event_lng = data.get("location_lng")
        if event_lat and event_lng:
            city_from_coords = get_city_from_coordinates(event_lat, event_lng)
            if city_from_coords:
                preliminary_city = city_from_coords

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

            # Определяем часовой пояс по городу (используем get_city_timezone для правильного fallback на UTC)
            tz_name = get_city_timezone(preliminary_city)  # Вернет UTC, если city=None или неизвестен
            tz = pytz.timezone(tz_name)

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

        # Если location_name пустое или "Место не указано", но есть координаты, пробуем reverse geocoding
        if (not location_name or location_name == "Место не указано") and lat and lng:
            logger.info(f"🌍 location_name пустое, пробуем reverse geocoding для координат ({lat}, {lng})")
            try:
                from utils.geo_utils import reverse_geocode

                reverse_name = await reverse_geocode(lat, lng)
                if reverse_name:
                    location_name = reverse_name
                    logger.info(f"✅ Получено название места через reverse geocoding: {location_name}")
                else:
                    logger.debug(f"⚠️ Не удалось получить название места для координат ({lat}, {lng})")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при reverse geocoding: {e}")

        # Используем новую упрощенную архитектуру
        # Определяем город заранее для использования в сообщении
        city = "bali"  # Значение по умолчанию
        try:
            from database import get_engine
            from utils.simple_timezone import get_city_from_coordinates

            engine = get_engine()
            events_service = UnifiedEventsService(engine)

            # Определяем город по координатам (для создания события используем регион из состояния)
            city = get_city_from_coordinates(lat, lng) if lat and lng else None
            if not city:
                # Если город не определен, используем регион из состояния или None (будет UTC)
                city = data.get("region")  # Может быть None

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

    # Формируем структурированное сообщение для поделиться, похожее на Community версию
    share_message = "🎉 **Новое событие!**\n\n"
    share_message += f"**{data['title']}**\n"
    share_message += f"📅 {data['date']} в {data['time']}\n"

    # Добавляем место на карте с активной ссылкой (компактно)
    if location_url:
        share_message += f"📍 [{location_name}]({location_url})\n"
    else:
        share_message += f"📍 {location_name}\n"

    # Добавляем описание
    if data.get("description"):
        share_message += f"\n📝 {data['description']}\n"

    # Добавляем информацию о создателе
    creator_name = callback.from_user.username or callback.from_user.first_name or "пользователь"
    share_message += f"\n*Создано пользователем @{creator_name}*\n\n"
    share_message += "💡 **Больше событий в боте:** [@EventAroundBot](https://t.me/EventAroundBot)"

    # Отправляем новое сообщение (которое можно переслать) вместо edit_text
    await callback.message.answer(
        share_message,
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )

    await callback.answer("Событие создано!")

    # Показываем крутую анимацию после сохранения
    await send_spinning_menu(callback.message)


@main_router.callback_query(F.data == "event_cancel")
async def cancel_event_creation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания события"""
    await state.clear()
    await callback.message.edit_text("❌ Создание мероприятия отменено.")
    await callback.answer("Создание отменено")


@main_router.callback_query(F.data == "manage_events")
async def handle_manage_events(callback: types.CallbackQuery):
    """Обработчик кнопки Управление событиями"""
    user_id = callback.from_user.id
    active_events = _get_active_user_events(user_id)

    if not active_events:
        # Проверяем, содержит ли сообщение фото
        if callback.message.photo:
            try:
                chat_id = callback.message.chat.id
                bot = callback.bot
                await callback.message.delete()
                await bot.send_message(
                    chat_id=chat_id,
                    text="У вас нет активных событий для управления.",
                    reply_markup=None,
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении сообщения с фото: {e}", exc_info=True)
                # Fallback: отправляем новое сообщение
                chat_id = callback.message.chat.id
                bot = callback.bot
                await bot.send_message(
                    chat_id=chat_id,
                    text="У вас нет активных событий для управления.",
                    reply_markup=None,
                )
        else:
            try:
                await callback.message.edit_text("У вас нет активных событий для управления.", reply_markup=None)
            except Exception as e:
                logger.error(f"❌ Ошибка при редактировании сообщения: {e}", exc_info=True)
                # Fallback: отправляем новое сообщение
                chat_id = callback.message.chat.id
                bot = callback.bot
                await bot.send_message(
                    chat_id=chat_id,
                    text="У вас нет активных событий для управления.",
                    reply_markup=None,
                )
        await callback.answer()
        return

    await _show_manage_event(callback, active_events, 0)

    await callback.answer()


def _get_active_user_events(user_id: int) -> list[dict]:
    """Возвращает активные события и недавно закрытые (в течение 24 часов) для управления"""
    from datetime import UTC, datetime, timedelta

    events = get_user_events(user_id)
    now_utc = datetime.now(UTC)

    # Получаем активные события (которые еще не начались)
    active_events = [
        e for e in events if e.get("status") == "open" and e.get("starts_at") and e["starts_at"] >= now_utc
    ]

    # Добавляем закрытые события, которые можно возобновить
    # Важно: событие должно быть закрыто менее 24 часов назад И еще не началось
    # Если событие уже прошло (starts_at < now_utc), его нельзя возобновить
    day_ago = datetime.now(UTC) - timedelta(hours=24)

    recent_closed_for_management = []
    for e in events:
        if e.get("status") == "closed":
            updated_at = e.get("updated_at_utc")
            starts_at = e.get("starts_at")
            if updated_at and starts_at:
                # Проверяем, что событие было закрыто в течение последних 24 часов
                # И что событие еще не началось
                if updated_at >= day_ago and starts_at >= now_utc:
                    recent_closed_for_management.append(e)

    # Дополнительная фильтрация: исключаем прошедшие события (на случай, если они попали в список)
    now_utc = datetime.now(UTC)
    active_events = [e for e in active_events if e.get("starts_at") and e["starts_at"] >= now_utc]
    recent_closed_for_management = [
        e for e in recent_closed_for_management if e.get("starts_at") and e["starts_at"] >= now_utc
    ]

    # Объединяем активные и недавно закрытые события
    return active_events + recent_closed_for_management


def _extract_index(callback_data: str, prefix: str) -> int | None:
    """Извлекает индекс события из callback_data"""
    try:
        return int(callback_data.removeprefix(prefix))
    except ValueError:
        return None


async def _show_manage_event(callback: types.CallbackQuery, events: list[dict], index: int):
    """Показывает событие под нужным индексом с навигацией"""
    if not events:
        return

    total = len(events)
    if index < 0 or index >= total:
        index = 0

    event = events[index]
    header = f"🔧 Управление событием ({index + 1}/{total}):\n\n"
    text = f"{header}{format_event_for_display(event)}"

    # Передаем updated_at_utc для проверки времени закрытия
    buttons = get_status_change_buttons(event["id"], event["status"], event.get("updated_at_utc"))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
        ]
    )

    # Добавляем навигацию: всегда показываем 3 кнопки (Список, Назад, Вперед)
    nav_row = [
        InlineKeyboardButton(text="📋 Список", callback_data=f"back_to_list_{event['id']}"),
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"prev_event_{max(0, index-1)}"),
        InlineKeyboardButton(text="▶️ Вперед", callback_data=f"next_event_{min(total-1, index+1)}"),
    ]
    keyboard.inline_keyboard.append(nav_row)

    await _send_or_edit_manage_message(callback, text, keyboard)


async def _send_or_edit_manage_message(
    callback: types.CallbackQuery, text: str, keyboard: InlineKeyboardMarkup
) -> None:
    """Отправляет или редактирует сообщение, учитывая наличие фото"""
    if callback.message.photo:
        try:
            chat_id = callback.message.chat.id
            bot = callback.bot
            await callback.message.delete()
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке управления событиями (фото): {e}", exc_info=True)
            chat_id = callback.message.chat.id
            bot = callback.bot
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"❌ Ошибка при редактировании управления событиями: {e}", exc_info=True)
            chat_id = callback.message.chat.id
            bot = callback.bot
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="Markdown")


@main_router.message(F.text == "🏠 Главное меню")
async def on_main_menu_button(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Главное меню' - очищает состояние и показывает анимацию ракеты"""
    # Очищаем состояние FSM
    await state.clear()

    # Показываем анимацию ракеты с главным меню
    await send_spinning_menu(message)


@main_router.message(~StateFilter(EventCreation, EventEditing, TaskFlow))
async def echo_message(message: types.Message, state: FSMContext):
    """Обработчик всех остальных сообщений (кроме FSM состояний)"""
    # Пропускаем геолокацию - она обрабатывается отдельным обработчиком
    if message.location:
        logger.info("📍 [DEBUG] echo_message: получена геолокация, пропускаем для отдельного обработчика")
        return

    current_state = await state.get_state()
    logger.info(
        f"echo_message: получили сообщение '{message.text}' от пользователя {message.from_user.id}, состояние: {current_state}"
    )
    logger.info("echo_message: отвечаем общим сообщением")
    await message.answer("Используйте кнопки меню для навигации:", reply_markup=main_menu_kb())


@main_router.callback_query(F.data.startswith("date_filter:"))
async def handle_date_filter_change(callback: types.CallbackQuery):
    """Обработчик переключения фильтра даты (Сегодня/Завтра)"""
    try:
        # Извлекаем тип фильтра из callback_data
        date_type = callback.data.split(":")[1]  # "today" или "tomorrow"

        # Получаем сохраненное состояние
        state = user_state.get(callback.message.chat.id)
        if not state:
            logger.warning(f"Состояние не найдено для пользователя {callback.message.chat.id}")
            await callback.answer("❌ Состояние потеряно. Отправьте геолокацию заново.")
            return

        # Проверяем, что фильтр действительно изменился
        current_filter = state.get("date_filter", "today")
        if current_filter == date_type:
            await callback.answer("Эта дата уже выбрана")
            return

        # Показываем индикатор загрузки
        try:
            await callback.message.edit_text("🔍 Загружаю события...")
        except Exception:
            pass

        # Получаем параметры из состояния
        lat = state.get("lat")
        lng = state.get("lng")
        radius = state.get("radius", 5)
        region = state.get("region", "bali")

        logger.info(
            f"🔍 ПЕРЕКЛЮЧЕНИЕ ДАТЫ: radius из состояния={radius}, "
            f"current_filter={current_filter}, date_type={date_type}"
        )

        if not lat or not lng:
            await callback.answer("❌ Геолокация не найдена. Отправьте геолокацию заново.")
            return

        # Определяем city по координатам (как при первом запросе)
        from utils.simple_timezone import get_city_from_coordinates

        city = get_city_from_coordinates(lat, lng)
        if not city:
            # Если город не определен по координатам, используем region из состояния
            city = region
            logger.info(
                f"ℹ️ Регион не определен по координатам ({lat}, {lng}), используем region={region} для временных границ"
            )
        else:
            logger.info(f"🌍 Определен city={city} по координатам ({lat}, {lng}) для временных границ")

        # Вычисляем date_offset
        date_offset = 0 if date_type == "today" else 1

        # Перезагружаем события с новым фильтром
        from database import get_engine

        engine = get_engine()
        events_service = UnifiedEventsService(engine)

        logger.info(
            f"🔄 Переключение фильтра даты: {current_filter} → {date_type} "
            f"(offset={date_offset}) для пользователя {callback.from_user.id}, "
            f"radius={radius} км из состояния"
        )

        events = events_service.search_events_today(
            city=city, user_lat=lat, user_lng=lng, radius_km=int(radius), date_offset=date_offset
        )

        logger.info(
            f"🔍 После переключения даты: найдено {len(events)} событий с radius_km={radius}, "
            f"date_offset={date_offset}"
        )

        # Конвертируем в старый формат для совместимости
        formatted_events = []
        for event in events:
            formatted_event = {
                "id": event.get("id"),
                "title": event["title"],
                "description": event["description"],
                "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
                "starts_at": event["starts_at"],
                "city": event.get("city"),
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
        logger.info(
            f"🔍 ПЕРЕД prepare_events_for_feed: найдено {len(events)} событий, "
            f"radius_km={radius}, user_point=({lat}, {lng})"
        )
        prepared, diag = prepare_events_for_feed(events, user_point=(lat, lng), radius_km=int(radius), with_diag=True)
        logger.info(
            f"🔍 ПОСЛЕ prepare_events_for_feed: осталось {len(prepared)} событий, "
            f"radius_km={radius}, dropped={diag.get('dropped', 0)}"
        )

        # Обогащаем события reverse geocoding для названий локаций
        prepared = await enrich_events_with_reverse_geocoding(prepared)

        # Группируем и считаем
        groups = group_by_type(prepared)
        counts = make_counts(groups)

        # Обновляем состояние (сохраняем радиус при переключении даты)
        state["prepared"] = prepared
        state["counts"] = counts
        state["date_filter"] = date_type
        state["radius"] = int(radius)  # Сохраняем текущий радиус
        state["page"] = 1  # Сбрасываем страницу на 1
        state["diag"] = diag
        user_state[callback.message.chat.id] = state

        # Рендерим первую страницу
        # ВАЖНО: Карта показывается только на первой странице
        # На последующих страницах отправляем текстовые сообщения без карты
        is_photo_message = callback.message.photo is not None
        is_first_page = True  # Всегда первая страница при переключении даты

        # Telegram ограничивает длину caption для медиа до 1024 символов
        MAX_CAPTION_LENGTH = 1024

        # Для первой страницы с картой динамически определяем, сколько событий поместится
        if is_first_page and is_photo_message:
            # Формируем заголовок
            header_html = render_header(counts, radius_km=int(radius))
            header_length = len(header_html.encode("utf-8"))

            # Пробуем добавить события по одному, пока не превысим лимит
            page_size = 0
            page_html_parts = []
            MAX_CAPTION_LENGTH - header_length - 2  # -2 для "\n\n"

            for idx, event in enumerate(prepared, start=1):
                event_html = render_event_html(event, idx, callback.from_user.id, is_caption=True)
                event_length = len(event_html.encode("utf-8"))

                # Проверяем, поместится ли событие (с учетом разделителя "\n")
                separator_length = len(b"\n") if page_html_parts else 0
                total_length = (
                    header_length
                    + 2
                    + sum(len(p.encode("utf-8")) for p in page_html_parts)
                    + separator_length
                    + event_length
                )

                if total_length <= MAX_CAPTION_LENGTH:
                    page_html_parts.append(event_html)
                    page_size += 1
                else:
                    break

            # Если не поместилось ни одного события, берем хотя бы одно (оно будет обрезано)
            if page_size == 0 and prepared:
                page_size = 1
                page_html_parts = [render_event_html(prepared[0], 1, callback.from_user.id, is_caption=True)]

            page_html = "\n".join(page_html_parts)
            total_pages = max(1, ceil(len(prepared) / max(page_size, 1)))
            logger.info(f"🔍 Динамический page_size для первой страницы с картой: {page_size} событий")
        else:
            page_size = 8  # Текстовые сообщения - 8 событий
            page_html, total_pages = render_page(
                prepared,
                page=1,
                page_size=page_size,
                user_id=callback.from_user.id,
                is_caption=False,
            )

        # Формируем финальный текст
        if is_first_page and is_photo_message:
            new_text = header_html + "\n\n" + page_html
        else:
            header_html = render_header(counts, radius_km=int(radius))
            new_text = header_html + "\n\n" + page_html

        # Создаем клавиатуру с правильным фильтром даты
        combined_keyboard = kb_pager(1, total_pages, current_radius=int(radius), date_filter=date_type)

        # Обновляем сообщение
        try:
            if callback.message.photo:
                # Проверяем длину текста для caption
                if len(new_text) > MAX_CAPTION_LENGTH:
                    logger.warning(
                        f"⚠️ Текст caption слишком длинный ({len(new_text)} символов), обрезаем до {MAX_CAPTION_LENGTH}"
                    )
                    new_text = truncate_html_safely(new_text, MAX_CAPTION_LENGTH)

                await callback.message.edit_caption(caption=new_text, parse_mode="HTML", reply_markup=combined_keyboard)
            else:
                await callback.message.edit_text(
                    new_text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=combined_keyboard
                )
            logger.info(f"✅ Фильтр даты переключен на {date_type}, найдено {len(prepared)} событий")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления сообщения при переключении даты: {e}")
            await callback.answer("❌ Не удалось переключить дату", show_alert=True)
            return

        await callback.answer(f"📅 Показаны события на {date_type}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки переключения даты: {e}")
        await callback.answer("❌ Произошла ошибка при переключении даты")


@main_router.callback_query(F.data.startswith("pg:"))
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
        date_filter = state.get("date_filter", "today")  # Получаем фильтр даты из состояния

        # Обогащаем события reverse geocoding для названий локаций
        prepared = await enrich_events_with_reverse_geocoding(prepared)

        # ВАЖНО: Карта показывается только на первой странице
        # На последующих страницах отправляем текстовые сообщения без карты
        is_photo_message = callback.message.photo is not None
        is_first_page = page == 1

        # Для первой страницы с картой используем меньше событий (лимит caption 1024 байта)
        # Tracking URL очень длинные, поэтому уменьшаем до 1 события
        if is_first_page and is_photo_message:
            page_size = 1  # Первая страница с картой - 1 событие (из-за длинных tracking URL)
        else:
            page_size = 8  # Текстовые сообщения - 8 событий

        # Правильный расчет total_pages с учетом смешанного размера страниц
        # Первая страница (с картой) имеет page_size=1, остальные - page_size=8
        if is_photo_message:
            # Есть карта: первая страница = 1 событие, остальные по 8
            if len(prepared) <= 1:
                total_pages = 1
            else:
                total_pages = 1 + ceil((len(prepared) - 1) / 8)
        else:
            # Нет карты: все страницы по 8 событий
            total_pages = max(1, ceil(len(prepared) / 8))

        # Рендерим страницу
        # Теперь карта отдельно, поэтому is_caption=False для всех страниц
        page_html, _ = render_page(
            prepared,
            page,
            page_size=page_size,
            user_id=callback.from_user.id,
            is_caption=False,  # Карта отдельно, нет ограничения caption
            first_page_was_photo=False,  # Карта теперь всегда отдельно
        )

        # Логируем показ событий в списке при пагинации (list_view)
        from database import get_engine

        engine = get_engine()
        participation_analytics = UserParticipationAnalytics(engine)

        # Определяем group_chat_id (NULL для World, значение для Community)
        group_chat_id = None
        if callback.message.chat.type != "private":
            group_chat_id = callback.message.chat.id

        # Логируем каждое показанное событие на текущей странице
        # Теперь все страницы по 8 событий (карта отдельно)
        start_idx = (page - 1) * page_size

        shown_events = prepared[start_idx : start_idx + page_size]
        for event in shown_events:
            event_id = event.get("id")
            if event_id:
                participation_analytics.record_list_view(
                    user_id=callback.from_user.id,
                    event_id=event_id,
                    group_chat_id=group_chat_id,
                )

        # Создаем клавиатуру пагинации с учетом фильтра даты
        combined_keyboard = kb_pager(page, total_pages, current_radius, date_filter=date_filter)

        # Обновляем сообщение (проверяем тип сообщения)
        new_text = render_header(counts, radius_km=current_radius) + "\n\n" + page_html

        try:
            # ВАЖНО: Карта показывается только на первой странице
            # На странице 2+ отправляем новое текстовое сообщение
            if is_first_page and is_photo_message:
                # Первая страница с картой - редактируем caption
                MAX_CAPTION_LENGTH = 1024
                if len(new_text) > MAX_CAPTION_LENGTH:
                    logger.warning(
                        f"⚠️ Текст caption слишком длинный ({len(new_text)} символов), обрезаем до {MAX_CAPTION_LENGTH}"
                    )
                    new_text = truncate_html_safely(new_text, MAX_CAPTION_LENGTH)

                await callback.message.edit_caption(
                    caption=new_text,
                    parse_mode="HTML",
                    reply_markup=combined_keyboard,
                )
                logger.info(f"✅ Страница {page} отредактирована (caption, длина: {len(new_text)})")
            elif is_first_page and not is_photo_message:
                # Первая страница без карты - редактируем текст
                await callback.message.edit_text(
                    new_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=combined_keyboard,
                )
                logger.info(f"✅ Страница {page} отредактирована (text, длина: {len(new_text)})")
            else:
                # Страница 2+ - удаляем старое сообщение и отправляем новое текстовое (без карты)
                # Сохраняем chat_id и message_thread_id перед удалением
                chat_id = callback.message.chat.id
                message_thread_id = getattr(callback.message, "message_thread_id", None)
                bot = callback.message.bot

                try:
                    # Удаляем старое сообщение (с картой или текстовое)
                    await callback.message.delete()
                    logger.info(f"🗑️ Удалено старое сообщение перед отправкой страницы {page}")
                except Exception as delete_error:
                    logger.warning(f"⚠️ Не удалось удалить старое сообщение: {delete_error}")

                # Отправляем новое текстовое сообщение через бота
                send_kwargs = {
                    "text": new_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                    "reply_markup": combined_keyboard,
                }
                if message_thread_id:
                    send_kwargs["message_thread_id"] = message_thread_id

                await bot.send_message(chat_id, **send_kwargs)
                logger.info(f"✅ Страница {page} отправлена как новое текстовое сообщение (длина: {len(new_text)})")
        except Exception as e:
            logger.error(f"❌ Ошибка редактирования/отправки страницы {page}: {e}")
            await callback.answer("❌ Не удалось перелистнуть страницу", show_alert=True)
            return

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


@main_router.callback_query(F.data == "loading")
async def handle_loading_button(callback: types.CallbackQuery):
    """Обработчик кнопки загрузки - просто отвечаем, что работаем"""
    await callback.answer("🔍 Ищем события...", show_alert=False)


@main_router.callback_query(F.data == "create_event")
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


@main_router.callback_query(F.data == "start_create")
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


@main_router.callback_query(F.data == "back_to_search")
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
@main_router.callback_query(F.data.startswith(CB_RADIUS_PREFIX))
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

    # Читаем переменные окружения СРАЗУ
    RUN_MODE = os.getenv("BOT_RUN_MODE", "webhook")
    PORT = int(os.getenv("PORT", "8000"))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")

    # В WEBHOOK РЕЖИМЕ: запускаем минимальный сервер СРАЗУ для health check
    # Это критично для Railway - health check должен быть доступен сразу
    webhook_app = None
    webhook_runner = None
    if RUN_MODE == "webhook" and WEBHOOK_URL:
        from aiohttp import web

        # Создаем минимальное приложение СРАЗУ
        webhook_app = web.Application()

        # Добавляем health check endpoint СРАЗУ
        async def health_check_early(request):
            return web.json_response({"ok": True, "status": "starting"})

        webhook_app.router.add_get("/health", health_check_early)
        webhook_app.router.add_get("/", health_check_early)

        # Запускаем сервер СРАЗУ для health check
        webhook_runner = web.AppRunner(webhook_app)
        await webhook_runner.setup()
        site = web.TCPSite(webhook_runner, "0.0.0.0", PORT)
        await site.start()
        logger.info(f"✅ Сервер запущен на http://0.0.0.0:{PORT} - health check доступен СРАЗУ")

    # Инициализируем BOT_ID для корректной фильтрации в групповых чатах
    global BOT_ID
    bot_info = await bot.me()
    BOT_ID = bot_info.id
    logger.info(f"BOT_ID инициализирован: {BOT_ID}")

    # === НОВАЯ ИНТЕГРАЦИЯ ГРУППОВЫХ ЧАТОВ (ИЗОЛИРОВАННЫЙ РОУТЕР) ===
    # Устанавливаем username бота для deep-links в group_router
    try:
        from group_router import set_bot_username

        set_bot_username(bot_info.username)

        # Menu Button уже настроен в основном боте - не дублируем

        logger.info("✅ Групповой роутер успешно проинициализирован")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации группового роутера: {e}")
        import traceback

        logger.error(f"❌ Детали ошибки: {traceback.format_exc()}")

    # Запускаем фоновую задачу для периодической очистки user_state
    asyncio.create_task(periodic_cleanup_user_state())
    logger.info("✅ Запущена фоновая задача для очистки user_state")

    # Вызываем очистку вручную при старте, чтобы удалить накопившиеся данные
    try:
        cleanup_user_state()
        cleanup_large_prepared_events()
        logger.info(f"🧹 При старте очищено user_state: осталось {len(user_state)} записей")
    except Exception as e:
        logger.error(f"Ошибка при очистке user_state при старте: {e}")

    # Запускаем фоновую задачу для очистки моментов
    from config import load_settings

    load_settings()

    # Очищаем просроченные задания при старте (отключено - ограничение по времени снято)
    # try:
    #     expired_count = mark_tasks_as_expired()
    #     if expired_count > 0:
    #         logger.info(f"При старте помечено как истекшие: {expired_count} заданий")
    #     else:
    #         logger.info("При старте просроченных заданий не найдено")
    # except Exception as e:
    #     logger.error(f"Ошибка очистки просроченных заданий при старте: {e}")

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
        # АГРЕССИВНАЯ очистка всех команд для всех scope и языков
        from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeDefault

        # Очищаем команды для всех типов чатов (без языка)
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
        await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())

        # Очищаем команды для русской локали
        await bot.delete_my_commands(scope=BotCommandScopeDefault(), language_code="ru")
        await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats(), language_code="ru")
        await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats(), language_code="ru")

        # Ждем дольше, чтобы Telegram точно обработал удаление
        await asyncio.sleep(3)

        from aiogram.types import BotCommandScopeChat

        # Админские команды - только для админа
        admin_commands = [
            types.BotCommand(command="ban", description="🚫 Забанить пользователя (админ)"),
            types.BotCommand(command="unban", description="✅ Разбанить пользователя (админ)"),
            types.BotCommand(command="banlist", description="📋 Список забаненных (админ)"),
            types.BotCommand(command="admin_event", description="🔍 Диагностика события (админ)"),
            types.BotCommand(command="diag_last", description="📊 Диагностика последнего запроса"),
            types.BotCommand(command="diag_search", description="🔍 Диагностика поиска событий"),
            types.BotCommand(command="diag_webhook", description="🔗 Диагностика webhook"),
            types.BotCommand(command="diag_commands", description="🔧 Диагностика команд бота"),
        ]

        # Используем эталонную функцию установки команд
        await setup_bot_commands()

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

        # Небольшая задержка для применения команд
        await asyncio.sleep(2)

        # ДИАГНОСТИКА: проверяем, что команды установлены
        try:
            current_commands = await bot.get_my_commands(scope=BotCommandScopeAllGroupChats())
            logger.info(f"🔍 Текущие команды для групп: {[cmd.command for cmd in current_commands]}")
        except Exception as e:
            logger.error(f"❌ Ошибка получения команд: {e}")

        # RUNTIME HEALTHCHECK: проверяем команды по всем скоупам и языкам
        try:
            await dump_commands_healthcheck(bot)
        except Exception as e:
            logger.error(f"❌ Ошибка healthcheck команд: {e}")

        # СТОРОЖ КОМАНД: проверяем и восстанавливаем команды при старте
        try:
            await ensure_commands(bot)
        except Exception as e:
            logger.error(f"❌ Ошибка сторожа команд при старте: {e}")

        # Устанавливаем кнопку меню с диагностикой
        try:
            from aiogram.types import MenuButtonCommands

            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.info("✅ Menu Button установлен успешно")
        except Exception as e:
            logger.warning(f"⚠️ Menu Button не удалось установить: {e}")
            # Fallback: полагаемся только на команды

        # Еще одна задержка для применения Menu Button
        await asyncio.sleep(2)

        # Настраиваем Menu Button специально для групп
        from group_router import setup_group_menu_button

        await setup_group_menu_button(bot)

        # Диагностика: проверяем Menu Button и команды
        try:
            # Проверяем текущий Menu Button
            menu_button = await bot.get_chat_menu_button()
            logger.info(f"🔍 Текущий Menu Button: {menu_button}")

            # Если Menu Button = WebApp, сбрасываем на Commands
            if hasattr(menu_button, "type") and menu_button.type == "web_app":
                logger.warning("⚠️ Menu Button перекрыт WebApp! Сбрасываем на Commands...")
                from aiogram.types import MenuButtonCommands, MenuButtonDefault

                await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
                await asyncio.sleep(1)
                await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
                logger.info("✅ Menu Button сброшен на Commands")

            # Проверяем команды по всем scope и языкам
            from aiogram.types import (
                BotCommandScopeAllGroupChats,
                BotCommandScopeAllPrivateChats,
                BotCommandScopeDefault,
            )

            for scope_name, scope in [
                ("Default", BotCommandScopeDefault()),
                ("PrivateChats", BotCommandScopeAllPrivateChats()),
                ("GroupChats", BotCommandScopeAllGroupChats()),
            ]:
                logger.info(f"🔍 Проверяем команды для {scope_name}:")

                # Без языка
                try:
                    commands = await bot.get_my_commands(scope=scope)
                    logger.info(f"  EN: {len(commands)} команд")
                    for cmd in commands:
                        logger.info(f"    - /{cmd.command}: {cmd.description}")
                except Exception as e:
                    logger.warning(f"  EN: Ошибка получения команд: {e}")

                # Русская локаль
                try:
                    commands_ru = await bot.get_my_commands(scope=scope, language_code="ru")
                    logger.info(f"  RU: {len(commands_ru)} команд")
                    for cmd in commands_ru:
                        logger.info(f"    - /{cmd.command}: {cmd.description}")
                except Exception as e:
                    logger.warning(f"  RU: Ошибка получения команд: {e}")

        except Exception as e:
            logger.warning(f"⚠️ Не удалось выполнить диагностику: {e}")

        logger.info("Команды бота и Menu Button установлены")
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

            # Используем уже созданное приложение (webhook_app) или создаем новое
            from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
            from aiohttp import web

            # Если приложение уже создано и запущено (для health check), используем его
            if webhook_app is not None and webhook_runner is not None:
                app = webhook_app
                logger.info("✅ Используем уже запущенное приложение для webhook - добавляем handlers")
                # Сервер уже запущен, просто добавляем handlers
                server_already_running = True
            else:
                # Создаем новое приложение (fallback для polling режима или если ранний запуск не был выполнен)
                app = web.Application()
                server_already_running = False
                logger.info("✅ Создаем новое приложение для webhook")

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

            # Обновляем health check endpoint (если был ранний, обновляем на готовый)
            async def health_check_ready(request):
                return web.json_response({"ok": True, "status": "ready"})

            # Удаляем старый health check если был, и добавляем новый
            # Удаляем маршруты которые могут конфликтовать
            try:
                # Пытаемся удалить старые маршруты если они есть
                for route in list(app.router.routes()):
                    if hasattr(route, "resource") and route.resource and hasattr(route.resource, "canonical"):
                        if route.resource.canonical == "/health":
                            app.router.routes().discard(route)
                        elif route.resource.canonical == "/":
                            app.router.routes().discard(route)
            except Exception:
                pass  # Игнорируем ошибки при удалении

            app.router.add_get("/health", health_check_ready)
            app.router.add_get("/", health_check_ready)

            # Добавляем API endpoint для отслеживания кликов
            async def track_click(request):
                """Отслеживание кликов по ссылкам и редирект на оригинальный URL"""
                try:
                    from urllib.parse import unquote

                    from database import get_engine
                    from utils.user_participation_analytics import UserParticipationAnalytics

                    # Получаем параметры из query string
                    user_id = int(request.query.get("user_id", 0))
                    event_id = int(request.query.get("event_id", 0))
                    click_type = request.query.get("click_type", "")
                    target_url = request.query.get("target_url", "")

                    if not user_id or not event_id or not target_url:
                        logger.warning(
                            f"⚠️ Неполные параметры для track_click: user_id={user_id}, event_id={event_id}, target_url={target_url}"
                        )
                        # Все равно редиректим на decoded_url если есть
                        if target_url:
                            decoded_url = unquote(target_url)
                            return web.HTTPFound(location=decoded_url)
                        return web.json_response({"error": "Missing parameters"}, status=400)

                    # Декодируем target_url
                    decoded_url = unquote(target_url)

                    # Валидация click_type
                    if click_type in ["source", "route"]:
                        # Логируем клик в базу данных
                        engine = get_engine()
                        analytics = UserParticipationAnalytics(engine)

                        if click_type == "source":
                            analytics.record_click_source(user_id, event_id)
                            logger.info(f"✅ Записан click_source: user_id={user_id}, event_id={event_id}")
                        elif click_type == "route":
                            analytics.record_click_route(user_id, event_id)
                            logger.info(f"✅ Записан click_route: user_id={user_id}, event_id={event_id}")

                    # Редиректим на оригинальный URL
                    return web.HTTPFound(location=decoded_url)

                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке клика: {e}")
                    # В случае ошибки все равно пытаемся редиректить
                    try:
                        if target_url:
                            decoded_url = unquote(target_url)
                            return web.HTTPFound(location=decoded_url)
                    except Exception:
                        pass
                    return web.json_response({"error": "Failed to process click tracking"}, status=500)

            app.router.add_get("/click", track_click)

            # Логируем зарегистрированные маршруты
            logger.info("Зарегистрированные маршруты:")
            for route in app.router.routes():
                logger.info(f"  {route.method} {route.resource.canonical}")

            # Запускаем фоновую задачу для периодического обновления команд
            asyncio.create_task(periodic_commands_update())
            logger.info("✅ Фоновая задача обновления команд запущена")

            # Запускаем сервер ТОЛЬКО если он еще не запущен
            if not server_already_running:
                # Запускаем объединенный сервер (webhook + health check)
                port = int(PORT)
                logger.info(f"Запуск объединенного сервера (webhook + health) на порту {port}")

                # Запускаем сервер в фоне
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, "0.0.0.0", port)
                await site.start()
                logger.info(f"Сервер запущен на http://0.0.0.0:{port}")
                webhook_runner = runner  # Сохраняем runner для cleanup
            else:
                logger.info("✅ Сервер уже запущен - handlers добавлены к существующему приложению")

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
                # Используем webhook_runner если он есть, иначе runner
                if webhook_runner is not None:
                    await webhook_runner.cleanup()
                elif "runner" in locals():
                    await runner.cleanup()

        else:
            # Polling режим для локальной разработки
            # Перед стартом снимаем вебхук
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook удален, запускаем polling")

            # Запускаем фоновую задачу для периодического обновления команд
            asyncio.create_task(periodic_commands_update())
            logger.info("✅ Фоновая задача обновления команд запущена")

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
@main_router.callback_query(F.data.startswith("close_event_"))
async def handle_close_event(callback: types.CallbackQuery):
    """Завершение мероприятия"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    success = change_event_status(event_id, "closed", user_id)
    if success:
        # Получаем закрытое событие для отображения
        closed_event = get_event_by_id(event_id, user_id)

        if closed_event:
            event_name = closed_event["title"]
            await callback.answer(f"✅ Мероприятие '{event_name}' завершено!")

            # Получаем список всех событий (включая закрытое) для навигации
            events = _get_active_user_events(user_id)
            # Находим индекс закрытого события
            event_index = next((i for i, e in enumerate(events) if e["id"] == event_id), 0)

            # Показываем событие через _show_manage_event с навигацией
            await _show_manage_event(callback, events, event_index)
        else:
            # Если событие не найдено, показываем первое событие из списка
            events = _get_active_user_events(user_id)
            if events:
                await _show_manage_event(callback, events, 0)
            else:
                await callback.answer("✅ Мероприятие завершено!")
    else:
        await callback.answer("❌ Ошибка при завершении мероприятия")


@main_router.callback_query(F.data.startswith("open_event_"))
async def handle_open_event(callback: types.CallbackQuery):
    """Возобновление мероприятия"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    # Получаем событие для проверки статуса и времени закрытия
    event = get_event_by_id(event_id, user_id)
    if not event:
        await callback.answer("❌ Событие не найдено", show_alert=True)
        return

    # Проверяем, что событие закрыто
    if event["status"] != "closed":
        await callback.answer("❌ Событие не закрыто, его нельзя возобновить", show_alert=True)
        return

    # Проверяем, что событие было закрыто в течение последних 24 часов
    from datetime import timedelta

    day_ago = datetime.now(UTC) - timedelta(hours=24)
    if event.get("updated_at_utc") and event["updated_at_utc"] < day_ago:
        await callback.answer(
            "❌ Возобновление возможно только в течение 24 часов после закрытия события", show_alert=True
        )
        return

    # Проверяем, что событие еще не началось (не прошло по времени)
    # Если событие уже прошло, просто не обрабатываем запрос (событие не должно было попасть в список)
    now_utc = datetime.now(UTC)
    if event.get("starts_at") and event["starts_at"] < now_utc:
        # Событие уже прошло - просто игнорируем (не должно было попасть в список)
        await callback.answer()
        return

    success = change_event_status(event_id, "open", user_id)
    if success:
        # Получаем возобновленное событие для отображения
        reopened_event = get_event_by_id(event_id, user_id)

        if reopened_event:
            event_name = reopened_event["title"]
            await callback.answer(f"🔄 Мероприятие '{event_name}' снова активно!")

            # Обновляем сообщение, показывая возобновленное событие с кнопкой "Завершить"
            text = f"📋 **Ваши события:**\n\n{format_event_for_display(reopened_event)}"
            buttons = get_status_change_buttons(reopened_event["id"], reopened_event["status"])
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
                ]
            )
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            # Если событие не найдено, показываем первое событие из списка
            events = get_user_events(user_id)
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
            await callback.answer("🔄 Мероприятие снова активно!")
    else:
        await callback.answer("❌ Ошибка при возобновлении мероприятия")


@main_router.callback_query(F.data.startswith("share_event_"))
async def handle_share_event(callback: types.CallbackQuery):
    """Поделиться событием - формирует структурированное сообщение для пересылки"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    # Получаем полные данные события
    event = get_event_by_id(event_id, user_id)
    if not event:
        await callback.answer("❌ Событие не найдено")
        return

    # Формируем структурированное сообщение (как после создания события)
    share_message = "🎉 **Новое событие!**\n\n"
    share_message += f"**{event['title']}**\n"

    # Форматируем дату и время
    if event.get("starts_at"):
        import pytz

        from database import User, get_session

        # Получаем часовой пояс пользователя
        user_tz = "Asia/Makassar"  # По умолчанию Бали
        try:
            with get_session() as session:
                user = session.get(User, event.get("organizer_id"))
                if user and user.user_tz:
                    user_tz = user.user_tz
        except Exception:
            pass

        # Конвертируем UTC в часовой пояс пользователя
        tz = pytz.timezone(user_tz)
        local_time = event["starts_at"].astimezone(tz)
        date_str = local_time.strftime("%d.%m.%Y")
        time_str = local_time.strftime("%H:%M")
        share_message += f"📅 {date_str} в {time_str}\n"
    else:
        share_message += "📅 Время не указано\n"

    # Добавляем место на карте с активной ссылкой (компактно)
    location_name = event.get("location_name") or "Место не указано"
    location_url = event.get("location_url")
    if location_url:
        share_message += f"📍 [{location_name}]({location_url})\n"
    else:
        share_message += f"📍 {location_name}\n"

    # Добавляем описание
    if event.get("description"):
        share_message += f"\n📝 {event['description']}\n"

    # Добавляем информацию о создателе
    creator_name = callback.from_user.username or callback.from_user.first_name or "пользователь"
    share_message += f"\n*Создано пользователем @{creator_name}*\n\n"
    share_message += "💡 **Больше событий в боте:** [@EventAroundBot](https://t.me/EventAroundBot)"

    # Отправляем сообщение, которое можно переслать
    await callback.message.answer(
        share_message,
        parse_mode="Markdown",
    )
    await callback.answer("✅ Сообщение готово к пересылке!")


@main_router.callback_query(F.data.startswith("edit_event_"))
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
@main_router.callback_query(F.data.startswith("edit_title_"))
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


@main_router.callback_query(F.data.startswith("edit_date_"))
async def handle_edit_date_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования даты"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.waiting_for_date)

    # Показываем текущую дату события для удобства
    try:
        import pytz

        from database import User, get_session

        events = get_user_events(callback.from_user.id)
        current_event = next((event for event in events if event["id"] == event_id), None)

        if current_event and current_event["starts_at"]:
            # Получаем часовой пояс пользователя
            user_tz = "Asia/Makassar"  # По умолчанию Бали
            try:
                with get_session() as session:
                    user = session.get(User, callback.from_user.id)
                    if user and user.user_tz:
                        user_tz = user.user_tz
            except Exception:
                pass

            # Конвертируем UTC время в локальное время пользователя
            tz = pytz.timezone(user_tz)
            local_time = current_event["starts_at"].astimezone(tz)
            current_date_str = local_time.strftime("%d.%m.%Y")
            await callback.message.answer(
                f"📅 Введите новую дату в формате ДД.ММ.ГГГГ (текущая дата: {current_date_str}):"
            )
        else:
            example_date = get_example_date()
            await callback.message.answer(f"📅 Введите новую дату в формате ДД.ММ.ГГГГ (например: {example_date}):")
    except Exception:
        example_date = get_example_date()
        await callback.message.answer(f"📅 Введите новую дату в формате ДД.ММ.ГГГГ (например: {example_date}):")

    await callback.answer()


@main_router.callback_query(F.data.startswith("edit_time_"))
async def handle_edit_time_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования времени"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.waiting_for_time)

    # Показываем текущее время события для удобства
    try:
        import pytz

        from database import User, get_session

        events = get_user_events(callback.from_user.id)
        current_event = next((event for event in events if event["id"] == event_id), None)

        if current_event and current_event["starts_at"]:
            # Получаем часовой пояс пользователя
            user_tz = "Asia/Makassar"  # По умолчанию Бали
            try:
                with get_session() as session:
                    user = session.get(User, callback.from_user.id)
                    if user and user.user_tz:
                        user_tz = user.user_tz
            except Exception:
                pass

            # Конвертируем UTC время в локальное время пользователя
            tz = pytz.timezone(user_tz)
            local_time = current_event["starts_at"].astimezone(tz)
            current_time_str = local_time.strftime("%H:%M")
            await callback.message.answer(
                f"⏰ Введите новое время в формате ЧЧ:ММ (текущее время: {current_time_str}):"
            )
        else:
            await callback.message.answer("⏰ Введите новое время в формате ЧЧ:ММ (например: 18:30):")
    except Exception:
        await callback.message.answer("⏰ Введите новое время в формате ЧЧ:ММ (например: 18:30):")

    await callback.answer()


@main_router.callback_query(F.data.regexp(r"^edit_location_\d+$"))
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
@main_router.callback_query(F.data.regexp(r"^edit_location_link_\d+$"))
async def handle_edit_location_link_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода готовой ссылки для редактирования"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.waiting_for_location)
    await callback.message.answer("🔗 Вставьте сюда ссылку из Google Maps:")
    await callback.answer()


@main_router.callback_query(F.data.regexp(r"^edit_location_map_\d+$"))
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


@main_router.callback_query(F.data.regexp(r"^edit_location_coords_\d+$"))
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


@main_router.callback_query(F.data.startswith("edit_description_"))
async def handle_edit_description_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования описания"""
    await state.set_state(EventEditing.waiting_for_description)
    await callback.message.answer("📝 Введите новое описание:")
    await callback.answer()


@main_router.callback_query(F.data.startswith("edit_finish_"))
async def handle_edit_finish(callback: types.CallbackQuery, state: FSMContext):
    """Завершение редактирования"""
    data = await state.get_data()
    event_id = data.get("event_id")
    user_id = callback.from_user.id

    if event_id:
        # Получаем список всех событий (включая обновленное) для навигации
        events = _get_active_user_events(user_id)
        # Находим индекс обновленного события
        event_index = next((i for i, e in enumerate(events) if e["id"] == event_id), None)

        if event_index is not None:
            # Показываем событие через _show_manage_event с навигацией
            await _show_manage_event(callback, events, event_index)
            await callback.answer("✅ Событие обновлено!")
        else:
            # Если событие не найдено в списке активных, получаем его напрямую
            all_events = get_user_events(user_id)
            updated_event = next((event for event in all_events if event["id"] == event_id), None)

            if updated_event:
                text = f"✅ **Событие обновлено!**\n\n{format_event_for_display(updated_event)}"
                buttons = get_status_change_buttons(updated_event["id"], updated_event["status"])
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
                    ]
                )
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
                await callback.answer("✅ Событие обновлено!")
            else:
                await callback.answer("❌ Событие не найдено")

    await state.clear()


# Обработчики ввода данных для редактирования
@main_router.message(EventEditing.waiting_for_title)
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


@main_router.message(EventEditing.waiting_for_date)
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


@main_router.message(EventEditing.waiting_for_time)
async def handle_time_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового времени"""
    data = await state.get_data()
    event_id = data.get("event_id")

    if event_id and message.text:
        # Для времени нужно получить текущую дату и объединить с новым временем
        try:
            from datetime import datetime

            import pytz

            from database import User, get_session

            # Получаем часовой пояс пользователя
            user_tz = "Asia/Makassar"  # По умолчанию Бали
            try:
                with get_session() as session:
                    user = session.get(User, message.from_user.id)
                    if user and user.user_tz:
                        user_tz = user.user_tz
            except Exception:
                pass

            # Получаем текущую дату события
            events = get_user_events(message.from_user.id)
            current_event = next((event for event in events if event["id"] == event_id), None)

            if current_event and current_event["starts_at"]:
                # Конвертируем UTC время в локальное время пользователя
                tz = pytz.timezone(user_tz)
                local_time = current_event["starts_at"].astimezone(tz)
                current_date = local_time.strftime("%d.%m.%Y")
                new_datetime = f"{current_date} {message.text.strip()}"
                success = update_event_field(event_id, "starts_at", new_datetime, message.from_user.id)
            else:
                # Если нет текущей даты, используем сегодняшнюю в локальном времени
                tz = pytz.timezone(user_tz)
                today_local = datetime.now(tz)
                today = today_local.strftime("%d.%m.%Y")
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


@main_router.message(EventEditing.waiting_for_location)
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


@main_router.message(EventEditing.waiting_for_description)
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


@main_router.callback_query(F.data.startswith("next_event_"))
async def handle_next_event(callback: types.CallbackQuery):
    """Переход к следующему событию"""
    user_id = callback.from_user.id
    target_index = _extract_index(callback.data, prefix="next_event_")
    active_events = _get_active_user_events(user_id)

    if target_index is None or target_index >= len(active_events):
        await callback.answer("Больше событий нет")
        return

    await _show_manage_event(callback, active_events, target_index)
    await callback.answer()


@main_router.callback_query(F.data.startswith("back_to_main_"))
async def handle_back_to_main(callback: types.CallbackQuery):
    """Возврат в главное меню (старый обработчик для совместимости)"""
    # Показываем анимацию ракеты с главным меню
    await callback.answer("🎯 Возврат в главное меню")
    await send_spinning_menu(callback.message)


@main_router.callback_query(F.data.startswith("back_to_list_"))
async def handle_back_to_list(callback: types.CallbackQuery):
    """Возврат к списку событий"""
    await callback.answer("📋 Возврат к списку событий")

    user_id = callback.from_user.id

    # Автомодерация: закрываем прошедшие события
    closed_count = auto_close_events()
    if closed_count > 0:
        await callback.message.answer(f"🤖 Автоматически закрыто {closed_count} прошедших событий")

    # Получаем события пользователя
    events = get_user_events(user_id)

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем текст сообщения
    text_parts = ["📋 **Мои события:**\n", f"**Баланс {rocket_balance} 🚀**\n"]

    # Созданные события
    if events:
        active_events = [e for e in events if e.get("status") == "open"]

        # Показываем также недавно закрытые события (за последние 7 дней)
        from datetime import datetime, timedelta

        import pytz

        tz_bali = pytz.timezone("Asia/Makassar")
        now_bali = datetime.now(tz_bali)
        week_ago = now_bali - timedelta(days=7)

        recent_closed_events = []
        for e in events:
            if e.get("status") == "closed":
                starts_at = e.get("starts_at")
                if starts_at:
                    local_time = starts_at.astimezone(tz_bali)
                    if local_time >= week_ago:
                        recent_closed_events.append(e)

        if active_events:
            text_parts.append("📝 **Созданные мной:**")
            for i, event in enumerate(active_events[:3], 1):
                title = event.get("title", "Без названия")
                location = event.get("location_name", "Место уточняется")
                starts_at = event.get("starts_at")

                if starts_at:
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = "Время уточняется"

                escaped_title = (
                    title.replace("\\", "\\\\")
                    .replace("*", "\\*")
                    .replace("_", "\\_")
                    .replace("`", "\\`")
                    .replace("[", "\\[")
                )
                escaped_location = (
                    location.replace("\\", "\\\\")
                    .replace("*", "\\*")
                    .replace("_", "\\_")
                    .replace("`", "\\`")
                    .replace("[", "\\[")
                )

                text_parts.append(f"{i}) {escaped_title}\n🕐 {time_str}\n📍 {escaped_location}\n")

            if len(active_events) > 3:
                text_parts.append(f"... и еще {len(active_events) - 3} событий")

        # Показываем недавно закрытые события
        if recent_closed_events:
            text_parts.append(f"\n🔴 **Недавно закрытые ({len(recent_closed_events)}):**")
            for i, event in enumerate(recent_closed_events[:3], 1):
                title = event.get("title", "Без названия")
                location = event.get("location_name", "Место уточняется")
                starts_at = event.get("starts_at")

                if starts_at:
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = "Время уточняется"

                escaped_title = (
                    title.replace("\\", "\\\\")
                    .replace("*", "\\*")
                    .replace("_", "\\_")
                    .replace("`", "\\`")
                    .replace("[", "\\[")
                )
                escaped_location = (
                    location.replace("\\", "\\\\")
                    .replace("*", "\\*")
                    .replace("_", "\\_")
                    .replace("`", "\\`")
                    .replace("[", "\\[")
                )

                text_parts.append(f"{i}) {escaped_title}\n🕐 {time_str}\n📍 {escaped_location} (закрыто)\n")

            if len(recent_closed_events) > 3:
                text_parts.append(f"... и еще {len(recent_closed_events) - 3} закрытых событий")

    # Если нет событий вообще
    if not events:
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else main_menu_kb()

    # Пытаемся отправить с изображением (как в on_my_events)
    import os
    from pathlib import Path

    photo_path = Path(__file__).parent / "images" / "my_events.png"

    if os.path.exists(photo_path):
        try:
            from aiogram.types import FSInputFile

            photo = FSInputFile(photo_path)
            # Удаляем старое сообщение и отправляем новое с изображением
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer_photo(photo, caption=text, reply_markup=keyboard, parse_mode="Markdown")
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото для 'Мои события': {e}", exc_info=True)

    # Fallback: отправляем только текст
    try:
        # Удаляем старое сообщение и отправляем новое
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")
        # Fallback - отправляем то же сообщение без Markdown
        await callback.message.answer(text, reply_markup=keyboard)


@main_router.callback_query(F.data.startswith("prev_event_"))
async def handle_prev_event(callback: types.CallbackQuery):
    """Возврат к предыдущему событию"""
    user_id = callback.from_user.id
    target_index = _extract_index(callback.data, prefix="prev_event_")
    active_events = _get_active_user_events(user_id)

    if target_index is None or target_index >= len(active_events):
        await callback.answer("Это единственное событие")
        return

    await _show_manage_event(callback, active_events, target_index)
    await callback.answer()


# Обработчик изменения статуса бота в чате
@main_router.my_chat_member()
async def handle_bot_chat_member_update(chat_member_update: ChatMemberUpdated, bot: Bot):
    """Обработчик изменения статуса бота в чате - настраиваем команды для групп"""

    # Проверяем, что это добавление бота в группу
    if chat_member_update.new_chat_member.status == "administrator" and chat_member_update.chat.type in [
        "group",
        "supergroup",
    ]:
        logger.info(f"Бот назначен админом в группе {chat_member_update.chat.id}")

        # Настраиваем команды для этой группы
        try:
            from group_router import setup_group_menu_button

            await setup_group_menu_button(bot)
            logger.info(f"✅ Команды настроены для группы {chat_member_update.chat.id}")
        except Exception as e:
            logger.warning(f"Не удалось настроить команды для группы {chat_member_update.chat.id}: {e}")

        # СТОРОЖ КОМАНД: проверяем и восстанавливаем команды при добавлении в группу
        try:
            await ensure_commands(bot)
            logger.info(f"✅ Сторож команд выполнен для группы {chat_member_update.chat.id}")
        except Exception as e:
            logger.error(f"❌ Ошибка сторожа команд для группы {chat_member_update.chat.id}: {e}")

        # УСТАНАВЛИВАЕМ КОМАНДЫ ДЛЯ КОНКРЕТНОЙ ГРУППЫ
        try:
            from group_router import ensure_group_start_command

            await ensure_group_start_command(bot, chat_member_update.chat.id)
            logger.info(f"✅ Команды установлены для группы {chat_member_update.chat.id}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось установить команды для группы {chat_member_update.chat.id}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
