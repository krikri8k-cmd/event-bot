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

# Импорт psutil для мониторинга памяти (опционально)
try:
    import psutil  # type: ignore

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

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
    cancel_task,
    complete_task,
    create_task_from_place,
    get_user_active_tasks,
)
from utils.event_translation import ensure_bilingual
from utils.geo_utils import get_timezone, haversine_km
from utils.i18n import format_translation, get_bot_username, t
from utils.static_map import build_static_map_url, fetch_static_map
from utils.unified_events_service import UnifiedEventsService
from utils.user_language import (
    get_user_language_or_default,
    needs_language_selection,
    set_user_language,
)
from utils.user_participation_analytics import UserParticipationAnalytics

# Тексты кнопок на обоих языках для сопоставления в обработчиках (reply-клавиатура)
_MAIN_MENU_BUTTON_TEXTS = (t("myevents.button.main_menu", "ru"), t("myevents.button.main_menu", "en"))
_FIND_ON_MAP_BUTTON_TEXTS = (t("tasks.button.find_on_map", "ru"), t("tasks.button.find_on_map", "en"))
_MY_EVENTS_BUTTON_TEXTS = (t("myevents.button.my_events", "ru"), t("myevents.button.my_events", "en"))
_MY_QUESTS_BUTTON_TEXTS = (t("myevents.button.my_quests", "ru"), t("myevents.button.my_quests", "en"))
_CANCEL_BUTTON_TEXTS = (t("common.cancel", "ru"), t("common.cancel", "en"))
_EVENTS_NEARBY_BUTTON_TEXTS = (t("menu.button.events_nearby", "ru"), t("menu.button.events_nearby", "en"))
_TASKS_TITLE_BUTTON_TEXTS = (t("tasks.title", "ru"), t("tasks.title", "en"))
_MY_ACTIVITIES_BUTTON_TEXTS = (t("menu.button.my_activities", "ru"), t("menu.button.my_activities", "en"))
_HELP_BUTTON_TEXTS = (t("command.help", "ru"), t("command.help", "en"))
_START_BUTTON_TEXTS = (t("menu.button.start", "ru"), t("menu.button.start", "en"))


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
    kept_by_type = {"source": 0, "user": 0, "community": 0, "ai_parsed": 0}

    logger.debug(f"🔍 PROCESSING {len(events)} events for filtering")
    for e in events:
        # 0) Сначала обогащаем локацию из текста
        e = enrich_venue_from_text(e)
        logger.debug(
            f"🔍 EVENT: {e.get('title')}, coords: {e.get('lat')}, {e.get('lng')}, type: {e.get('type')}, source: {e.get('source')}"
        )

        # Определяем тип события согласно ТЗ
        source = e.get("source", "")
        input_type = e.get("type", "")
        event_type = "source"  # по умолчанию

        # Проверяем, является ли это событием от группы (community)
        if source == "community" or input_type == "community":
            event_type = "community"
        # Проверяем, является ли это событием от пользователя (но не от группы)
        elif input_type == "user" or source in ["user_created", "user"]:
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

        # Для user и community URL не обязателен
        if event_type in ["user", "community"] and not url:
            # Пользовательские события и события от групп могут не иметь URL
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
            logger.debug(f"🔍 FILTERING USER EVENTS: user_radius={user_radius}, user_point={user_point}")
            if user_point and user_radius is not None:
                # Получаем координаты события
                event_lat = None
                event_lng = None

                # Проверяем новую структуру venue
                venue = e.get("venue", {})
                if venue.get("lat") is not None and venue.get("lon") is not None:
                    event_lat = venue.get("lat")
                    event_lng = venue.get("lon")
                    logger.debug(f"🔍 COORDS FROM VENUE: {event_lat}, {event_lng}")
                # Проверяем старую структуру
                elif e.get("lat") is not None and e.get("lng") is not None:
                    event_lat = e.get("lat")
                    event_lng = e.get("lng")
                    logger.debug(f"🔍 COORDS FROM EVENT: {event_lat}, {event_lng}")

                if event_lat is not None and event_lng is not None:
                    # Вычисляем расстояние
                    from utils.geo_utils import haversine_km

                    distance = haversine_km(user_point[0], user_point[1], event_lat, event_lng)
                    logger.debug(
                        f"🔍 FILTER CHECK: event='{title}', event_coords=({event_lat},{event_lng}), user_coords=({user_point[0]},{user_point[1]}), distance={distance:.2f}km, user_radius={user_radius}km"
                    )
                    if distance > user_radius:
                        logger.warning(
                            f"❌ FILTERED OUT: '{title}' - distance {distance:.2f}km > radius {user_radius}km"
                        )
                        drop.add("user_event_out_of_radius", title)
                        continue
                    else:
                        logger.debug(f"✅ KEPT: '{title}' - distance {distance:.2f}km <= radius {user_radius}km")
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
    community_count = sum(1 for e in events if e.get("type") == "community")

    summary_lines = [f"🗺 Найдено {len(events)} событий рядом!"]

    # Показываем только ненулевые счетчики
    if source_count > 0:
        summary_lines.append(f"• Из источников: {source_count}")
    if ai_parsed_count > 0:
        summary_lines.append(f"• AI-парсинг: {ai_parsed_count}")
    if user_count > 0:
        summary_lines.append(f"• От пользователей: {user_count}")
    if community_count > 0:
        summary_lines.append(f"• 💥 От групп: {community_count}")

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
    user_lang = get_user_language_or_default(message.from_user.id)
    header_html = render_header(counts, radius_km=int(radius), lang=user_lang)
    # Данные из БД уже с location_name (ingest). Enrich в хендлере не вызываем.
    events_text, total_pages = render_page(prepared_events, page + 1, page_size=8, user_id=message.from_user.id)

    # Отладочная информация

    text = header_html + "\n\n" + events_text

    # Вычисляем total_pages для fallback
    total_pages = max(1, ceil(len(prepared_events) / 8))

    # Создаем клавиатуру с кнопками пагинации и расширения радиуса
    keyboard = kb_pager(page + 1, total_pages, int(radius), lang=user_lang)

    try:
        # Отправляем компактный список событий в HTML формате
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"✅ Страница {page + 1} событий отправлена (HTML)")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки страницы {page + 1}: {e}")
        # Fallback - отправляем без форматирования (без превью ссылок)
        user_lang = get_user_language_or_default(message.from_user.id)
        header = format_translation("events.page", user_lang, page=page + 1, total=total_pages)
        await message.answer(f"{header}\n\n{text}", reply_markup=keyboard, disable_web_page_preview=True)


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
    logger.debug("prepared: kept=%s dropped=%s reasons_top3=%s", diag["kept"], diag["dropped"], diag["reasons_top3"])
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

    # Данные из БД уже с location_name (ingest). Enrich в хендлере не вызываем.
    # 6) Рендерим страницу
    user_lang = get_user_language_or_default(message.from_user.id)
    header_html = render_header(counts, radius_km=int(radius), lang=user_lang)
    page_html, total_pages = render_page(prepared, page=page + 1, page_size=8, user_id=message.from_user.id)
    text = header_html + "\n\n" + page_html

    # 6) Создаем клавиатуру пагинации с кнопками расширения радиуса
    inline_kb = kb_pager(page + 1, total_pages, int(radius), lang=user_lang) if total_pages > 1 else None

    try:
        # Отправляем компактный список событий в HTML формате
        await message.answer(text, reply_markup=inline_kb, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"✅ Страница {page + 1} событий отправлена (HTML)")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки страницы {page + 1}: {e}")
        # Fallback - отправляем без форматирования (без превью ссылок)
        user_lang = get_user_language_or_default(message.from_user.id)
        header = format_translation("events.page", user_lang, page=page + 1, total=total_pages)
        await message.answer(f"{header}\n\n{text}", reply_markup=inline_kb, disable_web_page_preview=True)

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
    user_lang = get_user_language_or_default(message.from_user.id)
    header_html = render_header(counts, radius_km=int(radius), lang=user_lang)

    # Формируем HTML карточки событий
    event_lines = []
    for idx, event in enumerate(page_events, start=start_idx + 1):
        event_html = render_event_html(event, idx, message.from_user.id)
        event_lines.append(event_html)

    text = header_html + "\n\n" + "\n".join(event_lines)

    # Создаем клавиатуру пагинации с кнопками расширения радиуса
    inline_kb = kb_pager(page + 1, total_pages, int(radius), lang=user_lang) if total_pages > 1 else None

    try:
        # Редактируем сообщение
        await message.edit_text(text, reply_markup=inline_kb, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"✅ Страница {page + 1} событий отредактирована (HTML)")
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования страницы {page + 1}: {e}")


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
                logger.debug(
                    "🚗 Используем location_url для маршрута, событие: %s", (e.get("title") or "Без названия")[:30]
                )
                return location_url
            else:
                # Нет валидного URL источника - пропускаем location_url для безопасности
                logger.debug(
                    "⚠️ Пропускаем location_url для ai-события без валидного URL: %s",
                    (e.get("title") or "Без названия")[:30],
                )
        else:
            # Для других типов событий (source, user) используем location_url
            logger.debug(
                "🚗 Используем location_url для маршрута, событие: %s", (e.get("title") or "Без названия")[:30]
            )
            return location_url

    # Поддерживаем новую структуру venue и старую
    # Приоритет: venue.name (из источника) > venue_name (из источника) > location_name (может быть из reverse geocoding)
    # Это важно, чтобы названия из источника имели приоритет над адресами
    # ПРИОРИТЕТ 1: Если есть place_id, используем ссылку на конкретное место
    place_id = e.get("place_id")
    if place_id:
        from utils.geo_utils import to_google_maps_link

        lat = e.get("lat")
        lng = e.get("lng")
        if lat is not None and lng is not None:
            logger.info(
                f"🚗 Используем place_id для маршрута: '{place_id}' для события '{e.get('title', 'Без названия')[:30]}'"
            )
            return to_google_maps_link(lat, lng, place_id)
        else:
            logger.warning(
                f"⚠️ place_id есть, но нет координат для события '{e.get('title', 'Без названия')[:30]}': lat={lat}, lng={lng}"
            )

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
        from utils.geo_utils import to_google_maps_link

        return to_google_maps_link(lat, lng)
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
    """Рендерит одну карточку в HTML. EN: title_en/description_en с fallback на RU; локация — всегда оригинальный location_name (без GPT)."""
    import logging

    logger = logging.getLogger(__name__)

    lang = get_user_language_or_default(user_id) if user_id else "ru"
    if lang == "en":
        title_en = (e.get("title_en") or "").strip()
        title_ru = (e.get("title") or "Событие").strip()
        display_title = title_en if title_en else title_ru
        if not title_en and title_ru:
            logger.debug(
                "render_event_html: lang=en, title_en пустой для id=%s, показываем оригинал",
                e.get("id"),
            )
    else:
        display_title = (e.get("title") or "Событие").strip()
    display_description = (
        (e.get("description_en") or e.get("description") or "").strip()
        if lang == "en"
        else (e.get("description") or "").strip()
    )
    # Локация всегда только оригинал (location_name), не переводим названия заведений
    display_location_name = (e.get("location_name") or "").strip()
    display_venue_name = (e.get("venue_name") or e.get("location_name") or "").strip()
    # Локализация подписей ссылок по языку пользователя
    source_link_label = t("event.source_link", lang)
    route_link_label = t("event.route_link", lang)

    title = html.escape(display_title or "Событие")
    when = e.get("when_str", "")

    logger.debug("🕐 render_event_html: title=%s, when_str=%s", title[:40] if title else "", when)

    # Если when_str пустое, используем функцию human_when с учетом часового пояса пользователя
    if not when:
        when = human_when(e, user_id=user_id)
    dist = f"{e['distance_km']:.1f} км" if e.get("distance_km") is not None else ""

    # Определяем тип события, если не установлен
    event_type = e.get("type")
    source = e.get("source", "")
    source_type = e.get("source_type", "")

    logger.debug("🔍 event_type=%s, source=%s, source_type=%s", event_type, source, source_type)

    if not event_type:
        if source == "community":
            event_type = "community"
        elif source == "user" or source_type == "user":
            event_type = "user"
        else:
            event_type = "source"

    logger.debug("🔍 FINAL: event_type=%s для события %s", event_type, (e.get("title") or "Без названия")[:20])

    # Поддерживаем новую структуру venue и старую; для EN используем display_venue_name (location_name_en или venue_name)
    venue = e.get("venue", {})
    venue_name = venue.get("name") or display_venue_name or e.get("venue_name")
    # НЕ используем location_url как venue_address - это ссылка, а не название места
    venue_address = venue.get("address") or e.get("address")

    logger.debug("🔍 VENUE: venue_name=%s, venue_address=%s", venue_name, venue_address)
    logger.debug(
        "🔍 EVENT FIELDS: venue_name=%s, location_name=%s, address=%s",
        (e.get("venue_name") or "")[:30],
        (e.get("location_name") or "")[:30],
        (e.get("address") or "")[:30],
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

    # Приоритет: venue_name → address → location_name → coords → description (локация всегда оригинал)
    location_name_from_event = display_location_name

    logger.debug(
        "🔍 LOCATION: venue_name=%s, lat=%s, lng=%s",
        (venue_name or "")[:30],
        e.get("lat"),
        e.get("lng"),
    )

    # Если нет названия места, но есть координаты - пробуем reverse geocoding прямо здесь
    if (
        not venue_name
        and not (venue_address and venue_address not in generic_venues)
        and not (location_name_from_event and location_name_from_event not in generic_venues)
        and e.get("lat")
        and e.get("lng")
    ):
        try:
            import asyncio

            from utils.geo_utils import reverse_geocode

            # Пробуем синхронно выполнить reverse geocoding (если есть event loop)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Если loop уже запущен, создаем задачу, но не ждем её
                    # В этом случае покажем координаты, но в фоне попробуем получить название
                    logger.debug("⚠️ Event loop уже запущен, пропускаем reverse geocoding в render_event_html")
                else:
                    # Если loop не запущен, можем запустить
                    reverse_name = loop.run_until_complete(reverse_geocode(e["lat"], e["lng"]))
                    if reverse_name and reverse_name not in generic_venues:
                        location_name_from_event = reverse_name
                        logger.info(f"✅ Получено название места через reverse geocoding в render: {reverse_name}")
            except RuntimeError:
                # Нет event loop, создаем новый
                reverse_name = asyncio.run(reverse_geocode(e["lat"], e["lng"]))
                if reverse_name and reverse_name not in generic_venues:
                    location_name_from_event = reverse_name
                    logger.info(f"✅ Получено название места через reverse geocoding в render: {reverse_name}")
        except Exception as geocode_error:
            logger.debug(f"⚠️ Не удалось выполнить reverse geocoding в render_event_html: {geocode_error}")

    if venue_name:
        venue_display = html.escape(venue_name)
        logger.debug(f"🔍 DEBUG: Используем venue_name: '{venue_display}'")
    elif venue_address and venue_address not in generic_venues:
        venue_display = html.escape(venue_address)
        logger.debug(f"🔍 DEBUG: Используем venue_address: '{venue_display}'")
    elif location_name_from_event and location_name_from_event not in generic_venues:
        # Используем location_name (может быть из reverse geocoding или из БД)
        venue_display = html.escape(location_name_from_event)
        logger.debug(f"🔍 DEBUG: Используем location_name: '{venue_display}'")
    elif e.get("lat") and e.get("lng"):
        venue_display = f"координаты ({e['lat']:.4f}, {e['lng']:.4f})"
        logger.debug(f"🔍 DEBUG: Используем координаты: '{venue_display}'")
    elif event_type in ["user", "community"] and (e.get("description") or display_description):
        # Для пользовательских событий и событий от групп показываем описание вместо "Локация уточняется"
        description = display_description
        if description:
            # Ограничиваем длину описания для красоты
            if len(description) > 100:
                description = description[:97] + "..."
            venue_display = html.escape(description)
            logger.debug(f"🔍 DEBUG: Используем описание: '{venue_display}'")
        else:
            # Если нет описания, проверяем location_name перед координатами
            if location_name_from_event and location_name_from_event not in generic_venues:
                venue_display = html.escape(location_name_from_event)
                logger.debug(f"🔍 DEBUG: Описание пустое, используем location_name: '{venue_display}'")
            elif e.get("lat") and e.get("lng"):
                venue_display = f"координаты ({e['lat']:.4f}, {e['lng']:.4f})"
                logger.debug(f"🔍 DEBUG: Описание пустое, используем координаты: '{venue_display}'")
            else:
                venue_display = "Локация"
                logger.debug(f"🔍 DEBUG: Описание пустое, используем fallback: '{venue_display}'")
    else:
        # Для событий от парсеров: проверяем location_name перед координатами
        if location_name_from_event and location_name_from_event not in generic_venues:
            venue_display = html.escape(location_name_from_event)
            logger.debug(f"🔍 DEBUG: Используем location_name как fallback: '{venue_display}'")
        elif e.get("lat") and e.get("lng"):
            venue_display = f"координаты ({e['lat']:.4f}, {e['lng']:.4f})"
            logger.debug(f"🔍 DEBUG: Используем координаты как fallback: '{venue_display}'")
        else:
            venue_display = "Локация"
            logger.debug(f"🔍 DEBUG: Используем fallback: '{venue_display}'")

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
    elif event_type == "community":
        # События от групп - показываем автора отдельно, группу отдельно
        organizer_id = e.get("organizer_id")
        organizer_username = e.get("organizer_username")
        group_name = e.get("community_name")

        logger.info(
            f"💬 Событие от группы: organizer_id={organizer_id}, organizer_username={organizer_username}, group_name={group_name}"
        )

        # Используем функцию для отображения автора (без группы, группа будет отдельно)
        from utils.author_display import format_author_display

        src_part = format_author_display(organizer_id, organizer_username)
        # Заменяем 👤 на 👥 для событий от групп
        src_part = src_part.replace("👤", "👥")
        logger.info(f"💬 Отображение автора из группы: {src_part}")
    else:
        # Для источников и AI-парсинга показываем источник
        src = get_source_url(e)
        if src:
            # Используем API endpoint для отслеживания кликов
            tracking_url = _build_tracking_url("source", e, src, user_id)
            src_part = f'🌐 <a href="{html.escape(tracking_url)}">{source_link_label}</a>'
        else:
            src_part = f"ℹ️ {t('event.source_not_specified', lang)}"

    # Маршрут с приоритетом venue_name → address → coords
    maps_url = build_maps_url(e)
    map_part = f'🚗 <a href="{_build_tracking_url("route", e, maps_url, user_id)}">{route_link_label}</a>'

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

    logger.debug("🕐 render_event_html ИТОГ: title=%s, when=%s, dist=%s", (title or "")[:40], when, dist)
    logger.debug("🔍 src_part len=%s, map_part len=%s", len(src_part or ""), len(map_part or ""))

    # Формируем строку с автором и группой (для community событий)
    if event_type == "community":
        # Для событий от групп: автор → маршрут → группа
        group_name = e.get("community_name")
        if group_name:
            group_part = f"  💥@{html.escape(group_name)}"
        else:
            group_part = "  💥от группы"
        author_line = f"{src_part}  {map_part}{group_part}" if src_part else f"{map_part}{group_part}"
    else:
        # Для остальных событий: автор → маршрут
        author_line = f"{src_part}  {map_part}" if src_part else map_part
    logger.debug("🔍 author_line len=%s", len(author_line or ""))

    # Добавляем описание для пользовательских событий и событий от групп (уже по языку: display_description)
    description_part = ""
    if event_type in ["user", "community"] and display_description:
        desc = display_description
        if len(desc) > 150:
            desc = desc[:147] + "..."
        description_part = f"\n📝 {html.escape(desc)}"
        logger.debug(f"🔍 DEBUG: Добавлено описание: '{desc[:50]}...'")

    logger.debug("🔍 ПЕРЕД final_html: venue_display len=%s", len(venue_display or ""))

    # Проверяем venue_display прямо в f-string
    test_venue = venue_display
    logger.debug("🔍 test_venue=%s", (test_venue or "")[:30])

    final_html = (
        f"{idx}) <b>{title}</b> — {when} ({dist}){timer_part}\n📍 {test_venue}\n{author_line}{description_part}\n"
    )
    logger.debug("🔍 ПОСЛЕ final_html: venue_display len=%s", len(venue_display or ""))
    logger.debug("🔍 FINAL HTML (lang=%s): %s", lang, final_html[:300] + ("..." if len(final_html) > 300 else ""))
    return final_html


def render_fallback(lat: float, lng: float, lang: str = "ru") -> str:
    """Fallback страница при ошибках в пайплайне (локализованные подписи ссылок)."""
    src_txt = t("event.source_not_specified", lang)
    route_txt = t("event.route_link", lang)
    maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    link_route = f'🚗 <a href="{maps_url}">{route_txt}</a>'
    line = f"ℹ️ {src_txt}  {link_route}"
    return (
        f"🗺 <b>Найдено рядом: 0</b>\n"
        f"• 👥 От пользователей: 0\n"
        f"• 🌐 Из источников: 0\n\n"
        f"1) <b>Попробуйте расширить поиск</b> — (0.0 км)\n"
        f"📍 Локация\n"
        f"{line}\n\n"
        f"2) <b>Создайте своё событие</b> — (0.0 км)\n"
        f"📍 Локация\n"
        f"{line}\n\n"
        f"3) <b>Проверьте позже</b> — (0.0 км)\n"
        f"📍 Локация\n"
        f"{line}"
    )


async def enrich_events_with_reverse_geocoding(events: list[dict], user_id: int | None = None) -> list[dict]:
    """
    Обогащает события обратным геокодированием для получения названий локаций из координат.
    user_id: если передан, в запросы Google API добавляется language=user_lang (en/ru).
    """
    import logging

    logger = logging.getLogger(__name__)
    geo_lang = get_user_language_or_default(user_id) if user_id else None

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

                reverse_name = await reverse_geocode(lat, lng, language=geo_lang)
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

    # Выполняем обогащение параллельно, но с ограничением для защиты от OOM
    import asyncio

    logger.info(f"🔄 Начинаем обогащение {len(events)} событий через reverse geocoding")
    # ОГРАНИЧЕНИЕ: обрабатываем максимум 10 событий параллельно для защиты от OOM
    MAX_PARALLEL_GEOCODE = 10
    enriched_events = []
    for i in range(0, len(events), MAX_PARALLEL_GEOCODE):
        batch = events[i : i + MAX_PARALLEL_GEOCODE]
        batch_results = await asyncio.gather(*[enrich_single_event(event) for event in batch])
        enriched_events.extend(batch_results)

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
        logger.debug(
            "🕐 render_page: событие %s - starts_at=%s, title=%s", idx, e.get("starts_at"), (e.get("title") or "")[:30]
        )
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


def kb_pager(
    page: int,
    total: int,
    current_radius: int = None,
    date_filter: str = "today",
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """Создает клавиатуру пагинации с кнопками расширения радиуса и фильтрации даты"""
    from config import load_settings

    settings = load_settings()

    buttons = []

    # Принцип «Все или ничего»: блок стрелок только при total > 1; один ряд: ← | Стр. N/M | →
    # Кольцо: Назад на 1-й → последняя; Вперёд на последней → 1-я
    if total > 1:
        prev_page = total if page == 1 else page - 1
        next_page = 1 if page == total else page + 1
        buttons.append(
            [
                InlineKeyboardButton(
                    text=format_translation("pager.page", lang, page=page, total=total),
                    callback_data="pg:noop",
                ),
                InlineKeyboardButton(text=t("pager.prev", lang), callback_data=f"pg:{prev_page}"),
                InlineKeyboardButton(text=t("pager.next", lang), callback_data=f"pg:{next_page}"),
            ]
        )

    # Добавляем кнопки фильтрации даты (Сегодня/Завтра)
    if date_filter == "today":
        buttons.append(
            [
                InlineKeyboardButton(text=t("pager.today_selected", lang), callback_data="date_filter:today"),
                InlineKeyboardButton(text=t("pager.tomorrow", lang), callback_data="date_filter:tomorrow"),
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(text=t("pager.today", lang), callback_data="date_filter:today"),
                InlineKeyboardButton(text=t("pager.tomorrow_selected", lang), callback_data="date_filter:tomorrow"),
            ]
        )

    # Добавляем кнопки расширения радиуса, используя фиксированные RADIUS_OPTIONS
    if current_radius is None:
        current_radius = int(settings.default_radius_km)

    # Добавляем кнопки изменения радиуса
    buttons.extend(build_radius_inline_buttons(current_radius, lang))

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def group_by_type(events):
    """Группирует события по типам согласно ТЗ"""
    return {
        "source": [e for e in events if e.get("type") == "source"],
        "user": [e for e in events if e.get("type") == "user"],
        "community": [e for e in events if e.get("type") == "community"],
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
        "community": len(groups.get("community", [])),  # События от групп
        "sources": len(groups.get("source", [])) + ai_count,  # AI события считаются как источники
    }
    logger.debug("🔍 make_counts: groups=%s, counts=%s", list(groups.keys()), counts)
    return counts


def render_header(counts, radius_km: int = None, lang: str = "ru") -> str:
    """Рендерит заголовок с счетчиками (только ненулевые)"""
    if radius_km:
        lines = [format_translation("events.header.found_in_radius", lang, radius=radius_km, count=counts["all"])]
    else:
        lines = [format_translation("events.header.found_nearby", lang, count=counts["all"])]

    if counts["user"]:
        lines.append(format_translation("events.header.from_users", lang, count=counts["user"]))
    if counts.get("community", 0):
        lines.append(format_translation("events.header.from_groups", lang, count=counts["community"]))
    if counts["sources"]:
        lines.append(format_translation("events.header.from_sources", lang, count=counts["sources"]))
    return "\n".join(lines)


# --- /Эталонные функции ---

# Загружаем настройки
# Для бота — токен обязателен
settings = load_settings(require_bot=True)

# Хранилище состояния для сохранения prepared событий по chat_id
# ВАЖНО: Очищаем старые записи для предотвращения утечек памяти
#
# АРХИТЕКТУРНОЕ ПРАВИЛО:
# - PostgreSQL является единственным источником правды (source of truth)
# - user_state - временный кэш для UI/навигации, может быть очищен в любой момент
# - ВАЖНО: Все критичные данные (события, пользователи) сохраняются в PostgreSQL СРАЗУ
# - Порядок операций: 1) Сохранение в PostgreSQL, 2) Обновление user_state
# - В user_state хранятся ТОЛЬКО простые типы: dict, list, int, str, float
# - ЗАПРЕЩЕНО хранить функции, замыкания, объекты с методами
user_state = {}
_user_state_timestamps = {}  # Время последнего использования для каждого chat_id
# СНИЖЕНО для более агрессивной защиты от OOM
USER_STATE_MAX_SIZE = 200  # Максимальное количество пользователей в памяти (было 500)
USER_STATE_TTL_SECONDS = 900  # Время жизни состояния: 15 минут (было 30 минут)


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
    MAX_PREPARED_EVENTS = 20  # Агрессивный лимит против OOM (было 50)

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


def get_memory_usage_mb() -> float:
    """Возвращает текущее использование памяти процесса в МБ"""
    if PSUTIL_AVAILABLE:
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024  # RSS в МБ
        except Exception:
            pass
    return 0.0


def get_memory_stats() -> dict:
    """Возвращает статистику использования памяти"""
    stats = {
        "user_state_size": len(user_state),
        "user_state_timestamps_size": len(_user_state_timestamps),
        "prepared_events_total": 0,
        "memory_mb": get_memory_usage_mb(),
    }

    # Подсчитываем общее количество prepared событий
    for state in user_state.values():
        if "prepared" in state and isinstance(state["prepared"], list):
            stats["prepared_events_total"] += len(state["prepared"])

    return stats


def log_memory_stats():
    """Логирует статистику использования памяти"""
    stats = get_memory_stats()
    logger.info(
        f"📊 MEMORY STATS: "
        f"user_state={stats['user_state_size']}, "
        f"prepared_events={stats['prepared_events_total']}, "
        f"memory={stats['memory_mb']:.1f}MB"
    )


# Порог памяти для принудительной очистки (в МБ). 256 МБ — агрессивная защита от OOM.
MEMORY_THRESHOLD_MB = 256


def force_memory_cleanup():
    """Принудительная очистка памяти при превышении порога"""
    global user_state, _user_state_timestamps

    if not PSUTIL_AVAILABLE:
        return

    memory_mb = get_memory_usage_mb()
    if memory_mb < MEMORY_THRESHOLD_MB:
        return

    logger.warning(
        f"⚠️ MEMORY GUARD: Память превысила порог ({memory_mb:.1f}MB > {MEMORY_THRESHOLD_MB}MB), "
        f"выполняю принудительную очистку"
    )

    # Агрессивная очистка user_state (удаляем 70% самых старых для более радикальной очистки)
    if len(user_state) > 0:
        sorted_chats = sorted(_user_state_timestamps.items(), key=lambda x: x[1])
        to_remove = max(1, int(len(user_state) * 0.7))  # Удаляем 70% самых старых
        removed_count = 0
        for chat_id, _ in sorted_chats[:to_remove]:
            if chat_id in user_state:
                user_state.pop(chat_id, None)
                _user_state_timestamps.pop(chat_id, None)
                removed_count += 1

        logger.warning(f"🧹 MEMORY GUARD: Удалено {removed_count} записей из user_state")

    # Очистка prepared_events (оставляем только последние 10 вместо 20)
    for chat_id, state in list(user_state.items()):
        if "prepared" in state and isinstance(state["prepared"], list):
            if len(state["prepared"]) > 10:
                state["prepared"] = state["prepared"][-10:]

    # Очистка _processed_callbacks через middleware (если доступен)
    # Это будет сделано в самом middleware

    # Логируем результат
    new_memory_mb = get_memory_usage_mb()
    logger.warning(
        f"✅ MEMORY GUARD: Очистка завершена, память: {new_memory_mb:.1f}MB "
        f"(освобождено {memory_mb - new_memory_mb:.1f}MB)"
    )


async def periodic_cleanup_user_state():
    """Периодическая очистка user_state каждые 5 минут + логирование памяти каждые 2 минуты"""
    memory_log_interval = 120  # 2 минуты для логирования памяти (было 5)
    cleanup_interval = 300  # 5 минут для очистки (было 15)
    last_memory_log = time.time()
    last_cleanup = time.time()

    while True:
        await asyncio.sleep(30)  # Проверяем каждые 30 секунд для более частой проверки
        current_time = time.time()

        try:
            # Логирование памяти каждые 2 минуты
            if current_time - last_memory_log >= memory_log_interval:
                log_memory_stats()
                last_memory_log = current_time

            # Очистка каждые 5 минут
            if current_time - last_cleanup >= cleanup_interval:
                cleanup_user_state()
                cleanup_large_prepared_events()
                logger.debug("🧹 Периодическая очистка user_state выполнена")
                last_cleanup = current_time

            # Memory guard: проверка и принудительная очистка при превышении порога
            force_memory_cleanup()

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


def build_radius_inline_buttons(current_radius: int, lang: str = "ru") -> list[list[InlineKeyboardButton]]:
    """Формирует список кнопок для изменения радиуса поиска."""
    buttons_row = []
    for radius_option in RADIUS_OPTIONS:
        if radius_option == current_radius:
            continue
        buttons_row.append(
            InlineKeyboardButton(
                text=format_translation("pager.radius_km", lang, radius=radius_option),
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
    user_lang = get_user_language_or_default(user_id)
    logger.info(f"📍 perform_nearby_search: user_id={user_id}, lat={lat}, lng={lng}, source={source}")

    loading_message = await message.answer(
        t("search.loading", user_lang),
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

            logger.debug("🌍 Поиск событий: координаты=(%s, %s), радиус=%s км, регион=%s", lat, lng, radius, city)

            # Только SELECT из БД; парсинг (BaliForum, KudaGo, AI) не вызывается — данные обновляются по расписанию.
            events = events_service.search_events_today(city=city, user_lat=lat, user_lng=lng, radius_km=int(radius))

            formatted_events = []
            logger.debug("🕐 Получили %s событий из UnifiedEventsService", len(events))
            for event in events:
                formatted_event = {
                    "id": event.get("id"),
                    "title": event["title"],
                    "title_en": event.get("title_en"),
                    "description": event["description"],
                    "description_en": event.get("description_en"),
                    "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
                    "starts_at": event["starts_at"],
                    "city": event.get("city"),
                    "location_name": event["location_name"],
                    "location_name_en": event.get("location_name_en"),
                    "location_url": event["location_url"],
                    "lat": event["lat"],
                    "lng": event["lng"],
                    "source": event.get("source", ""),
                    "source_type": event.get("source_type", ""),
                    "url": event.get("event_url", ""),
                    "community_name": "",
                    "community_link": "",
                    "venue_name": event.get("venue_name"),
                    "address": event.get("address"),
                    "organizer_id": event.get("organizer_id"),
                    "organizer_username": event.get("organizer_username"),
                    "place_id": event.get("place_id"),
                }
                formatted_events.append(formatted_event)

            events = sort_events_by_time(formatted_events)
            logger.debug("📅 События отсортированы по времени")
        except Exception:
            logger.exception("❌ Ошибка при поиске событий")
            try:
                await loading_message.delete()
            except Exception:
                pass
            user_id = message.from_user.id
            fallback = render_fallback(lat, lng, get_user_language_or_default(user_id))
            await message.answer(
                fallback,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=main_menu_kb(user_id=user_id),
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
                            InlineKeyboardButton(
                                text=t("pager.today_selected", user_lang), callback_data="date_filter:today"
                            ),
                            InlineKeyboardButton(
                                text=t("pager.tomorrow", user_lang), callback_data="date_filter:tomorrow"
                            ),
                        ]
                    )
                else:
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(text=t("pager.today", user_lang), callback_data="date_filter:today"),
                            InlineKeyboardButton(
                                text=t("pager.tomorrow_selected", user_lang),
                                callback_data="date_filter:tomorrow",
                            ),
                        ]
                    )

                # Добавляем кнопки радиуса
                keyboard_buttons.extend(build_radius_inline_buttons(current_radius, user_lang))

                # Добавляем кнопку создания события
                keyboard_buttons.append(
                    [InlineKeyboardButton(text=t("menu.button.create_event", user_lang), callback_data="create_event")]
                )
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

            header_html = render_header(counts, radius_km=int(radius), lang=user_lang)
            # Данные из БД уже с location_name (заполняется при ingest). Enrich в хендлере не вызываем.
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

                logger.debug(
                    "📊 list_view: user_id=%s, event_id=%s, group_chat_id=%s",
                    user_id,
                    event_id,
                    group_chat_id,
                )
                participation_analytics.record_list_view(
                    user_id=user_id,
                    event_id=event_id,
                    group_chat_id=group_chat_id,
                )

            total_pages = max(1, ceil(len(prepared) / 8))
            date_filter_state = user_state.get(message.chat.id, {}).get("date_filter", "today")
            combined_keyboard = kb_pager(1, total_pages, int(radius), date_filter=date_filter_state, lang=user_lang)

            # ИСПРАВЛЕНИЕ: Отправляем карту и список событий отдельными сообщениями
            if map_bytes:
                # Отправляем карту отдельным сообщением
                map_file = BufferedInputFile(map_bytes, filename="map.jpg")
                map_caption = ""  # Без подписи — карта и так понятна
                map_message = await message.answer_photo(
                    map_file,
                    caption=map_caption,
                    parse_mode="HTML",
                )
                logger.info("✅ Карта отправлена отдельным сообщением (send_compact_events_list)")
                # Освобождаем память сразу после отправки карты
                del map_bytes
                del map_file

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
                logger.debug("✅ Список событий отправлен отдельным сообщением (send_compact_events_list)")

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
        # СНИЖЕНО для более агрессивной защиты от OOM
        self._max_size = 5000  # Максимальное количество хранимых ID (было 10000)

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

            # Очищаем старые записи, если слишком много (in-place, без создания списка)
            if len(self._processed_callbacks) > self._max_size:
                # Удаляем первые 2500 элементов (старые записи) - более агрессивная очистка
                # Используем итератор для более эффективной очистки
                removed_count = 0
                for item in list(self._processed_callbacks):  # Создаем список только один раз
                    if removed_count >= 2500:  # Было 5000
                        break
                    self._processed_callbacks.discard(item)
                    removed_count += 1
                logger.debug(f"🧹 Очищено {removed_count} старых callback ID из _processed_callbacks")

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
                    ban_msg = t("errors.banned", get_user_language_or_default(user_id))
                    try:
                        if hasattr(event, "answer"):
                            await event.answer(ban_msg)
                        elif hasattr(event, "message") and event.message:
                            await event.message.answer(ban_msg)
                    except Exception:
                        pass  # Игнорируем ошибки отправки
                    return  # Прерываем обработку

        return await handler(event, data)


def _get_tg_user_from_event(event: Any):
    """Извлечь Telegram User из события (Update, Message, CallbackQuery и т.д.)."""
    if (
        hasattr(event, "from_user")
        and getattr(event, "from_user", None)
        and not getattr(event.from_user, "is_bot", True)
    ):
        return event.from_user
    if hasattr(event, "message") and getattr(event, "message", None):
        msg = event.message
        if hasattr(msg, "from_user") and msg.from_user and not getattr(msg.from_user, "is_bot", True):
            return msg.from_user
    if hasattr(event, "message") and getattr(event, "message", None) is None and hasattr(event, "from_user"):
        if event.from_user and not getattr(event.from_user, "is_bot", True):
            return event.from_user
    # Aiogram 3: event может быть Update
    for attr in ("message", "edited_message", "callback_query", "inline_query", "my_chat_member", "chat_member"):
        obj = getattr(event, attr, None)
        if obj is None:
            continue
        if hasattr(obj, "from_user") and obj.from_user and not getattr(obj.from_user, "is_bot", True):
            return obj.from_user
    return None


class EnsureUserMiddleware(BaseMiddleware):
    """Создаёт запись в users при любом первом взаимодействии (не только /start)."""

    async def __call__(
        self, handler: Callable[[Any, dict[str, Any]], Awaitable[Any]], event: Any, data: dict[str, Any]
    ) -> Any:
        tg_user = (
            data.get("event_from_user")
            if isinstance(data.get("event_from_user"), types.User)
            else _get_tg_user_from_event(event)
        )
        if tg_user:
            asyncio.create_task(ensure_user_exists(tg_user.id, tg_user))
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

# Регистрация пользователя при любом первом взаимодействии (ЛС и группы)
dp.update.middleware(EnsureUserMiddleware())
logging.info("✅ EnsureUser middleware подключен")

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


def edit_event_keyboard(event_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для редактирования события"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("edit.button.title", lang), callback_data=f"edit_title_{event_id}")],
            [InlineKeyboardButton(text=t("edit.button.date", lang), callback_data=f"edit_date_{event_id}")],
            [InlineKeyboardButton(text=t("edit.button.time", lang), callback_data=f"edit_time_{event_id}")],
            [InlineKeyboardButton(text=t("edit.button.location", lang), callback_data=f"edit_location_{event_id}")],
            [
                InlineKeyboardButton(
                    text=t("edit.button.description", lang), callback_data=f"edit_description_{event_id}"
                )
            ],
            [InlineKeyboardButton(text=t("edit.button.finish", lang), callback_data=f"edit_finish_{event_id}")],
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
            # Синхронизация с Community: если это событие из community — обновить и там
            if event.source == "community" and event.external_id and str(event.external_id).startswith("community:"):
                from utils.sync_community_world_events import sync_world_event_to_community

                sync_world_event_to_community(event_id, get_session)
            return True

    except Exception as e:
        logging.error(f"Ошибка обновления события {event_id}: {e}")
        return False


async def send_spinning_menu(message, lang: str | None = None):
    """Отправляет анимированное меню с эпической ракетой. Если передан lang, клавиатура в этом языке (чтобы не переключаться на русский после создания события)."""
    rocket_frames = ["🚀", "🔥", "💥", "⚡", "🎯"]
    user_id = message.from_user.id
    reply_kb = main_menu_kb(lang=lang, user_id=user_id if lang is None else None)

    # Отправляем первый кадр (reply-клавиатура только у answer, edit_text не меняет reply keyboard)
    menu_message = await message.answer(rocket_frames[0], reply_markup=reply_kb)

    # Анимируем эпический полет (динамичная анимация)
    try:
        for frame in rocket_frames[1:]:
            await asyncio.sleep(0.5)  # Пауза между кадрами для эффектности
            await menu_message.edit_text(frame)
    except Exception:
        # Если редактирование не удалось, просто оставляем мишень
        try:
            await menu_message.edit_text("🎯")
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


def main_menu_kb(lang: str | None = None, user_id: int | None = None) -> ReplyKeyboardMarkup:
    """
    Создаёт главное меню с учётом языка

    Args:
        lang: Код языка ('ru' или 'en'). Если не указан, будет получен из user_id или использован 'ru'
        user_id: ID пользователя для получения языка из БД (если lang не указан)
    """
    from config import load_settings

    load_settings()

    # Определяем язык
    if lang is None:
        if user_id is not None:
            lang = get_user_language_or_default(user_id)
        else:
            lang = "ru"

    keyboard = [
        [
            KeyboardButton(text=t("menu.button.events_nearby", lang)),
            KeyboardButton(text=t("menu.button.interesting_places", lang)),
        ],
        [
            KeyboardButton(text=t("menu.button.create", lang)),
            KeyboardButton(text=t("menu.button.my_activities", lang)),
        ],
        [
            KeyboardButton(text=t("menu.button.add_bot_to_chat", lang)),
            KeyboardButton(text=t("menu.button.start", lang)),
        ],
    ]

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def language_selection_kb(detected_lang: str | None = None) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру выбора языка
    detected_lang используется только для порядка кнопок
    """
    buttons = [
        InlineKeyboardButton(text=t("language.button.ru", "ru"), callback_data="lang_ru"),
        InlineKeyboardButton(text=t("language.button.en", "en"), callback_data="lang_en"),
    ]

    # Если detected_lang == "en", показываем английский первым
    if detected_lang == "en":
        buttons.reverse()

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def _build_public_commands(lang: str) -> list:
    """Собирает список публичных команд для указанного языка через i18n."""
    return [
        types.BotCommand(command="start", description=t("command.start", lang)),
        types.BotCommand(command="nearby", description=t("command.nearby", lang)),
        types.BotCommand(command="create", description=t("command.create", lang)),
        types.BotCommand(command="myevents", description=t("command.myevents", lang)),
        types.BotCommand(command="tasks", description=t("command.tasks", lang)),
        types.BotCommand(command="mytasks", description=t("command.mytasks", lang)),
        types.BotCommand(command="share", description=t("command.share", lang)),
        types.BotCommand(command="help", description=t("command.help", lang)),
        types.BotCommand(command="language", description=t("command.language", lang)),
    ]


def _build_group_commands(lang: str) -> list:
    """Собирает список команд для групп для указанного языка через i18n."""
    return [types.BotCommand(command="start", description=t("command.group.start", lang))]


# Флаг: команды уже установлены в этой сессии (процесса) — не вызывать set_my_commands повторно при каждом /start
_bot_commands_set_this_session = False


async def setup_bot_commands():
    """ЭТАЛОН: Устанавливает команды бота для всех языков и скоупов"""
    global _bot_commands_set_this_session
    if _bot_commands_set_this_session:
        logger.debug("Команды уже установлены в этой сессии, пропускаем set_my_commands")
        return
    try:
        from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeDefault

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

        # Устанавливаем команды для всех скоупов и языков (lang=None — fallback для ru)
        scope_builders = [
            (BotCommandScopeDefault(), _build_public_commands),
            (BotCommandScopeAllPrivateChats(), _build_public_commands),
            (BotCommandScopeAllGroupChats(), _build_group_commands),
        ]

        languages = [None, "ru", "en"]  # None = default (ru), ru, en

        for scope, build_commands in scope_builders:
            for lang in languages:
                try:
                    cmd_lang = "ru" if lang is None else lang
                    commands = build_commands(cmd_lang)
                    await bot.set_my_commands(commands, scope=scope, language_code=lang)
                    logger.debug(f"✅ Команды установлены: {scope.__class__.__name__} {lang or 'default'}")
                except Exception as e:
                    logger.error(f"❌ Ошибка установки команд {scope.__class__.__name__} {lang}: {e}")

        # Принудительно показываем меню команд в ЛС
        try:
            from aiogram.types import MenuButtonCommands

            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.debug("✅ Menu Button установлен для принудительного показа команд")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось установить Menu Button: {e}")

        _bot_commands_set_this_session = True
        logger.info("✅ Команды бота установлены для всех языков и скоупов")

    except Exception as e:
        logger.error(f"❌ Ошибка установки команд бота: {e}")


async def ensure_group_commands(bot):
    """СТОРОЖ КОМАНД ДЛЯ ГРУПП: проверяет и восстанавливает команды в группах"""
    try:
        from contextlib import suppress

        from aiogram.types import BotCommandScopeAllGroupChats

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
                    group_cmds = _build_group_commands("ru" if lang is None else lang)
                    await bot.set_my_commands(group_cmds, scope=BotCommandScopeAllGroupChats(), language_code=lang)
            logger.info("✅ Команды для групп восстановлены")
        else:
            logger.info("✅ Команды для групп в порядке")

    except Exception as e:
        logger.error(f"❌ Ошибка сторожа команд для групп: {e}")


async def ensure_commands(bot):
    """СТОРОЖ КОМАНД: idempotent auto-heal - проверяет и восстанавливает команды"""
    try:
        from contextlib import suppress

        LANGS = [None, "ru", "en"]  # расширяй при необходимости

        async def _set(scope, build_fn):
            """Устанавливает команды для всех языков через build_fn(lang)"""
            for lang in LANGS:
                with suppress(Exception):
                    cmd_lang = "ru" if lang is None else lang
                    cmds = build_fn(cmd_lang)
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
            await _set(types.BotCommandScopeDefault(), _build_public_commands)
            await _set(types.BotCommandScopeAllPrivateChats(), _build_public_commands)
            await _set(types.BotCommandScopeAllGroupChats(), _build_group_commands)
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
            types.BotCommand(command="nearby", description="📍 События рядом - найти события поблизости"),
            types.BotCommand(command="create", description="➕ Создать новое событие"),
            types.BotCommand(command="myevents", description="📋 Мои события - просмотр созданных событий"),
            types.BotCommand(command="tasks", description="🎯 Интересные места - найти задания поблизости"),
            types.BotCommand(command="mytasks", description="🏆 Мои квесты - просмотр выполненных заданий"),
            types.BotCommand(command="share", description="🔗 Добавить бота в чат"),
            types.BotCommand(command="help", description=t("command.help", "ru")),
        ]

        scopes = [
            BotCommandScopeDefault(),
            BotCommandScopeAllPrivateChats(),
            BotCommandScopeAllGroupChats(),
        ]

        logger.debug("🔍 HEALTHCHECK: Проверяем команды бота...")

        for lang in (None, "ru", "en"):
            for scope in scopes:
                try:
                    cmds = await bot.get_my_commands(scope=scope, language_code=lang)
                    scope_name = scope.__class__.__name__
                    lang_name = lang or "default"
                    cmd_list = [c.command for c in cmds]

                    logger.debug(f"HEALTHCHECK: {scope_name} язык={lang_name!r} => {cmd_list}")

                    if "start" not in cmd_list:
                        logger.error(f"❌ КРИТИЧНО: /start отсутствует в {scope_name} (язык={lang_name!r})!")
                        # Автоматически восстанавливаем команды
                        try:
                            if scope_name == "BotCommandScopeAllGroupChats":
                                restore_cmds = group_commands
                            else:
                                restore_cmds = public_commands
                            await bot.set_my_commands(restore_cmds, scope=scope, language_code=lang)
                            logger.info(f"🔄 Восстановлены команды для {scope_name} (язык={lang_name!r})")
                        except Exception as restore_error:
                            logger.error(
                                f"❌ Не удалось восстановить команды для {scope_name} (язык={lang_name!r}): {restore_error}"
                            )
                    else:
                        logger.debug(f"✅ /start найден в {scope_name} (язык={lang_name!r})")

                except Exception as e:
                    logger.error(f"❌ Ошибка проверки {scope.__class__.__name__} (язык={lang!r}): {e}")

        logger.debug("✅ HEALTHCHECK завершен")

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
@main_router.message(F.text.in_(_START_BUTTON_TEXTS))
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

            from tasks_service import create_task_from_place

            user_lang = get_user_language_or_default(user_id)
            success, message_text = create_task_from_place(user_id, place_id, user_lat, user_lng, lang=user_lang)

            await message.answer(message_text, reply_markup=main_menu_kb(user_id=user_id))
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
        # Проверяем, нужно ли показывать экран выбора языка
        if needs_language_selection(user_id):
            # Получаем язык из Telegram для подсказки (только для порядка кнопок)
            detected_lang = message.from_user.language_code
            if detected_lang and detected_lang.startswith("en"):
                detected_lang = "en"
            else:
                detected_lang = "ru"

            # Показываем экран выбора языка
            choose_text = t("language.choose", "ru")  # Используем билингвальный текст
            await message.answer(choose_text, reply_markup=language_selection_kb(detected_lang))
            return

        # Язык выбран, получаем его из БД (меню всегда по user_id — единый источник правды)
        user_lang = get_user_language_or_default(user_id)
        welcome_text = t("menu.greeting", user_lang)
        await message.answer(welcome_text, reply_markup=main_menu_kb(user_id=user_id))
    else:
        # Групповой чат - упрощенный функционал для событий участников
        # Для групповых чатов язык не проверяем (используем русский по умолчанию)
        user_lang = get_user_language_or_default(user_id)
        welcome_text = t("group.greeting", user_lang)

        # Получаем username бота для создания ссылки (с кешированием)
        bot_info = await get_bot_info_cached()

        # Создаем inline кнопки для групповых чатов
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("group.button.create_event", user_lang),
                        url=f"https://t.me/{bot_info.username}?start=group_{message.chat.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=t("group.button.events_list", user_lang),
                        callback_data="group_chat_events",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=t("group.button.full_version", user_lang),
                        url=f"https://t.me/{bot_info.username}",
                    )
                ],
                [InlineKeyboardButton(text=t("group.button.hide_bot", user_lang), callback_data="group_hide_bot")],
            ]
        )

        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")


@main_router.message(Command("language"))
async def cmd_language(message: types.Message):
    """Обработчик команды /language - выбор языка"""

    # Получаем язык из Telegram для подсказки (только для порядка кнопок)
    detected_lang = message.from_user.language_code
    if detected_lang and detected_lang.startswith("en"):
        detected_lang = "en"
    else:
        detected_lang = "ru"

    # Показываем экран выбора языка
    choose_text = t("language.choose", "ru")  # Билингвальный текст
    await message.answer(choose_text, reply_markup=language_selection_kb(detected_lang))


@main_router.callback_query(F.data.startswith("lang_"))
async def handle_language_selection(callback: types.CallbackQuery):
    """Обработчик выбора языка"""
    user_id = callback.from_user.id
    lang_code = callback.data.replace("lang_", "")

    if lang_code not in ["ru", "en"]:
        await callback.answer(t("language.invalid", get_user_language_or_default(user_id)))
        return

    # Сохраняем язык в БД
    success = set_user_language(user_id, lang_code)

    if success:
        # Показываем подтверждение на выбранном языке
        if lang_code == "ru":
            confirmation = t("language.changed", "ru")
        else:
            confirmation = t("language.changed", "en")

        await callback.answer(confirmation)
        await callback.message.edit_text(confirmation)

        # Если это был первый выбор языка, показываем главное меню
        # (проверяем, было ли предыдущее сообщение экраном выбора языка)
        if "Choose language" in callback.message.text or "Выберите язык" in callback.message.text:
            user_lang = get_user_language_or_default(user_id)
            welcome_text = t("menu.greeting", user_lang)
            await callback.message.answer(welcome_text, reply_markup=main_menu_kb(user_id=user_id))
    else:
        await callback.answer(t("language.save_error", get_user_language_or_default(user_id)))


def get_community_cancel_kb(user_id: int | None = None) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой отмены для группового события"""
    lang = get_user_language_or_default(user_id) if user_id else "ru"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("community.cancel", lang), callback_data="community_cancel")]]
    )


