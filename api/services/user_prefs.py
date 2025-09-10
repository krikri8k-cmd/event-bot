#!/usr/bin/env python3
"""
Сервис для работы с настройками пользователей
"""

import logging
from typing import Any

from sqlalchemy import text

from database import get_session

logger = logging.getLogger(__name__)


def get_user_prefs(telegram_user_id: int) -> dict[str, Any] | None:
    """Получает настройки пользователя."""
    try:
        with get_session() as session:
            row = (
                session.execute(
                    text(
                        "SELECT telegram_user_id, lat, lon, radius_km, city, country "
                        "FROM user_prefs WHERE telegram_user_id = :uid"
                    ),
                    {"uid": telegram_user_id},
                )
                .mappings()
                .first()
            )

            if row:
                return dict(row)
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении настроек пользователя {telegram_user_id}: {e}")
        return None


def upsert_user_location(telegram_user_id: int, lat: float, lon: float, city: str = None, country: str = None) -> bool:
    """Обновляет или создает локацию пользователя."""
    try:
        with get_session() as session:
            session.execute(
                text("""
                INSERT INTO user_prefs(telegram_user_id, lat, lon, city, country)
                VALUES (:uid, :lat, :lon, :city, :country)
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                  lat = EXCLUDED.lat,
                  lon = EXCLUDED.lon,
                  city = EXCLUDED.city,
                  country = EXCLUDED.country,
                  updated_at = NOW()
            """),
                {"uid": telegram_user_id, "lat": lat, "lon": lon, "city": city, "country": country},
            )
            session.commit()
            logger.info(f"Локация пользователя {telegram_user_id} обновлена: ({lat}, {lon})")
            return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении локации пользователя {telegram_user_id}: {e}")
        return False


def set_user_radius(telegram_user_id: int, radius_km: float) -> bool:
    """Устанавливает радиус поиска для пользователя."""
    try:
        with get_session() as session:
            session.execute(
                text("""
                INSERT INTO user_prefs(telegram_user_id, radius_km)
                VALUES (:uid, :r)
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                  radius_km = EXCLUDED.radius_km,
                  updated_at = NOW()
            """),
                {"uid": telegram_user_id, "r": float(radius_km)},
            )
            session.commit()
            logger.info(f"Радиус пользователя {telegram_user_id} установлен: {radius_km} км")
            return True
    except Exception as e:
        logger.error(f"Ошибка при установке радиуса пользователя {telegram_user_id}: {e}")
        return False


def delete_user_prefs(telegram_user_id: int) -> bool:
    """Удаляет настройки пользователя."""
    try:
        with get_session() as session:
            session.execute(
                text("DELETE FROM user_prefs WHERE telegram_user_id = :uid"),
                {"uid": telegram_user_id},
            )
            session.commit()
            logger.info(f"Настройки пользователя {telegram_user_id} удалены")
            return True
    except Exception as e:
        logger.error(f"Ошибка при удалении настроек пользователя {telegram_user_id}: {e}")
        return False
