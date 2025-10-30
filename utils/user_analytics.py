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
        """Увеличить счетчик суммарных сессий пользователя (legacy)"""
        try:
            with get_session() as session:
                result = session.execute(
                    text(
                        """
                    UPDATE users
                    SET total_sessions = total_sessions + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """
                    ),
                    {"user_id": user_id},
                )

                session.commit()

                if result.rowcount > 0:
                    logger.info(f"✅ Увеличено количество сессий (legacy) для пользователя {user_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден для обновления сессий (legacy)")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления сессий (legacy) для пользователя {user_id}: {e}")
            return False

    @staticmethod
    def increment_sessions_world(user_id: int) -> bool:
        """Увеличить счетчик сессий World и суммарный total_sessions"""
        try:
            with get_session() as session:
                result = session.execute(
                    text(
                        """
                    UPDATE users
                    SET total_sessions_world = total_sessions_world + 1,
                        total_sessions = total_sessions + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """
                    ),
                    {"user_id": user_id},
                )
                session.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Ошибка increment_sessions_world для пользователя {user_id}: {e}")
            return False

    @staticmethod
    def increment_sessions_community(user_id: int) -> bool:
        """Увеличить счетчик сессий Community и суммарный total_sessions"""
        try:
            with get_session() as session:
                result = session.execute(
                    text(
                        """
                    UPDATE users
                    SET total_sessions_community = total_sessions_community + 1,
                        total_sessions = total_sessions + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """
                    ),
                    {"user_id": user_id},
                )
                session.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Ошибка increment_sessions_community для пользователя {user_id}: {e}")
            return False

    @staticmethod
    def increment_tasks_accepted(user_id: int) -> bool:
        """Увеличить счетчик принятых заданий"""
        try:
            with get_session() as session:
                result = session.execute(
                    text(
                        """
                    UPDATE users
                    SET tasks_accepted_total = tasks_accepted_total + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """
                    ),
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
                    text(
                        """
                    UPDATE users
                    SET tasks_completed_total = tasks_completed_total + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """
                    ),
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
    def increment_events_created_world(user_id: int) -> bool:
        """Увеличить счетчик созданных событий World версии"""
        try:
            with get_session() as session:
                result = session.execute(
                    text(
                        """
                    UPDATE users
                    SET events_created_world = events_created_world + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """
                    ),
                    {"user_id": user_id},
                )

                session.commit()

                if result.rowcount > 0:
                    logger.info(f"✅ Увеличено количество созданных событий World для пользователя {user_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден для обновления созданных событий World")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления созданных событий World для пользователя {user_id}: {e}")
            return False

    @staticmethod
    def increment_events_created_community(user_id: int) -> bool:
        """Увеличить счетчик созданных событий Community версии"""
        try:
            with get_session() as session:
                result = session.execute(
                    text(
                        """
                    UPDATE users
                    SET events_created_community = events_created_community + 1,
                        updated_at_utc = NOW()
                    WHERE id = :user_id
                """
                    ),
                    {"user_id": user_id},
                )

                session.commit()

                if result.rowcount > 0:
                    logger.info(f"✅ Увеличено количество созданных событий Community для пользователя {user_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден для обновления созданных событий Community")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления созданных событий Community для пользователя {user_id}: {e}")
            return False

    @staticmethod
    def get_user_stats(user_id: int) -> dict | None:
        """Получить статистику пользователя"""
        try:
            with get_session() as session:
                result = session.execute(
                    text(
                        """
                    SELECT
                        total_sessions,
                        total_sessions_world,
                        total_sessions_community,
                        tasks_accepted_total,
                        tasks_completed_total,
                        events_created_world,
                        events_created_community,
                        rockets_balance
                    FROM users
                    WHERE id = :user_id
                """
                    ),
                    {"user_id": user_id},
                )

                row = result.fetchone()
                if row:
                    total_sessions_calc = (row[1] or 0) + (row[2] or 0)
                    return {
                        "total_sessions": row[0] if row[0] is not None else total_sessions_calc,
                        "total_sessions_world": row[1] or 0,
                        "total_sessions_community": row[2] or 0,
                        "tasks_accepted_total": row[3],
                        "tasks_completed_total": row[4],
                        "events_created_world": row[5],
                        "events_created_community": row[6],
                        "events_created_total": (row[5] or 0) + (row[6] or 0),
                        "rockets_balance": row[7],
                    }
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики пользователя {user_id}: {e}")
            return None