async def start_group_event_creation(message: types.Message, group_id: int, state: FSMContext):
    """Запуск создания события для группы в ЛС"""
    logger.info(f"🔥 start_group_event_creation: запуск FSM для группы {group_id}, пользователь {message.from_user.id}")

    # Запускаем FSM для создания группового события
    await state.set_state(CommunityEventCreation.waiting_for_title)
    await state.update_data(group_id=group_id, creator_id=message.from_user.id, scope="group")

    user_lang = get_user_language_or_default(message.from_user.id)
    welcome_text = t("create.group.welcome_pm", user_lang)

    await message.answer(
        welcome_text, parse_mode="Markdown", reply_markup=get_community_cancel_kb(message.from_user.id)
    )


async def start_group_event_editing(message: types.Message, event_id: int, chat_id: int, state: FSMContext):
    """Запуск редактирования Community события в ЛС"""
    from database import CommunityEvent, get_session

    logger.info(
        f"🔥 start_group_event_editing: запуск редактирования события {event_id} из группы {chat_id}, "
        f"пользователь {message.from_user.id}"
    )

    # Загружаем событие из БД (используем синхронную сессию для простоты)
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)
    try:
        with get_session() as session:
            event = (
                session.query(CommunityEvent)
                .filter(CommunityEvent.id == event_id, CommunityEvent.chat_id == chat_id)
                .first()
            )

            if not event:
                await message.answer(t("edit.group.event_not_found", user_lang))
                return

            # Проверяем права доступа
            can_edit = event.organizer_id == user_id
            if not can_edit:
                await message.answer(t("edit.group.no_permission", user_lang))
                return

            # Форматируем дату и время для отображения
            not_spec = t("common.not_specified", user_lang)
            date_str = event.starts_at.strftime("%d.%m.%Y") if event.starts_at else not_spec
            time_str = event.starts_at.strftime("%H:%M") if event.starts_at else not_spec

            # Показываем информацию о событии и меню редактирования
            event_info = format_translation(
                "edit.group.header",
                user_lang,
                title=event.title or not_spec,
                date=date_str,
                time=time_str,
                location=event.location_name or not_spec,
                description=event.description or not_spec,
            )

            # Создаем клавиатуру для редактирования
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t("edit.button.title", user_lang),
                            callback_data=f"pm_edit_title_{event_id}_{chat_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=t("edit.button.date", user_lang),
                            callback_data=f"pm_edit_date_{event_id}_{chat_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=t("edit.button.time", user_lang),
                            callback_data=f"pm_edit_time_{event_id}_{chat_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=t("edit.button.location", user_lang),
                            callback_data=f"pm_edit_location_{event_id}_{chat_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=t("edit.button.description", user_lang),
                            callback_data=f"pm_edit_description_{event_id}_{chat_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=t("edit.button.finish", user_lang),
                            callback_data=f"pm_edit_finish_{event_id}_{chat_id}",
                        )
                    ],
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
        user_lang = get_user_language_or_default(message.from_user.id)
        await message.answer(t("errors.event_load_failed", user_lang))


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

            # Обновляем поле (title/title_en и description/description_en — в паре,
            # чтобы в EN-версии списка в группе отображалось новое значение)
            if field == "title":
                event.title = value
                event.title_en = value
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
                event.description_en = value
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

        # Синхронизация с World: если событие опубликовано в основной бот — обновить и там
        from database import async_session_maker
        from utils.sync_community_world_events import sync_community_event_to_world

        async with async_session_maker() as session:
            await sync_community_event_to_world(session, chat_id, event_id)
        return True

    except Exception as e:
        logger.error(f"Ошибка обновления события {event_id}: {e}")
        return False


