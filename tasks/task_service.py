"""
Сервис для функции "Цель на Районе"
Изолированная разработка - не влияет на существующий функционал
"""

import logging
from datetime import date, datetime

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from database import DailyViewTasks, TaskPlace, TaskTemplate, User, UserTask, get_session

logger = logging.getLogger(__name__)


class TaskService:
    """Сервис для управления заданиями"""

    def __init__(self):
        self.category_place_types = {
            "body": ["park", "beach", "gym", "yoga_studio", "outdoor_space"],
            "spirit": ["temple", "viewpoint", "park", "beach", "cliff"],
            "career": ["exhibition", "library", "coworking", "work_space"],
            "social": ["dance_studio", "cafe", "tourist_attraction", "bar", "billiard"],
        }

    def get_three_tasks(self, category: str, user_id: int, lat: float, lng: float) -> list[dict]:
        """
        Получить 3 задания для категории с местами в радиусе 5км, исключая уже показанные сегодня
        """
        try:
            with get_session() as session:
                # Получаем места в радиусе 5км для категории
                places = self._get_nearby_places(session, category, lat, lng, radius_km=5, limit=3)

                if not places:
                    return self._get_fallback_tasks(category)

                # Получаем уже показанные сегодня шаблоны
                today = date.today()
                seen_templates = (
                    session.query(DailyViewTasks.view_key)
                    .filter(
                        and_(
                            DailyViewTasks.user_id == user_id,
                            DailyViewTasks.view_type == "template",
                            func.date(DailyViewTasks.view_date) == today,
                        )
                    )
                    .all()
                )
                seen_template_ids = [int(t[0]) for t in seen_templates]

                # Получаем доступные шаблоны для категории
                available_templates = (
                    session.query(TaskTemplate)
                    .filter(
                        and_(
                            TaskTemplate.category == category,
                            ~TaskTemplate.id.in_(seen_template_ids) if seen_template_ids else True,
                        )
                    )
                    .limit(3)
                    .all()
                )

                if not available_templates:
                    # Если нет новых шаблонов, возвращаем универсальные
                    return self._get_fallback_tasks(category)

                # Фиксируем просмотренные шаблоны
                for template in available_templates:
                    daily_view = DailyViewTasks(
                        user_id=user_id, view_type="template", view_key=str(template.id), view_date=datetime.now()
                    )
                    session.add(daily_view)

                session.commit()

                # Объединяем задания с местами
                result = []
                for i, template in enumerate(available_templates):
                    place = places[i] if i < len(places) else places[0]  # Fallback на первое место

                    result.append(
                        {
                            "id": template.id,
                            "title": template.title,
                            "description": template.description,
                            "place_type": template.place_type,
                            "rocket_value": template.rocket_value,
                            "place": {
                                "id": place.id,
                                "name": place.name,
                                "lat": place.lat,
                                "lng": place.lng,
                                "distance_km": place.distance_km,
                                "google_maps_url": place.google_maps_url,
                                "description": place.description,
                            },
                        }
                    )

                return result

        except Exception as e:
            logger.error(f"Ошибка получения заданий: {e}")
            return self._get_fallback_tasks(category)

    def _get_nearby_places(
        self, session: Session, category: str, lat: float, lng: float, radius_km: float = 5, limit: int = 3
    ) -> list:
        """Получить места в радиусе от пользователя"""
        # Получаем все места категории
        places = (
            session.query(TaskPlace).filter(and_(TaskPlace.category == category, TaskPlace.is_active is True)).all()
        )

        # Вычисляем расстояние и фильтруем по радиусу
        nearby_places = []
        for place in places:
            distance = self._calculate_distance(lat, lng, place.lat, place.lng)
            if distance <= radius_km:
                place.distance_km = round(distance, 1)
                nearby_places.append(place)

        # Сортируем по расстоянию и берем ближайшие
        nearby_places.sort(key=lambda x: x.distance_km)
        return nearby_places[:limit]

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Вычисляет расстояние между двумя точками в км"""
        import math

        # Формула гаверсинуса
        R = 6371  # Радиус Земли в км

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)

        a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _get_fallback_tasks(self, category: str) -> list[dict]:
        """Универсальные задания если нет подходящих мест"""
        fallback_tasks = {
            "body": {
                "title": "Домашняя тренировка",
                "description": "Сделай 20 приседаний, 10 отжиманий и 1 минуту планки дома.",
                "place_type": "home",
            },
            "spirit": {
                "title": "Медитация дома",
                "description": "Найди тихое место дома, сядь удобно и медитируй 5 минут.",
                "place_type": "home",
            },
            "career": {
                "title": "Онлайн обучение",
                "description": "Посмотри 15-минутный урок по твоей профессии на YouTube.",
                "place_type": "home",
            },
            "social": {
                "title": "Позвони другу",
                "description": "Позвони старому другу и поговори 10 минут о жизни.",
                "place_type": "home",
            },
        }

        task = fallback_tasks.get(category, fallback_tasks["body"])
        return [
            {
                "id": 0,  # Специальный ID для fallback
                "title": task["title"],
                "description": task["description"],
                "place_type": task["place_type"],
                "rocket_value": 1,
            }
        ]

    def start_task(self, user_id: int, template_id: int, place_data: dict) -> int | None:
        """Начать выполнение задания"""
        try:
            with get_session() as session:
                # Получаем шаблон
                template = session.get(TaskTemplate, template_id)
                if not template:
                    return None

                # Создаем пользовательское задание
                user_task = UserTask(
                    user_id=user_id,
                    template_id=template_id,
                    category=template.category,
                    title=template.title,
                    description=template.description,
                    rocket_value=template.rocket_value,
                    place_id=place_data.get("place_id"),
                    place_name=place_data.get("place_name"),
                    place_lat=place_data.get("lat"),
                    place_lng=place_data.get("lng"),
                    place_url=place_data.get("url"),
                    status="active",
                )

                session.add(user_task)
                session.commit()

                return user_task.id

        except Exception as e:
            logger.error(f"Ошибка создания задания: {e}")
            return None

    def complete_task(self, user_task_id: int, user_note: str) -> bool:
        """Завершить задание"""
        try:
            with get_session() as session:
                user_task = session.get(UserTask, user_task_id)
                if not user_task or user_task.status != "active":
                    return False

                # Обновляем задание
                user_task.status = "done"
                user_task.completed_at = datetime.now()
                user_task.user_note = user_note

                # Начисляем ракеты и обновляем счетчики
                user = session.get(User, user_task.user_id)
                if user:
                    user.rockets_balance += user_task.rocket_value
                    # Увеличиваем счетчик выполненных заданий
                    user.tasks_completed_total = (user.tasks_completed_total or 0) + 1

                session.commit()
                return True

        except Exception as e:
            logger.error(f"Ошибка завершения задания: {e}")
            return False

    def cancel_task(self, user_task_id: int) -> bool:
        """Отменить задание"""
        try:
            with get_session() as session:
                user_task = session.get(UserTask, user_task_id)
                if not user_task or user_task.status != "active":
                    return False

                user_task.status = "cancelled"
                session.commit()
                return True

        except Exception as e:
            logger.error(f"Ошибка отмены задания: {e}")
            return False

    def get_user_tasks(self, user_id: int, status: str = "active") -> list[dict]:
        """Получить задания пользователя"""
        try:
            with get_session() as session:
                tasks = (
                    session.query(UserTask)
                    .filter(and_(UserTask.user_id == user_id, UserTask.status == status))
                    .order_by(UserTask.started_at.desc())
                    .all()
                )

                return [
                    {
                        "id": task.id,
                        "title": task.title,
                        "description": task.description,
                        "place_name": task.place_name,
                        "place_url": task.place_url,
                        "started_at": task.started_at,
                        "completed_at": task.completed_at,
                        "user_note": task.user_note,
                        "rocket_value": task.rocket_value,
                    }
                    for task in tasks
                ]

        except Exception as e:
            logger.error(f"Ошибка получения заданий пользователя: {e}")
            return []

    def get_user_rockets(self, user_id: int) -> int:
        """Получить количество ракет пользователя"""
        try:
            with get_session() as session:
                user = session.get(User, user_id)
                return user.rockets_balance if user else 0
        except Exception as e:
            logger.error(f"Ошибка получения ракет: {e}")
            return 0
