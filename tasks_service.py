#!/usr/bin/env python3
"""
Сервис для работы с заданиями "Цели на районе"
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_

from database import Task, User, UserTask, get_session

logger = logging.getLogger(__name__)

# Дата начала системы заданий (фиксированная дата)
START_DATE = datetime(2025, 10, 3, 0, 0, 0, tzinfo=UTC)  # 3 октября 2025


def get_daily_tasks(category: str, date: datetime | None = None) -> list[Task]:
    """
    Получает 3 задания на день для указанной категории

    Args:
        category: 'body' или 'spirit'
        date: дата для получения заданий (по умолчанию сегодня)

    Returns:
        Список из 3 заданий
    """
    if date is None:
        date = datetime.now(UTC)

    # Вычисляем день с начала (1-5, потом по кругу)
    days_since_start = (date - START_DATE).days
    day_number = (days_since_start % 5) + 1  # 1-5, потом снова 1

    # Получаем 3 задания подряд (используем order_index 1-15 напрямую)
    start_index = (day_number - 1) * 3 + 1
    end_index = start_index + 2

    with get_session() as session:
        tasks = (
            session.query(Task)
            .filter(
                and_(
                    Task.category == category,
                    Task.is_active == True,  # noqa: E712
                    Task.order_index >= start_index,
                    Task.order_index <= end_index,
                )
            )
            .order_by(Task.order_index)
            .all()
        )

        logger.info(
            f"Получены задания для {category}, день {day_number}: {len(tasks)} заданий "
            f"(индексы {start_index}-{end_index})"
        )

        # Если не найдено заданий, попробуем получить любые 3 активных задания
        if not tasks:
            logger.warning(
                f"Задания не найдены для {category} с индексами {start_index}-{end_index}, пробуем любые активные"
            )
            tasks = (
                session.query(Task)
                .filter(
                    and_(
                        Task.category == category,
                        Task.is_active == True,  # noqa: E712
                    )
                )
                .order_by(Task.order_index)
                .limit(3)
                .all()
            )
            logger.info(f"Получены альтернативные задания для {category}: {len(tasks)} заданий")

        return tasks


def accept_task(user_id: int, task_id: int, user_lat: float = None, user_lng: float = None) -> bool:
    """
    Принимает задание пользователем

    Args:
        user_id: ID пользователя
        task_id: ID задания
        user_lat: Широта пользователя (для определения часового пояса)
        user_lng: Долгота пользователя (для определения часового пояса)

    Returns:
        True если задание принято успешно
    """
    try:
        with get_session() as session:
            # Проверяем, что задание существует и активно
            task = session.query(Task).filter(and_(Task.id == task_id, Task.is_active == True)).first()  # noqa: E712

            if not task:
                logger.error(f"Задание {task_id} не найдено или неактивно")
                return False

            # Проверяем, что у пользователя нет активных заданий этого типа
            existing_task = (
                session.query(UserTask)
                .filter(and_(UserTask.user_id == user_id, UserTask.task_id == task_id, UserTask.status == "active"))
                .first()
            )

            if existing_task:
                logger.warning(f"Пользователь {user_id} уже имеет активное задание {task_id}")
                return False

            # Определяем часовой пояс пользователя
            if user_lat is not None and user_lng is not None:
                from zoneinfo import ZoneInfo

                from utils.simple_timezone import get_city_from_coordinates, get_city_timezone

                city = get_city_from_coordinates(user_lat, user_lng)
                tz_name = get_city_timezone(city)
                user_tz = ZoneInfo(tz_name)

                # Используем местное время пользователя
                accepted_at_local = datetime.now(user_tz)
                accepted_at = accepted_at_local.astimezone(UTC)

                logger.info(
                    f"Пользователь {user_id} в городе {city} (часовой пояс {tz_name}), "
                    f"местное время: {accepted_at_local.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            else:
                # Fallback на UTC если координаты не переданы
                accepted_at = datetime.now(UTC)
                logger.info(f"Пользователь {user_id} без координат, используется UTC время")

            expires_at = accepted_at + timedelta(hours=24)

            user_task = UserTask(
                user_id=user_id, task_id=task_id, status="active", accepted_at=accepted_at, expires_at=expires_at
            )

            session.add(user_task)

            # Обновляем счетчик принятых заданий
            user = session.get(User, user_id)
            if user:
                user.tasks_accepted_total = (user.tasks_accepted_total or 0) + 1

            session.commit()

            logger.info(f"Пользователь {user_id} принял задание {task_id}, истекает {expires_at}")
            return True

    except Exception as e:
        logger.error(f"Ошибка принятия задания {task_id} пользователем {user_id}: {e}")
        return False


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
                tz_name = get_city_timezone(city)
                user_tz = ZoneInfo(tz_name)

                logger.info(f"Пользователь {user_id} в городе {city} (часовой пояс {tz_name})")
            except Exception as e:
                logger.warning(f"Не удалось определить часовой пояс для пользователя {user_id}: {e}")

        user_tasks = (
            session.query(UserTask, Task)
            .join(Task)
            .filter(and_(UserTask.user_id == user_id, UserTask.status == "active"))
            .all()
        )

        result = []
        for user_task, task in user_tasks:
            # Дополнительная проверка на просроченность (на всякий случай)
            expires_at_check = user_task.expires_at
            if expires_at_check.tzinfo is None:
                expires_at_check = expires_at_check.replace(tzinfo=UTC)
            else:
                expires_at_check = expires_at_check.astimezone(UTC)

            # Если задание просрочено, пропускаем его
            if datetime.now(UTC) > expires_at_check:
                logger.info(f"Пропускаем просроченное задание {user_task.id} для пользователя {user_id}")
                continue

            # Конвертируем время в местный часовой пояс
            accepted_at = user_task.accepted_at
            expires_at = user_task.expires_at

            if user_tz is not None:
                # Конвертируем UTC время в местное время пользователя
                if accepted_at.tzinfo is None:
                    accepted_at = accepted_at.replace(tzinfo=UTC)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)

                accepted_at = accepted_at.astimezone(user_tz)
                expires_at = expires_at.astimezone(user_tz)

            result.append(
                {
                    "id": user_task.id,
                    "task_id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "category": task.category,
                    "location_url": task.location_url,
                    "accepted_at": accepted_at,
                    "expires_at": expires_at,
                    "status": user_task.status,
                }
            )

        return result


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

            # Проверяем, что задание не просрочено
            expires_at = user_task.expires_at
            if expires_at.tzinfo is None:
                # Если нет информации о часовом поясе, считаем что это UTC
                expires_at = expires_at.replace(tzinfo=UTC)

            if datetime.now(UTC) > expires_at:
                logger.warning(f"Задание {user_task_id} просрочено")
                return False

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

    Returns:
        Количество помеченных заданий
    """
    try:
        with get_session() as session:
            now = datetime.now(UTC)
            active_tasks = session.query(UserTask).filter(UserTask.status == "active").all()

            expired_count = 0
            for task in active_tasks:
                # Если нет timezone, считаем что это UTC
                expires_at = task.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                else:
                    expires_at = expires_at.astimezone(UTC)

                if now > expires_at:
                    task.status = "expired"
                    expired_count += 1

            session.commit()

            logger.info(f"Помечено как истекшие: {expired_count} заданий")
            return expired_count

    except Exception as e:
        logger.error(f"Ошибка пометки заданий как истекших: {e}")
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
            session.query(UserTask, Task)
            .join(Task)
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
        for user_task, task in approaching_tasks:
            result.append(
                {
                    "user_id": user_task.user_id,
                    "task_title": task.title,
                    "expires_at": user_task.expires_at,
                    "hours_left": (user_task.expires_at - datetime.now(UTC)).total_seconds() / 3600,
                }
            )

        return result