async def _refresh_community_event_messages_in_chat(bot: Bot, event_id: int, chat_id: int) -> None:
    """После редактирования Community события из ЛС — обновляет карточки в группе (notification/reminder/event_start)."""
    from database import async_session_maker
    from group_router import update_community_event_tracked_messages

    async with async_session_maker() as session:
        await update_community_event_tracked_messages(bot, session, event_id, chat_id)


# === ОБРАБОТЧИКИ РЕДАКТИРОВАНИЯ COMMUNITY СОБЫТИЙ В ПРИВАТНОМ ЧАТЕ ===
@main_router.callback_query(F.data.startswith("pm_edit_title_"))
async def pm_edit_title_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования названия Community события"""
    user_lang = get_user_language_or_default(callback.from_user.id)
    try:
        # Формат: pm_edit_title_{event_id}_{chat_id}
        parts = callback.data.replace("pm_edit_title_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_title)
            await callback.message.answer(t("edit.enter_title", user_lang))
            await callback.answer()
        else:
            await callback.answer(t("edit.group.invalid_format", user_lang), show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_title_: {e}")
        await callback.answer(t("edit.group.error", user_lang), show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_date_"))
async def pm_edit_date_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования даты Community события"""
    user_lang = get_user_language_or_default(callback.from_user.id)
    try:
        parts = callback.data.replace("pm_edit_date_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_date)
            await callback.message.answer(t("edit.enter_date", user_lang))
            await callback.answer()
        else:
            await callback.answer(t("edit.group.invalid_format", user_lang), show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_date_: {e}")
        await callback.answer(t("edit.group.error", user_lang), show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_time_"))
async def pm_edit_time_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования времени Community события"""
    user_lang = get_user_language_or_default(callback.from_user.id)
    try:
        parts = callback.data.replace("pm_edit_time_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_time)
            await callback.message.answer(t("edit.enter_time", user_lang))
            await callback.answer()
        else:
            await callback.answer(t("edit.group.invalid_format", user_lang), show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_time_: {e}")
        await callback.answer(t("edit.group.error", user_lang), show_alert=True)


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
            lang = get_user_language_or_default(callback.from_user.id)
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_location)

            # Создаем клавиатуру с 3 кнопками для выбора способа ввода локации
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t("community.location_link", lang),
                            callback_data=f"pm_edit_location_link_{event_id}_{chat_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=t("community.location_map", lang),
                            callback_data=f"pm_edit_location_map_{event_id}_{chat_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=t("community.location_coords", lang),
                            callback_data=f"pm_edit_location_coords_{event_id}_{chat_id}",
                        )
                    ],
                ]
            )

            lang = get_user_language_or_default(callback.from_user.id)
            await callback.message.answer(
                t("create.location_prompt", lang),
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            await callback.answer()
        else:
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.answer(t("edit.group.invalid_format", user_lang), show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_location_: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("edit.group.error", user_lang), show_alert=True)


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
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.answer(t("edit.group.invalid_format", user_lang), show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_location_link_: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("edit.group.error", user_lang), show_alert=True)


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

            user_lang = get_user_language_or_default(callback.from_user.id)
            # Показываем кнопку с картой
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t("tasks.button.find_on_map", user_lang),
                            url="https://www.google.com/maps",
                        )
                    ],
                ]
            )
            await callback.message.answer(
                t("edit.location_map_prompt", user_lang),
                reply_markup=keyboard,
            )
            await callback.answer()
        else:
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.answer(t("edit.group.invalid_format", user_lang), show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_location_map_: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("edit.group.error", user_lang), show_alert=True)


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
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.message.answer(
                t("edit.location_coords_prompt", user_lang),
                parse_mode="Markdown",
            )
            await callback.answer()
        else:
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.answer(t("edit.group.invalid_format", user_lang), show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_location_coords_: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("edit.group.error", user_lang), show_alert=True)


@main_router.callback_query(F.data.startswith("pm_edit_description_"))
async def pm_edit_description_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования описания Community события"""
    user_lang = get_user_language_or_default(callback.from_user.id)
    try:
        parts = callback.data.replace("pm_edit_description_", "").split("_")
        if len(parts) >= 2:
            event_id = int(parts[0])
            chat_id = int(parts[1])
            await state.update_data(event_id=event_id, chat_id=chat_id)
            await state.set_state(CommunityEventEditing.waiting_for_description)
            await callback.message.answer(t("edit.enter_description", user_lang))
            await callback.answer()
        else:
            await callback.answer(t("edit.group.invalid_format", user_lang), show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_description_: {e}")
        await callback.answer(t("edit.group.error", user_lang), show_alert=True)


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
                    user_lang = get_user_language_or_default(callback.from_user.id)
                    not_spec = t("common.not_specified", user_lang)
                    date_str = event.starts_at.strftime("%d.%m.%Y") if event.starts_at else not_spec
                    time_str = event.starts_at.strftime("%H:%M") if event.starts_at else not_spec

                    text = format_translation(
                        "edit.group.updated_summary",
                        user_lang,
                        title=event.title or not_spec,
                        date=date_str,
                        time=time_str,
                        location=event.location_name or not_spec,
                        description=event.description or not_spec,
                    )
                    await callback.message.edit_text(text, parse_mode="Markdown")
                    await callback.answer(t("edit.group.updated_toast", user_lang))
                else:
                    user_lang = get_user_language_or_default(callback.from_user.id)
                    await callback.answer(t("edit.group.event_not_found", user_lang), show_alert=True)

            await state.clear()
        else:
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.answer(t("edit.group.invalid_format", user_lang), show_alert=True)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга pm_edit_finish_: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("edit.group.error", user_lang), show_alert=True)


# === ОБРАБОТЧИКИ ВВОДА ДАННЫХ ДЛЯ РЕДАКТИРОВАНИЯ COMMUNITY СОБЫТИЙ ===
@main_router.message(CommunityEventEditing.waiting_for_title)
async def pm_handle_title_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового названия Community события"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

    if event_id and chat_id and message.text:
        success = await update_community_event_field_pm(event_id, "title", message.text.strip(), user_id, chat_id)
        if success:
            await _refresh_community_event_messages_in_chat(message.bot, event_id, chat_id)
            await message.answer(t("edit.title_updated", user_lang))
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer(t("edit.title_update_error", user_lang))
    else:
        await message.answer(t("edit.invalid_title", user_lang))


@main_router.message(CommunityEventEditing.waiting_for_date)
async def pm_handle_date_input(message: types.Message, state: FSMContext):
    """Обработка ввода новой даты Community события"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

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
            await _refresh_community_event_messages_in_chat(message.bot, event_id, chat_id)
            await message.answer(t("edit.date_updated", user_lang))
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer(t("edit.date_format_error", user_lang))
    else:
        await message.answer(t("edit.invalid_date", user_lang))


@main_router.message(CommunityEventEditing.waiting_for_time)
async def pm_handle_time_input(message: types.Message, state: FSMContext):
    """Обработка ввода нового времени Community события"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

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
            await _refresh_community_event_messages_in_chat(message.bot, event_id, chat_id)
            await message.answer(t("edit.time_updated", user_lang))
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer(t("edit.time_format_error", user_lang))
    else:
        await message.answer(t("edit.invalid_time", user_lang))


@main_router.message(CommunityEventEditing.waiting_for_location)
async def pm_handle_location_input(message: types.Message, state: FSMContext):
    """Обработка ввода новой локации Community события"""
    data = await state.get_data()
    event_id = data.get("event_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

    if not event_id or not chat_id or not message.text:
        await message.answer(t("edit.invalid_location", user_lang))
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
                await _refresh_community_event_messages_in_chat(message.bot, event_id, chat_id)
                await message.answer(
                    format_translation(
                        "edit.location_updated",
                        user_lang,
                        location=location_data.get("name", "Место на карте"),
                    ),
                    parse_mode="Markdown",
                )
                await start_group_event_editing(message, event_id, chat_id, state)
            else:
                await message.answer(t("edit.location_update_error", user_lang))
        else:
            await message.answer(t("edit.location_google_maps_error", user_lang))

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
                    await _refresh_community_event_messages_in_chat(message.bot, event_id, chat_id)
                    await message.answer(
                        format_translation("edit.location_updated", user_lang, location=f"{lat:.6f}, {lng:.6f}"),
                        parse_mode="Markdown",
                    )
                    await start_group_event_editing(message, event_id, chat_id, state)
                else:
                    await message.answer(t("edit.location_update_error", user_lang))
            else:
                await message.answer(t("edit.coords_out_of_range", user_lang))
        except ValueError:
            await message.answer(t("edit.coords_format", user_lang))

    else:
        # Обычный текст - обновляем только название
        success = await update_community_event_field_pm(event_id, "location_name", location_input, user_id, chat_id)
        if success:
            await _refresh_community_event_messages_in_chat(message.bot, event_id, chat_id)
            await message.answer(
                format_translation("edit.location_updated", user_lang, location=location_input),
                parse_mode="Markdown",
            )
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer(t("edit.location_update_error", user_lang))


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

    user_lang = get_user_language_or_default(user_id)
    description_lower = description.lower()
    if any(indicator in description_lower for indicator in spam_indicators):
        await message.answer(t("create.validation.no_links_in_description", user_lang))
        return

    if event_id and chat_id and description:
        success = await update_community_event_field_pm(event_id, "description", description, user_id, chat_id)
        if success:
            await _refresh_community_event_messages_in_chat(message.bot, event_id, chat_id)
            await message.answer(t("edit.description_updated", user_lang))
            await start_group_event_editing(message, event_id, chat_id, state)
        else:
            await message.answer(t("edit.description_update_error", user_lang))
    else:
        await message.answer(t("edit.invalid_description", user_lang))


# Обработчики FSM для создания событий в ЛС (для групп)
@main_router.message(CommunityEventCreation.waiting_for_title)
async def process_community_title_pm(message: types.Message, state: FSMContext):
    """Обработка названия события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_title_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation("create.validation.no_text", lang, next_prompt=t("create.group.enter_title", lang)),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
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
            t("create.validation.no_commands_in_title", lang),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
        )
        return

    title_lower = title.lower()
    if any(indicator in title_lower for indicator in spam_indicators):
        await message.answer(
            t("create.validation.no_links_in_title", lang),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
        )
        return

    await state.update_data(title=title)
    await state.set_state(CommunityEventCreation.waiting_for_date)
    example_date = get_example_date()

    await message.answer(
        format_translation("create.title_saved", lang, title=title, example_date=example_date),
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(message.from_user.id),
    )


@main_router.message(CommunityEventCreation.waiting_for_date)
async def process_community_date_pm(message: types.Message, state: FSMContext):
    """Обработка даты события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_date_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation(
                "create.validation.no_text",
                lang,
                next_prompt=t("create.enter_date", lang).format(example_date="15.12.2024"),
            ),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
        )
        return

    date = message.text.strip()
    logger.info(f"🔥 process_community_date_pm: получили дату '{date}' от пользователя {message.from_user.id}")

    # Валидация формата даты DD.MM.YYYY

    if not re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", date):
        await message.answer(
            t("create.validation.invalid_date_format", lang),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
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
                format_translation(
                    "create.validation.past_date", lang, date=date, today=today_bali.strftime("%d.%m.%Y")
                ),
                parse_mode="Markdown",
                reply_markup=get_community_cancel_kb(message.from_user.id),
            )
            return
    except ValueError:
        await message.answer(
            t("create.validation.invalid_date_value", lang),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
        )
        return

    await state.update_data(date=date)
    await state.set_state(CommunityEventCreation.waiting_for_time)

    await message.answer(
        format_translation("create.date_saved", lang, date=date),
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(message.from_user.id),
    )


@main_router.message(CommunityEventCreation.waiting_for_time)
async def process_community_time_pm(message: types.Message, state: FSMContext):
    """Обработка времени события в ЛС для группы"""
    lang = get_user_language_or_default(message.from_user.id)
    logger.info(
        f"🔥 process_community_time_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    if not message.text:
        await message.answer(
            format_translation("create.validation.no_text", lang, next_prompt=t("create.enter_time", lang)),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
        )
        return

    time = message.text.strip()
    logger.info(f"🔥 process_community_time_pm: получили время '{time}' от пользователя {message.from_user.id}")

    # Валидация формата времени HH:MM
    if not re.match(r"^\d{1,2}:\d{2}$", time):
        await message.answer(
            t("create.validation.invalid_time_format", lang),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
        )
        return

    await state.update_data(time=time)
    await state.set_state(CommunityEventCreation.waiting_for_city)

    await message.answer(
        format_translation("create.time_saved", lang, time=time)
        .replace("📍 **Отправьте геолокацию или введите место:**", "")
        .strip()
        + "\n\n"
        + t("create.enter_city", lang),
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(message.from_user.id),
    )


@main_router.message(CommunityEventCreation.waiting_for_city)
async def process_community_city_pm(message: types.Message, state: FSMContext):
    """Обработка города события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_city_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation("create.validation.no_text", lang, next_prompt=t("create.enter_city", lang)),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
        )
        return

    city = message.text.strip()
    logger.info(f"🔥 process_community_city_pm: получили город '{city}' от пользователя {message.from_user.id}")

    await state.update_data(city=city)
    await state.set_state(CommunityEventCreation.waiting_for_location_type)
    # Создаем клавиатуру для выбора типа локации (как в World режиме)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("community.location_link", lang), callback_data="community_location_link")],
            [InlineKeyboardButton(text=t("community.location_map", lang), callback_data="community_location_map")],
            [
                InlineKeyboardButton(
                    text=t("community.location_coords", lang), callback_data="community_location_coords"
                )
            ],
        ]
    )

    await message.answer(
        format_translation("create.city_saved", lang, city=city),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@main_router.message(CommunityEventCreation.waiting_for_location_type)
async def handle_community_location_type_text(message: types.Message, state: FSMContext):
    """Обработка текстовых сообщений в состоянии выбора типа локации в Community режиме"""
    text = message.text.strip()
    lang = get_user_language_or_default(message.from_user.id)

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
                    location_name=t("create.place_by_coords", lang),
                    location_lat=lat,
                    location_lng=lng,
                    location_url=text,
                )

                # Переходим к описанию
                await state.set_state(CommunityEventCreation.waiting_for_description)
                await message.answer(
                    format_translation("create.place_by_coords_message", lang, lat=lat, lng=lng)
                    + t("create.enter_description", lang),
                    parse_mode="Markdown",
                    reply_markup=get_community_cancel_kb(message.from_user.id),
                )
                return
            else:
                raise ValueError("Invalid coordinates range")
        except (ValueError, TypeError):
            await message.answer(
                t("create.invalid_coords", lang),
                parse_mode="Markdown",
                reply_markup=get_community_cancel_kb(message.from_user.id),
            )
            return

    # Если не распознали, показываем подсказку
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("community.location_link", lang), callback_data="community_location_link")],
            [InlineKeyboardButton(text=t("community.location_map", lang), callback_data="community_location_map")],
            [
                InlineKeyboardButton(
                    text=t("community.location_coords", lang), callback_data="community_location_coords"
                )
            ],
        ]
    )
    await message.answer(
        t("create.location_prompt", lang),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@main_router.message(CommunityEventCreation.waiting_for_location_url)
async def process_community_location_url_pm(message: types.Message, state: FSMContext, bot: Bot, session: AsyncSession):
    """Обработка ссылки на место события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_location_url_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation(
                "create.validation.no_text", lang, next_prompt=t("create.group.ask_location_link", lang)
            ),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
        )
        return

    location_input = message.text.strip()
    logger.info(f"🔥 process_community_location_url_pm: получили ввод от пользователя {message.from_user.id}")

    # Определяем название места по ссылке и пробуем достать координаты
    location_name = t("create.place_by_link", lang)
    location_lat = None
    location_lng = None
    location_url = None

    def _looks_like_url(text: str) -> bool:
        tlower = text.lower().strip()
        return (
            tlower.startswith(("http://", "https://", "www."))
            or "maps.google.com" in tlower
            or "goo.gl" in tlower
            or "maps.app.goo.gl" in tlower
            or "yandex.ru/maps" in tlower
        )

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
                t("create.invalid_coords", lang),
                parse_mode="Markdown",
                reply_markup=get_community_cancel_kb(message.from_user.id),
            )
            return
    else:
        # Это должна быть ссылка — проверяем, что ввод похож на ссылку
        if not _looks_like_url(location_input):
            await message.answer(
                t("create.validation.invalid_location_link", lang),
                parse_mode="Markdown",
                reply_markup=get_community_cancel_kb(message.from_user.id),
            )
            return

        location_url = location_input
        try:
            if "maps.google.com" in location_url or "goo.gl" in location_url or "maps.app.goo.gl" in location_url:
                from utils.geo_utils import parse_google_maps_link

                try:
                    location_data = await parse_google_maps_link(location_url)
                    logger.info(f"🌍 parse_google_maps_link (community) ответ: {location_data}")
                    if location_data:
                        location_name = location_data.get("name") or t("create.place_on_map", lang)
                        location_lat = location_data.get("lat")
                        location_lng = location_data.get("lng")
                    else:
                        # Ссылка не распознана — просим отправить нормальную ссылку
                        await message.answer(
                            t("create.validation.location_link_parse_failed", lang),
                            parse_mode="Markdown",
                            reply_markup=get_community_cancel_kb(message.from_user.id),
                        )
                        return
                except Exception as parse_error:
                    logger.error(f"❌ Ошибка при парсинге Google Maps ссылки: {parse_error}")
                    import traceback

                    logger.error(traceback.format_exc())
                    await message.answer(
                        t("create.validation.location_link_parse_failed", lang),
                        parse_mode="Markdown",
                        reply_markup=get_community_cancel_kb(message.from_user.id),
                    )
                    return
            elif "yandex.ru/maps" in location_url:
                location_name = t("create.place_yandex", lang)
            else:
                location_name = t("create.place_by_link", lang)
        except Exception as e:
            logger.error(f"❌ Не удалось обработать ссылку для community события: {e}")
            import traceback

            logger.error(traceback.format_exc())
            await message.answer(
                t("create.validation.location_link_parse_failed", lang),
                parse_mode="Markdown",
                reply_markup=get_community_cancel_kb(message.from_user.id),
            )
            return

    await state.update_data(
        location_url=location_url,
        location_name=location_name,
        location_lat=location_lat,
        location_lng=location_lng,
    )
    await state.set_state(CommunityEventCreation.waiting_for_description)

    place_label = t("create.label_place", lang)
    coords_label = t("create.coordinates_label", lang)
    if location_lat and location_lng:
        location_text = f"📍 **{place_label}** {location_name}\n**{coords_label}** {location_lat}, {location_lng}"
    else:
        location_text = f"📍 **{place_label}** {location_name}"

    await message.answer(
        format_translation("create.place_saved_then_desc", lang, location_text=location_text),
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(message.from_user.id),
    )


@main_router.message(CommunityEventCreation.waiting_for_description)
async def process_community_description_pm(message: types.Message, state: FSMContext):
    """Обработка описания события в ЛС для группы"""
    logger.info(
        f"🔥 process_community_description_pm: получено сообщение от пользователя {message.from_user.id}, текст: '{message.text}'"
    )

    lang = get_user_language_or_default(message.from_user.id)
    if not message.text:
        await message.answer(
            format_translation("create.validation.no_text", lang, next_prompt=t("create.enter_description", lang)),
            parse_mode="Markdown",
            reply_markup=get_community_cancel_kb(message.from_user.id),
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
    not_spec = t("common.not_specified", lang)
    city_info = f"\n🏙️ **{t('create.label_city', lang)}** {data.get('city') or not_spec}" if data.get("city") else ""
    await message.answer(
        t("create.check_data_group", lang) + f"**{t('create.label_title', lang)}** {data.get('title') or not_spec}\n"
        f"**{t('create.label_date', lang)}** {data.get('date') or not_spec}\n"
        f"**{t('create.label_time', lang)}** {data.get('time') or not_spec}{city_info}\n"
        f"**{t('create.label_place', lang)}** {data.get('location_name') or not_spec}\n"
        f"**{t('create.label_link', lang)}** {data.get('location_url') or not_spec}\n"
        f"**{t('create.label_description', lang)}** {data.get('description') or not_spec}\n\n"
        + t("create.confirm_question", lang),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("community.confirm_chat_only", lang), callback_data="community_event_confirm_chat"
                    ),
                    InlineKeyboardButton(
                        text=t("community.confirm_world", lang), callback_data="community_event_confirm_world"
                    ),
                ],
                [InlineKeyboardButton(text=t("common.cancel", lang), callback_data="community_event_cancel_pm")],
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
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("create.wait_already_started", user_lang))
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
    user_lang = get_user_language_or_default(callback.from_user.id)

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
            desc = (
                (event.get("description_en") or event.get("description") or "").strip()
                if user_lang == "en"
                else (event.get("description") or "").strip()
            )
            title_display = (
                (event.get("title_en") or event.get("title") or "").strip()
                if user_lang == "en"
                else (event.get("title") or "").strip()
            )
            text += f"**{i}. {title_display}**\n"
            if desc:
                text += f"   {desc[:100]}{'...' if len(desc) > 100 else ''}\n"
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
    user_lang = get_user_language_or_default(callback.from_user.id)
    await callback.answer(t("group.hide_toast", user_lang), show_alert=False)

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

    # Удаляем уведомление через 4 секунды
    try:
        await asyncio.sleep(4)
        await note.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления уведомления

    logger.info(f"✅ Бот скрыт в чате {chat_id} пользователем {user_id}, удалено сообщений: {deleted}")


@main_router.callback_query(F.data.regexp(r"^delete_message_\d+$"))
async def handle_delete_message(callback: types.CallbackQuery):
    """Обработчик кнопки удаления сообщения"""
    try:
        await callback.message.delete()
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("group.message_deleted", user_lang))
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении сообщения: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("group.message_delete_failed", user_lang))


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
        user_lang = get_user_language_or_default(user_id)
        await callback.answer(t("create.wait_in_progress", user_lang), show_alert=False)
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

        creator_lang = get_user_language_or_default(callback.from_user.id)
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
            admin_id=admin_id,
            admin_ids=admin_ids,
            creator_lang=creator_lang,
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
                bot=bot,
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
        lang_community = get_user_language_or_default(callback.from_user.id)
        time_at = t("share.time_at", lang_community)
        event_text = (
            f"🎉 **{t('share.new_event', lang_community)}**\n\n"
            f"**{safe_title}**\n"
            f"📅 {safe_date} {time_at} {safe_time}\n"
            f"🏙️ {safe_city}\n"
            f"📍 {safe_location_name}\n"
        )
        if data.get("location_url"):
            # URL не экранируем, так как он должен быть кликабельным
            event_text += f"🔗 {data['location_url']}\n"
        event_text += (
            "\n"
            f"📝 {safe_description}\n\n"
            f"*{format_translation('event.created_by', lang_community, username=safe_username)}*\n\n"
        )
        # Список участников в тексте (как в напоминаниях), без кнопки «Участники»
        from utils.community_participants_service_optimized import get_participants_optimized

        participants = await get_participants_optimized(session, event_id)
        if participants:
            mentions = " ".join(f"@{p.get('username', '')}" for p in participants if p.get("username"))
            event_text += t("reminder.participants", lang_community).format(count=len(participants)) + "\n"
            event_text += mentions + "\n\n"
        else:
            event_text += t("reminder.no_participants", lang_community) + "\n\n"
        event_text += t("group.card.footer", lang_community)

        # Inline-кнопки: только Join / Leave (участники уже в тексте)
        card_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("group.card.join", lang_community),
                        callback_data=f"join_event:{event_id}",
                    ),
                    InlineKeyboardButton(
                        text=t("group.card.leave", lang_community),
                        callback_data=f"leave_event:{event_id}",
                    ),
                ]
            ]
        )

        try:
            # Отправляем через send_tracked с тегом "notification" (не удаляется автоматически)
            from utils.messaging_utils import send_tracked

            group_message = await send_tracked(
                bot,
                session,
                chat_id=group_id,
                text=event_text,
                tag="notification",
                event_id=event_id,
                parse_mode="Markdown",
                reply_markup=card_keyboard,
            )

            # Показываем ссылку на опубликованное сообщение (только для супергрупп с chat_id, начинающимся на -100)
            is_supergroup = str(group_id).startswith("-100")
            group_link = build_message_link(group_id, group_message.message_id) if is_supergroup else None

            # Сообщение об успешном создании (используем уже экранированные значения)
            time_at_success = t("share.time_at", lang_community)
            success_text_parts = [
                t("create.community.event_created_published", lang_community),
                f"**{safe_title}**\n",
                f"📅 {safe_date} {time_at_success} {safe_time}\n",
                f"🏙️ {safe_city}\n",
                f"📍 {safe_location_name}\n",
            ]
            if data.get("location_url"):
                success_text_parts.append(f"🔗 {data['location_url']}\n")
            if group_link:
                success_text_parts.extend(
                    [
                        "\n",
                        t("create.community.published_in_group", lang_community),
                        format_translation("create.community.link_to_message", lang_community, url=group_link),
                    ]
                )
            if publish_world:
                if world_publish_status and world_publish_status.get("success"):
                    success_text_parts.append(t("create.community.available_in_world", lang_community))
                else:
                    success_text_parts.append(t("create.community.world_publish_failed", lang_community))

            success_text_parts.append("\n🚀")
            success_text = "".join(success_text_parts)

            # Отправляем новое сообщение с ReplyKeyboardMarkup вместо edit_text
            user_id = callback.from_user.id
            await callback.message.answer(
                success_text, parse_mode="Markdown", reply_markup=main_menu_kb(user_id=user_id)
            )

            # Восстанавливаем команды бота после создания события
            await setup_bot_commands()

        except Exception as e:
            logger.error(f"Ошибка публикации в группу: {e}")
            time_at_fail = t("share.time_at", lang_community)
            await callback.message.edit_text(
                t("create.community.event_created_only", lang_community) + f"**{safe_title}**\n"
                f"📅 {safe_date} {time_at_fail} {safe_time}\n"
                f"🏙️ {safe_city}\n"
                f"📍 {safe_location_name}\n\n" + t("create.community.publish_to_group_failed", lang_community),
                parse_mode="Markdown",
            )

        await state.clear()

        # Очищаем флаг обработки после успешного создания
        if hasattr(confirm_community_event_pm, "_processing"):
            confirm_community_event_pm._processing.pop(user_id, None)

    except Exception as e:
        logger.error(f"Ошибка создания события: {e}")
        err_lang = get_user_language_or_default(callback.from_user.id)
        await callback.message.edit_text(t("create.group.error_creating", err_lang), parse_mode="Markdown")

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
    bot: Bot = None,
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

        # Получаем название группы
        community_name = None
        if bot and chat_id:
            try:
                chat = await bot.get_chat(chat_id)
                community_name = chat.title
                logger.info(f"🌍 Получено название группы: {community_name}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить название группы {chat_id}: {e}")

        external_id = f"community:{chat_id}:{community_event_id}"

        # Берём title_en/description_en из events_community (уже переведено при создании) — без повторного вызова API
        title_en = None
        description_en = None
        try:
            with engine.connect() as conn:
                from sqlalchemy import text

                row = conn.execute(
                    text("SELECT title_en, description_en FROM events_community WHERE id = :id AND chat_id = :chat_id"),
                    {"id": community_event_id, "chat_id": chat_id},
                ).fetchone()
                if row and (row[0] or row[1]):
                    title_en = row[0]
                    description_en = row[1]
        except Exception as e:
            logger.debug("publish_community_event_to_world: не удалось взять EN из events_community: %s", e)
        title_for_world = event_data["title"]
        description_for_world = event_data["description"]
        if not title_en and not description_en:
            bilingual = ensure_bilingual(
                title=event_data["title"],
                description=event_data.get("description") or "",
            )
            title_for_world = bilingual.get("title") or event_data["title"]
            description_for_world = bilingual.get("description") or event_data["description"]
            title_en = bilingual.get("title_en")
            description_en = bilingual.get("description_en")

        world_event_id = events_service.create_user_event(
            organizer_id=organizer_id,
            title=title_for_world,
            description=description_for_world,
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
            community_name=community_name,
            title_en=title_en,
            description_en=description_en,
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
    user_lang = get_user_language_or_default(callback.from_user.id)

    # Получаем данные для информативного сообщения
    data = await state.get_data()
    group_id = data.get("group_id")

    await state.clear()

    cancel_text = t("community.cancel_group_title", user_lang)
    if group_id:
        cancel_text += t("community.cancel_return_or_stay", user_lang)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=t("menu.button.events_nearby", user_lang), callback_data="nearby_events"),
                    InlineKeyboardButton(text=t("menu.button.start", user_lang), callback_data="start_menu"),
                ]
            ]
        )

        await callback.message.edit_text(cancel_text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        cancel_text += t("community.cancel_create_via_start", user_lang)
        await callback.message.edit_text(cancel_text, parse_mode="Markdown")
    await callback.answer(t("create.cancelled", user_lang), show_alert=False)


@main_router.callback_query(F.data == "group_cancel_create")
async def handle_group_cancel_create(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик отмены создания события в групповых чатах"""
    await state.clear()

    user_lang = get_user_language_or_default(callback.from_user.id)
    await callback.message.edit_text(t("community.event_cancelled", user_lang))
    await callback.answer()


@main_router.callback_query(F.data == "group_back_to_start")
async def handle_group_back_to_start(callback: types.CallbackQuery):
    """Обработчик возврата в главное меню группового чата"""
    user_lang = get_user_language_or_default(callback.from_user.id)
    welcome_text = t("group.greeting", user_lang)

    bot_info = await get_bot_info_cached()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("group.button.create_event", user_lang),
                    url=f"https://t.me/{bot_info.username}?start=group_{callback.message.chat.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("group.button.events_list", user_lang),
                    callback_data="group_chat_events",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("group.button.full_version", user_lang),
                    url=f"https://t.me/{bot_info.username}",
                )
            ],
            [InlineKeyboardButton(text=t("group.button.hide_bot", user_lang), callback_data="group_hide_bot")],
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

    # Получаем язык пользователя
    user_lang = get_user_language_or_default(user_id)

    # Показываем приветственное сообщение с главным меню
    welcome_text = t("menu.greeting", user_lang)
    await callback.message.answer(welcome_text, reply_markup=main_menu_kb(user_id=user_id))


@main_router.callback_query(F.data == "nearby_events")
async def on_nearby_events_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'События рядом' из callback"""
    await callback.answer()

    user_id = callback.from_user.id
    user_lang = get_user_language_or_default(user_id)

    # Устанавливаем состояние для поиска событий
    await state.set_state(EventSearch.waiting_for_location)

    # Создаем клавиатуру с кнопкой геолокации и главным меню
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=t("tasks.button.send_location", user_lang),
                    request_location=True,
                )
            ],
            [KeyboardButton(text=t("tasks.button.find_on_map", user_lang))],
            [KeyboardButton(text=t("tasks.button.main_menu", user_lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    # Отправляем новое сообщение с ReplyKeyboardMarkup
    await callback.message.answer(
        t("search.geo_prompt", user_lang),
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
    user_lang = get_user_language_or_default(callback.from_user.id)
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer(t("common.access_denied", user_lang))
        return

    key = callback.data.split(":", maxsplit=1)[1]
    location = TEST_LOCATIONS.get(key)
    if not location:
        await callback.answer(t("common.location_not_found", user_lang))
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
@main_router.message(F.text.in_(_EVENTS_NEARBY_BUTTON_TEXTS))
async def on_what_nearby(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'События рядом'"""
    user_id = message.from_user.id
    lang = get_user_language_or_default(user_id)
    logger.debug("📍 Команда /nearby от пользователя %s", user_id)

    # Инкрементируем сессию World (с проверкой времени)
    if message.chat.type == "private":
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(message.from_user.id, min_interval_minutes=6)

    # Устанавливаем состояние для поиска событий
    await state.set_state(EventSearch.waiting_for_location)
    current_state = await state.get_state()
    logger.debug("📍 Состояние установлено: %s для пользователя %s", current_state, user_id)

    # Создаем клавиатуру с кнопкой геолокации и главным меню
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("tasks.button.send_location", lang), request_location=True)],
            [KeyboardButton(text=t("tasks.button.find_on_map", lang))],
            [KeyboardButton(text=t("tasks.button.main_menu", lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,  # Изменено на False, чтобы кнопка не исчезала на MacBook
    )

    await message.answer(
        t("tasks.press_location_hint", lang),
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
    user_lang = get_user_language_or_default(user_id)
    keyboard = [
        [InlineKeyboardButton(text=t("tasks.category.food", user_lang), callback_data="task_category:food")],
        [InlineKeyboardButton(text=t("tasks.category.health", user_lang), callback_data="task_category:health")],
        [InlineKeyboardButton(text=t("tasks.category.places", user_lang), callback_data="task_category:places")],
        [InlineKeyboardButton(text=t("tasks.button.main_menu", user_lang), callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await message.answer(
        t("tasks.location_received", user_lang),
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

    logger.info(f"📍 [ЗАДАНИЯ] Показаны категории для пользователя {user_id}")


# Обработчик для текстовых сообщений в состоянии ожидания геолокации (для MacBook)
@main_router.message(EventSearch.waiting_for_location, F.text)
async def on_location_text_input(message: types.Message, state: FSMContext):
    """Обработчик текстового ввода координат или ссылки Google Maps для MacBook"""
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)
    text = message.text.strip()
    logger.info(f"📍 [TEXT_INPUT] Получен текст в состоянии waiting_for_location: user_id={user_id}, text={text[:100]}")

    # Если пользователь нажал "Главное меню", вызываем соответствующий обработчик
    if text in _MAIN_MENU_BUTTON_TEXTS:
        logger.info(f"📍 [TEXT_INPUT] Обнаружена кнопка 'Главное меню', возвращаем в меню для пользователя {user_id}")
        await state.clear()
        await send_spinning_menu(message, lang=user_lang)
        return

    # Если пользователь нажал "🌍 Найти на карте" / "Find on map", показываем inline-кнопку с картой
    if text in _FIND_ON_MAP_BUTTON_TEXTS:
        logger.info(f"📍 [TEXT_INPUT] Обнаружена кнопка Find on map от пользователя {user_id}")
        maps_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("tasks.button.find_on_map", user_lang),
                        url="https://www.google.com/maps",
                    )
                ],
            ]
        )
        await message.answer(
            t("edit.location_map_prompt", user_lang),
            reply_markup=maps_keyboard,
        )
        return

    # Специальная обработка для MacBook: если пользователь нажал кнопку "📍 События рядом" повторно
    if text == "📍 События рядом":
        logger.info(
            f"📍 [TEXT_INPUT] Обнаружен повторный запрос '📍 События рядом' от пользователя {user_id} (MacBook)"
        )
        maps_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("tasks.button.find_on_map", user_lang),
                        url="https://www.google.com/maps",
                    )
                ],
            ]
        )
        await message.answer(
            t("search.geo_prompt", user_lang),
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
                    [
                        InlineKeyboardButton(
                            text=t("tasks.button.find_on_map", user_lang),
                            url="https://www.google.com/maps",
                        )
                    ],
                ]
            )
            await message.answer(
                t("search.geo_prompt", user_lang),
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
                await message.answer(t("edit.coords_out_of_range", user_lang))
                return
    except ValueError:
        # Не координаты, возможно это другой текст - пропускаем
        logger.info("📍 [TEXT_INPUT] Текст не является координатами или ссылкой, пропускаем")
        pass

    # Если это не координаты и не ссылка, показываем подсказку
    maps_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("tasks.button.find_on_map", user_lang),
                    url="https://www.google.com/maps",
                )
            ],
        ]
    )
    await message.answer(
        t("search.geo_prompt", user_lang),
        parse_mode="Markdown",
        reply_markup=maps_keyboard,
    )


# Обработчик для текстовых сообщений в состоянии ожидания геолокации для заданий (для MacBook)
@main_router.message(TaskFlow.waiting_for_location, F.text)
async def on_location_text_input_tasks(message: types.Message, state: FSMContext):
    """Обработчик текстового ввода координат или ссылки Google Maps для заданий (MacBook)"""
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)
    text = message.text.strip()
    logger.info(
        f"📍 [TEXT_INPUT_TASKS] Получен текст в состоянии TaskFlow.waiting_for_location: user_id={user_id}, text={text[:100]}"
    )

    # Если пользователь нажал "Главное меню", вызываем соответствующий обработчик
    if text in _MAIN_MENU_BUTTON_TEXTS:
        logger.info(
            f"📍 [TEXT_INPUT_TASKS] Обнаружена кнопка 'Главное меню', возвращаем в меню для пользователя {user_id}"
        )
        await state.clear()
        user_lang = get_user_language_or_default(user_id)
        await send_spinning_menu(message, lang=user_lang)
        return

    # Если пользователь нажал "🌍 Найти на карте" / "Find on map", показываем inline-кнопку с картой
    if text in _FIND_ON_MAP_BUTTON_TEXTS:
        logger.info(f"📍 [TEXT_INPUT_TASKS] Обнаружена кнопка Find on map от пользователя {user_id}")
        user_lang = get_user_language_or_default(user_id)
        maps_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("tasks.button.find_on_map", user_lang),
                        url="https://www.google.com/maps",
                    )
                ],
            ]
        )
        await message.answer(
            t("edit.location_map_prompt", user_lang),
            reply_markup=maps_keyboard,
        )
        return

    # Специальная обработка для MacBook: если пользователь нажал кнопку "🎯 Интересные места" повторно
    if text == "🎯 Интересные места":
        logger.info(
            f"📍 [TEXT_INPUT_TASKS] Обнаружен повторный запрос '🎯 Интересные места' от пользователя {user_id} (MacBook)"
        )
        user_lang = get_user_language_or_default(user_id)
        maps_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("tasks.button.find_on_map", user_lang),
                        url="https://www.google.com/maps",
                    )
                ],
            ]
        )
        await message.answer(
            t("tasks.press_location_hint", user_lang),
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
            user_lang = get_user_language_or_default(user_id)
            maps_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t("tasks.button.find_on_map", user_lang),
                            url="https://www.google.com/maps",
                        )
                    ],
                ]
            )
            await message.answer(
                t("edit.coords_link_failed", user_lang),
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
                await message.answer(t("edit.coords_out_of_range", user_lang))
                return
    except ValueError:
        # Не координаты, возможно это другой текст - пропускаем
        logger.info("📍 [TEXT_INPUT_TASKS] Текст не является координатами или ссылкой, пропускаем")
        pass

    # Если это не координаты и не ссылка, показываем подсказку
    user_lang = get_user_language_or_default(user_id)
    maps_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("tasks.button.find_on_map", user_lang),
                    url="https://www.google.com/maps",
                )
            ],
        ]
    )
    await message.answer(
        t("tasks.press_location_hint", user_lang),
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
    user_lang = get_user_language_or_default(user_id)
    keyboard = [
        [InlineKeyboardButton(text=t("tasks.category.food", user_lang), callback_data="task_category:food")],
        [InlineKeyboardButton(text=t("tasks.category.health", user_lang), callback_data="task_category:health")],
        [InlineKeyboardButton(text=t("tasks.category.places", user_lang), callback_data="task_category:places")],
        [InlineKeyboardButton(text=t("tasks.button.main_menu", user_lang), callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await message.answer(
        t("tasks.location_received", user_lang),
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
    logger.debug("📍 Получена геолокация от пользователя %s: lat=%s, lng=%s", user_id, lat, lng)

    # Проверяем состояние - если это для заданий, не обрабатываем здесь
    current_state = await state.get_state()
    logger.debug("📍 Обработчик событий: состояние=%s, user_id=%s", current_state, user_id)

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
        user_lang = get_user_language_or_default(user_id)
        await message.answer(t("errors.location_failed", user_lang))
        return

    lat = message.location.latitude
    lng = message.location.longitude

    # Логируем получение геолокации
    logger.debug(f"📍 Получена геолокация для событий: lat={lat} lon={lng} (источник=пользователь)")

    # Показываем индикатор загрузки
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)
    loading_message = await message.answer(
        t("search.loading", user_lang),
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
        logger.debug(f"🔎 Поиск с координатами=({lat}, {lng}) радиус={radius}км источник=пользователь")

        # Ищем события из всех источников
        try:
            logger.debug(f"🔍 Начинаем поиск событий для координат ({lat}, {lng}) с радиусом {radius} км")

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

            logger.debug("🌍 Поиск: координаты=(%s, %s), радиус=%s км, регион=%s", lat, lng, radius, city)
            logger.debug("🔍 SEARCH COORDS: lat=%s, lng=%s, radius=%s", lat, lng, radius)
            # Только SELECT из БД; парсинг (BaliForum, KudaGo, AI) по расписанию, не по запросу
            events = events_service.search_events_today(city=city, user_lat=lat, user_lng=lng, radius_km=int(radius))

            # Конвертируем в старый формат для совместимости
            formatted_events = []
            logger.debug("🕐 Получили %s событий из UnifiedEventsService", len(events))
            for event in events:
                starts_at_value = event.get("starts_at")
                logger.debug(
                    "🕐 ДО конвертации: %s - starts_at: %s", event.get("title", "")[:40], type(starts_at_value).__name__
                )

                formatted_event = {
                    "id": event.get("id"),  # Добавляем id для отслеживания кликов
                    "title": event["title"],
                    "title_en": event.get("title_en"),  # для мультиязычности (render_event_html)
                    "description": event["description"],
                    "description_en": event.get("description_en"),
                    "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
                    "starts_at": event["starts_at"],  # Добавляем поле starts_at!
                    "city": event.get("city"),  # Город события (может быть None)
                    "location_name": event["location_name"],
                    "location_name_en": event.get("location_name_en"),
                    "location_url": event["location_url"],
                    "lat": event["lat"],
                    "lng": event["lng"],
                    "source": event.get("source", ""),  # Сохраняем оригинальный source из БД
                    "source_type": event.get("source_type", ""),  # Добавляем source_type отдельно
                    "url": event.get("event_url", ""),
                    "community_name": "",
                    "community_link": "",
                    "venue_name": event.get("venue_name"),
                    "address": event.get("address"),
                    # Добавляем поля автора для пользовательских событий
                    "organizer_id": event.get("organizer_id"),
                    "organizer_username": event.get("organizer_username"),
                }

                logger.debug(
                    "🕐 ПОСЛЕ конвертации: %s - starts_at: %s",
                    formatted_event.get("title", "")[:40],
                    formatted_event.get("starts_at"),
                )

                # Логируем конвертацию для пользовательских событий
                if event.get("source") == "user":
                    logger.debug(
                        f"🔍 CONVERT USER EVENT: title='{event.get('title')}', "
                        f"organizer_id={event.get('organizer_id')} -> {formatted_event.get('organizer_id')}, "
                        f"organizer_username='{event.get('organizer_username')}' -> '{formatted_event.get('organizer_username')}'"
                    )
                formatted_events.append(formatted_event)

            events = formatted_events
            logger.debug("✅ Поиск завершен, найдено %s событий", len(events))
        except Exception:
            logger.exception("❌ Ошибка при поиске событий")
            # Удаляем сообщение загрузки при ошибке
            try:
                await loading_message.delete()
            except Exception:
                pass
            user_id = message.from_user.id
            fallback = render_fallback(lat, lng, get_user_language_or_default(user_id))
            await message.answer(
                fallback,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=main_menu_kb(user_id=user_id),
            )
            return

        # Сортируем события по времени (ближайшие первыми)
        events = sort_events_by_time(events)
        logger.debug("📅 События отсортированы по времени")

        # Ракеты за поиск убраны из системы

        # Единый конвейер: prepared → groups → counts → render
        try:
            prepared, diag = prepare_events_for_feed(
                events, user_point=(lat, lng), radius_km=int(radius), with_diag=True
            )
            logger.debug(
                "prepared: kept=%s dropped=%s reasons_top3=%s", diag["kept"], diag["dropped"], diag["reasons_top3"]
            )
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
                user_lang = get_user_language_or_default(message.from_user.id)
                if date_filter_state == "today":
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(
                                text=t("pager.today_selected", user_lang), callback_data="date_filter:today"
                            ),
                            InlineKeyboardButton(
                                text=t("pager.tomorrow", user_lang), callback_data="date_filter:tomorrow"
                            ),
                        ]
                    )
                else:
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(text=t("pager.today", user_lang), callback_data="date_filter:today"),
                            InlineKeyboardButton(
                                text=t("pager.tomorrow_selected", user_lang),
                                callback_data="date_filter:tomorrow",
                            ),
                        ]
                    )

                # Добавляем кнопки радиуса
                keyboard_buttons.extend(build_radius_inline_buttons(current_radius, user_lang))

                # Добавляем кнопку создания события
                keyboard_buttons.append(
                    [
                        InlineKeyboardButton(
                            text=t("menu.button.create_event", user_lang),
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

                # Получаем язык пользователя для i18n
                user_id = message.from_user.id
                user_lang = get_user_language_or_default(user_id)

                suggestion_line = (
                    format_translation("events.suggestion.change_radius", user_lang, radius=suggested_radius)
                    if suggested_radius != current_radius
                    else format_translation("events.suggestion.repeat_search", user_lang)
                )

                # Формируем текст сообщения в зависимости от фильтра даты
                date_text = "на сегодня" if date_filter_state == "today" else "на завтра"

                not_found_text = format_translation(
                    "events.not_found_with_radius", user_lang, radius=current_radius, date_text=date_text
                )
                create_text = format_translation("events.suggestion.create_your_own", user_lang)

                await message.answer(
                    f"{not_found_text}\n\n{suggestion_line}{create_text}",
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
            user_lang = get_user_language_or_default(message.from_user.id)
            header_html = render_header(counts, radius_km=int(radius), lang=user_lang)

            # Данные из БД уже с location_name (ingest). Enrich в хендлере не вызываем — убираем дублирование.
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
                        logger.debug(
                            "Событие %s: %s - координаты (%.6f, %.6f)",
                            i,
                            (event.get("title") or "")[:30],
                            event_lat,
                            event_lng,
                        )
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

                # 3) Создаем заголовок с событиями (prepared уже из БД, второй вызов enrich убран)
                user_lang = get_user_language_or_default(message.from_user.id)
                header_html = render_header(counts, radius_km=int(radius), lang=user_lang)

                # 5) Рендерим события для первой страницы
                # ИСПРАВЛЕНИЕ: Теперь карта и список событий отправляются отдельными сообщениями
                # Это позволяет показывать больше событий сразу (без ограничения 1024 байта для caption)
                page_size = 8  # Показываем 8 событий на первой странице (как и на остальных)
                page_html, total_pages = render_page(
                    prepared, page=1, page_size=page_size, user_id=message.from_user.id, is_caption=False
                )
                events_text = header_html + "\n\n" + page_html
                logger.debug("🔍 page_size для первой страницы: %s событий", page_size)

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
                        logger.debug(
                            "📊 list_view: user_id=%s, event_id=%s, group_chat_id=%s",
                            message.from_user.id,
                            event_id,
                            group_chat_id,
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
                combined_keyboard = kb_pager(1, total_pages, int(radius), date_filter=date_filter_state, lang=user_lang)

                # 7) НОВАЯ ЛОГИКА: Отправляем карту и список событий ОТДЕЛЬНЫМИ сообщениями
                # Это решает проблему с лимитом 1024 байта для caption и позволяет показывать больше событий
                if map_bytes:
                    # 7.1) Отправляем карту отдельным сообщением (без caption или с минимальным текстом)
                    from aiogram.types import BufferedInputFile

                    map_file = BufferedInputFile(map_bytes, filename="map.png")
                    map_caption = ""  # Без подписи — карта и так понятна
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
                    logger.debug("✅ Список событий отправлен отдельным сообщением")

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
                    logger.debug("✅ События отправлены в одном сообщении без карты")

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
                    user_id = message.from_user.id
                    await message.answer(
                        f"📋 Найдено {len(prepared)} событий в радиусе {radius} км",
                        reply_markup=main_menu_kb(user_id=user_id),
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
            user_id = message.from_user.id
            fallback = render_fallback(lat, lng, get_user_language_or_default(user_id))
            await message.answer(
                fallback,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=main_menu_kb(user_id=user_id),
            )

    except Exception as e:
        logger.error(f"Ошибка при поиске событий: {e}")
        user_id = message.from_user.id
        user_lang = get_user_language_or_default(user_id)
        await message.answer(t("search.error.general", user_lang), reply_markup=main_menu_kb(user_id=user_id))


@main_router.message(Command("create"))
@main_router.message(F.text.in_({"➕ Создать", "➕ Create"}))
async def on_create(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Создать' / 'Create' (reply-клавиатура)"""
    # Инкрементируем сессию World (с проверкой времени)
    if message.chat.type == "private":
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(message.from_user.id, min_interval_minutes=6)

    await state.set_state(EventCreation.waiting_for_title)
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)
    await message.answer(
        t("create.start", user_lang),
        parse_mode="Markdown",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=t("common.cancel", user_lang))]], resize_keyboard=True
        ),
    )


