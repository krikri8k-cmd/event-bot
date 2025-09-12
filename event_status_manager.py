#!/usr/bin/env python3
"""
Менеджер статусов событий для бота
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text

from database import Event, get_session, init_engine

logger = logging.getLogger(__name__)

# Валидные статусы событий
VALID_STATUSES = ["open", "closed", "canceled", "active", "draft"]

# Эмодзи для статусов
STATUS_EMOJIS = {"open": "🟢", "closed": "🔴", "canceled": "🚫", "active": "🟡", "draft": "📝"}

# Описания статусов
STATUS_DESCRIPTIONS = {
    "open": "Активно",
    "closed": "Завершено",
    "canceled": "Отменено",
    "active": "Активно (legacy)",
    "draft": "Черновик",
}


def get_status_emoji(status: str) -> str:
    """Возвращает эмодзи для статуса"""
    return STATUS_EMOJIS.get(status, "❓")


def get_status_description(status: str) -> str:
    """Возвращает описание статуса"""
    return STATUS_DESCRIPTIONS.get(status, "Неизвестно")


def is_valid_status(status: str) -> bool:
    """Проверяет, является ли статус валидным"""
    return status in VALID_STATUSES


def auto_close_events() -> int:
    """
    Автоматически закрывает события, которые прошли
    Возвращает количество закрытых событий
    """
    try:
        with get_session() as session:
            result = session.execute(text("SELECT auto_close_events()")).scalar()
            logger.info(f"Автомодерация: закрыто {result} событий")
            return result or 0
    except Exception as e:
        logger.error(f"Ошибка автомодерации: {e}")
        return 0


def change_event_status(event_id: int, new_status: str, user_id: int) -> bool:
    """
    Изменяет статус события
    Возвращает True, если изменение успешно
    """
    if not is_valid_status(new_status):
        logger.error(f"Невалидный статус: {new_status}")
        return False

    try:
        with get_session() as session:
            # Проверяем, что событие принадлежит пользователю
            event = session.query(Event).filter(Event.id == event_id, Event.organizer_id == user_id).first()

            if not event:
                logger.warning(f"Событие {event_id} не найдено или не принадлежит пользователю {user_id}")
                return False

            old_status = event.status
            event.status = new_status
            event.updated_at_utc = datetime.now(UTC)

            session.commit()
            logger.info(f"Статус события {event_id} изменен с '{old_status}' на '{new_status}'")
            return True

    except Exception as e:
        logger.error(f"Ошибка изменения статуса события {event_id}: {e}")
        return False


def get_user_events(user_id: int, status_filter: str | None = None) -> list[dict[str, Any]]:
    """
    Получает события пользователя с возможной фильтрацией по статусу
    """
    try:
        # Инициализируем engine если нужно
        load_dotenv("app.local.env")
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            init_engine(database_url)

        with get_session() as session:
            # Используем SQL запрос для совместимости
            if status_filter and is_valid_status(status_filter):
                query = text("""
                    SELECT id, title, description, status, starts_at, location_name,
                           created_at_utc, updated_at_utc
                    FROM events
                    WHERE organizer_id = :user_id AND status = :status
                    ORDER BY created_at_utc DESC
                """)
                result = session.execute(query, {"user_id": user_id, "status": status_filter})
            else:
                query = text("""
                    SELECT id, title, description, status, starts_at, location_name,
                           created_at_utc, updated_at_utc
                    FROM events
                    WHERE organizer_id = :user_id
                    ORDER BY created_at_utc DESC
                """)
                result = session.execute(query, {"user_id": user_id})

            events = result.fetchall()

            result_list = []
            for event in events:
                result_list.append(
                    {
                        "id": event.id,
                        "title": event.title,
                        "description": event.description,
                        "status": event.status,
                        "status_emoji": get_status_emoji(event.status),
                        "status_description": get_status_description(event.status),
                        "starts_at": event.starts_at,
                        "location_name": event.location_name,
                        "created_at_utc": event.created_at_utc,
                        "updated_at_utc": event.updated_at_utc,
                    }
                )

            return result_list

    except Exception as e:
        logger.error(f"Ошибка получения событий пользователя {user_id}: {e}")
        import traceback

        traceback.print_exc()
        return []


def get_event_by_id(event_id: int, user_id: int) -> dict[str, Any] | None:
    """
    Получает конкретное событие пользователя
    """
    try:
        with get_session() as session:
            query = text("""
                SELECT id, title, description, status, starts_at, location_name,
                       created_at_utc, updated_at_utc
                FROM events
                WHERE id = :event_id AND organizer_id = :user_id
            """)
            result = session.execute(query, {"event_id": event_id, "user_id": user_id})
            event = result.fetchone()

            if not event:
                return None

            return {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "status": event.status,
                "status_emoji": get_status_emoji(event.status),
                "status_description": get_status_description(event.status),
                "starts_at": event.starts_at,
                "location_name": event.location_name,
                "created_at_utc": event.created_at_utc,
                "updated_at_utc": event.updated_at_utc,
            }

    except Exception as e:
        logger.error(f"Ошибка получения события {event_id}: {e}")
        return None


def format_event_for_display(event: dict[str, Any]) -> str:
    """
    Форматирует событие для отображения в Telegram
    """
    lines = []

    # Заголовок с эмодзи статуса
    lines.append(f"{event['status_emoji']} **{event['title']}**")

    # Время
    if event["starts_at"]:
        time_str = event["starts_at"].strftime("%d.%m.%Y | %H:%M")
        lines.append(f"📅 {time_str}")
    else:
        lines.append("📅 Время не указано")

    # Место
    if event["location_name"]:
        lines.append(f"📍 {event['location_name']}")

    # Статус
    lines.append(f"📊 Статус: {event['status_description']}")

    # Описание (если есть)
    if event["description"]:
        desc = event["description"][:100] + "..." if len(event["description"]) > 100 else event["description"]
        lines.append(f"📄 {desc}")

    return "\n".join(lines)


def get_status_change_buttons(event_id: int, current_status: str) -> list[dict[str, str]]:
    """
    Возвращает кнопки для изменения статуса события
    """
    buttons = []

    # Кнопки в зависимости от текущего статуса
    if current_status == "open":
        buttons.extend(
            [
                {"text": "❌ Закрыть", "callback_data": f"close_event_{event_id}"},
                {"text": "🚫 Отменить", "callback_data": f"cancel_event_{event_id}"},
            ]
        )
    elif current_status == "closed":
        buttons.extend(
            [
                {"text": "✅ Открыть", "callback_data": f"open_event_{event_id}"},
                {"text": "🚫 Отменить", "callback_data": f"cancel_event_{event_id}"},
            ]
        )
    elif current_status == "canceled":
        buttons.extend(
            [
                {"text": "✅ Открыть", "callback_data": f"open_event_{event_id}"},
                {"text": "❌ Закрыть", "callback_data": f"close_event_{event_id}"},
            ]
        )

    # Кнопка редактирования (всегда доступна)
    buttons.append({"text": "✏ Редактировать", "callback_data": f"edit_event_{event_id}"})

    return buttons


def get_events_statistics(user_id: int) -> dict[str, int]:
    """
    Получает статистику событий пользователя
    """
    try:
        with get_session() as session:
            stats = {}

            for status in VALID_STATUSES:
                query = text("""
                    SELECT COUNT(*)
                    FROM events
                    WHERE organizer_id = :user_id AND status = :status
                """)
                result = session.execute(query, {"user_id": user_id, "status": status})
                count = result.scalar() or 0
                stats[status] = count

            return stats

    except Exception as e:
        logger.error(f"Ошибка получения статистики пользователя {user_id}: {e}")
        return {status: 0 for status in VALID_STATUSES}
