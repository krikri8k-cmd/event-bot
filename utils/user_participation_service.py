"""
Сервис для управления участием пользователей в событиях
"""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class UserParticipationService:
    """Сервис для управления участием пользователей в событиях"""

    def __init__(self, engine: Engine):
        self.engine = engine

    def add_participation(self, user_id: int, event_id: int, participation_type: str) -> bool:
        """
        Добавить участие пользователя в событии

        Args:
            user_id: ID пользователя Telegram
            event_id: ID события
            participation_type: 'going' или 'maybe'

        Returns:
            bool: True если успешно добавлено/обновлено
        """
        if participation_type not in ["going", "maybe"]:
            logger.error(f"Неверный тип участия: {participation_type}")
            return False

        try:
            with self.engine.begin() as conn:
                # Используем ON CONFLICT для обновления существующей записи
                result = conn.execute(
                    text("""
                        INSERT INTO user_participation (user_id, event_id, participation_type)
                        VALUES (:user_id, :event_id, :participation_type)
                        ON CONFLICT (user_id, event_id)
                        DO UPDATE SET
                            participation_type = EXCLUDED.participation_type,
                            created_at = NOW()
                        RETURNING id
                    """),
                    {"user_id": user_id, "event_id": event_id, "participation_type": participation_type},
                )

                result.fetchone()[0]
                logger.info(f"✅ Участие добавлено: user_id={user_id}, event_id={event_id}, type={participation_type}")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка добавления участия: {e}")
            return False

    def remove_participation(self, user_id: int, event_id: int) -> bool:
        """
        Удалить участие пользователя в событии

        Args:
            user_id: ID пользователя Telegram
            event_id: ID события

        Returns:
            bool: True если успешно удалено
        """
        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    text("""
                        DELETE FROM user_participation
                        WHERE user_id = :user_id AND event_id = :event_id
                    """),
                    {"user_id": user_id, "event_id": event_id},
                )

                deleted_count = result.rowcount
                if deleted_count > 0:
                    logger.info(f"✅ Участие удалено: user_id={user_id}, event_id={event_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Участие не найдено: user_id={user_id}, event_id={event_id}")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка удаления участия: {e}")
            return False

    def get_user_participations(self, user_id: int, participation_type: str | None = None) -> list[dict]:
        """
        Получить события пользователя по типу участия

        Args:
            user_id: ID пользователя Telegram
            participation_type: 'going', 'maybe' или None (все)

        Returns:
            List[Dict]: Список событий с информацией об участии
        """
        try:
            with self.engine.connect() as conn:
                if participation_type:
                    query = text("""
                        SELECT e.id, e.title, e.description, e.starts_at,
                               e.location_name, e.city, e.lat, e.lng,
                               e.source, up.participation_type, up.created_at
                        FROM user_participation up
                        JOIN events e ON up.event_id = e.id
                        WHERE up.user_id = :user_id
                        AND up.participation_type = :participation_type
                        AND e.starts_at > NOW()
                        ORDER BY e.starts_at ASC
                    """)
                    params = {"user_id": user_id, "participation_type": participation_type}
                else:
                    query = text("""
                        SELECT e.id, e.title, e.description, e.starts_at,
                               e.location_name, e.city, e.lat, e.lng,
                               e.source, up.participation_type, up.created_at
                        FROM user_participation up
                        JOIN events e ON up.event_id = e.id
                        WHERE up.user_id = :user_id
                        AND e.starts_at > NOW()
                        ORDER BY up.participation_type, e.starts_at ASC
                    """)
                    params = {"user_id": user_id}

                result = conn.execute(query, params)

                participations = []
                for row in result.fetchall():
                    participations.append(
                        {
                            "event_id": row[0],
                            "title": row[1],
                            "description": row[2],
                            "starts_at": row[3],
                            "location_name": row[4],
                            "city": row[5],
                            "lat": row[6],
                            "lng": row[7],
                            "source": row[8],
                            "participation_type": row[9],
                            "added_at": row[10],
                        }
                    )

                logger.info(f"📋 Найдено {len(participations)} участий для пользователя {user_id}")
                return participations

        except Exception as e:
            logger.error(f"❌ Ошибка получения участий: {e}")
            return []

    def get_user_participation_status(self, user_id: int, event_id: int) -> str | None:
        """
        Получить статус участия пользователя в конкретном событии

        Args:
            user_id: ID пользователя Telegram
            event_id: ID события

        Returns:
            Optional[str]: 'going', 'maybe' или None если не участвует
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT participation_type
                        FROM user_participation
                        WHERE user_id = :user_id AND event_id = :event_id
                    """),
                    {"user_id": user_id, "event_id": event_id},
                )

                row = result.fetchone()
                return row[0] if row else None

        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса участия: {e}")
            return None

    def cleanup_expired_participations(self) -> int:
        """
        Очистить участия для завершившихся событий

        Returns:
            int: Количество удаленных записей
        """
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("SELECT cleanup_expired_participations()"))
                message = result.fetchone()[0]

                # Извлекаем количество из сообщения
                deleted_count = 0
                if "Удалено" in message:
                    try:
                        deleted_count = int(message.split()[1])
                    except (IndexError, ValueError):
                        pass

                logger.info(f"🧹 Очистка участий: {message}")
                return deleted_count

        except Exception as e:
            logger.error(f"❌ Ошибка очистки участий: {e}")
            return 0

    def get_event_participants(self, event_id: int) -> dict[str, list[dict]]:
        """
        Получить участников события

        Args:
            event_id: ID события

        Returns:
            Dict: {'going': [...], 'maybe': [...]}
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT up.user_id, up.participation_type, up.created_at
                        FROM user_participation up
                        WHERE up.event_id = :event_id
                        ORDER BY up.participation_type, up.created_at ASC
                    """),
                    {"event_id": event_id},
                )

                participants = {"going": [], "maybe": []}
                for row in result.fetchall():
                    user_id, participation_type, created_at = row
                    participants[participation_type].append({"user_id": user_id, "created_at": created_at})

                logger.info(
                    f"👥 Событие {event_id}: {len(participants['going'])} пойдут, {len(participants['maybe'])} возможно"
                )
                return participants

        except Exception as e:
            logger.error(f"❌ Ошибка получения участников: {e}")
            return {"going": [], "maybe": []}