@main_router.message(F.text.in_(_CANCEL_BUTTON_TEXTS))
async def cancel_creation(message: types.Message, state: FSMContext):
    """Отмена создания события"""
    await state.clear()
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)
    await message.answer(t("create.cancelled", user_lang), reply_markup=main_menu_kb(user_id=user_id))


async def _handle_my_events_via_bot(bot: Bot, chat_id: int, user_id: int, is_private: bool):
    """Вспомогательная функция для обработки 'Мои события' через bot напрямую"""
    lang = get_user_language_or_default(user_id)
    logger.debug(f"🔍 _handle_my_events_via_bot: запрос от пользователя {user_id}")

    # Инкрементируем сессию World (с проверкой времени)
    if is_private:
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(user_id, min_interval_minutes=6)

    # Автомодерация: закрываем прошедшие события
    closed_count = auto_close_events()
    if closed_count > 0:
        await bot.send_message(
            chat_id=chat_id, text=format_translation("myevents.auto_closed", lang, count=closed_count)
        )

    # Получаем события пользователя
    events = get_user_events(user_id)
    logger.debug(
        f"🔍 _handle_my_events_via_bot: найдено {len(events) if events else 0} событий для пользователя {user_id}"
    )

    # Получаем события с участием (все добавленные события)
    all_participations = []

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем текст сообщения (та же логика, что и в on_my_events)
    text_parts = [
        t("myevents.header", lang),
        format_translation("myevents.balance", lang, rocket_balance=rocket_balance),
    ]

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
                updated_at = e.get("updated_at_utc")
                if updated_at:
                    local_time = updated_at.astimezone(tz_bali)
                    if local_time >= day_ago:
                        recent_closed_events.append(e)

        if active_events:
            text_parts.append(t("myevents.created_by_me", lang))
            for i, event in enumerate(active_events[:3], 1):
                title = event.get("title", t("common.title_not_specified", lang))
                location = event.get("location_name", t("common.location_tba", lang))
                starts_at = event.get("starts_at")

                if starts_at:
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = t("common.time_tba", lang)

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
                text_parts.append(format_translation("myevents.and_more", lang, count=len(active_events) - 3))

        if recent_closed_events:
            text_parts.append(
                f"\n{format_translation('myevents.recently_closed', lang, count=len(recent_closed_events))}"
            )
            for i, event in enumerate(recent_closed_events[:3], 1):
                title = event.get("title", t("common.title_not_specified", lang))
                location = event.get("location_name", t("common.location_tba", lang))
                starts_at = event.get("starts_at")

                if starts_at:
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = t("common.time_tba", lang)

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

                text_parts.append(
                    f"{i}) {escaped_title}\n🕐 {time_str}\n📍 {escaped_location} {t('common.closed', lang)}\n"
                )

            if len(recent_closed_events) > 3:
                text_parts.append(
                    format_translation("myevents.and_more_closed", lang, count=len(recent_closed_events) - 3)
                )

    # Добавленные события
    if all_participations:
        text_parts.append(f"\n➕ **Добавленные ({len(all_participations)}):**")
        for i, event in enumerate(all_participations[:3], 1):
            title = event.get("title", t("common.title_not_specified", lang))
            starts_at = event.get("starts_at")
            if starts_at:
                import pytz

                tz_bali = pytz.timezone("Asia/Makassar")
                local_time = starts_at.astimezone(tz_bali)
                time_str = local_time.strftime("%H:%M")
            else:
                time_str = "Время уточняется"
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

    if not events and not all_participations:
        rocket_balance = get_user_rockets(user_id)
        text_parts = [
            t("myevents.header", lang),
            t("myevents.no_events", lang) + "\n",
            format_translation("myevents.balance", lang, rocket_balance=rocket_balance).strip(),
        ]

    text = "\n".join(text_parts)

    # Создаем клавиатуру
    keyboard_buttons = []
    if events:
        keyboard_buttons.append(
            [InlineKeyboardButton(text=t("myevents.button.manage_events", lang), callback_data="manage_events")]
        )
    if all_participations:
        keyboard_buttons.append(
            [InlineKeyboardButton(text=t("myevents.button.all_added", lang), callback_data="view_participations")]
        )
    # Добавляем кнопки навигации: Главное меню и Мои квесты на одной линии
    keyboard_buttons.append(
        [
            InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main"),
            InlineKeyboardButton(text=t("myevents.button.my_quests", lang), callback_data="show_my_tasks"),
        ]
    )
    keyboard = (
        InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else main_menu_kb(user_id=user_id)
    )

    # Отправляем сообщение через bot
    import os
    from pathlib import Path

    photo_path = Path(__file__).parent / "images" / "my_events.png"

    if os.path.exists(photo_path):
        try:
            from aiogram.types import FSInputFile

            photo = FSInputFile(photo_path)
            await bot.send_photo(
                chat_id=chat_id, photo=photo, caption=text, reply_markup=keyboard, parse_mode="Markdown"
            )
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото: {e}", exc_info=True)

    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)


