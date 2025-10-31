#!/usr/bin/env python3
"""
Сервис для аналитики взаимодействий пользователей с событиями
"""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class UserParticipationAnalytics:
    """Сервис для отслеживания взаимодействий пользователей с событиями"""

    def __init__(self, engine: Engine):
        self.engine = engine

    def record_list_view(self, user_id: int, event_id: int, group_chat_id: int | None = None) -> bool:
        """
        Записать, что событие было показано пользователю в списке "Что рядом"

        Args:
            user_id: ID пользователя
            event_id: ID события
            group_chat_id: ID группового чата (для Community) или None (для World)

        Returns:
            bool: True если успешно записано/обновлено
        """
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO user_participation (
                            user_id, event_id, group_chat_id, list_view, participation_type
                        )
                        VALUES (:user_id, :event_id, :group_chat_id, TRUE, NULL)
                        ON CONFLICT (user_id, event_id)
                        DO UPDATE SET
                            list_view = TRUE,
                            updated_at = NOW()
                    """),
                    {
                        "user_id": user_id,
                        "event_id": event_id,
                        "group_chat_id": group_chat_id,
                    },
                )
                logger.debug(f"✅ Записано list_view: user_id={user_id}, event_id={event_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка записи list_view: {e}")
            return False

    def record_click_source(self, user_id: int, event_id: int) -> bool:
        """
        Записать, что пользователь нажал на источник или автора события

        Args:
            user_id: ID пользователя
            event_id: ID события

        Returns:
            bool: True если успешно записано/обновлено
        """
        try:
            with self.engine.begin() as conn:
                # Проверяем, существует ли запись
                result = conn.execute(
                    text("""
                        SELECT id FROM user_participation
                        WHERE user_id = :user_id AND event_id = :event_id
                    """),
                    {"user_id": user_id, "event_id": event_id},
                )

                if result.fetchone():
                    # Запись существует - обновляем
                    conn.execute(
                        text("""
                            UPDATE user_participation
                            SET click_source = TRUE, updated_at = NOW()
                            WHERE user_id = :user_id AND event_id = :event_id
                        """),
                        {"user_id": user_id, "event_id": event_id},
                    )
                    logger.debug(f"✅ Обновлен click_source: user_id={user_id}, event_id={event_id}")
                else:
                    # Записи нет - создаем новую
                    conn.execute(
                        text("""
                            INSERT INTO user_participation (
                                user_id, event_id, click_source, participation_type
                            )
                            VALUES (:user_id, :event_id, TRUE, NULL)
                        """),
                        {"user_id": user_id, "event_id": event_id},
                    )
                    logger.debug(f"✅ Создана запись с click_source: user_id={user_id}, event_id={event_id}")

                return True
        except Exception as e:
            logger.error(f"❌ Ошибка записи click_source: {e}")
            return False

    def record_click_route(self, user_id: int, event_id: int) -> bool:
        """
        Записать, что пользователь нажал на кнопку маршрута

        Args:
            user_id: ID пользователя
            event_id: ID события

        Returns:
            bool: True если успешно записано/обновлено
        """
        try:
            with self.engine.begin() as conn:
                # Проверяем, существует ли запись
                result = conn.execute(
                    text("""
                        SELECT id FROM user_participation
                        WHERE user_id = :user_id AND event_id = :event_id
                    """),
                    {"user_id": user_id, "event_id": event_id},
                )

                if result.fetchone():
                    # Запись существует - обновляем
                    conn.execute(
                        text("""
                            UPDATE user_participation
                            SET click_route = TRUE, updated_at = NOW()
                            WHERE user_id = :user_id AND event_id = :event_id
                        """),
                        {"user_id": user_id, "event_id": event_id},
                    )
                    logger.debug(f"✅ Обновлен click_route: user_id={user_id}, event_id={event_id}")
                else:
                    # Записи нет - создаем новую
                    conn.execute(
                        text("""
                            INSERT INTO user_participation (
                                user_id, event_id, click_route, participation_type
                            )
                            VALUES (:user_id, :event_id, TRUE, NULL)
                        """),
                        {"user_id": user_id, "event_id": event_id},
                    )
                    logger.debug(f"✅ Создана запись с click_route: user_id={user_id}, event_id={event_id}")

                return True
        except Exception as e:
            logger.error(f"❌ Ошибка записи click_route: {e}")
            return False
