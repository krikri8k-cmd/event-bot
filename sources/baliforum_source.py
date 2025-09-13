#!/usr/bin/env python3
"""
Источник событий из BaliForum
"""

import logging
from typing import Any

from sources.baliforum import fetch as fetch_baliforum_events

logger = logging.getLogger(__name__)


class BaliForumSource:
    """Источник событий из BaliForum"""

    def __init__(self):
        self.name = "baliforum"
        self.display_name = "BaliForum"

    @property
    def country_code(self) -> str:
        return "ID"

    def is_enabled(self) -> bool:
        """Проверяет, включен ли источник BaliForum"""
        import os

        return os.getenv("ENABLE_BALIFORUM", "0").strip() == "1"

    def get_metrics(self) -> dict:
        """Возвращает метрики источника"""
        return {}

    async def fetch_events(self, lat: float, lng: float, radius_km: float) -> list[dict[str, Any]]:
        """
        Получает события из BaliForum

        Args:
            lat: Широта
            lng: Долгота
            radius_km: Радиус поиска в км

        Returns:
            Список событий в формате для enhanced_event_search
        """
        try:
            logger.info(f"🌴 Ищем события в {self.display_name}...")

            # Получаем события из BaliForum
            raw_events = fetch_baliforum_events(limit=100)

            if not raw_events:
                logger.info(f"   ⚠️ {self.display_name} не вернул события")
                return []

            # Конвертируем RawEvent в формат для enhanced_event_search
            events = []
            for event in raw_events:
                try:
                    # Пропускаем события без координат
                    if not event.lat or not event.lng:
                        logger.debug(f"   ⚠️ Пропускаем событие без координат: {event.title}")
                        continue

                    # Проверяем, что событие в радиусе
                    distance = self._calculate_distance(lat, lng, event.lat, event.lng)
                    if distance > radius_km:
                        logger.debug(f"   ⚠️ Событие вне радиуса ({distance:.1f} км): {event.title}")
                        continue

                    events.append(
                        {
                            "type": "source",
                            "title": event.title,
                            "description": event.description or "",
                            "time_local": event.starts_at.strftime("%Y-%m-%d %H:%M") if event.starts_at else "",
                            "start_time": event.starts_at,
                            "venue": {
                                "name": "",  # BaliForum не всегда имеет venue
                                "address": "",
                                "lat": event.lat,
                                "lon": event.lng,
                            },
                            "source_url": event.url or "",
                            "lat": event.lat,
                            "lng": event.lng,
                            "source": self.name,
                            "distance_km": round(distance, 2),
                        }
                    )
                except Exception as e:
                    logger.warning(f"   ⚠️ Ошибка при обработке события '{event.title}': {e}")
                    continue

            if events:
                logger.info(f"   ✅ Найдено {len(events)} событий в {self.display_name}")
            else:
                logger.info(f"   ⚠️ {self.display_name} не вернул событий в радиусе {radius_km}км")

            return events

        except Exception as e:
            logger.error(f"   ❌ Ошибка при поиске в {self.display_name}: {e}")
            return []

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Вычисляет расстояние между двумя точками в км (упрощенная версия)"""
        from math import asin, cos, radians, sin, sqrt

        # Конвертируем в радианы
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])

        # Формула Haversine
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
        c = 2 * asin(sqrt(a))

        # Радиус Земли в км
        r = 6371
        return c * r