async def _handle_my_tasks_via_bot(bot: Bot, chat_id: int, user_id: int, is_private: bool):
    """Вспомогательная функция для обработки 'Мои квесты' через bot напрямую"""
    lang = get_user_language_or_default(user_id)
    # Инкрементируем сессию World (с проверкой времени)
    if is_private:
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(user_id, min_interval_minutes=6)

    # Получаем активные задания пользователя
    active_tasks = get_user_active_tasks(user_id)

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем текст сообщения
    if not active_tasks:
        message_text = (
            f"🏆 **{t('mytasks.title', lang)}**\n\n"
            f"{t('mytasks.empty', lang)}\n\n"
            f"**{format_translation('myevents.balance', lang, rocket_balance=rocket_balance).strip()}**\n\n"
            f"🎯 {t('mytasks.empty_hint', lang)}"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main"),
                    InlineKeyboardButton(text=t("myevents.button.my_events", lang), callback_data="show_my_events"),
                ],
            ]
        )
    else:
        message_text = t("mytasks.active_header", lang) + "\n\n"
        message_text += t("mytasks.reward_line", lang) + "\n\n"
        message_text += format_translation("myevents.balance", lang, rocket_balance=rocket_balance)

        km_suffix = t("mytasks.km_suffix", lang)
        place_label = t("mytasks.place_label", lang)
        for i, task in enumerate(active_tasks, 1):
            category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
            category_emoji = category_emojis.get(task["category"], "📋")
            task_title = (task.get("title_en") if lang == "en" else None) or task["title"]

            message_text += f"{i}) {category_emoji} **{task_title}**\n"

            if task.get("place_name") or task.get("place_url"):
                place_name = (
                    (task.get("place_name_en") if lang == "en" else None)
                    or task.get("place_name")
                    or t("group.list.place_on_map", lang)
                )
                place_url = task.get("place_url")
                distance = task.get("distance_km")

                if place_url:
                    if distance:
                        message_text += (
                            f"📍 **{place_label}** [{place_name} ({distance:.1f} {km_suffix})]({place_url})\n"
                        )
                    else:
                        message_text += f"📍 **{place_label}** [{place_name}]({place_url})\n"
                else:
                    if distance:
                        message_text += f"📍 **{place_label}** {place_name} ({distance:.1f} {km_suffix})\n"
                    else:
                        message_text += f"📍 **{place_label}** {place_name}\n"

            if task.get("promo_code"):
                message_text += format_translation("tasks.promo_code", lang, code=task["promo_code"]) + "\n"

            message_text += "\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("myevents.button.manage_tasks", lang), callback_data="manage_tasks")],
                [
                    InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main"),
                    InlineKeyboardButton(text=t("myevents.button.my_events", lang), callback_data="show_my_events"),
                ],
            ]
        )

    # Отправляем сообщение через bot
    import os
    from pathlib import Path

    photo_path = Path(__file__).parent / "images" / "my_quests.png"

    if os.path.exists(photo_path):
        try:
            from aiogram.types import FSInputFile

            photo = FSInputFile(photo_path)
            if keyboard:
                await bot.send_photo(
                    chat_id=chat_id, photo=photo, caption=message_text, reply_markup=keyboard, parse_mode="Markdown"
                )
            else:
                await bot.send_photo(chat_id=chat_id, photo=photo, caption=message_text, parse_mode="Markdown")
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото: {e}", exc_info=True)

    if keyboard:
        await bot.send_message(chat_id=chat_id, text=message_text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await bot.send_message(chat_id=chat_id, text=message_text, parse_mode="Markdown")


@main_router.message(Command("myevents"))
@main_router.message(F.text.in_(_MY_EVENTS_BUTTON_TEXTS))
async def on_my_events(message: types.Message):
    """Обработчик кнопки 'Мои события' с управлением статусами"""
    user_id = message.from_user.id
    lang = get_user_language_or_default(user_id)
    logger.debug(f"🔍 on_my_events: запрос от пользователя {user_id}")

    # Инкрементируем сессию World (с проверкой времени)
    if message.chat.type == "private":
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(user_id, min_interval_minutes=6)

    # Автомодерация: закрываем прошедшие события
    closed_count = auto_close_events()
    if closed_count > 0:
        await message.answer(format_translation("myevents.auto_closed", lang, count=closed_count))

    # Получаем события пользователя
    events = get_user_events(user_id)
    logger.debug(f"🔍 on_my_events: найдено {len(events) if events else 0} событий для пользователя {user_id}")

    # Получаем события с участием (все добавленные события)
    all_participations = []

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем текст сообщения
    text_parts = [
        t("myevents.header", lang),
        format_translation("myevents.balance", lang, rocket_balance=rocket_balance),
    ]

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
            text_parts.append(t("myevents.created_by_me", lang))
            for i, event in enumerate(active_events[:3], 1):
                title = event.get("title", t("common.title_not_specified", lang))
                event.get("starts_at")
                location = event.get("location_name", "Место уточняется")

                # Форматируем время проведения события (которое указал пользователь)
                starts_at = event.get("starts_at")
                if starts_at:
                    # Конвертируем UTC в местное время Бали
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = t("common.time_tba", lang)

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
                text_parts.append(format_translation("myevents.and_more", lang, count=len(active_events) - 3))

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

                text_parts.append(
                    f"{i}) {escaped_title}\n🕐 {time_str}\n📍 {escaped_location} {t('common.closed', lang)}\n"
                )

            if len(recent_closed_events) > 3:
                text_parts.append(
                    format_translation("myevents.and_more_closed", lang, count=len(recent_closed_events) - 3)
                )

    # Добавленные события
    if all_participations:
        text_parts.append(f"\n➕ **Добавленные ({len(all_participations)}):**")
        for i, event in enumerate(all_participations[:3], 1):
            title = event.get("title", t("common.title_not_specified", lang))
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

    # Добавляем кнопки навигации: Главное меню и Мои квесты на одной линии
    keyboard_buttons.append(
        [
            InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main"),
            InlineKeyboardButton(text=t("myevents.button.my_quests", lang), callback_data="show_my_tasks"),
        ]
    )

    keyboard = (
        InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else main_menu_kb(user_id=user_id)
    )

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
    user_id = message.from_user.id
    bot_info = await get_bot_info_cached()
    user_lang = get_user_language_or_default(user_id)
    bot_link = f"t.me/{bot_info.username}?startgroup=true"
    text = format_translation("share.title", user_lang, bot_link=bot_link)

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
                user_id = message.from_user.id
                await message.answer_photo(photo, caption=text, reply_markup=main_menu_kb(user_id=user_id))
                return
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить фото инструкции: {e}, отправляем только текст")
                break

    # Если фото нет или произошла ошибка, отправляем только текст
    user_id = message.from_user.id
    await message.answer(text, reply_markup=main_menu_kb(user_id=user_id))


def is_admin_user(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    from config import load_settings

    settings = load_settings()
    return user_id in settings.admin_ids


@main_router.message(Command("ban"))
async def on_ban(message: types.Message):
    """Команда для бана пользователя (только для админов)"""
    user_lang = get_user_language_or_default(message.from_user.id)
    if not is_admin_user(message.from_user.id):
        await message.answer(t("admin.permission.denied", user_lang))
        return

    try:
        command_parts = message.text.split(maxsplit=2)
        if len(command_parts) < 2:
            await message.answer(t("admin.ban.usage", user_lang))
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
            username_part = f" (@{username})" if username else ""
            ban_lines = []
            if days:
                ban_lines.append(
                    format_translation(
                        "admin.ban.success.temporary",
                        user_lang,
                        user_id=user_id_to_ban,
                        username_part=username_part,
                        days=days,
                    )
                )
            else:
                ban_lines.append(
                    format_translation(
                        "admin.ban.success.permanent",
                        user_lang,
                        user_id=user_id_to_ban,
                        username_part=username_part,
                    )
                )
            if reason:
                ban_lines.append(format_translation("admin.ban.reason", user_lang, reason=reason))
            await message.answer("\n".join(ban_lines))
        else:
            await message.answer(t("admin.ban.error", user_lang))

    except ValueError:
        await message.answer(t("admin.ban.invalid_id", user_lang))
    except Exception as e:
        logger.error(f"Ошибка в команде ban: {e}")
        error_text = str(e).replace("{", "{{").replace("}", "}}")
        await message.answer(format_translation("admin.error.exception", user_lang, error=error_text))


@main_router.message(Command("unban"))
async def on_unban(message: types.Message):
    """Команда для разбана пользователя (только для админов)"""
    user_lang = get_user_language_or_default(message.from_user.id)
    if not is_admin_user(message.from_user.id):
        await message.answer(t("admin.permission.denied", user_lang))
        return

    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.answer(t("admin.unban.usage", user_lang))
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
            await message.answer(format_translation("admin.unban.success", user_lang, user_id=user_id_to_unban))
        else:
            await message.answer(format_translation("admin.unban.not_found", user_lang, user_id=user_id_to_unban))

    except ValueError:
        await message.answer(t("admin.ban.invalid_id", user_lang))
    except Exception as e:
        logger.error(f"Ошибка в команде unban: {e}")
        error_text = str(e).replace("{", "{{").replace("}", "}}")
        await message.answer(format_translation("admin.error.exception", user_lang, error=error_text))


@main_router.message(Command("banlist"))
async def on_banlist(message: types.Message):
    """Команда для просмотра списка забаненных пользователей (только для админов)"""
    user_lang = get_user_language_or_default(message.from_user.id)
    if not is_admin_user(message.from_user.id):
        await message.answer(t("admin.permission.denied", user_lang))
        return

    try:
        from database import get_engine
        from utils.ban_service import BanService

        engine = get_engine()
        ban_service = BanService(engine)

        banned_users = ban_service.get_banned_users(limit=20)

        if not banned_users:
            await message.answer(t("admin.banlist.empty", user_lang))
            return

        text_lines = [t("admin.banlist.header", user_lang), ""]
        for ban in banned_users:
            user_info = f"ID: {ban['user_id']}"
            if ban["username"]:
                user_info += f" (@{ban['username']})"
            if ban["first_name"]:
                user_info += f" - {ban['first_name']}"

            text_lines.append(format_translation("admin.banlist.item", user_lang, user_info=user_info))
            if ban["reason"]:
                text_lines.append(format_translation("admin.banlist.reason", user_lang, reason=ban["reason"]))
            if ban["expires_at"]:
                expires_str = ban["expires_at"].strftime("%d.%m.%Y %H:%M")
                text_lines.append(format_translation("admin.banlist.until", user_lang, date=expires_str))
            else:
                text_lines.append(t("admin.banlist.permanent", user_lang))
            text_lines.append("")

        text = "\n".join(text_lines)
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в команде banlist: {e}")
        error_text = str(e).replace("{", "{{").replace("}", "}}")
        await message.answer(format_translation("admin.error.exception", user_lang, error=error_text))


@main_router.message(Command("admin_event"))
async def on_admin_event(message: types.Message):
    """Обработчик команды /admin_event для диагностики событий"""
    user_lang = get_user_language_or_default(message.from_user.id)
    try:
        # Извлекаем ID события из команды
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.answer(t("admin.event.usage", user_lang))
            return

        event_id = int(command_parts[1])

        # Ищем событие в БД
        with get_session() as session:
            event = session.get(Event, event_id)
            if not event:
                await message.answer(format_translation("admin.event.not_found", user_lang, event_id=event_id))
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
                f"<b>{t('event.source_link', user_lang)}:</b> {source}",
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
        await message.answer(t("admin.event.invalid_id", user_lang))
    except Exception as e:
        logger.error(f"Ошибка в команде admin_event: {e}")
        await message.answer(t("admin.event.error", user_lang))


@main_router.message(Command("diag_webhook"))
async def on_diag_webhook(message: types.Message):
    """Диагностика webhook"""
    lang = get_user_language_or_default(message.from_user.id)
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
        await message.answer(format_translation("diag.error_msg", lang, error=str(e)))


@main_router.message(Command("diag_commands"))
async def on_diag_commands(message: types.Message):
    """Диагностика команд бота"""
    lang = get_user_language_or_default(message.from_user.id)
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
        await message.answer(format_translation("diag.commands_error", lang, error=str(e)))


@main_router.message(Command("diag_last"))
async def on_diag_last(message: types.Message):
    """Обработчик команды /diag_last для диагностики последнего запроса"""
    user_lang = get_user_language_or_default(message.from_user.id)
    try:
        # Получаем состояние последнего запроса
        state = user_state.get(message.chat.id)
        if not state:
            await message.answer(t("search.no_last_request", user_lang))
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
        user_lang = get_user_language_or_default(message.from_user.id)
        await message.answer(t("diag.error", user_lang))


@main_router.message(Command("diag_all"))
async def on_diag_all(message: types.Message):
    """Обработчик команды /diag_all для полной диагностики системы"""
    user_lang = get_user_language_or_default(message.from_user.id)
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
            # ОГРАНИЧЕНИЕ: используем limit для защиты от OOM
            sources = session.query(Event.source).filter(Event.source.isnot(None)).distinct().limit(50).all()

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
        await message.answer(t("diag.error", user_lang))


@main_router.message(Command("diag_search"))
async def on_diag_search(message: types.Message):
    """Обработчик команды /diag_search для диагностики поиска"""
    user_lang = get_user_language_or_default(message.from_user.id)
    try:
        # Получаем состояние последнего запроса
        state = user_state.get(message.chat.id)
        if not state:
            await message.answer(t("search.no_last_request", user_lang))
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
        await message.answer(t("diag.search_error", user_lang))


@main_router.message(F.text.in_(_TASKS_TITLE_BUTTON_TEXTS))
async def on_tasks_goal(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Интересные места' - объяснение и запрос геолокации"""
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

    # Устанавливаем состояние для заданий
    await state.set_state(TaskFlow.waiting_for_location)

    # Создаем клавиатуру с кнопкой геолокации (one_time_keyboard=False - кнопка не исчезнет на MacBook)
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=t("tasks.button.send_location", user_lang),
                    request_location=True,
                )
            ],
            [KeyboardButton(text=t("tasks.button.find_on_map", user_lang))],
            [KeyboardButton(text=t("tasks.button.main_menu", user_lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,  # Изменено на False, чтобы кнопка не исчезала на MacBook
    )

    quest_text = (
        f"{t('tasks.title', user_lang)}\n" f"{t('tasks.reward', user_lang)}\n\n" f"{t('tasks.description', user_lang)}"
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


@main_router.message(F.text.in_(_MY_ACTIVITIES_BUTTON_TEXTS))
async def on_my_activities(message: types.Message):
    """Обработчик кнопки 'Мои активности' - показывает выбор между событиями и квестами"""
    user_lang = get_user_language_or_default(message.from_user.id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("myevents.button.my_events", user_lang), callback_data="show_my_events")],
            [InlineKeyboardButton(text=t("myevents.button.my_quests", user_lang), callback_data="show_my_tasks")],
        ]
    )
    await message.answer(t("tasks.choose_section", user_lang), reply_markup=keyboard)


@main_router.callback_query(F.data == "show_my_events")
async def show_my_events_callback(callback: types.CallbackQuery):
    """Callback обработчик для показа событий"""
    await callback.answer()

    # Удаляем сообщение с выбором
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Вызываем логику напрямую через bot
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    bot = callback.bot
    is_private = callback.message.chat.type == "private"

    await _handle_my_events_via_bot(bot, chat_id, user_id, is_private)


@main_router.callback_query(F.data == "show_my_tasks")
async def show_my_tasks_callback(callback: types.CallbackQuery):
    """Callback обработчик для показа квестов"""
    await callback.answer()

    # Удаляем сообщение с выбором
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Вызываем логику напрямую через bot
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    bot = callback.bot
    is_private = callback.message.chat.type == "private"

    await _handle_my_tasks_via_bot(bot, chat_id, user_id, is_private)


@main_router.message(F.text.in_(_MY_QUESTS_BUTTON_TEXTS))
async def on_my_tasks(message: types.Message):
    """Обработчик кнопки 'Мои квесты'"""
    user_id = message.from_user.id
    lang = get_user_language_or_default(user_id)

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
            f"🏆 **{t('mytasks.title', lang)}**\n\n"
            f"{t('mytasks.empty', lang)}\n\n"
            f"**{format_translation('myevents.balance', lang, rocket_balance=rocket_balance).strip()}**\n\n"
            f"🎯 {t('mytasks.empty_hint', lang)}"
        )
        # Добавляем кнопки навигации даже когда нет заданий
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main"),
                    InlineKeyboardButton(text=t("myevents.button.my_events", lang), callback_data="show_my_events"),
                ],
            ]
        )
    else:
        # Формируем сообщение со списком активных заданий (i18n + title_en для EN)
        message_text = t("mytasks.active_header", lang) + "\n\n"
        message_text += t("mytasks.reward_line", lang) + "\n\n"
        message_text += format_translation("myevents.balance", lang, rocket_balance=rocket_balance) + "\n\n"

        km_suffix = t("mytasks.km_suffix", lang)
        place_label = t("mytasks.place_label", lang)
        for i, task in enumerate(active_tasks, 1):
            category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
            category_emoji = category_emojis.get(task["category"], "📋")
            task_title = (task.get("title_en") if lang == "en" else None) or task["title"]

            message_text += f"{i}) {category_emoji} **{task_title}**\n"

            if task.get("place_name") or task.get("place_url"):
                place_name = (
                    (task.get("place_name_en") if lang == "en" else None)
                    or task.get("place_name")
                    or t("group.list.place_on_map", lang)
                )
                place_url = task.get("place_url")
                distance = task.get("distance_km")

                if place_url:
                    if distance:
                        message_text += (
                            f"📍 **{place_label}** [{place_name} ({distance:.1f} {km_suffix})]({place_url})\n"
                        )
                    else:
                        message_text += f"📍 **{place_label}** [{place_name}]({place_url})\n"
                else:
                    if distance:
                        message_text += f"📍 **{place_label}** {place_name} ({distance:.1f} {km_suffix})\n"
                    else:
                        message_text += f"📍 **{place_label}** {place_name}\n"

            if task.get("promo_code"):
                message_text += format_translation("tasks.promo_code", lang, code=task["promo_code"]) + "\n"

            message_text += "\n"

        # Добавляем кнопку управления заданиями
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("myevents.button.manage_tasks", lang), callback_data="manage_tasks")],
                [
                    InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main"),
                    InlineKeyboardButton(text=t("myevents.button.my_events", lang), callback_data="show_my_events"),
                ],
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
    """Обработчик команды /tasks - Интересные места"""
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

    # Инкрементируем сессию World (с проверкой времени)
    if message.chat.type == "private":
        from utils.user_analytics import UserAnalytics

        UserAnalytics.maybe_increment_sessions_world(message.from_user.id, min_interval_minutes=6)

    # Устанавливаем состояние для заданий
    await state.set_state(TaskFlow.waiting_for_location)

    # Создаем клавиатуру с кнопкой геолокации
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=t("tasks.button.send_location", user_lang),
                    request_location=True,
                )
            ],
            [KeyboardButton(text=t("tasks.button.find_on_map", user_lang))],
            [KeyboardButton(text=t("tasks.button.main_menu", user_lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    quest_text = (
        f"{t('tasks.title', user_lang)}\n" f"{t('tasks.reward', user_lang)}\n\n" f"{t('tasks.description', user_lang)}"
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


@main_router.message(Command("mytasks"))
async def cmd_mytasks(message: types.Message):
    """Обработчик команды /mytasks - Мои квесты"""
    user_id = message.from_user.id
    lang = get_user_language_or_default(user_id)

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
            f"🏆 **{t('mytasks.title', lang)}**\n\n"
            f"{t('mytasks.empty', lang)}\n\n"
            f"**{format_translation('myevents.balance', lang, rocket_balance=rocket_balance).strip()}**\n\n"
            f"🎯 {t('mytasks.empty_hint', lang)}"
        )
        # Клавиатура не нужна, когда нет заданий
        keyboard = None
    else:
        # Формируем сообщение со списком активных заданий (i18n + title_en для EN)
        message_text = t("mytasks.active_header", lang) + "\n\n"
        message_text += t("mytasks.reward_line", lang) + "\n\n"
        message_text += format_translation("myevents.balance", lang, rocket_balance=rocket_balance)

        km_suffix = t("mytasks.km_suffix", lang)
        place_label = t("mytasks.place_label", lang)
        for i, task in enumerate(active_tasks, 1):
            category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
            category_emoji = category_emojis.get(task["category"], "📋")
            task_title = (task.get("title_en") if lang == "en" else None) or task["title"]

            message_text += f"{i}) {category_emoji} **{task_title}**\n"

            if task.get("place_name") or task.get("place_url"):
                place_name = (
                    (task.get("place_name_en") if lang == "en" else None)
                    or task.get("place_name")
                    or t("group.list.place_on_map", lang)
                )
                place_url = task.get("place_url")
                distance = task.get("distance_km")

                if place_url:
                    if distance:
                        message_text += (
                            f"📍 **{place_label}** [{place_name} ({distance:.1f} {km_suffix})]({place_url})\n"
                        )
                    else:
                        message_text += f"📍 **{place_label}** [{place_name}]({place_url})\n"
                else:
                    if distance:
                        message_text += f"📍 **{place_label}** {place_name} ({distance:.1f} {km_suffix})\n"
                    else:
                        message_text += f"📍 **{place_label}** {place_name}\n"

            if task.get("promo_code"):
                message_text += format_translation("tasks.promo_code", lang, code=task["promo_code"]) + "\n"

            message_text += "\n"

        # Добавляем кнопку управления заданиями
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("myevents.button.manage_tasks", lang), callback_data="manage_tasks")],
                [
                    InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main"),
                    InlineKeyboardButton(text=t("myevents.button.my_events", lang), callback_data="show_my_events"),
                ],
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
    lang = get_user_language_or_default(user_id)
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
                    text=f"🏆 **{t('mytasks.title', lang)}**\n\n{t('mytasks.empty', lang)}",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении сообщения с фото: {e}", exc_info=True)
                # Fallback: отправляем новое сообщение
                chat_id = callback.message.chat.id
                bot = callback.bot
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🏆 **{t('mytasks.title', lang)}**\n\n{t('mytasks.empty', lang)}",
                    parse_mode="Markdown",
                )
        else:
            try:
                await callback.message.edit_text(
                    f"🏆 **{t('mytasks.title', lang)}**\n\n{t('mytasks.empty', lang)}",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при редактировании сообщения: {e}", exc_info=True)
                # Fallback: отправляем новое сообщение
                chat_id = callback.message.chat.id
                bot = callback.bot
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🏆 **{t('mytasks.title', lang)}**\n\n{t('mytasks.empty', lang)}",
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
    lang = get_user_language_or_default(user_id)
    task = tasks[task_index]

    # Вычисляем оставшееся время
    expires_at = task["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    time_left = expires_at - datetime.now(UTC)
    int(time_left.total_seconds() / 3600)

    category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
    category_emoji = category_emojis.get(task["category"], "📋")
    category_name = t(f"tasks.category.{task['category']}", lang) if task.get("category") else task.get("category", "")
    task_title = (task.get("title_en") if lang == "en" else None) or task["title"]
    task_description = (task.get("title_en") if lang == "en" else None) or task["description"]

    message_text = f"📋 **{task_title}**\n\n"
    message_text += f"{category_emoji} **{t('mytasks.label_category', lang)}** {category_name}\n"
    message_text += f"📝 **{t('mytasks.label_description', lang)}** {task_description}\n"

    km_suffix = t("mytasks.km_suffix", lang)
    place_label = t("mytasks.place_label", lang)
    if task.get("place_name") or task.get("place_url"):
        place_name = (
            (task.get("place_name_en") if lang == "en" else None)
            or task.get("place_name")
            or t("group.list.place_on_map", lang)
        )
        place_url = task.get("place_url")
        distance = task.get("distance_km")

        if place_url:
            if distance:
                message_text += f"📍 **{place_label}** [{place_name} ({distance:.1f} {km_suffix})]({place_url})\n"
            else:
                message_text += f"📍 **{place_label}** [{place_name}]({place_url})\n"
        else:
            if distance:
                message_text += f"📍 **{place_label}** {place_name} ({distance:.1f} {km_suffix})\n"
            else:
                message_text += f"📍 **{place_label}** {place_name}\n"

    if task.get("promo_code"):
        message_text += format_translation("tasks.promo_code", lang, code=task["promo_code"]) + "\n"

    # Создаем клавиатуру для навигации
    keyboard = []

    keyboard.append(
        [
            InlineKeyboardButton(
                text=t("mytasks.button.done", lang), callback_data=f"task_complete:{task['id']}:{task_index}"
            ),
            InlineKeyboardButton(
                text=t("mytasks.button.cancel", lang), callback_data=f"task_cancel:{task['id']}:{task_index}"
            ),
        ]
    )

    # Навигация в едином стиле: Стр. N/M | Назад | Вперёд (кольцо)
    if len(tasks) > 1:
        total_t = len(tasks)
        prev_idx = (total_t - 1) if task_index == 0 else (task_index - 1)
        next_idx = 0 if task_index == total_t - 1 else (task_index + 1)
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=format_translation("pager.page", lang, page=task_index + 1, total=total_t),
                    callback_data="task_nav_noop",
                ),
                InlineKeyboardButton(text=t("pager.prev", lang), callback_data=f"task_nav:{prev_idx}"),
                InlineKeyboardButton(text=t("pager.next", lang), callback_data=f"task_nav:{next_idx}"),
            ]
        )

    # Кнопки возврата
    keyboard.append([InlineKeyboardButton(text=t("mytasks.button.back_to_list", lang), callback_data="my_tasks_list")])
    keyboard.append([InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main")])

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


@main_router.callback_query(F.data == "task_nav_noop")
async def handle_task_nav_noop(callback: types.CallbackQuery):
    await callback.answer()
    return


@main_router.callback_query(F.data.startswith("task_nav:"))
async def handle_task_navigation(callback: types.CallbackQuery):
    """Обработчик навигации по заданиям (кольцо)"""
    user_id = callback.from_user.id
    try:
        task_index = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer()
        return

    active_tasks = get_user_active_tasks(user_id)
    if not active_tasks:
        await callback.answer()
        return
    total = len(active_tasks)
    if task_index < 0:
        task_index = total - 1
    elif task_index >= total:
        task_index = 0

    await show_task_detail(callback, active_tasks, task_index, user_id)
    await callback.answer()


@main_router.callback_query(F.data == "my_tasks_list")
async def handle_back_to_tasks_list(callback: types.CallbackQuery):
    """Возврат к списку заданий"""
    user_id = callback.from_user.id
    lang = get_user_language_or_default(user_id)
    active_tasks = get_user_active_tasks(user_id)

    if not active_tasks:
        # Получаем баланс ракет пользователя
        from rockets_service import get_user_rockets

        rocket_balance = get_user_rockets(user_id)

        text = (
            f"🏆 **{t('mytasks.title', lang)}**\n\n"
            f"{t('mytasks.empty', lang)}\n\n"
            f"**{format_translation('myevents.balance', lang, rocket_balance=rocket_balance).strip()}**\n\n"
            f"🎯 {t('mytasks.empty_hint', lang)}"
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

    # Формируем сообщение со списком активных заданий (i18n + title_en для EN)
    message_text = t("mytasks.active_header", lang) + "\n\n"
    message_text += t("mytasks.reward_line", lang) + "\n"
    message_text += t("mytasks.motivation_line", lang) + "\n\n"
    message_text += format_translation("myevents.balance", lang, rocket_balance=rocket_balance) + "\n\n"

    km_suffix = t("mytasks.km_suffix", lang)
    place_label = t("mytasks.place_label", lang)
    time_label = t("mytasks.time_to_complete", lang)
    for i, task in enumerate(active_tasks, 1):
        expires_at = task["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        start_time = task["accepted_at"]
        end_time = expires_at
        time_period = f"{start_time.strftime('%d.%m.%Y %H:%M')} → {end_time.strftime('%d.%m.%Y %H:%M')}"

        category_emojis = {"food": "🍔", "health": "💪", "places": "🌟"}
        category_emoji = category_emojis.get(task["category"], "📋")
        task_title = (task.get("title_en") if lang == "en" else None) or task["title"]

        message_text += f"{i}) {category_emoji} **{task_title}**\n"
        message_text += f"⏰ **{time_label}** {time_period}\n"

        if task.get("place_name") or task.get("place_url"):
            place_name = (
                (task.get("place_name_en") if lang == "en" else None)
                or task.get("place_name")
                or t("group.list.place_on_map", lang)
            )
            place_url = task.get("place_url")
            distance = task.get("distance_km")

            if place_url:
                if distance:
                    message_text += f"📍 **{place_label}** [{place_name} ({distance:.1f} {km_suffix})]({place_url})\n"
                else:
                    message_text += f"📍 **{place_label}** [{place_name}]({place_url})\n"
            else:
                if distance:
                    message_text += f"📍 **{place_label}** {place_name} ({distance:.1f} {km_suffix})\n"
                else:
                    message_text += f"📍 **{place_label}** {place_name}\n"

        if task.get("promo_code"):
            message_text += format_translation("tasks.promo_code", lang, code=task["promo_code"]) + "\n"

        message_text += "\n"

    # Добавляем кнопку управления заданиями
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("myevents.button.manage_tasks", lang), callback_data="manage_tasks")],
            [InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main")],
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

    logger.debug(f"🔍 handle_expand_radius: пользователь {user_id} расширяет радиус до {new_radius} км")

    # Получаем сохраненное состояние
    state_data = user_state.get(chat_id)
    if not state_data:
        await callback.answer(t("search.state_expired", get_user_language_or_default(callback.from_user.id)))
        return

    lat = state_data.get("lat")
    lng = state_data.get("lng")
    region = state_data.get("region", "bali")

    if not lat or not lng:
        await callback.answer(
            t("search.location_not_found", get_user_language_or_default(callback.from_user.id)),
            show_alert=True,
        )
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

    logger.debug(f"🔍 РАСШИРЕНИЕ РАДИУСА: radius={new_radius} км, date_filter={date_filter}, date_offset={date_offset}")

    events = events_service.search_events_today(
        city=city,
        user_lat=lat,
        user_lng=lng,
        radius_km=new_radius,
        date_offset=date_offset,
        message_id=f"{callback.message.message_id}",
    )

    # Конвертируем в старый формат для совместимости (с полями _en для мультиязычности)
    formatted_events = []
    for event in events:
        formatted_event = {
            "id": event.get("id"),
            "title": event["title"],
            "title_en": event.get("title_en"),
            "description": event["description"],
            "description_en": event.get("description_en"),
            "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
            "starts_at": event["starts_at"],
            "city": event.get("city"),  # Город события (может быть None)
            "location_name": event["location_name"],
            "location_name_en": event.get("location_name_en"),
            "location_url": event["location_url"],
            "lat": event["lat"],
            "lng": event["lng"],
            "source": event.get("source", ""),
            "source_type": event.get("source_type", ""),
            "url": event.get("event_url", ""),
            "community_name": "",
            "community_link": "",
            "venue_name": event.get("venue_name"),
            "address": event.get("address"),
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
        user_lang = get_user_language_or_default(user_id)

        # Добавляем кнопки фильтрации даты (Сегодня/Завтра)
        if date_filter == "today":
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(text=t("pager.today_selected", user_lang), callback_data="date_filter:today"),
                    InlineKeyboardButton(text=t("pager.tomorrow", user_lang), callback_data="date_filter:tomorrow"),
                ]
            )
        else:
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(text=t("pager.today", user_lang), callback_data="date_filter:today"),
                    InlineKeyboardButton(
                        text=t("pager.tomorrow_selected", user_lang),
                        callback_data="date_filter:tomorrow",
                    ),
                ]
            )

        # Добавляем кнопки радиуса
        keyboard_buttons.extend(build_radius_inline_buttons(current_radius, user_lang))

        # Добавляем кнопку создания события
        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text=t("menu.button.create_event", user_lang),
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
        # Получаем язык пользователя для i18n
        user_lang = get_user_language_or_default(user_id)

        suggestion_line = (
            format_translation("events.suggestion.change_radius", user_lang, radius=suggested_radius)
            if suggested_radius != current_radius
            else format_translation("events.suggestion.repeat_search", user_lang)
        )

        # Формируем текст сообщения в зависимости от фильтра даты
        date_text = "на сегодня" if date_filter == "today" else "на завтра"

        not_found_text = format_translation(
            "events.not_found_with_radius", user_lang, radius=current_radius, date_text=date_text
        )
        create_text = format_translation("events.suggestion.create_your_own", user_lang)

        await callback.message.edit_text(
            f"{not_found_text}\n\n{suggestion_line}{create_text}",
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

    # Данные из БД уже с location_name (ingest). Enrich в хендлере не вызываем.
    # Рендерим страницу
    user_lang = get_user_language_or_default(user_id)
    header_html = render_header(counts, radius_km=new_radius, lang=user_lang)
    events_text, total_pages = render_page(prepared, 1, page_size=8, user_id=user_id)

    text = header_html + "\n\n" + events_text

    # Создаем клавиатуру с кнопками пагинации и расширения радиуса
    keyboard = kb_pager(1, total_pages, new_radius, date_filter=date_filter, lang=user_lang)

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
            # Освобождаем память после создания файла
            del map_bytes
            map_caption = ""

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

    user_lang = get_user_language_or_default(callback.from_user.id)
    await callback.answer(format_translation("pager.radius_expanded", user_lang, radius=new_radius))


@main_router.callback_query(F.data.startswith("task_complete:"))
async def handle_task_complete(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик завершения задания"""
    user_task_id = int(callback.data.split(":")[1])
    user_lang = get_user_language_or_default(callback.from_user.id)

    await state.set_state(EventCreation.waiting_for_feedback)
    await state.update_data(user_task_id=user_task_id)

    text = t("mytasks.completed_title", user_lang) + "\n\n" + t("mytasks.share_impressions", user_lang)
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()


@main_router.callback_query(F.data.startswith("task_cancel:"))
async def handle_task_cancel(callback: types.CallbackQuery):
    """Обработчик отмены задания"""
    parts = callback.data.split(":")
    user_task_id = int(parts[1])
    task_index = int(parts[2]) if len(parts) > 2 else None
    user_id = callback.from_user.id

    # Отменяем задание
    success = cancel_task(user_task_id)

    if not success:
        user_lang = get_user_language_or_default(user_id)
        await callback.message.edit_text(
            t("mytasks.cancel_error", user_lang),
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    # Получаем обновленный список заданий (без удаленного)
    active_tasks = get_user_active_tasks(user_id)

    if not active_tasks:
        # Нет активных заданий
        user_lang = get_user_language_or_default(user_id)
        await callback.message.edit_text(
            f"🏆 **{t('mytasks.title', user_lang)}**\n\n{t('mytasks.empty', user_lang)}",
            parse_mode="Markdown",
        )
        await callback.answer(t("tasks.cancelled", user_lang))
        return

    # Определяем, какое задание показать после удаления
    # Если удалили не последнее, показываем задание с тем же индексом
    # Если удалили последнее, показываем предыдущее
    if task_index is not None:
        if task_index >= len(active_tasks):
            # Удалили последнее задание, показываем предыдущее
            new_index = len(active_tasks) - 1
        else:
            # Показываем задание с тем же индексом (которое теперь на месте удаленного)
            new_index = task_index
    else:
        # Если индекс не передан, показываем первое задание
        new_index = 0

    # Показываем следующее задание
    await show_task_detail(callback, active_tasks, new_index, user_id)
    user_lang = get_user_language_or_default(user_id)
    await callback.answer(t("tasks.cancelled", user_lang))


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

    lang = get_user_language_or_default(user_id)
    category_name = t(f"tasks.category.{category}", lang)
    no_places_text = t("tasks.no_places_in_category", lang)

    # Если мест нет
    if not all_places:
        text = f"🎯 **{category_name}**\n\n{no_places_text}"
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("pager.prev", lang), callback_data="back_to_tasks")],
                [InlineKeyboardButton(text=t("tasks.button.main_menu", lang), callback_data="back_to_main")],
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
    text += t("tasks.places_found", lang).format(count=len(all_places)) + "\n\n"

    # Получаем username бота для создания deep links
    bot_info = await message_or_callback.bot.get_me() if hasattr(message_or_callback, "bot") else None
    bot_username = bot_info.username if bot_info else get_bot_username()

    take_quest_label = t("tasks.take_quest", lang)

    # Добавляем каждое место с ссылкой "Забрать квест" в тексте
    for idx, place in enumerate(page_places, start=start_idx + 1):
        # Название места по языку (name_en для EN, иначе name)
        place_display_name = (getattr(place, "name_en", None) or place.name) if lang == "en" else place.name
        if place.google_maps_url:
            escaped_name = (
                place_display_name.replace("[", "\\[").replace("]", "\\]").replace("(", "\\(").replace(")", "\\)")
            )
            text += f"**{idx}. [{escaped_name}]({place.google_maps_url})**\n"
        else:
            text += f"**{idx}. {place_display_name}**\n"

        # Расстояние
        if hasattr(place, "distance_km") and place.distance_km:
            text += t("tasks.km_from_you", lang).format(distance=place.distance_km) + "\n"

        # Промокод
        if place.promo_code:
            text += t("tasks.promo_code", lang).format(code=place.promo_code) + "\n"

        # Короткое задание (task_hint) по языку
        hint_text = (
            (getattr(place, "task_hint_en", None) or place.task_hint) if lang == "en" else (place.task_hint or "")
        )
        if hint_text:
            text += f"💡 {hint_text}\n"

        # Ссылка "Забрать квест"
        deep_link = f"https://t.me/{bot_username}?start=add_quest_{place.id}"
        text += f"[{take_quest_label}]({deep_link})\n\n"

    # Создаем клавиатуру: при total_pages > 1 — один ряд ← | Стр. N/M | → (кольцо), иначе без стрелок
    keyboard = []

    if total_pages > 1:
        prev_p = total_pages if page == 1 else page - 1
        next_p = 1 if page == total_pages else page + 1
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=t("pager.page", lang).format(page=page, total=total_pages),
                    callback_data="places_page:noop",
                ),
                InlineKeyboardButton(text=t("pager.prev", lang), callback_data=f"places_page:{category}:{prev_p}"),
                InlineKeyboardButton(text=t("pager.next", lang), callback_data=f"places_page:{category}:{next_p}"),
            ]
        )

    # Кнопки управления
    keyboard.append(
        [
            InlineKeyboardButton(text=t("tasks.button.list", lang), callback_data="back_to_tasks"),
            InlineKeyboardButton(text=t("tasks.button.main_menu", lang), callback_data="back_to_main"),
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

        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("tasks.added", user_lang))

    except Exception as e:
        logger.error(f"Ошибка начала задания: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("tasks.start_error", user_lang))


@main_router.callback_query(F.data == "back_to_main")
async def handle_back_to_main_tasks(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик возврата в главное меню из заданий. Явно передаём язык, чтобы reply-клавиатура была на выбранном языке."""
    await state.clear()
    user_lang = get_user_language_or_default(callback.from_user.id)
    await send_spinning_menu(callback.message, lang=user_lang)
    await callback.answer()


@main_router.callback_query(F.data == "show_bot_commands")
async def handle_show_bot_commands(callback: types.CallbackQuery):
    """Обработчик показа команд бота"""
    lang = get_user_language_or_default(callback.from_user.id)
    commands_text = t("commands.list", lang)

    # Создаем клавиатуру с кнопкой возврата
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("mytasks.button.back_to_tasks", lang), callback_data="back_to_tasks")],
            [InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main")],
        ]
    )

    await callback.message.edit_text(commands_text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()


@main_router.callback_query(F.data == "back_to_tasks")
async def handle_back_to_tasks(callback: types.CallbackQuery):
    """Обработчик возврата к выбору категории заданий"""
    user_lang = get_user_language_or_default(callback.from_user.id)
    keyboard = [
        [InlineKeyboardButton(text=t("tasks.category.food", user_lang), callback_data="task_category:food")],
        [InlineKeyboardButton(text=t("tasks.category.health", user_lang), callback_data="task_category:health")],
        [InlineKeyboardButton(text=t("tasks.category.places", user_lang), callback_data="task_category:places")],
        [InlineKeyboardButton(text=t("tasks.button.main_menu", user_lang), callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    header = t("tasks.title", user_lang)
    body = t("tasks.categories_intro", user_lang)
    await callback.message.edit_text(
        f"{header}\n\n{body}",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    await callback.answer()


@main_router.callback_query(F.data.startswith("places_page:"))
async def handle_places_page(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик пагинации мест"""
    parts = callback.data.split(":")
    user_lang = get_user_language_or_default(callback.from_user.id)
    if len(parts) < 3 or parts[2] == "noop":
        await callback.answer(t("tasks.page_edge", user_lang))
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
        await callback.answer(t("tasks.require_location", user_lang))
        return

    # Показываем страницу мест
    await show_tasks_for_category(callback.message, category, user_id, user_lat, user_lng, state, page=page)
    await callback.answer()


@main_router.callback_query(F.data.startswith("add_place_to_quests:"))
async def handle_add_place_to_quests(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик добавления места в квесты"""
    place_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    logger.info(f"🎯 handle_add_place_to_quests: user_id={user_id}, place_id={place_id}")

    # Получаем координаты пользователя из БД
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        user_lat = user.last_lat if user else None
        user_lng = user.last_lng if user else None

    user_lang = get_user_language_or_default(user_id)
    success, message_text = create_task_from_place(user_id, place_id, user_lat, user_lng, lang=user_lang)

    logger.info(
        f"🎯 handle_add_place_to_quests: user_id={user_id}, place_id={place_id}, "
        f"success={success}, message='{message_text[:50]}'"
    )

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

    task_index = next((i for i, t in enumerate(active_tasks) if t["id"] == user_task_id), None)
    lang = get_user_language_or_default(callback.from_user.id)

    keyboard = [
        [InlineKeyboardButton(text=t("mytasks.button.done", lang), callback_data=f"task_complete:{user_task_id}")],
        [
            InlineKeyboardButton(
                text=t("mytasks.button.cancel", lang),
                callback_data=f"task_cancel:{user_task_id}:{task_index if task_index is not None else 0}",
            )
        ],
        [InlineKeyboardButton(text=t("mytasks.button.back_to_list", lang), callback_data="my_tasks")],
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
        user_lang = get_user_language_or_default(user_id)
        await message.answer(t("tasks.complete_not_found", user_lang))
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
@main_router.message(F.text.in_(_HELP_BUTTON_TEXTS))
async def on_help(message: types.Message):
    """Обработчик кнопки 'Написать отзыв Разработчику'"""
    lang = get_user_language_or_default(message.from_user.id)
    feedback_text = t("help.feedback.text", lang)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("help.button.write", lang), url="https://t.me/Fincontro")],
            [InlineKeyboardButton(text=t("myevents.button.main_menu", lang), callback_data="back_to_main")],
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

    # Получаем язык пользователя для i18n
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

    # Проверяем на команды (символ / в начале)
    if title.startswith("/"):
        await message.answer(
            t("create.validation.no_commands_in_title", user_lang),
            parse_mode="Markdown",
        )
        return

    title_lower = title.lower()
    if any(indicator in title_lower for indicator in spam_indicators):
        await message.answer(
            t("create.validation.no_links_in_title", user_lang),
            parse_mode="Markdown",
        )
        return

    # Сохраняем chat_id для групповых чатов
    await state.update_data(title=title, chat_id=chat_id, chat_type=chat_type)
    await state.set_state(EventCreation.waiting_for_date)
    example_date = get_example_date()

    # Разные сообщения для личных и групповых чатов
    if chat_type == "private":
        await message.answer(
            format_translation("create.title_saved", user_lang, title=title, example_date=example_date),
            parse_mode="Markdown",
        )
    else:
        # Для групповых чатов используем edit_text
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
        )
        await message.edit_text(
            format_translation("create.title_saved", user_lang, title=title, example_date=example_date),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


@main_router.message(EventCreation.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    """Шаг 2: Обработка даты события"""
    date = message.text.strip()
    logger.info(f"process_date: получили дату '{date}' от пользователя {message.from_user.id}")

    # Получаем язык пользователя для i18n
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

    # Валидация формата даты DD.MM.YYYY

    if not re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", date):
        await message.answer(
            t("create.validation.invalid_date_format", user_lang),
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
                format_translation(
                    "create.validation.past_date", user_lang, date=date, today=today_bali.strftime("%d.%m.%Y")
                ),
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
    await message.answer(format_translation("create.date_saved", user_lang, date=date), parse_mode="Markdown")


@main_router.message(EventCreation.waiting_for_time)
async def process_time(message: types.Message, state: FSMContext):
    """Шаг 3: Обработка времени события"""
    time = message.text.strip()
    logger.info(f"process_time: получили время '{time}' от пользователя {message.from_user.id}")

    # Получаем язык пользователя для i18n
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

    # Валидация формата времени HH:MM

    if not re.match(r"^\d{1,2}:\d{2}$", time):
        await message.answer(
            t("create.validation.invalid_time_format", user_lang),
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
            [InlineKeyboardButton(text=t("community.location_link", user_lang), callback_data="location_link")],
            [InlineKeyboardButton(text=t("community.location_map", user_lang), callback_data="location_map")],
            [InlineKeyboardButton(text=t("community.location_coords", user_lang), callback_data="location_coords")],
        ]
    )

    await message.answer(
        format_translation("create.time_saved", user_lang, time=time)
        .replace("📍 **Отправьте геолокацию или введите место:**", "")
        .strip()
        + "\n\n"
        + t("create.location_prompt", user_lang),
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
            user_lang = get_user_language_or_default(message.from_user.id)
            await message.answer(
                format_translation(
                    "create.place_defined",
                    user_lang,
                    name=location_data.get("name", t("group.list.place_on_map", user_lang)),
                )
                + t("create.add_description", user_lang),
                parse_mode="Markdown",
            )
        else:
            user_lang = get_user_language_or_default(message.from_user.id)
            await message.answer(t("create.link_failed", user_lang))

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
                user_lang = get_user_language_or_default(message.from_user.id)
                await message.answer(
                    format_translation("create.place_by_coords", user_lang, lat=lat, lng=lng)
                    + t("create.add_description", user_lang),
                    parse_mode="Markdown",
                )
            else:
                raise ValueError("Invalid coordinates range")

        except ValueError:
            user_lang = get_user_language_or_default(message.from_user.id)
            await message.answer(t("create.invalid_coords", user_lang), parse_mode="Markdown")
    else:
        # Не ссылка - напоминаем о кнопках
        user_lang = get_user_language_or_default(message.from_user.id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("community.location_link", user_lang), callback_data="location_link")],
                [InlineKeyboardButton(text=t("community.location_map", user_lang), callback_data="location_map")],
            ]
        )

        await message.answer(
            t("create.location_use_buttons", user_lang),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


# Обработчики для выбора типа локации
@main_router.callback_query(F.data == "location_link")
async def handle_location_link_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода готовой ссылки"""
    lang = get_user_language_or_default(callback.from_user.id)
    current_state = await state.get_state()

    if current_state == TaskFlow.waiting_for_custom_location:
        # Для заданий
        await callback.message.answer(t("create.paste_google_maps_link", lang))
    else:
        # Для событий
        await state.set_state(EventCreation.waiting_for_location_link)
        await callback.message.answer(t("create.paste_google_maps_link", lang))

    await callback.answer()


@main_router.callback_query(F.data == "location_map")
async def handle_location_map_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор поиска на карте"""
    current_state = await state.get_state()

    # Создаем кнопку для открытия Google Maps
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("create.button_open_google_maps", get_user_language_or_default(callback.from_user.id)),
                    url="https://www.google.com/maps",
                )
            ]
        ]
    )

    lang = get_user_language_or_default(callback.from_user.id)
    if current_state == TaskFlow.waiting_for_custom_location:
        # Для заданий
        await callback.message.answer(t("edit.location_map_prompt", lang), reply_markup=keyboard)
    else:
        # Для событий
        await state.set_state(EventCreation.waiting_for_location_link)
        await callback.message.answer(t("edit.location_map_prompt", lang), reply_markup=keyboard)

    await callback.answer()


@main_router.callback_query(F.data == "location_coords")
async def handle_location_coords_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода координат"""
    current_state = await state.get_state()

    lang = get_user_language_or_default(callback.from_user.id)
    if current_state == TaskFlow.waiting_for_custom_location:
        # Для заданий
        await callback.message.answer(
            t("edit.location_coords_prompt", lang),
            parse_mode="Markdown",
        )
    else:
        # Для событий
        await state.set_state(EventCreation.waiting_for_location_link)
        await callback.message.answer(
            t("edit.location_coords_prompt", lang),
            parse_mode="Markdown",
        )

    await callback.answer()


# Обработчики для выбора типа локации в Community режиме
@main_router.callback_query(F.data == "community_location_link")
async def handle_community_location_link_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода готовой ссылки в Community режиме"""
    lang = get_user_language_or_default(callback.from_user.id)
    await state.set_state(CommunityEventCreation.waiting_for_location_url)
    await callback.message.answer(
        t("create.paste_google_maps_link", lang),
        reply_markup=get_community_cancel_kb(callback.from_user.id),
    )
    await callback.answer()


@main_router.callback_query(F.data == "community_location_map")
async def handle_community_location_map_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор поиска на карте в Community режиме"""
    # Создаем кнопку для открытия Google Maps
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("create.button_open_google_maps", get_user_language_or_default(callback.from_user.id)),
                    url="https://www.google.com/maps",
                )
            ]
        ]
    )
    await state.set_state(CommunityEventCreation.waiting_for_location_url)
    lang = get_user_language_or_default(callback.from_user.id)
    await callback.message.answer(t("edit.location_map_prompt", lang), reply_markup=keyboard)
    await callback.answer()


@main_router.callback_query(F.data == "community_location_coords")
async def handle_community_location_coords_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода координат в Community режиме"""
    await state.set_state(CommunityEventCreation.waiting_for_location_url)
    lang = get_user_language_or_default(callback.from_user.id)
    await callback.message.answer(
        t("edit.location_coords_prompt", lang),
        parse_mode="Markdown",
        reply_markup=get_community_cancel_kb(callback.from_user.id),
    )
    await callback.answer()


@main_router.message(TaskFlow.waiting_for_custom_location)
async def process_task_custom_location(message: types.Message, state: FSMContext):
    """Legacy: состояние больше не используется. Сбрасываем и показываем меню."""
    await state.clear()
    user_id = message.from_user.id
    lang = get_user_language_or_default(user_id)
    await message.answer(t("tasks.require_location", lang), reply_markup=main_menu_kb(user_id=user_id))


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
    logger.debug(f"🔍 parse_google_maps_link результат: {location_data}")

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

    lang = get_user_language_or_default(message.from_user.id)
    place_default = t("create.place_on_map", lang)
    # Сохраняем данные локации
    await state.update_data(
        location_name=location_data.get("name", place_default),
        location_lat=lat,
        location_lng=lng,
        location_url=location_data["raw_link"],
    )

    # Показываем подтверждение
    location_name = location_data.get("name", place_default)

    # Создаем кнопки подтверждения
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("create.button_open_on_map", lang), url=link)],
            [
                InlineKeyboardButton(text=t("create.button_yes", lang), callback_data="location_confirm"),
                InlineKeyboardButton(text=t("create.button_change", lang), callback_data="location_change"),
            ],
        ]
    )

    # Формируем сообщение в зависимости от наличия координат
    loc_label = t("create.location_label", lang)
    coords_label = t("create.coordinates_label", lang)
    q = t("create.confirm_location_question", lang)
    link_saved = t("create.location_link_saved", lang)
    if lat is not None and lng is not None:
        location_text = f"📍 **{loc_label}** {location_name}\n🌍 {coords_label} {lat:.6f}, {lng:.6f}\n\n{q}"
    else:
        location_text = f"📍 **{loc_label}** {location_name}\n🌍 {link_saved}\n\n{q}"

    await message.answer(
        location_text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# Обработчики подтверждения локации
@main_router.callback_query(F.data == "location_confirm")
async def handle_location_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение локации"""
    lang = get_user_language_or_default(callback.from_user.id)
    await state.set_state(EventCreation.waiting_for_description)
    await callback.message.answer(
        t("create.place_saved_short", lang),
        parse_mode="Markdown",
    )
    await callback.answer()


@main_router.callback_query(F.data == "location_change")
async def handle_location_change(callback: types.CallbackQuery, state: FSMContext):
    """Изменение локации"""
    lang = get_user_language_or_default(callback.from_user.id)
    await state.set_state(EventCreation.waiting_for_location_type)

    # Создаем клавиатуру для выбора типа локации
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("community.location_link", lang), callback_data="location_link")],
            [InlineKeyboardButton(text=t("community.location_map", lang), callback_data="location_map")],
            [InlineKeyboardButton(text=t("community.location_coords", lang), callback_data="location_coords")],
        ]
    )

    lang = get_user_language_or_default(callback.from_user.id)
    await callback.message.answer(t("create.location_prompt", lang), reply_markup=keyboard)
    await callback.answer()


@main_router.message(EventCreation.waiting_for_location)
async def process_location(message: types.Message, state: FSMContext):
    """Шаг 4: Обработка места события"""
    location = message.text.strip()
    logger.info(f"process_location: получили место '{location}' от пользователя {message.from_user.id}")

    # Получаем язык пользователя для i18n
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

    await state.update_data(location=location)
    await state.set_state(EventCreation.waiting_for_description)
    location_text = f"*{location}*"
    await message.answer(
        format_translation("create.location_saved", user_lang, location_text=location_text),
        parse_mode="Markdown",
    )


@main_router.message(EventCreation.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    """Шаг 5: Обработка описания события"""
    description = message.text.strip()
    logger.info(f"process_description: получили описание от пользователя {message.from_user.id}")

    # Получаем язык пользователя для i18n
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

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
        await message.answer(t("create.validation.no_links_in_description", user_lang))
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

    # Показываем итог перед подтверждением (экранируем пользовательский ввод для Markdown)
    safe_title = escape_markdown(data.get("title", "") or "")
    safe_date = escape_markdown(data.get("date", "") or "")
    safe_time = escape_markdown(data.get("time", "") or "")
    safe_description = escape_markdown(data.get("description", "") or "")
    not_spec = t("common.not_specified", user_lang)
    location_text = data.get("location", not_spec)
    if "location_name" in data and data["location_name"]:
        location_text = escape_markdown(data["location_name"])
        if "location_url" in data and data["location_url"]:
            location_text += f"\n🌍 [{t('create.button_open_on_map', user_lang)}]({data['location_url']})"
    else:
        location_text = escape_markdown(location_text if location_text else not_spec)

    await message.answer(
        f"📌 **{t('create.check_event_data', user_lang)}**\n\n"
        f"**{t('create.label_title', user_lang)}** {safe_title}\n"
        f"**{t('create.label_date', user_lang)}** {safe_date}\n"
        f"**{t('create.label_time', user_lang)}** {safe_time}\n"
        f"**{t('create.label_place', user_lang)}** {location_text}\n"
        f"**{t('create.label_description', user_lang)}** {safe_description}\n\n"
        f"{t('create.confirm_instruction', user_lang)}",
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text=t("create.button_save", user_lang), callback_data="event_confirm"),
                    types.InlineKeyboardButton(text=t("common.cancel", user_lang), callback_data="event_cancel"),
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
    lang = get_user_language_or_default(message.from_user.id)
    await message.answer(
        t("create.time_saved_ask_city", lang, time=time),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
        ),
    )


async def handle_community_city_step(message: types.Message, state: FSMContext):
    """Обработка города события"""
    if not message.text:
        lang = get_user_language_or_default(message.from_user.id)
        await message.answer(
            t("create.validation.no_text", lang, next_prompt=t("create.enter_city", lang)),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="group_cancel_create")]]
            ),
        )
        return

    city = message.text.strip()
    await state.update_data(city=city, step="location_name")
    lang = get_user_language_or_default(message.from_user.id)
    await message.answer(
        t("create.city_saved_ask_place", lang, city=city),
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
    lang = get_user_language_or_default(message.from_user.id)

    # Показываем итог перед подтверждением
    await message.answer(
        f"📌 **{t('create.check_event_data', lang)}**\n\n"
        f"**{t('create.label_title', lang)}** {data['title']}\n"
        f"**{t('create.label_date', lang)}** {data['date']}\n"
        f"**{t('create.label_time', lang)}** {data['time']}\n"
        f"**{t('create.label_city', lang)}** {data['city']}\n"
        f"**{t('create.label_place', lang)}** {data['location_name']}\n"
        f"**{t('create.label_link', lang)}** {data['location_url']}\n"
        f"**{t('create.label_description', lang)}** {description}\n\n"
        f"{t('create.confirm_instruction', lang)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=t("create.button_save", lang), callback_data="community_event_confirm"),
                    InlineKeyboardButton(text=t("common.cancel", lang), callback_data="group_cancel_create"),
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

    lang = get_user_language_or_default(message.from_user.id)
    await message.answer(
        t("create.time_saved_ask_city", lang, time=time),
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
    lang = get_user_language_or_default(message.from_user.id)
    logger.info(
        f"🔥 process_community_city_group: получено сообщение от пользователя {message.from_user.id} в чате {message.chat.id}, текст: '{message.text}'"
    )

    # Проверяем, что сообщение содержит текст
    if not message.text:
        await message.answer(
            t("create.validation.no_text", lang, next_prompt=t("create.enter_city", lang)),
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

    lang = get_user_language_or_default(message.from_user.id)
    # Создаем клавиатуру для выбора типа локации (как в World режиме)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("community.location_link", lang), callback_data="community_location_link")],
            [InlineKeyboardButton(text=t("community.location_map", lang), callback_data="community_location_map")],
            [
                InlineKeyboardButton(
                    text=t("community.location_coords", lang), callback_data="community_location_coords"
                )
            ],
            [InlineKeyboardButton(text=t("common.cancel", lang), callback_data="group_cancel_create")],
        ]
    )

    await message.answer(
        format_translation("create.city_saved", lang, city=city),
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
    lang = get_user_language_or_default(message.from_user.id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("community.location_link", lang), callback_data="community_location_link")],
            [InlineKeyboardButton(text=t("community.location_map", lang), callback_data="community_location_map")],
            [
                InlineKeyboardButton(
                    text=t("community.location_coords", lang), callback_data="community_location_coords"
                )
            ],
            [InlineKeyboardButton(text=t("common.cancel", lang), callback_data="group_cancel_create")],
        ]
    )
    await message.answer(
        t("create.location_prompt", lang),
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
    lang = get_user_language_or_default(message.from_user.id)

    # Показываем итог перед подтверждением
    await message.answer(
        f"📌 **{t('create.check_event_data', lang)}**\n\n"
        f"**{t('create.label_title', lang)}** {data['title']}\n"
        f"**{t('create.label_date', lang)}** {data['date']}\n"
        f"**{t('create.label_time', lang)}** {data['time']}\n"
        f"**{t('create.label_city', lang)}** {data['city']}\n"
        f"**{t('create.label_place', lang)}** {data['location_name']}\n"
        f"**{t('create.label_link', lang)}** {data['location_url']}\n"
        f"**{t('create.label_description', lang)}** {data['description']}\n\n"
        f"{t('create.confirm_instruction', lang)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=t("create.button_save", lang), callback_data="community_event_confirm"),
                    InlineKeyboardButton(text=t("common.cancel", lang), callback_data="group_cancel_create"),
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
        user_lang = get_user_language_or_default(user_id)
        await callback.answer(t("create.wait_in_progress", user_lang), show_alert=False)
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

        creator_lang = get_user_language_or_default(callback.from_user.id)
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
            admin_id=admin_id,
            admin_ids=admin_ids,
            creator_lang=creator_lang,
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
    user_lang = get_user_language_or_default(callback.from_user.id)
    logger.info(f"confirm_event: подтверждение создания события от пользователя {callback.from_user.id}")

    # Создаём событие в БД
    with get_session() as session:
        # Сначала создаем пользователя, если его нет (язык по умолчанию из Telegram, чтобы клавиатура не переключалась на русский)
        user = session.get(User, callback.from_user.id)
        if not user:
            tg_lang = (getattr(callback.from_user, "language_code", None) or "").strip().lower()[:2]
            default_lang = "en" if tg_lang == "en" else "ru"
            user = User(
                id=callback.from_user.id,
                username=callback.from_user.username,
                language_code=default_lang,
            )
            session.add(user)
            session.commit()

        # Объединяем дату и время
        logger.debug(f"🔍 DATA: {data}")
        time_local = f"{data['date']} {data['time']}"
        logger.debug(f"🔍 TIME_LOCAL: {time_local}")

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
            logger.debug(f"🔍 TIME_LOCAL_FIXED: {time_local_fixed}")

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

            # Двусторонний перевод RU<->EN: всегда заполняем title/title_en и description/description_en
            bilingual = ensure_bilingual(
                title=data["title"],
                description=data.get("description") or "",
            )
            title_ru = bilingual.get("title") or data["title"]
            description_ru = bilingual.get("description") or data.get("description")
            title_en = bilingual.get("title_en")
            description_en = bilingual.get("description_en")

            # Создаем событие
            event_id = events_service.create_user_event(
                organizer_id=callback.from_user.id,
                title=title_ru,
                description=description_ru,
                starts_at_utc=starts_at,
                city=city,
                lat=lat,
                lng=lng,
                location_name=location_name,
                location_url=location_url,
                max_participants=data.get("max_participants"),
                chat_id=data.get("chat_id"),  # Добавляем chat_id для групповых чатов
                organizer_username=callback.from_user.username,
                title_en=title_en,
                description_en=description_en,
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

    # Формируем структурированное сообщение для поделиться (экранируем пользовательский ввод для Markdown)
    user_lang = get_user_language_or_default(callback.from_user.id)
    safe_title = escape_markdown(data.get("title", "") or "")
    safe_date = escape_markdown(data.get("date", "") or "")
    safe_time = escape_markdown(data.get("time", "") or "")
    safe_location = escape_markdown(location_name or "")
    safe_description = escape_markdown(data.get("description", "") or "")
    creator_name = callback.from_user.username or callback.from_user.first_name or "пользователь"
    safe_creator = escape_markdown(creator_name)

    share_message = f"🎉 **{t('share.new_event', user_lang)}**\n\n"
    share_message += f"**{safe_title}**\n"
    share_message += f"📅 {safe_date} {t('share.time_at', user_lang)} {safe_time}\n"

    # Добавляем место на карте с активной ссылкой (компактно)
    if location_url:
        share_message += f"📍 [{safe_location}]({location_url})\n"
    else:
        share_message += f"📍 {safe_location}\n"

    # Добавляем описание
    if data.get("description"):
        share_message += f"\n📝 {safe_description}\n"

    # Добавляем информацию о создателе (локализованно)
    share_message += "\n*" + format_translation("event.created_by", user_lang, username=safe_creator) + "*\n\n"
    _ub = get_bot_username()
    share_message += f"💡 **{t('share.more_events_in_bot', user_lang)}** [@{_ub}](https://t.me/{_ub})"

    # Отправляем новое сообщение (которое можно переслать) вместо edit_text.
    # Меню по user_id, чтобы язык всегда из БД.
    await callback.message.answer(
        share_message,
        parse_mode="Markdown",
        reply_markup=main_menu_kb(user_id=callback.from_user.id),
    )

    await callback.answer(t("event.created", user_lang))

    # Показываем крутую анимацию после сохранения (тот же язык для клавиатуры)
    await send_spinning_menu(callback.message, lang=user_lang)


@main_router.callback_query(F.data == "event_cancel")
async def cancel_event_creation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания события"""
    user_lang = get_user_language_or_default(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(t("create.cancelled_full", user_lang))
    await callback.answer(t("create.cancelled", user_lang))


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

    lang = get_user_language_or_default(callback.from_user.id if callback.from_user else 0)
    event = events[index]
    header = format_translation("manage_event.header", lang, current=index + 1, total=total) + "\n\n"
    text = f"{header}{format_event_for_display(event, lang)}"

    # Передаем updated_at_utc для проверки времени закрытия, lang для i18n кнопок
    buttons = get_status_change_buttons(event["id"], event["status"], event.get("updated_at_utc"), lang=lang)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
        ]
    )

    # Навигация: при total > 1 — Список | Назад | Вперёд (кольцо); при total == 1 — только Список
    prev_idx = (total - 1) if index == 0 else (index - 1)
    next_idx = 0 if index == total - 1 else (index + 1)
    nav_row = [InlineKeyboardButton(text=t("manage_event.nav.list", lang), callback_data=f"back_to_list_{event['id']}")]
    if total > 1:
        nav_row.extend(
            [
                InlineKeyboardButton(text=t("manage_event.nav.back", lang), callback_data=f"prev_event_{prev_idx}"),
                InlineKeyboardButton(text=t("manage_event.nav.forward", lang), callback_data=f"next_event_{next_idx}"),
            ]
        )
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


