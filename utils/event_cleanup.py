"""
Утилиты для очистки событий по датам
"""

from datetime import UTC, datetime

from sqlalchemy import text


def cleanup_old_events(engine, region: str = "bali") -> int:
    """
    Очищает события после наступления следующего дня

    Args:
        engine: SQLAlchemy engine
        region: Регион для определения часового пояса

    Returns:
        Количество удаленных событий
    """
    from utils.time_window import REGION_TZ

    if region not in REGION_TZ:
        raise ValueError(f"Unknown region: {region}")

    tz = REGION_TZ[region]
    now_local = datetime.now(tz)

    # События старше сегодняшнего дня
    cutoff_date = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_utc = cutoff_date.astimezone(UTC)

    with engine.connect() as conn:
        # Удаляем старые пользовательские события
        user_deleted = conn.execute(
            text("""
            DELETE FROM events_user
            WHERE starts_at < :cutoff_utc
        """),
            {"cutoff_utc": cutoff_utc},
        ).rowcount

        # Удаляем старые парсерные события из объединенной таблицы events
        parser_deleted = conn.execute(
            text("""
            DELETE FROM events
            WHERE starts_at < :cutoff_utc
            AND source IS NOT NULL
        """),
            {"cutoff_utc": cutoff_utc},
        ).rowcount

        # Удаляем старые события из объединенной таблицы
        events_deleted = conn.execute(
            text("""
            DELETE FROM events
            WHERE starts_at < :cutoff_utc
        """),
            {"cutoff_utc": cutoff_utc},
        ).rowcount

        conn.commit()

        total_deleted = user_deleted + parser_deleted + events_deleted

        print("🧹 Очистка событий завершена:")
        print(f"   📊 Удалено пользовательских: {user_deleted}")
        print(f"   📊 Удалено парсерных: {parser_deleted}")
        print(f"   📊 Удалено из events: {events_deleted}")
        print(f"   📊 Всего удалено: {total_deleted}")
        print(f"   🕒 Дата отсечения: {cutoff_utc} (UTC)")

        return total_deleted


def get_active_events_count(engine, region: str = "bali") -> dict:
    """
    Получает количество активных событий по типам

    Args:
        engine: SQLAlchemy engine
        region: Регион

    Returns:
        Словарь с количеством событий по типам
    """
    from utils.time_window import today_window_utc_for

    start_utc, end_utc = today_window_utc_for(region)

    with engine.connect() as conn:
        # Пользовательские события
        user_count = conn.execute(
            text("""
            SELECT COUNT(*) FROM events_user
            WHERE starts_at BETWEEN :start_utc AND :end_utc
        """),
            {"start_utc": start_utc, "end_utc": end_utc},
        ).fetchone()[0]

        # Парсерные события (из объединенной таблицы events)
        parser_count = conn.execute(
            text("""
            SELECT COUNT(*) FROM events
            WHERE starts_at BETWEEN :start_utc AND :end_utc
            AND source IS NOT NULL
        """),
            {"start_utc": start_utc, "end_utc": end_utc},
        ).fetchone()[0]

        # Объединенные события
        events_count = conn.execute(
            text("""
            SELECT COUNT(*) FROM events
            WHERE starts_at BETWEEN :start_utc AND :end_utc
        """),
            {"start_utc": start_utc, "end_utc": end_utc},
        ).fetchone()[0]

        return {
            "user_events": user_count,
            "parser_events": parser_count,
            "total_events": events_count,
            "date_range": f"{start_utc} - {end_utc}",
        }


def cleanup_old_moments(engine) -> int:
    """
    Очищает истекшие моменты

    Args:
        engine: SQLAlchemy engine

    Returns:
        Количество удаленных моментов
    """
    now_utc = datetime.now(UTC)

    with engine.connect() as conn:
        deleted = conn.execute(
            text("""
            DELETE FROM moments
            WHERE expires_at < :now_utc OR is_active = false
        """),
            {"now_utc": now_utc},
        ).rowcount

        conn.commit()

        print("⚡ Очистка моментов завершена:")
        print(f"   📊 Удалено истекших моментов: {deleted}")

        return deleted
