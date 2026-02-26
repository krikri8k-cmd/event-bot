#!/usr/bin/env python3
"""
Простой менеджер статусов событий
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Загружаем переменные окружения
load_dotenv("app.local.env")

# Создаем engine
database_url = os.getenv("DATABASE_URL")
engine = create_engine(database_url)

# Валидные статусы событий
VALID_STATUSES = ["open", "closed", "canceled"]

# Эмодзи для статусов
STATUS_EMOJIS = {"open": "🟢", "closed": "🔴", "canceled": "🚫"}

# Описания статусов
STATUS_DESCRIPTIONS = {"open": "Активно", "closed": "Завершено", "canceled": "Отменено"}


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
    """Автоматически закрывает события, которые прошли"""
    try:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT auto_close_events()")).scalar()
            return result or 0
    except Exception as e:
        print(f"Ошибка автомодерации: {e}")
        return 0


def change_event_status(event_id: int, new_status: str, user_id: int) -> bool:
    """Изменяет статус события"""
    if not is_valid_status(new_status):
        print(f"Невалидный статус: {new_status}")
        return False

    try:
        with engine.begin() as conn:
            # Проверяем, что событие принадлежит пользователю
            result = conn.execute(
                text("""
                SELECT id FROM events
                WHERE id = :event_id AND organizer_id = :user_id
            """),
                {"event_id": event_id, "user_id": user_id},
            )

            if not result.fetchone():
                print(f"Событие {event_id} не найдено или не принадлежит пользователю {user_id}")
                return False

            # Обновляем статус
            conn.execute(
                text("""
                UPDATE events
                SET status = :new_status, updated_at_utc = NOW()
                WHERE id = :event_id
            """),
                {"new_status": new_status, "event_id": event_id},
            )

            print(f"Статус события {event_id} изменен на '{new_status}'")

        # Синхронизация с Community: если событие из community — обновить статус и там
        from database import get_session
        from utils.sync_community_world_events import sync_world_event_to_community

        sync_world_event_to_community(event_id, get_session)
        return True

    except Exception as e:
        print(f"Ошибка изменения статуса события {event_id}: {e}")
        return False


def get_user_events(user_id: int, status_filter: str = None):
    """Получает события пользователя"""
    try:
        with engine.connect() as conn:
            if status_filter and is_valid_status(status_filter):
                query = text("""
                    SELECT id, title, description, status, starts_at, location_name,
                           created_at_utc, updated_at_utc
                    FROM events
                    WHERE organizer_id = :user_id AND status = :status
                    ORDER BY created_at_utc DESC
                """)
                result = conn.execute(query, {"user_id": user_id, "status": status_filter})
            else:
                query = text("""
                    SELECT id, title, description, status, starts_at, location_name,
                           created_at_utc, updated_at_utc
                    FROM events
                    WHERE organizer_id = :user_id
                    ORDER BY created_at_utc DESC
                """)
                result = conn.execute(query, {"user_id": user_id})

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
        print(f"Ошибка получения событий пользователя {user_id}: {e}")
        return []


def get_event_by_id(event_id: int, user_id: int):
    """Получает конкретное событие пользователя"""
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT id, title, description, status, starts_at, location_name, location_url,
                       organizer_id, created_at_utc, updated_at_utc
                FROM events
                WHERE id = :event_id AND organizer_id = :user_id
            """)
            result = conn.execute(query, {"event_id": event_id, "user_id": user_id})
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
                "location_url": event.location_url,
                "organizer_id": event.organizer_id,
                "created_at_utc": event.created_at_utc,
                "updated_at_utc": event.updated_at_utc,
            }

    except Exception as e:
        print(f"Ошибка получения события {event_id}: {e}")
        return None


def get_events_statistics(user_id: int):
    """Получает статистику событий пользователя"""
    try:
        with engine.connect() as conn:
            stats = {}

            for status in VALID_STATUSES:
                query = text("""
                    SELECT COUNT(*)
                    FROM events
                    WHERE organizer_id = :user_id AND status = :status
                """)
                result = conn.execute(query, {"user_id": user_id, "status": status})
                count = result.scalar() or 0
                stats[status] = count

            return stats

    except Exception as e:
        print(f"Ошибка получения статистики пользователя {user_id}: {e}")
        return {status: 0 for status in VALID_STATUSES}