@main_router.message(F.text.in_(_MAIN_MENU_BUTTON_TEXTS))
async def on_main_menu_button(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Главное меню' — очищает состояние и показывает меню на языке из БД."""
    await state.clear()
    user_lang = get_user_language_or_default(message.from_user.id)
    await send_spinning_menu(message, lang=user_lang)


@main_router.message(~StateFilter(EventCreation, EventEditing, TaskFlow, CommunityEventCreation, CommunityEventEditing))
async def echo_message(message: types.Message, state: FSMContext):
    """Обработчик всех остальных сообщений (кроме FSM состояний)"""
    # Пропускаем геолокацию - она обрабатывается отдельным обработчиком
    if message.location:
        logger.debug("📍 echo_message: получена геолокация, пропускаем для отдельного обработчика")
        return

    current_state = await state.get_state()
    logger.info(
        f"echo_message: получили сообщение '{message.text}' от пользователя {message.from_user.id}, состояние: {current_state}"
    )
    logger.info("echo_message: отвечаем общим сообщением")
    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)
    await message.answer(
        t("menu.use_buttons", user_lang),
        reply_markup=main_menu_kb(user_id=user_id),
    )


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
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.answer(t("pager.state_lost", user_lang))
            return

        # Проверяем, что фильтр действительно изменился
        current_filter = state.get("date_filter", "today")
        if current_filter == date_type:
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.answer(t("pager.date_already_selected", user_lang))
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
            await callback.answer(
                t("search.location_not_found", get_user_language_or_default(callback.from_user.id)),
                show_alert=True,
            )
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

        # Конвертируем в старый формат для совместимости (с полями _en для мультиязычности)
        formatted_events = []
        for event in events:
            formatted_event = {
                "id": event.get("id"),
                "title": event["title"],
                "title_en": event.get("title_en"),
                "description": event["description"],
                "description_en": event.get("description_en"),
                "time_local": event["starts_at"].strftime("%Y-%m-%d %H:%M") if event["starts_at"] else None,
                "starts_at": event["starts_at"],
                "city": event.get("city"),
                "location_name": event["location_name"],
                "location_name_en": event.get("location_name_en"),
                "location_url": event["location_url"],
                "lat": event["lat"],
                "lng": event["lng"],
                "source": event.get("source", ""),
                "source_type": event.get("source_type", ""),
                "url": event.get("event_url", ""),
                "community_name": "",
                "community_link": "",
                "venue_name": event.get("venue_name"),
                "address": event.get("address"),
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

        # Данные из БД уже с location_name (ingest). Enrich в хендлере не вызываем.
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
        user_lang = get_user_language_or_default(callback.from_user.id)
        if is_first_page and is_photo_message:
            # Формируем заголовок
            header_html = render_header(counts, radius_km=int(radius), lang=user_lang)
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
            logger.debug("🔍 Динамический page_size для первой страницы с картой: %s событий", page_size)
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
            header_html = render_header(counts, radius_km=int(radius), lang=user_lang)
            new_text = header_html + "\n\n" + page_html

        # Создаем клавиатуру с правильным фильтром даты
        combined_keyboard = kb_pager(1, total_pages, current_radius=int(radius), date_filter=date_type, lang=user_lang)

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
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.answer(t("pager.date_switch_failed", user_lang), show_alert=True)
            return

        await callback.answer(f"📅 Показаны события на {date_type}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки переключения даты: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("pager.date_error", user_lang))


@main_router.callback_query(F.data.startswith("pg:"))
async def handle_pagination(callback: types.CallbackQuery):
    """Обработчик пагинации событий"""

    try:
        # Извлекаем номер страницы из callback_data
        token = callback.data.split(":", 1)[1]
        user_lang = get_user_language_or_default(callback.from_user.id)
        if token == "noop":
            await callback.answer(t("pager.page_edge", user_lang))
            return

        page = int(token)

        # Получаем сохраненное состояние
        state = user_state.get(callback.message.chat.id)
        if not state:
            logger.warning(f"Состояние не найдено для пользователя {callback.message.chat.id}")
            await callback.answer(t("pager.state_not_found", user_lang))
            return

        prepared = state["prepared"]
        counts = state["counts"]
        current_radius = state.get("radius", 5)
        date_filter = state.get("date_filter", "today")  # Получаем фильтр даты из состояния

        # Данные из БД уже с location_name (ingest). Enrich в хендлере не вызываем.
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

        # Кольцо: выходим за границы — переходим на противоположный конец
        if page < 1:
            page = total_pages
        elif page > total_pages:
            page = 1

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
        user_lang = get_user_language_or_default(callback.from_user.id)
        combined_keyboard = kb_pager(page, total_pages, current_radius, date_filter=date_filter, lang=user_lang)

        # Обновляем сообщение (проверяем тип сообщения)
        new_text = render_header(counts, radius_km=current_radius, lang=user_lang) + "\n\n" + page_html

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
            await callback.answer(t("pager.page_failed", user_lang), show_alert=True)
            return

        # Обновляем состояние
        state["page"] = page
        user_state[callback.message.chat.id] = state

        await callback.answer()

        # Клавиатура главного меню уже есть у пользователя

    except (ValueError, IndexError) as e:
        logger.error(f"❌ Ошибка обработки пагинации: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("pager.request_error", user_lang))
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в пагинации: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("pager.general_error", user_lang))


@main_router.callback_query(F.data == "loading")
async def handle_loading_button(callback: types.CallbackQuery):
    """Обработчик кнопки загрузки - просто отвечаем, что работаем"""
    user_lang = get_user_language_or_default(callback.from_user.id)
    await callback.answer(t("search.loading_toast", user_lang), show_alert=False)


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
        user_id = callback.from_user.id
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
            reply_markup=main_menu_kb(user_id=user_id),
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике создания события: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("pager.general_error", user_lang))


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
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("pager.use_create", user_lang))

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике начала создания: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("pager.general_error", user_lang))


