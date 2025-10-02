#!/usr/bin/env python3
"""
Сервис для работы с ракетами пользователей
"""

import logging

from database import User, get_session

logger = logging.getLogger(__name__)


def get_user_rockets(user_id: int) -> int:
    """Получает количество ракет пользователя"""
    try:
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                return user.rockets_balance or 0
    except Exception as e:
        logger.error(f"Ошибка получения ракет пользователя {user_id}: {e}")
    return 0


def add_rockets(user_id: int, amount: int, reason: str = "") -> bool:
    """Добавляет ракеты пользователю"""
    try:
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.rockets_balance = (user.rockets_balance or 0) + amount
                session.commit()
                logger.info(f"Добавлено {amount} ракет пользователю {user_id}. Причина: {reason}")
                return True
            else:
                logger.warning(f"Пользователь {user_id} не найден")
                return False
    except Exception as e:
        logger.error(f"Ошибка добавления ракет пользователю {user_id}: {e}")
        return False


def spend_rockets(user_id: int, amount: int, reason: str = "") -> bool:
    """Тратит ракеты пользователя"""
    try:
        with get_session() as session:
            user = session.get(User, user_id)
            if user:
                current_balance = user.rockets_balance or 0
                if current_balance >= amount:
                    user.rockets_balance = current_balance - amount
                    session.commit()
                    logger.info(f"Потрачено {amount} ракет пользователем {user_id}. Причина: {reason}")
                    return True
                else:
                    logger.warning(f"Недостаточно ракет у пользователя {user_id}: {current_balance} < {amount}")
                    return False
            else:
                logger.warning(f"Пользователь {user_id} не найден")
                return False
    except Exception as e:
        logger.error(f"Ошибка траты ракет пользователем {user_id}: {e}")
        return False


def award_rockets_for_activity(user_id: int, activity_type: str) -> int:
    """Награждает ракетами за активность"""
    rewards = {
        "first_search": 5,  # Первый поиск событий
        "daily_search": 1,  # Ежедневный поиск
        "event_join": 2,  # Присоединение к событию
        "event_create": 10,  # Создание события
        "task_complete": 3,  # Выполнение задания "Цели на районе"
    }

    amount = rewards.get(activity_type, 0)
    if amount > 0:
        if add_rockets(user_id, amount, f"Активность: {activity_type}"):
            return amount
    return 0
