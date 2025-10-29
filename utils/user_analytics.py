#!/usr/bin/env python3
"""
Утилиты для обновления аналитики пользователей
"""

import logging

from sqlalchemy import text

from database import get_session

logger = logging.getLogger(__name__)


class UserAnalytics:
    """Класс для работы с аналитикой пользователей"""

    @staticmethod
    def increment_sessions(user_id: int) -> bool:
        """Увеличить счетчик сессий пользователя"""
        try:
            with get_session() as session:
                result = session.execute(
                    text("""
                    UPDATE users
                    SET total_sessions = total_sessions + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """),
                    {"user_id": user_id},
                )

                session.commit()

                if result.rowcount > 0:
                    logger.info(f"✅ Увеличено количество сессий для пользователя {user_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден для обновления сессий")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления сессий для пользователя {user_id}: {e}")
            return False

    @staticmethod
    def increment_tasks_accepted(user_id: int) -> bool:
        """Увеличить счетчик принятых заданий"""
        try:
            with get_session() as session:
                result = session.execute(
                    text("""
                    UPDATE users
                    SET tasks_accepted_total = tasks_accepted_total + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """),
                    {"user_id": user_id},
                )

                session.commit()

                if result.rowcount > 0:
                    logger.info(f"✅ Увеличено количество принятых заданий для пользователя {user_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден для обновления принятых заданий")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления принятых заданий для пользователя {user_id}: {e}")
            return False

    @staticmethod
    def increment_tasks_completed(user_id: int) -> bool:
        """Увеличить счетчик выполненных заданий"""
        try:
            with get_session() as session:
                result = session.execute(
                    text("""
                    UPDATE users
                    SET tasks_completed_total = tasks_completed_total + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """),
                    {"user_id": user_id},
                )

                session.commit()

                if result.rowcount > 0:
                    logger.info(f"✅ Увеличено количество выполненных заданий для пользователя {user_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден для обновления выполненных заданий")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления выполненных заданий для пользователя {user_id}: {e}")
            return False

    @staticmethod
    def increment_events_created(user_id: int) -> bool:
        """Увеличить счетчик созданных событий"""
        try:
            with get_session() as session:
                result = session.execute(
                    text("""
                    UPDATE users
                    SET events_created_total = events_created_total + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """),
                    {"user_id": user_id},
                )

                session.commit()

                if result.rowcount > 0:
                    logger.info(f"✅ Увеличено количество созданных событий для пользователя {user_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден для обновления созданных событий")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления созданных событий для пользователя {user_id}: {e}")
            return False

    @staticmethod
    def get_user_stats(user_id: int) -> dict | None:
        """Получить статистику пользователя"""
        try:
            with get_session() as session:
                result = session.execute(
                    text("""
                    SELECT
                        total_sessions,
                        tasks_accepted_total,
                        tasks_completed_total,
                        events_created_total,
                        rockets_balance
                    FROM users
                    WHERE id = :user_id
                """),
                    {"user_id": user_id},
                )

                row = result.fetchone()
                if row:
                    return {
                        "total_sessions": row[0],
                        "tasks_accepted_total": row[1],
                        "tasks_completed_total": row[2],
                        "events_created_total": row[3],
                        "rockets_balance": row[4],
                    }
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики пользователя {user_id}: {e}")
            return None