@main_router.callback_query(F.data == "back_to_search")
async def handle_back_to_search(callback: types.CallbackQuery):
    """Обработчик возврата к поиску"""
    try:
        # Возвращаемся к главному меню
        user_id = callback.from_user.id
        await callback.message.edit_text(
            "🔍 <b>Поиск событий</b>\n\nОтправьте геолокацию, чтобы найти события рядом с вами.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(user_id=user_id),
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике возврата к поиску: {e}")
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.answer(t("pager.general_error", user_lang))


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
        log_memory_stats()  # Логируем начальное состояние памяти
        logger.info(f"🧹 При старте очищено user_state: осталось {len(user_state)} записей")
    except Exception as e:
        logger.error(f"Ошибка при очистке user_state при старте: {e}")

    # Восстанавливаем автоудаление сообщений после перезапуска
    try:
        from utils.messaging_utils import restore_auto_delete_on_startup

        asyncio.create_task(restore_auto_delete_on_startup(bot))
        logger.info("✅ Запущено восстановление автоудаления сообщений после перезапуска")
    except Exception as e:
        logger.error(f"❌ Ошибка при восстановлении автоудаления: {e}")

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
            logger.debug(f"🔍 Текущие команды для групп: {[cmd.command for cmd in current_commands]}")
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
            logger.debug(f"🔍 Текущий Menu Button: {menu_button}")

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
                logger.debug(f"🔍 Проверяем команды для {scope_name}:")

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
            user_lang = get_user_language_or_default(user_id)
            await callback.answer(t("event.completed", user_lang))

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
                user_lang = get_user_language_or_default(user_id)
                await callback.answer(t("event.completed", user_lang))
    else:
        user_lang = get_user_language_or_default(user_id)
        await callback.answer(t("event.complete_error", user_lang))


@main_router.callback_query(F.data.startswith("open_event_"))
async def handle_open_event(callback: types.CallbackQuery):
    """Возобновление мероприятия"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    # Получаем событие для проверки статуса и времени закрытия
    event = get_event_by_id(event_id, user_id)
    if not event:
        user_lang = get_user_language_or_default(user_id)
        await callback.answer(t("event.not_found", user_lang), show_alert=True)
        return

    # Проверяем, что событие закрыто
    if event["status"] != "closed":
        user_lang = get_user_language_or_default(user_id)
        await callback.answer(t("event.not_closed", user_lang), show_alert=True)
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
            user_lang = get_user_language_or_default(user_id)
            await callback.answer(t("event.resumed", user_lang))

            # Получаем список всех событий пользователя (включая закрытые для навигации)
            events = _get_active_user_events(user_id)

            # Находим индекс возобновленного события
            event_index = next((i for i, e in enumerate(events) if e.get("id") == event_id), 0)

            # Используем _show_manage_event для правильного отображения с навигацией
            await _show_manage_event(callback, events, event_index)
        else:
            # Если событие не найдено, показываем первое событие из списка
            events = _get_active_user_events(user_id)
            if events:
                await _show_manage_event(callback, events, 0)
            else:
                user_lang = get_user_language_or_default(user_id)
                await callback.answer(t("event.resumed", user_lang))
    else:
        user_lang = get_user_language_or_default(user_id)
        await callback.answer(t("event.resume_error", user_lang))


@main_router.callback_query(F.data.startswith("share_event_"))
async def handle_share_event(callback: types.CallbackQuery):
    """Поделиться событием - формирует структурированное сообщение для пересылки"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    # Получаем полные данные события
    event = get_event_by_id(event_id, user_id)
    if not event:
        user_lang = get_user_language_or_default(user_id)
        await callback.answer(t("event.not_found", user_lang))
        return

    user_lang = get_user_language_or_default(user_id)
    # Формируем структурированное сообщение (как после создания события)
    share_message = f"🎉 **{t('share.new_event', user_lang)}**\n\n"
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
        share_message += f"📅 {date_str} {t('share.time_at', user_lang)} {time_str}\n"
    else:
        share_message += "📅 Время не указано\n"

    # Добавляем место на карте с активной ссылкой (компактно)
    location_name = event.get("location_name") or "Место не указано"
    location_url = event.get("location_url")
    if location_url:
        share_message += f"📍 [{location_name}]({location_url})\n"
    else:
        share_message += f"📍 {location_name}\n"

    # Добавляем описание (для EN — description_en, иначе description)
    desc = (
        (event.get("description_en") or event.get("description") or "").strip()
        if user_lang == "en"
        else (event.get("description") or "").strip()
    )
    if desc:
        share_message += f"\n📝 {desc}\n"

    # Добавляем информацию о создателе (локализованно)
    creator_name = callback.from_user.username or callback.from_user.first_name or "пользователь"
    safe_creator = escape_markdown(creator_name)
    share_message += "\n*" + format_translation("event.created_by", user_lang, username=safe_creator) + "*\n\n"
    _ub = get_bot_username()
    share_message += f"💡 **{t('share.more_events_in_bot', user_lang)}** [@{_ub}](https://t.me/{_ub})"

    # Отправляем сообщение, которое можно переслать
    await callback.message.answer(
        share_message,
        parse_mode="Markdown",
    )
    await callback.answer(t("event.ready_to_forward", user_lang))


@main_router.callback_query(F.data.startswith("edit_event_"))
async def handle_edit_event(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования события"""
    event_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    # Проверяем, что событие принадлежит пользователю
    events = get_user_events(user_id)
    event_exists = any(event["id"] == event_id for event in events)

    user_lang = get_user_language_or_default(user_id)

    if not event_exists:
        await callback.answer(t("edit.event_not_found", user_lang))
        return

    # Сохраняем ID события в состоянии
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.choosing_field)

    # Показываем меню редактирования
    keyboard = edit_event_keyboard(event_id, user_lang)
    await callback.message.answer(t("edit.header", user_lang), parse_mode="Markdown", reply_markup=keyboard)
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

    user_lang = get_user_language_or_default(user_id)
    await callback.message.answer(t("edit.enter_title", user_lang))
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
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.message.answer(
                format_translation("edit.enter_date_with_current", user_lang, current_date=current_date_str)
            )
        else:
            example_date = get_example_date()
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.message.answer(
                format_translation("edit.enter_date_with_example", user_lang, example_date=example_date)
            )
    except Exception:
        example_date = get_example_date()
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.message.answer(
            format_translation("edit.enter_date_with_example", user_lang, example_date=example_date)
        )

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
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.message.answer(
                format_translation("edit.enter_time_with_current", user_lang, current_time=current_time_str)
            )
        else:
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.message.answer(t("edit.enter_time_with_example", user_lang))
    except Exception:
        user_lang = get_user_language_or_default(callback.from_user.id)
        await callback.message.answer(t("edit.enter_time_with_example", user_lang))

    await callback.answer()


@main_router.callback_query(F.data.regexp(r"^edit_location_\d+$"))
async def handle_edit_location_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования локации - показываем меню выбора типа"""
    event_id = int(callback.data.split("_")[-1])
    lang = get_user_language_or_default(callback.from_user.id)

    # Сохраняем ID события в состоянии
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.waiting_for_location_type)

    # Создаем клавиатуру для выбора типа локации (как при создании)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("community.location_link", lang), callback_data=f"edit_location_link_{event_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("community.location_map", lang), callback_data=f"edit_location_map_{event_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("community.location_coords", lang), callback_data=f"edit_location_coords_{event_id}"
                )
            ],
            [InlineKeyboardButton(text=t("group.button.back", lang), callback_data=f"edit_event_{event_id}")],
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
    lang = get_user_language_or_default(callback.from_user.id)
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.waiting_for_location)
    await callback.message.answer(t("create.paste_google_maps_link", lang))
    await callback.answer()


