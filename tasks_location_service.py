#!/usr/bin/env python3
"""
Сервис для работы с локациями заданий
- Поиск ближайших мест по радиусу
- Ротация локаций (не показывать повторно 3 дня)
- Гарантия показа всех локаций в регионе
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func

from database import DailyViewTasks, TaskPlace, get_session
from utils.geo_utils import haversine_km

logger = logging.getLogger(__name__)

# Настройки ротации
EXCLUDE_PLACE_DAYS = 3  # Не показывать место 3 дня подряд
PRIORITY_DAYS = 7  # После 7 дней - высокий приоритет


def get_user_region(lat: float, lng: float) -> str:
    """
    Определяет регион пользователя по координатам

    Args:
        lat: Широта
        lng: Долгота

    Returns:
        Код региона: 'moscow', 'spb', 'bali', 'jakarta', 'unknown'
    """
    # Москва
    if 55.5 <= lat <= 56.0 and 37.3 <= lng <= 37.9:
        return "moscow"

    # СПб
    elif 59.8 <= lat <= 60.1 and 30.0 <= lng <= 30.6:
        return "spb"

    # Бали
    elif -8.9 <= lat <= -8.1 and 114.4 <= lng <= 115.6:
        return "bali"

    # Джакарта
    elif -6.4 <= lat <= -6.1 and 106.6 <= lng <= 106.9:
        return "jakarta"

    # По умолчанию
    return "unknown"


def get_user_region_type(lat: float, lng: float) -> str:
    """
    Определяет тип региона пользователя: город (city) или остров (island)

    Args:
        lat: Широта
        lng: Долгота

    Returns:
        Тип региона: 'city' или 'island'
    """
    region = get_user_region(lat, lng)

    # Маппинг регионов на типы
    region_types = {
        "moscow": "city",
        "spb": "city",
        "jakarta": "city",
        "bali": "island",
    }

    return region_types.get(region, "city")  # По умолчанию город


def get_task_type_for_region(region_type: str) -> str:
    """
    Преобразует тип региона в тип задания

    Args:
        region_type: 'city' или 'island'

    Returns:
        Тип задания: 'urban' или 'island'
    """
    mapping = {
        "city": "urban",
        "island": "island",
    }
    return mapping.get(region_type, "urban")


def find_nearest_available_place(
    category: str,
    place_type: str,
    user_lat: float,
    user_lng: float,
    user_id: int,
    task_type: str = "urban",
    exclude_days: int = EXCLUDE_PLACE_DAYS,
) -> TaskPlace | None:
    """
    Находит ближайшее доступное место с учетом ротации

    Args:
        category: Категория задания ('body', 'spirit', etc.)
        place_type: Тип места ('cafe', 'park', 'gym', etc.)
        user_lat: Широта пользователя
        user_lng: Долгота пользователя
        user_id: ID пользователя
        task_type: Тип задания ('urban' или 'island')
        exclude_days: Количество дней для исключения (по умолчанию 3)

    Returns:
        TaskPlace или None если места не найдены
    """
    region = get_user_region(user_lat, user_lng)

    with get_session() as session:
        # 1. Получаем все места категории и типа в регионе, с учетом типа задания
        places = (
            session.query(TaskPlace)
            .filter(
                and_(
                    TaskPlace.category == category,
                    TaskPlace.place_type == place_type,
                    TaskPlace.task_type == task_type,  # Фильтр по типу задания
                    TaskPlace.is_active == True,  # noqa: E712
                    TaskPlace.region == region,
                )
            )
            .all()
        )

        if not places:
            logger.warning(f"Места не найдены: category={category}, place_type={place_type}, region={region}")
            return None

        # 2. Вычисляем расстояние и время последнего показа для каждого места
        datetime.now(UTC) - timedelta(days=exclude_days)

        places_with_priority = []
        for place in places:
            place.distance_km = haversine_km(user_lat, user_lng, place.lat, place.lng)

            # Получаем дату последнего показа этого места пользователю
            last_shown = (
                session.query(DailyViewTasks.view_date)
                .filter(
                    and_(
                        DailyViewTasks.user_id == user_id,
                        DailyViewTasks.view_type == "place",
                        DailyViewTasks.view_key == str(place.id),
                    )
                )
                .order_by(DailyViewTasks.view_date.desc())
                .first()
            )

            if last_shown:
                days_since_shown = (datetime.now(UTC) - last_shown[0]).days
                place.days_since_shown = days_since_shown
            else:
                place.days_since_shown = 999  # Никогда не показывалось - максимальный приоритет

            places_with_priority.append(place)

        # 3. Сортируем по приоритету:
        # - Сначала места, которые не показывались >7 дней (высокий приоритет)
        # - Потом места, которые не показывались 3-7 дней (средний приоритет)
        # - Потом места, которые не показывались <3 дней (низкий приоритет)
        # - Внутри каждой группы сортируем по расстоянию

        def get_priority(place):
            days = place.days_since_shown

            # Приоритет 1: не показывалось >7 дней (обязательно показать)
            if days > PRIORITY_DAYS:
                return (0, place.distance_km)

            # Приоритет 2: не показывалось 3-7 дней
            elif days >= exclude_days:
                return (1, place.distance_km)

            # Приоритет 3: показывалось недавно (<3 дней)
            else:
                return (2, place.distance_km)

        places_with_priority.sort(key=get_priority)

        # 4. Берем первое место (самое приоритетное)
        return places_with_priority[0] if places_with_priority else None


def find_oldest_unshown_place_in_region(
    category: str,
    place_type: str,
    region: str,
    user_id: int,
    task_type: str = "urban",
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> TaskPlace | None:
    """
    Находит место в регионе, которое дольше всего не показывалось пользователю
    Гарантирует показ всех локаций в регионе

    Args:
        category: Категория задания
        place_type: Тип места
        region: Регион
        user_id: ID пользователя
        task_type: Тип задания ('urban' или 'island')
        user_lat: Широта пользователя (для вычисления расстояния)
        user_lng: Долгота пользователя (для вычисления расстояния)

    Returns:
        TaskPlace или None
    """
    with get_session() as session:
        # Получаем все места региона с учетом типа задания
        places = (
            session.query(TaskPlace)
            .filter(
                and_(
                    TaskPlace.category == category,
                    TaskPlace.place_type == place_type,
                    TaskPlace.task_type == task_type,  # Фильтр по типу задания
                    TaskPlace.region == region,
                    TaskPlace.is_active == True,  # noqa: E712
                )
            )
            .all()
        )

        if not places:
            return None

        # Для каждого места находим дату последнего показа и вычисляем расстояние
        places_with_dates = []
        for place in places:
            last_shown = (
                session.query(DailyViewTasks.view_date)
                .filter(
                    and_(
                        DailyViewTasks.user_id == user_id,
                        DailyViewTasks.view_type == "place",
                        DailyViewTasks.view_key == str(place.id),
                    )
                )
                .order_by(DailyViewTasks.view_date.desc())
                .first()
            )

            if last_shown:
                days_since = (datetime.now(UTC) - last_shown[0]).days
            else:
                days_since = 999  # Никогда не показывалось

            # Вычисляем расстояние, если есть координаты пользователя
            if user_lat is not None and user_lng is not None:
                place.distance_km = haversine_km(user_lat, user_lng, place.lat, place.lng)

            places_with_dates.append((place, days_since))

        # Сортируем по времени последнего показа (самое старое первым)
        places_with_dates.sort(key=lambda x: x[1])

        # Возвращаем место, которое дольше всего не показывалось
        return places_with_dates[0][0] if places_with_dates else None


def mark_place_as_shown(user_id: int, place_id: int) -> None:
    """
    Сохраняет факт показа места пользователю

    Args:
        user_id: ID пользователя
        place_id: ID места
    """
    with get_session() as session:
        # Проверяем, не записано ли уже сегодня
        today = datetime.now(UTC).date()
        existing = (
            session.query(DailyViewTasks)
            .filter(
                and_(
                    DailyViewTasks.user_id == user_id,
                    DailyViewTasks.view_type == "place",
                    DailyViewTasks.view_key == str(place_id),
                    func.date(DailyViewTasks.view_date) == today,
                )
            )
            .first()
        )

        if not existing:
            view = DailyViewTasks(
                user_id=user_id,
                view_type="place",
                view_key=str(place_id),
                view_date=datetime.now(UTC),
            )
            session.add(view)
            session.commit()
            logger.info(f"Место {place_id} отмечено как показанное пользователю {user_id}")


def get_tasks_with_places(
    category: str, user_id: int, user_lat: float, user_lng: float, task_type: str = "urban"
) -> list[dict]:
    """
    Получает задания с локациями для категории и типа задания

    Args:
        category: Категория заданий ('body', 'spirit')
        user_id: ID пользователя
        user_lat: Широта пользователя
        user_lng: Долгота пользователя
        task_type: Тип задания ('urban' или 'island')

    Returns:
        Список словарей с заданиями и местами
    """
    # Определяем типы мест для категории
    category_place_types = {
        "body": ["cafe", "park", "gym"],
        "spirit": ["temple", "park", "viewpoint"],
    }

    place_types = category_place_types.get(category, ["park"])

    tasks_with_places = []

    for place_type in place_types:
        # Находим место с приоритетом
        place = find_nearest_available_place(
            category=category,
            place_type=place_type,
            user_lat=user_lat,
            user_lng=user_lng,
            user_id=user_id,
            task_type=task_type,  # Передаем тип задания
            exclude_days=EXCLUDE_PLACE_DAYS,
        )

        # Если нет места в радиусе, но есть в регионе - берем самое давно не показывавшееся
        if not place:
            region = get_user_region(user_lat, user_lng)
            place = find_oldest_unshown_place_in_region(
                category=category,
                place_type=place_type,
                region=region,
                user_id=user_id,
                task_type=task_type,  # Передаем тип задания
                user_lat=user_lat,
                user_lng=user_lng,
            )

        # Сохраняем факт показа
        if place:
            mark_place_as_shown(user_id, place.id)

        tasks_with_places.append(
            {
                "place_type": place_type,
                "place": place,
            }
        )

    return tasks_with_places