def format_event_for_display(event, lang: str | None = None):
    """Форматирует событие для отображения в Telegram. Если передан lang, строки переводятся через i18n."""
    from utils.i18n import t

    lines = []

    # Заголовок с эмодзи статуса
    lines.append(f"{event['status_emoji']} **{event['title']}**")

    # Время (конвертируем в часовой пояс пользователя)
    if event["starts_at"]:
        import pytz

        from database import User, get_session

        # Получаем часовой пояс пользователя из БД
        user_tz = "Asia/Makassar"  # По умолчанию Бали
        try:
            with get_session() as session:
                user = session.get(User, event.get("organizer_id"))
                if user and user.user_tz:
                    user_tz = user.user_tz
        except Exception:
            pass  # Используем значение по умолчанию

        # Конвертируем UTC в часовой пояс пользователя
        tz = pytz.timezone(user_tz)
        local_time = event["starts_at"].astimezone(tz)
        time_str = local_time.strftime("%d.%m.%Y | %H:%M")
        lines.append(f"📅 {time_str}")
    else:
        time_tba = t("manage_event.time_tba", lang) if lang else "Время не указано"
        lines.append(f"📅 {time_tba}")

    # Место
    if event["location_name"]:
        lines.append(f"📍 {event['location_name']}")

    # Статус
    if lang:
        status_key = (
            f"manage_event.status.{event['status']}"
            if event["status"] in VALID_STATUSES
            else "manage_event.status.unknown"
        )
        status_desc = t(status_key, lang)
        status_label = t("manage_event.status_label", lang)
        lines.append(f"{status_label} {status_desc}")
    else:
        lines.append(f"📊 Статус: {event['status_description']}")

    # Описание (если есть)
    if event["description"]:
        desc = event["description"][:100] + "..." if len(event["description"]) > 100 else event["description"]
        lines.append(f"📄 {desc}")

    return "\n".join(lines)


def get_status_change_buttons(event_id: int, current_status: str, updated_at_utc=None, lang: str | None = None):
    """Возвращает кнопки для изменения статуса события. Если передан lang, подписи кнопок через i18n."""
    from datetime import UTC, datetime, timedelta

    from utils.i18n import t

    def _text(key: str) -> str:
        return t(key, lang) if lang else _default_text(key)

    def _default_text(key: str) -> str:
        defaults = {
            "manage_event.button.finish_event": "⛔ Завершить мероприятие",
            "manage_event.button.resume": "🔄 Возобновить мероприятие",
            "manage_event.button.edit": "✏ Редактировать",
            "manage_event.button.share": "🔗 Поделиться",
        }
        return defaults.get(key, key)

    buttons = []

    # Кнопки в зависимости от текущего статуса
    if current_status == "open":
        buttons.append({"text": _text("manage_event.button.finish_event"), "callback_data": f"close_event_{event_id}"})
    elif current_status == "closed":
        # Показываем кнопку "Возобновить" только если событие закрыто менее 24 часов назад
        can_resume = True
        if updated_at_utc:
            day_ago = datetime.now(UTC) - timedelta(hours=24)
            # Если updated_at_utc это datetime без timezone, добавляем UTC
            if updated_at_utc.tzinfo is None:
                updated_at_utc_tz = updated_at_utc.replace(tzinfo=UTC)
            else:
                updated_at_utc_tz = updated_at_utc
            if updated_at_utc_tz < day_ago:
                can_resume = False

        if can_resume:
            buttons.append({"text": _text("manage_event.button.resume"), "callback_data": f"open_event_{event_id}"})
    elif current_status == "canceled":
        # Для отмененных событий показываем только возобновление
        buttons.append({"text": _text("manage_event.button.resume"), "callback_data": f"open_event_{event_id}"})

    # Кнопка редактирования (всегда доступна)
    buttons.append({"text": _text("manage_event.button.edit"), "callback_data": f"edit_event_{event_id}"})

    # Кнопка поделиться событием
    buttons.append({"text": _text("manage_event.button.share"), "callback_data": f"share_event_{event_id}"})

    return buttons