@main_router.callback_query(F.data.regexp(r"^edit_location_map_\d+$"))
async def handle_edit_location_map_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор поиска на карте для редактирования"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)

    # Создаем кнопку для открытия Google Maps
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("create.button_open_google_maps", get_user_language_or_default(callback.from_user.id)),
                    url="https://www.google.com/maps",
                )
            ]
        ]
    )

    await state.set_state(EventEditing.waiting_for_location)
    lang = get_user_language_or_default(callback.from_user.id)
    await callback.message.answer(t("edit.location_map_prompt", lang), reply_markup=keyboard)
    await callback.answer()


@main_router.callback_query(F.data.regexp(r"^edit_location_coords_\d+$"))
async def handle_edit_location_coords_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор ввода координат для редактирования"""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id)

    await state.set_state(EventEditing.waiting_for_location)
    lang = get_user_language_or_default(callback.from_user.id)
    await callback.message.answer(
        t("edit.location_coords_prompt", lang),
        parse_mode="Markdown",
    )
    await callback.answer()


@main_router.callback_query(F.data.startswith("edit_description_"))
async def handle_edit_description_choice(callback: types.CallbackQuery, state: FSMContext):
    """Выбор редактирования описания"""
    await state.set_state(EventEditing.waiting_for_description)
    user_lang = get_user_language_or_default(callback.from_user.id)
    await callback.message.answer(t("edit.enter_description", user_lang))
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
            user_lang = get_user_language_or_default(callback.from_user.id)
            await callback.answer(t("event.updated", user_lang))
        else:
            # Если событие не найдено в списке активных, получаем его напрямую
            all_events = get_user_events(user_id)
            updated_event = next((event for event in all_events if event["id"] == event_id), None)

            if updated_event:
                user_lang = get_user_language_or_default(callback.from_user.id)
                text = f"**{t('event.updated', user_lang)}**\n\n{format_event_for_display(updated_event, user_lang)}"
                buttons = get_status_change_buttons(
                    updated_event["id"], updated_event["status"], updated_event.get("updated_at_utc"), lang=user_lang
                )
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])] for btn in buttons
                    ]
                )
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
                await callback.answer(t("event.updated", user_lang))
            else:
                user_lang = get_user_language_or_default(callback.from_user.id)
                await callback.answer(t("event.not_found", user_lang))

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

    user_id = message.from_user.id
    user_lang = get_user_language_or_default(user_id)

    if event_id and message.text:
        logging.info(f"handle_title_input: вызываем update_event_field для события {event_id}")
        success = update_event_field(event_id, "title", message.text.strip(), user_id)
        logging.info(f"handle_title_input: результат update_event_field: {success}")

        if success:
            await message.answer(t("edit.title_updated", user_lang))
            keyboard = edit_event_keyboard(event_id, user_lang)
            await message.answer(t("edit.choose_what_to_change", user_lang), reply_markup=keyboard)
            await state.set_state(EventEditing.choosing_field)
        else:
            await message.answer(t("edit.title_update_error", user_lang))
    else:
        await message.answer(t("edit.invalid_title", user_lang))


@main_router.message(EventEditing.waiting_for_date)
async def handle_date_input(message: types.Message, state: FSMContext):
    """Обработка ввода новой даты"""
    data = await state.get_data()
    event_id = data.get("event_id")

    user_lang = get_user_language_or_default(message.from_user.id)

    if event_id and message.text:
        success = update_event_field(event_id, "starts_at", message.text.strip(), message.from_user.id)
        if success:
            await message.answer(t("edit.date_updated", user_lang))
            keyboard = edit_event_keyboard(event_id, user_lang)
            await message.answer(t("edit.choose_what_to_change", user_lang), reply_markup=keyboard)
            await state.set_state(EventEditing.choosing_field)
        else:
            await message.answer(t("edit.date_format_error", user_lang))
    else:
        await message.answer(t("edit.invalid_date", user_lang))


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

            user_lang = get_user_language_or_default(message.from_user.id)
            if success:
                await message.answer(t("edit.time_updated", user_lang))
                keyboard = edit_event_keyboard(event_id, user_lang)
                await message.answer(t("edit.choose_what_to_change", user_lang), reply_markup=keyboard)
                await state.set_state(EventEditing.choosing_field)
            else:
                await message.answer(t("edit.time_format_error", user_lang))
        except Exception:
            user_lang = get_user_language_or_default(message.from_user.id)
            await message.answer(t("edit.time_format_error", user_lang))
    else:
        user_lang = get_user_language_or_default(message.from_user.id)
        await message.answer(t("edit.invalid_time", user_lang))


@main_router.message(EventEditing.waiting_for_location)
async def handle_location_input(message: types.Message, state: FSMContext):
    """Обработка ввода новой локации (ссылка, координаты или текст)"""
    data = await state.get_data()
    event_id = data.get("event_id")

    user_lang = get_user_language_or_default(message.from_user.id)
    if not event_id or not message.text:
        await message.answer(t("edit.invalid_location", user_lang))
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
                    format_translation(
                        "edit.location_updated", user_lang, location=location_data.get("name", "Место на карте")
                    ),
                    parse_mode="Markdown",
                )
            else:
                await message.answer(t("edit.location_update_error", user_lang))
        else:
            await message.answer(t("edit.location_google_maps_error", user_lang))

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

                    await message.answer(
                        format_translation("edit.location_updated", user_lang, location=f"{lat:.6f}, {lng:.6f}"),
                        parse_mode="Markdown",
                    )
                else:
                    await message.answer(t("edit.location_update_error", user_lang))
            else:
                await message.answer(t("edit.coords_out_of_range", user_lang))
        except ValueError:
            await message.answer(t("edit.coords_format", user_lang))

    else:
        # Обычный текст - обновляем только название
        success = update_event_field(event_id, "location_name", location_input, message.from_user.id)
        if success:
            await message.answer(
                format_translation("edit.location_updated", user_lang, location=location_input), parse_mode="Markdown"
            )
        else:
            await message.answer(t("edit.location_update_error", user_lang))

    # Возвращаемся к меню редактирования
    keyboard = edit_event_keyboard(event_id, user_lang)
    await message.answer(t("edit.choose_what_to_change", user_lang), reply_markup=keyboard)
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

    user_lang = get_user_language_or_default(message.from_user.id)

    if event_id and description:
        success = update_event_field(event_id, "description", description, message.from_user.id)
        if success:
            await message.answer(t("edit.description_updated", user_lang))
            keyboard = edit_event_keyboard(event_id, user_lang)
            await message.answer(t("edit.choose_what_to_change", user_lang), reply_markup=keyboard)
            await state.set_state(EventEditing.choosing_field)
        else:
            await message.answer(t("edit.description_update_error", user_lang))
    else:
        await message.answer(t("edit.invalid_description", user_lang))


@main_router.callback_query(F.data.startswith("next_event_"))
async def handle_next_event(callback: types.CallbackQuery):
    """Переход к следующему событию (кольцо: с последней — на первую)"""
    user_id = callback.from_user.id
    target_index = _extract_index(callback.data, prefix="next_event_")
    active_events = _get_active_user_events(user_id)
    total = len(active_events)

    if target_index is None or total == 0:
        await callback.answer()
        return
    # Кольцо: выходим за границы — переходим на другой конец
    if target_index >= total:
        target_index = 0
    elif target_index < 0:
        target_index = total - 1

    await _show_manage_event(callback, active_events, target_index)
    await callback.answer()


@main_router.callback_query(F.data.startswith("back_to_main_"))
async def handle_back_to_main(callback: types.CallbackQuery):
    """Возврат в главное меню (старый обработчик для совместимости)"""
    user_lang = get_user_language_or_default(callback.from_user.id)
    await callback.answer(t("carousel.back_to_menu", user_lang))
    await send_spinning_menu(callback.message, lang=user_lang)


@main_router.callback_query(F.data.startswith("back_to_list_"))
async def handle_back_to_list(callback: types.CallbackQuery):
    """Возврат к списку событий"""
    user_id = callback.from_user.id
    user_lang = get_user_language_or_default(user_id)
    await callback.answer(t("carousel.back_to_list", user_lang))

    # Автомодерация: закрываем прошедшие события
    closed_count = auto_close_events()
    if closed_count > 0:
        await callback.message.answer(format_translation("myevents.auto_closed", user_lang, count=closed_count))

    # Получаем события пользователя
    events = get_user_events(user_id)

    # Получаем баланс ракет пользователя
    from rockets_service import get_user_rockets

    rocket_balance = get_user_rockets(user_id)

    # Формируем текст сообщения
    text_parts = [
        t("myevents.header", user_lang),
        format_translation("myevents.balance", user_lang, rocket_balance=rocket_balance),
    ]

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
            text_parts.append(t("myevents.created_by_me", user_lang))
            for i, event in enumerate(active_events[:3], 1):
                title = event.get("title", t("common.title_not_specified", user_lang))
                location = event.get("location_name", t("common.location_tba", user_lang))
                starts_at = event.get("starts_at")

                if starts_at:
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = t("common.time_tba", user_lang)

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
                text_parts.append(format_translation("myevents.and_more", user_lang, count=len(active_events) - 3))

        # Показываем недавно закрытые события
        if recent_closed_events:
            text_parts.append(
                format_translation("myevents.recently_closed", user_lang, count=len(recent_closed_events))
            )
            for i, event in enumerate(recent_closed_events[:3], 1):
                title = event.get("title", t("common.title_not_specified", user_lang))
                location = event.get("location_name", t("common.location_tba", user_lang))
                starts_at = event.get("starts_at")

                if starts_at:
                    local_time = starts_at.astimezone(tz_bali)
                    time_str = local_time.strftime("%d.%m.%Y %H:%M")
                else:
                    time_str = t("common.time_tba", user_lang)

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

                text_parts.append(
                    f"{i}) {escaped_title}\n🕐 {time_str}\n📍 {escaped_location} {t('common.closed', user_lang)}\n"
                )

            if len(recent_closed_events) > 3:
                text_parts.append(
                    format_translation("myevents.and_more_closed", user_lang, count=len(recent_closed_events) - 3)
                )

    # Если нет событий вообще
    if not events:
        text_parts = [
            t("myevents.header", user_lang),
            t("myevents.no_events", user_lang) + "\n",
            format_translation("myevents.balance", user_lang, rocket_balance=rocket_balance),
        ]

    text = "\n".join(text_parts)

    # Создаем клавиатуру
    keyboard_buttons = []

    if events:
        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text=t("myevents.button.manage_events", user_lang),
                    callback_data="manage_events",
                )
            ]
        )

    keyboard = (
        InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else main_menu_kb(user_id=user_id)
    )

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
    """Возврат к предыдущему событию (кольцо: с первой — на последнюю)"""
    user_id = callback.from_user.id
    target_index = _extract_index(callback.data, prefix="prev_event_")
    active_events = _get_active_user_events(user_id)
    total = len(active_events)

    if target_index is None or total == 0:
        await callback.answer()
        return
    # Кольцо: выходим за границы — переходим на другой конец
    if target_index < 0:
        target_index = total - 1
    elif target_index >= total:
        target_index = 0

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
