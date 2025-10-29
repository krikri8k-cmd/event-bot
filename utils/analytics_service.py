"""
Сервис для работы с аналитикой бота
Отслеживает активность пользователей, статистику групп и метрики
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Сервис для работы с аналитикой бота"""

    def __init__(self, engine: Engine):
        self.engine = engine

    def save_metric(
        self,
        metric_name: str,
        metric_value: dict[str, Any],
        scope: str = "global",
        target_id: int | None = None,
        target_date: date | None = None,
    ) -> bool:
        """
        Сохранить метрику в таблицу analytics

        Args:
            metric_name: Название метрики ('daily_user_activity', 'group_statistics', etc.)
            metric_value: Данные метрики в виде словаря
            scope: Область метрики ('global', 'group', 'user', 'event')
            target_id: ID группы, пользователя или события (если scope != global)
            target_date: Дата метрики (по умолчанию сегодня)

        Returns:
            bool: True если успешно сохранено
        """
        if target_date is None:
            target_date = date.today()

        try:
            with self.engine.begin() as conn:
                # Используем ON CONFLICT для обновления существующей записи
                # Для global scope используем 0 как target_id
                effective_target_id = target_id if target_id is not None else 0

                result = conn.execute(
                    text("""
                        INSERT INTO analytics (metric_name, scope, target_id, metric_value, date)
                        VALUES (:metric_name, :scope, :target_id, :metric_value, :date)
                        ON CONFLICT (metric_name, scope, target_id, date)
                        DO UPDATE SET
                            metric_value = EXCLUDED.metric_value,
                            created_at = NOW()
                        RETURNING id
                    """),
                    {
                        "metric_name": metric_name,
                        "scope": scope,
                        "target_id": effective_target_id,
                        "metric_value": json.dumps(metric_value, ensure_ascii=False),
                        "date": target_date,
                    },
                )

                record_id = result.scalar()
                logger.info(f"✅ Метрика {metric_name} ({scope}) сохранена с ID {record_id} на дату {target_date}")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения метрики {metric_name}: {e}")
            return False

    def get_metric(self, metric_name: str, target_date: date | None = None) -> dict[str, Any] | None:
        """
        Получить метрику по названию и дате

        Args:
            metric_name: Название метрики
            target_date: Дата метрики (по умолчанию сегодня)

        Returns:
            Dict с данными метрики или None
        """
        if target_date is None:
            target_date = date.today()

        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT metric_value
                        FROM analytics
                        WHERE metric_name = :metric_name AND date = :date
                    """),
                    {"metric_name": metric_name, "date": target_date},
                )

                row = result.fetchone()
                if row:
                    metric_data = row[0]
                    if isinstance(metric_data, str):
                        return json.loads(metric_data)
                    else:
                        return metric_data
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения метрики {metric_name}: {e}")
            return None

    def get_metrics_period(self, metric_name: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        """
        Получить метрики за период

        Args:
            metric_name: Название метрики
            start_date: Начальная дата
            end_date: Конечная дата

        Returns:
            Список метрик за период
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT date, metric_value
                        FROM analytics
                        WHERE metric_name = :metric_name
                        AND date >= :start_date
                        AND date <= :end_date
                        ORDER BY date DESC
                    """),
                    {"metric_name": metric_name, "start_date": start_date, "end_date": end_date},
                )

                metrics = []
                for row in result:
                    metric_data = row[1]
                    if isinstance(metric_data, str):
                        data = json.loads(metric_data)
                    else:
                        data = metric_data

                    metrics.append({"date": row[0], "data": data})
                return metrics

        except Exception as e:
            logger.error(f"❌ Ошибка получения метрик {metric_name} за период: {e}")
            return []

    def get_latest_metric(self, metric_name: str) -> dict[str, Any] | None:
        """
        Получить последнюю метрику по названию

        Args:
            metric_name: Название метрики

        Returns:
            Dict с данными последней метрики или None
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT metric_value
                        FROM analytics
                        WHERE metric_name = :metric_name
                        ORDER BY date DESC
                        LIMIT 1
                    """),
                    {"metric_name": metric_name},
                )

                row = result.fetchone()
                if row:
                    metric_data = row[0]
                    if isinstance(metric_data, str):
                        return json.loads(metric_data)
                    else:
                        return metric_data
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка получения последней метрики {metric_name}: {e}")
            return None

    def collect_daily_user_activity(self) -> bool:
        """
        Собрать ежедневную статистику активности пользователей

        Returns:
            bool: True если успешно собрано
        """
        try:
            with self.engine.connect() as conn:
                # Подсчитываем активных пользователей за сегодня
                today = date.today()

                # Общее количество пользователей
                total_users_result = conn.execute(text("SELECT COUNT(*) FROM users"))
                total_users = total_users_result.scalar()

                # Новые пользователи за сегодня
                new_users_result = conn.execute(
                    text("SELECT COUNT(*) FROM users WHERE DATE(created_at_utc) = :today"), {"today": today}
                )
                new_users = new_users_result.scalar()

                # Пользователи с активностью за последние 24 часа (примерно)
                # Используем таблицу users с updated_at_utc как индикатор активности
                active_users_result = conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM users
                        WHERE updated_at_utc >= NOW() - INTERVAL '24 hours'
                    """)
                )
                active_users = active_users_result.scalar()

                # Статистика по типам чатов - используем bot_messages для групп
                group_chats_result = conn.execute(
                    text("""
                        SELECT COUNT(DISTINCT chat_id)
                        FROM bot_messages
                        WHERE created_at >= NOW() - INTERVAL '24 hours'
                    """)
                )
                group_chats = group_chats_result.scalar()

                # Для личных чатов используем разность
                private_chats = max(0, active_users - group_chats)

                # Сохраняем метрику
                metric_data = {
                    "total_users": total_users,
                    "new_users": new_users,
                    "returning_users": active_users - new_users,
                    "private_chats": private_chats,
                    "group_chats": group_chats,
                    "collected_at": datetime.now().isoformat(),
                }

                return self.save_metric("daily_user_activity", metric_data, "global", 0, today)

        except Exception as e:
            logger.error(f"❌ Ошибка сбора ежедневной активности пользователей: {e}")
            return False

    def collect_group_statistics(self) -> bool:
        """
        Собрать статистику по группам

        Returns:
            bool: True если успешно собрано
        """
        try:
            with self.engine.connect() as conn:
                today = date.today()

                # Общее количество групп
                total_groups_result = conn.execute(text("SELECT COUNT(*) FROM chat_settings"))
                total_groups = total_groups_result.scalar()

                # Активные группы (с активностью за последние 7 дней)
                active_groups_result = conn.execute(
                    text("""
                        SELECT COUNT(DISTINCT chat_id)
                        FROM bot_messages
                        WHERE created_at >= NOW() - INTERVAL '7 days'
                    """)
                )
                active_groups = active_groups_result.scalar()

                # Группы с созданными событиями
                groups_with_events_result = conn.execute(
                    text("""
                        SELECT COUNT(DISTINCT chat_id)
                        FROM events_community
                        WHERE created_at >= NOW() - INTERVAL '30 days'
                    """)
                )
                groups_with_events = groups_with_events_result.scalar()

                # Сохраняем метрику
                metric_data = {
                    "total_groups": total_groups,
                    "active_groups": active_groups,
                    "total_members": 0,  # Будем собирать отдельно
                    "active_members": 0,  # Будем собирать отдельно
                    "groups_with_events": groups_with_events,
                    "collected_at": datetime.now().isoformat(),
                }

                return self.save_metric("group_statistics", metric_data, "global", 0, today)

        except Exception as e:
            logger.error(f"❌ Ошибка сбора статистики групп: {e}")
            return False

    def get_dau_trend(self, days: int = 30) -> list[dict[str, Any]]:
        """
        Получить тренд DAU за последние N дней

        Args:
            days: Количество дней для анализа

        Returns:
            Список с данными DAU по дням
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        return self.get_metrics_period("daily_user_activity", start_date, end_date)

    def get_group_activity_summary(self) -> dict[str, Any]:
        """
        Получить сводку по активности групп

        Returns:
            Dict с данными активности групп
        """
        latest_metric = self.get_latest_metric("group_statistics")
        if not latest_metric:
            return {}

        return {
            "total_groups": latest_metric.get("total_groups", 0),
            "active_groups": latest_metric.get("active_groups", 0),
            "groups_with_events": latest_metric.get("groups_with_events", 0),
            "activity_rate": round(
                (latest_metric.get("active_groups", 0) / max(latest_metric.get("total_groups", 1), 1)) * 100, 2
            ),
        }

    def collect_group_activity(self, group_id: int, group_name: str = None) -> bool:
        """
        Собрать активность конкретной группы

        Args:
            group_id: ID группы
            group_name: Название группы (опционально)

        Returns:
            bool: True если успешно собрано
        """
        try:
            with self.engine.connect() as conn:
                today = date.today()

                # Получаем количество участников группы (примерно)
                # Это сложно получить точно без API Telegram, используем приблизительную оценку
                members_count = 0  # Будем собирать отдельно через API

                # Активные пользователи в группе за последние 7 дней
                # Используем приблизительную оценку через количество сообщений
                active_users_result = conn.execute(
                    text("""
                        SELECT COUNT(DISTINCT message_id)
                        FROM bot_messages
                        WHERE chat_id = :group_id
                        AND created_at >= NOW() - INTERVAL '7 days'
                    """),
                    {"group_id": group_id},
                )
                active_users = active_users_result.scalar() or 0

                # События созданные в группе за последние 30 дней
                events_created_result = conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM events_community
                        WHERE chat_id = :group_id
                        AND created_at >= NOW() - INTERVAL '30 days'
                    """),
                    {"group_id": group_id},
                )
                events_created = events_created_result.scalar() or 0

                # Команды использованные в группе за последние 7 дней
                # Используем количество сообщений как приблизительную оценку команд
                commands_used = active_users  # Приблизительная оценка

                # Сохраняем метрику
                metric_data = {
                    "group_name": group_name or f"Group {group_id}",
                    "members": members_count,
                    "active_users": active_users,
                    "events_created": events_created,
                    "commands_used": commands_used,
                    "collected_at": datetime.now().isoformat(),
                }

                return self.save_metric("group_activity", metric_data, "group", group_id, today)

        except Exception as e:
            logger.error(f"❌ Ошибка сбора активности группы {group_id}: {e}")
            return False

    def get_dau_data(self, days: int = 30) -> list[dict[str, Any]]:
        """
        Получить данные DAU за период

        Args:
            days: Количество дней для анализа

        Returns:
            Список с данными DAU по дням
        """
        try:
            with self.engine.connect() as conn:
                end_date = date.today()
                start_date = end_date - timedelta(days=days)

                result = conn.execute(
                    text("""
                        SELECT
                            date,
                            (metric_value->>'total_users')::INTEGER as total_users,
                            (metric_value->>'new_users')::INTEGER as new_users,
                            (metric_value->>'returning_users')::INTEGER as returning_users,
                            (metric_value->>'private_chats')::INTEGER as private_chats,
                            (metric_value->>'group_chats')::INTEGER as group_chats
                        FROM analytics
                        WHERE metric_name = 'daily_user_activity'
                        AND scope = 'global'
                        AND date >= :start_date
                        AND date <= :end_date
                        ORDER BY date DESC
                    """),
                    {"start_date": start_date, "end_date": end_date},
                )

                dau_data = []
                for row in result:
                    dau_data.append(
                        {
                            "date": row[0],
                            "total_users": row[1] or 0,
                            "new_users": row[2] or 0,
                            "returning_users": row[3] or 0,
                            "private_chats": row[4] or 0,
                            "group_chats": row[5] or 0,
                        }
                    )

                return dau_data

        except Exception as e:
            logger.error(f"❌ Ошибка получения данных DAU: {e}")
            return []

    def get_top_groups(self, limit: int = 10, target_date: date | None = None) -> list[dict[str, Any]]:
        """
        Получить топ активных групп

        Args:
            limit: Количество групп для возврата
            target_date: Дата для анализа (по умолчанию сегодня)

        Returns:
            Список с данными топ групп
        """
        if target_date is None:
            target_date = date.today()

        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT
                            target_id,
                            metric_value->>'group_name' as group_name,
                            (metric_value->>'active_users')::INTEGER as active_users,
                            (metric_value->>'events_created')::INTEGER as events_created,
                            (metric_value->>'commands_used')::INTEGER as commands_used
                        FROM analytics
                        WHERE metric_name = 'group_activity'
                        AND scope = 'group'
                        AND date = :target_date
                        ORDER BY (metric_value->>'active_users')::INTEGER DESC
                        LIMIT :limit
                    """),
                    {"target_date": target_date, "limit": limit},
                )

                top_groups = []
                for row in result:
                    top_groups.append(
                        {
                            "group_id": row[0],
                            "group_name": row[1] or f"Group {row[0]}",
                            "active_users": row[2] or 0,
                            "events_created": row[3] or 0,
                            "commands_used": row[4] or 0,
                        }
                    )

                return top_groups

        except Exception as e:
            logger.error(f"❌ Ошибка получения топ групп: {e}")
            return []

    def collect_all_metrics(self) -> dict[str, bool]:
        """
        Собрать все метрики за день

        Returns:
            Dict с результатами сбора каждой метрики
        """
        results = {}

        # Собираем общую активность пользователей
        results["daily_user_activity"] = self.collect_daily_user_activity()

        # Собираем статистику групп
        results["group_statistics"] = self.collect_group_statistics()

        # Собираем активность по каждой группе
        try:
            with self.engine.connect() as conn:
                # Получаем список всех групп
                groups_result = conn.execute(text("SELECT chat_id FROM chat_settings"))

                group_activity_success = 0
                total_groups = 0

                for row in groups_result:
                    group_id = row[0]
                    total_groups += 1

                    if self.collect_group_activity(group_id):
                        group_activity_success += 1

                results["group_activity"] = {
                    "success": group_activity_success,
                    "total": total_groups,
                    "success_rate": round((group_activity_success / max(total_groups, 1)) * 100, 1),
                }

        except Exception as e:
            logger.error(f"❌ Ошибка сбора активности групп: {e}")
            results["group_activity"] = {"success": 0, "total": 0, "success_rate": 0}

        return results
