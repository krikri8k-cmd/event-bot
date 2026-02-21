#!/usr/bin/env python3
"""
Сервис для работы с заданиями "Цели на районе"
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_

from database import User, UserTask, get_session

logger = logging.getLogger(__name__)


def create_task_from_place(
    user_id: int, place_id: int, user_lat: float = None, user_lng: float = None
) -> tuple[bool, str]:
    """
    Создает задание на основе места (добавляет место в квесты)

    Args:
        user_id: ID пользователя
        place_id: ID места из task_places
        user_lat: Широта пользователя (для определения часового пояса)
        user_lng: Долгота пользователя (для определения часового пояса)

    Returns:
        True если задание создано успешно
    """
    try:
        from database import TaskPlace

        with get_session() as session:
            # Получаем место
            place = session.query(TaskPlace).filter(TaskPlace.id == place_id).first()

            if not place:
                logger.error(f"Место {place_id} не найдено")
                return False, "❌ Место не найдено"

            # Проверяем, что у пользователя нет активного задания для этого места
            # Проверяем напрямую по place_id в UserTask - это самый надежный способ
            existing_task = (
                session.query(UserTask)
                .filter(
                    and_(
                        UserTask.user_id == user_id,
                        UserTask.place_id == place.id,
                        UserTask.status == "active",
                    )
                )
                .first()
            )

            if existing_task:
                logger.warning(f"Пользователь {user_id} уже имеет активное задание для места {place_id} ({place.name})")
                return False, f"⚠️ Квест для места '{place.name}' уже добавлен в Мои квесты"

            if place.task_hint:
                logger.info(f"✅ GPT-задание для места {place.id} ({place.name}): task_id NULL")

            # Определяем часовой пояс пользователя
            if user_lat is not None and user_lng is not None:
                from zoneinfo import ZoneInfo

                from utils.simple_timezone import get_city_from_coordinates, get_city_timezone

                city = get_city_from_coordinates(user_lat, user_lng)
                if city:
                    tz_name = get_city_timezone(city)
                    user_tz = ZoneInfo(tz_name)
                else:
                    user_tz = ZoneInfo("UTC")

                accepted_at_local = datetime.now(user_tz)
                accepted_at = accepted_at_local.astimezone(UTC)
            else:
                accepted_at = datetime.now(UTC)

            # Устанавливаем очень большое время истечения (10 лет) - ограничение по времени отключено
            expires_at = accepted_at + timedelta(days=3650)

            # Frozen данные: task_hint или default (таблица tasks не используется)
            if place.task_hint:
                frozen_title = place.task_hint
                frozen_description = place.task_hint
                frozen_task_hint = place.task_hint
                logger.info(
                    f"✅ Используем GPT task_hint из места {place.id} ({place.name}): " f"'{place.task_hint[:50]}...'"
                )
            else:
                frozen_title = f"Посети {place.name}"
                frozen_description = "Посети это место и сделай фото"
                frozen_task_hint = None
                logger.info(f"✅ Default текст для места {place.id} ({place.name})")

            # Создаем UserTask с информацией о конкретном месте и замороженными данными
            # task_id может быть NULL для GPT-генерированных заданий
            user_task_kwargs = {
                "user_id": user_id,
                "status": "active",
                "accepted_at": accepted_at,
                "expires_at": expires_at,
                "place_id": place.id,
                "place_name": place.name,
                "place_url": place.google_maps_url,
                "promo_code": place.promo_code,
            }

            # Добавляем замороженные данные
            # ВАЖНО: Требуется применение миграции 035
            user_task_kwargs.update(
                {
                    "frozen_title": frozen_title,
                    "frozen_description": frozen_description,
                    "frozen_task_hint": frozen_task_hint,
                    "frozen_category": place.category,
                }
            )
            logger.debug(f"✅ Добавлены замороженные данные для места {place.id}")

            user_task = UserTask(**user_task_kwargs)

            # НЕ сохраняем location_url в Task, так как одно задание может быть для разных мест
            # Информация о месте хранится в UserTask.place_url

            session.add(user_task)

            # Обновляем счетчик принятых заданий
            user = session.get(User, user_id)
            if user:
                user.tasks_accepted_total = (user.tasks_accepted_total or 0) + 1

            session.commit()

            logger.info(f"Пользователь {user_id} добавил место {place_id} ({place.name}) в квесты")
            return True, f"✅ Квест для места '{place.name}' добавлен в Мои квесты"

    except Exception as e:
        logger.error(
            f"Ошибка создания задания из места {place_id} для пользователя {user_id}: {e}",
            exc_info=True,
        )
        # Возвращаем более информативное сообщение об ошибке
        # Если это ошибка валидации или дубликата, возвращаем соответствующее сообщение
        error_str = str(e).lower()
        if "already" in error_str or "duplicate" in error_str or "уже" in error_str:
            return False, "🙈 Квест уже добавлен"
        else:
            return False, f"❌ Ошибка при добавлении квеста: {str(e)[:50]}"


def get_user_active_tasks(user_id: int) -> list[dict]:
    """
    Получает активные задания пользователя с конвертацией времени в местный часовой пояс

    Args:
        user_id: ID пользователя

    Returns:
        Список активных заданий с информацией (время в местном часовом поясе)
    """
    # Помечаем все просроченные задания как истекшие
    mark_tasks_as_expired()

    with get_session() as session:
        # Получаем пользователя для определения часового пояса
        user = session.get(User, user_id)

        # Определяем часовой пояс пользователя
        user_tz = None
        if user and user.last_lat is not None and user.last_lng is not None:
            try:
                from zoneinfo import ZoneInfo

                from utils.simple_timezone import get_city_from_coordinates, get_city_timezone

                city = get_city_from_coordinates(user.last_lat, user.last_lng)
                if city:
                    tz_name = get_city_timezone(city)
                    user_tz = ZoneInfo(tz_name)
                    logger.info(f"Пользователь {user_id} в городе {city} (часовой пояс {tz_name})")
                else:
                    # Если город не определен, используем UTC
                    user_tz = ZoneInfo("UTC")
                    logger.info(f"Пользователь {user_id}: город не определен, используем UTC")
            except Exception as e:
                logger.warning(f"Не удалось определить часовой пояс для пользователя {user_id}: {e}")

        user_tasks_rows = (
            session.query(UserTask).filter(and_(UserTask.user_id == user_id, UserTask.status == "active")).all()
        )

        result = []
        for user_task in user_tasks_rows:
            accepted_at = user_task.accepted_at
            expires_at = user_task.expires_at

            if user_tz is not None:
                if accepted_at.tzinfo is None:
                    accepted_at = accepted_at.replace(tzinfo=UTC)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                accepted_at = accepted_at.astimezone(user_tz)
                expires_at = expires_at.astimezone(user_tz)

            has_frozen_fields = (
                user_task.frozen_title is not None
                and user_task.frozen_description is not None
                and user_task.frozen_title
                and user_task.frozen_description
            )

            if has_frozen_fields:
                task_title = user_task.frozen_title
                task_description = user_task.frozen_description
                task_category = user_task.frozen_category
                task_hint = user_task.frozen_task_hint
            else:
                task_title = user_task.place_name or "Задание"
                task_description = f"Посети {user_task.place_name or 'это место'} и сделай фото"
                task_category = user_task.frozen_category
                task_hint = None

            task_type_from_place = None
            if user_task.place_id:
                from database import TaskPlace

                place = session.query(TaskPlace).filter(TaskPlace.id == user_task.place_id).first()
                if place:
                    task_type_from_place = getattr(place, "task_type", None)

            task_dict = {
                "id": user_task.id,
                "title": task_title,
                "description": task_description,
                "category": task_category,
                "location_url": user_task.place_url,
                "accepted_at": accepted_at,
                "expires_at": expires_at,
                "status": user_task.status,
                "task_type": task_type_from_place,
                "task_hint": task_hint,
            }

            # Получаем информацию о месте и промокоде
            # ПРИОРИТЕТ 1: Если у UserTask уже есть place_id, загружаем место из базы
            if user_task.place_id:
                from database import TaskPlace

                place_from_db = session.query(TaskPlace).filter(TaskPlace.id == user_task.place_id).first()
                if place_from_db:
                    # Используем место из базы (самый надежный источник)
                    task_dict["place_name"] = place_from_db.name
                    task_dict["place_url"] = place_from_db.google_maps_url
                    task_dict["promo_code"] = place_from_db.promo_code
                    # Английский текст задания для экрана «Мои квесты» (fallback на task_hint/ru)
                    hint_en = getattr(place_from_db, "task_hint_en", None)
                    if hint_en and str(hint_en).strip():
                        task_dict["title_en"] = hint_en
                    else:
                        task_dict["title_en"] = place_from_db.task_hint or task_dict["title"]
                    task_dict["place_name_en"] = getattr(place_from_db, "name_en", None) or place_from_db.name

                    # Обновляем поля в UserTask, если они отсутствуют или изменились
                    if not user_task.place_name or user_task.place_name != place_from_db.name:
                        user_task.place_name = place_from_db.name
                    if not user_task.place_url or user_task.place_url != place_from_db.google_maps_url:
                        user_task.place_url = place_from_db.google_maps_url
                    if place_from_db.promo_code and user_task.promo_code != place_from_db.promo_code:
                        user_task.promo_code = place_from_db.promo_code
                    session.commit()

                    # Вычисляем расстояние, если есть координаты пользователя
                    if user and user.last_lat is not None and user.last_lng is not None:
                        from utils.radius_calc import haversine_distance

                        distance = haversine_distance(
                            user.last_lat,
                            user.last_lng,
                            place_from_db.lat,
                            place_from_db.lng,
                        )
                        task_dict["distance_km"] = round(distance, 1)
                    logger.debug(
                        f"✅ Используем место из базы для UserTask {user_task.id}: "
                        f"{place_from_db.name} (ID: {user_task.place_id})"
                    )
                else:
                    # Место удалено из базы, но есть place_id - очищаем его
                    logger.warning(
                        f"⚠️ Место {user_task.place_id} не найдено в базе для UserTask {user_task.id}, очищаем place_id"
                    )
                    user_task.place_id = None
                    user_task.place_name = None
                    user_task.place_url = None
                    user_task.promo_code = None
                    session.commit()
            # ПРИОРИТЕТ 2: Если есть place_name и place_url, но нет place_id (старые данные)
            elif user_task.place_name and user_task.place_url:
                task_dict["place_name"] = user_task.place_name
                task_dict["place_url"] = user_task.place_url
                if user_task.promo_code:
                    task_dict["promo_code"] = user_task.promo_code
                logger.debug(
                    f"✅ Используем место из UserTask (без place_id) для UserTask {user_task.id}: "
                    f"{user_task.place_name}"
                )
            # ПРИОРИТЕТ 3: Если есть координаты пользователя, но нет места - НЕ ИЩЕМ ДИНАМИЧЕСКИ
            # По рекомендации: задание должно быть зафиксировано при создании
            # Если места нет - показываем задание без места
            elif user and user.last_lat is not None and user.last_lng is not None:
                try:
                    from tasks_location_service import (
                        find_nearest_available_place,
                        generate_search_query_url,
                        get_user_region,
                        get_user_region_type,
                    )

                    # Определяем регион пользователя
                    region = get_user_region(user.last_lat, user.last_lng)
                    region_type = get_user_region_type(user.last_lat, user.last_lng)

                    task_type = task_type_from_place or "urban"
                    logger.info(
                        f"Поиск места для UserTask {user_task.id}: category={task_category}, "
                        f"task_type={task_type}, region={region}, region_type={region_type}, user_id={user_id}"
                    )

                    if region == "unknown":
                        logger.info(f"Регион unknown: используем поисковые запросы для UserTask {user_task.id}")

                        if user_task.place_url:
                            task_dict["place_url"] = user_task.place_url
                            if "?q=" in user_task.place_url:
                                # Извлекаем запрос из URL
                                from urllib.parse import parse_qs, urlparse

                                parsed = urlparse(user_task.place_url)
                                query_params = parse_qs(parsed.query)
                                query = query_params.get("query", ["Место на карте"])[0]
                                task_dict["place_name"] = query
                            else:
                                task_dict["place_name"] = "Место на карте"
                        else:
                            # Генерируем поисковый запрос на основе типа места
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
                            place_types = category_place_types.get(task_category, ["park"])
                            place_type = place_types[0]  # Берем первый тип места

                            search_url = generate_search_query_url(
                                place_type=place_type,
                                user_lat=user.last_lat,
                                user_lng=user.last_lng,
                                region_type=region_type,
                            )
                            task_dict["place_url"] = search_url
                            task_dict["place_name"] = "Ближайшее место"
                    else:
                        if user_task.place_url:
                            task_dict["place_url"] = user_task.place_url
                            from database import TaskPlace

                            place_from_db = (
                                session.query(TaskPlace)
                                .filter(TaskPlace.google_maps_url == user_task.place_url)
                                .first()
                            )
                            if place_from_db:
                                task_dict["place_name"] = place_from_db.name
                                task_dict["promo_code"] = place_from_db.promo_code
                                if user.last_lat and user.last_lng:
                                    from utils.radius_calc import haversine_distance

                                    distance = haversine_distance(
                                        user.last_lat,
                                        user.last_lng,
                                        place_from_db.lat,
                                        place_from_db.lng,
                                    )
                                    task_dict["distance_km"] = round(distance, 1)
                            else:
                                task_dict["place_name"] = "Место на карте"
                            logger.debug(
                                f"✅ Используем существующее место для UserTask {user_task.id}: {user_task.place_url}"
                            )
                        else:
                            place = None
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
                            place_types = category_place_types.get(task_category, ["park"])

                            for place_type in place_types:
                                logger.info(
                                    f"Попытка найти место: category={task_category}, "
                                    f"place_type={place_type}, task_type={task_type}"
                                )
                                place = find_nearest_available_place(
                                    category=task_category,
                                    place_type=place_type,
                                    task_type=task_type,
                                    user_lat=user.last_lat,
                                    user_lng=user.last_lng,
                                    user_id=user_id,
                                    exclude_days=0,  # Не исключаем места, которые уже показывались
                                )
                                if place:
                                    logger.info(f"✅ Найдено место: {place.name} (ID: {place.id})")
                                    break

                            # Если не нашли по типу места, пробуем без фильтра по типу
                            if not place:
                                from tasks_location_service import find_oldest_unshown_place_in_region

                                for place_type in place_types:
                                    place = find_oldest_unshown_place_in_region(
                                        category=task_category,
                                        place_type=place_type,
                                        region=region,
                                        user_id=user_id,
                                        task_type=task_type,
                                        user_lat=user.last_lat,
                                        user_lng=user.last_lng,
                                    )
                                    if place:
                                        break

                            if place:
                                task_dict["place_name"] = place.name
                                task_dict["place_url"] = place.google_maps_url
                                task_dict["promo_code"] = place.promo_code
                                if hasattr(place, "distance_km"):
                                    task_dict["distance_km"] = place.distance_km

                                # ВАЖНО: Сохраняем найденное место в UserTask, чтобы оно не менялось каждый раз
                                # Это нужно для заданий, которые были приняты без конкретного места
                                # НО: по рекомендации консультанта, динамический поиск места должен быть отключен
                                # Оставляем только для обратной совместимости со старыми заданиями
                                if not user_task.place_id and place.id:
                                    user_task.place_id = place.id
                                    user_task.place_name = place.name
                                    user_task.place_url = place.google_maps_url
                                    user_task.promo_code = place.promo_code
                                    # ВАЖНО: Замороженные данные будут добавлены после применения миграции 035
                                    # TODO: После применения миграции раскомментировать:
                                    # if not user_task.frozen_title:
                                    #     user_task.frozen_title = task.title
                                    # if not user_task.frozen_description:
                                    #     user_task.frozen_description = task.description
                                    # if not user_task.frozen_category:
                                    #     user_task.frozen_category = task_category
                                    # if place.task_hint and not user_task.frozen_task_hint:
                                    #     user_task.frozen_task_hint = place.task_hint
                                    session.commit()
                                    logger.info(
                                        f"💾 Сохранено место в UserTask {user_task.id}: {place.name} (ID: {place.id})"
                                    )

                                logger.info(
                                    f"✅ Место найдено для UserTask {user_task.id}: {place.name}, "
                                    f"промокод={place.promo_code}"
                                )
                            else:
                                logger.warning(
                                    f"⚠️ Место не найдено для UserTask {user_task.id}: "
                                    f"category={task_category}, task_type={task_type}"
                                )
                except Exception as e:
                    logger.error(
                        "❌ Ошибка получения информации о месте для UserTask %s: %s",
                        user_task.id,
                        e,
                        exc_info=True,
                    )

            result.append(task_dict)

        return result


def get_user_completed_tasks_today(user_id: int) -> list[int]:
    """
    Получает список ID заданий, выполненных пользователем сегодня

    Args:
        user_id: ID пользователя

    Returns:
        Список task_id выполненных заданий за сегодня (по UTC)
    """
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    with get_session() as session:
        completed_tasks = (
            session.query(UserTask.id)
            .filter(
                and_(
                    UserTask.user_id == user_id,
                    UserTask.status == "completed",
                    UserTask.completed_at >= today_start,
                )
            )
            .all()
        )
        return [uid for (uid,) in completed_tasks]


def complete_task(user_task_id: int, feedback: str) -> bool:
    """
    Завершает задание с фидбеком

    Args:
        user_task_id: ID принятого задания пользователя
        feedback: Фидбек пользователя

    Returns:
        True если задание завершено успешно
    """
    try:
        with get_session() as session:
            user_task = (
                session.query(UserTask).filter(and_(UserTask.id == user_task_id, UserTask.status == "active")).first()
            )

            if not user_task:
                logger.error(f"Активное задание {user_task_id} не найдено")
                return False

            # Проверка на просрочку отключена - задания можно завершать в любое время

            # Обновляем статус и фидбек
            user_task.status = "completed"
            user_task.feedback = feedback
            user_task.completed_at = datetime.now(UTC)

            # Увеличиваем счетчик выполненных заданий
            user = session.get(User, user_task.user_id)
            if user:
                user.tasks_completed_total = (user.tasks_completed_total or 0) + 1

            session.commit()

            logger.info(f"Задание {user_task_id} завершено с фидбеком")
            return True

    except Exception as e:
        logger.error(f"Ошибка завершения задания {user_task_id}: {e}")
        return False


def cancel_task(user_task_id: int) -> bool:
    """
    Отменяет задание

    Args:
        user_task_id: ID принятого задания пользователя

    Returns:
        True если задание отменено успешно
    """
    try:
        with get_session() as session:
            user_task = (
                session.query(UserTask).filter(and_(UserTask.id == user_task_id, UserTask.status == "active")).first()
            )

            if not user_task:
                logger.error(f"Активное задание {user_task_id} не найдено")
                return False

            user_task.status = "cancelled"
            session.commit()

            logger.info(f"Задание {user_task_id} отменено")
            return True

    except Exception as e:
        logger.error(f"Ошибка отмены задания {user_task_id}: {e}")
        return False


def get_expired_tasks() -> list[UserTask]:
    """
    Получает просроченные задания для автоматической отмены

    Returns:
        Список просроченных заданий
    """
    with get_session() as session:
        now = datetime.now(UTC)
        active_tasks = session.query(UserTask).filter(UserTask.status == "active").all()

        expired_tasks = []
        for task in active_tasks:
            # Если нет timezone, считаем что это UTC
            expires_at = task.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            else:
                expires_at = expires_at.astimezone(UTC)

            if now > expires_at:
                expired_tasks.append(task)

        return expired_tasks


def mark_tasks_as_expired() -> int:
    """
    Помечает просроченные задания как истекшие

    ОТКЛЮЧЕНО: Ограничение по времени на выполнение заданий отключено.
    Задания больше не помечаются как истекшие.

    Returns:
        Количество помеченных заданий (всегда 0)
    """
    # Функция отключена - ограничение по времени снято
    logger.debug("mark_tasks_as_expired вызвана, но отключена (ограничение по времени снято)")
    return 0


def get_tasks_approaching_deadline(hours_before: int = 2) -> list[dict]:
    """
    Получает задания, приближающиеся к дедлайну

    Args:
        hours_before: За сколько часов до дедлайна уведомлять

    Returns:
        Список заданий с информацией о пользователях
    """
    deadline_threshold = datetime.now(UTC) + timedelta(hours=hours_before)

    with get_session() as session:
        approaching_tasks = (
            session.query(UserTask)
            .filter(
                and_(
                    UserTask.status == "active",
                    UserTask.expires_at <= deadline_threshold,
                    UserTask.expires_at > datetime.now(UTC),
                )
            )
            .all()
        )
        result = []
        for user_task in approaching_tasks:
            title = user_task.frozen_title or user_task.place_name or "Задание"
            result.append(
                {
                    "user_id": user_task.user_id,
                    "task_title": title,
                    "expires_at": user_task.expires_at,
                    "hours_left": (user_task.expires_at - datetime.now(UTC)).total_seconds() / 3600,
                }
            )
        return result
