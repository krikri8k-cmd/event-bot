#!/usr/bin/env python3
"""
Источник событий из BaliForum
"""

import logging
import time
from typing import Any

from sources.baliforum import fetch as fetch_baliforum_events
from utils.structured_logging import StructuredLogger

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
        start_time = time.time()
        parsed = 0
        skipped_no_time_count = 0
        skipped_no_coords = 0
        errors = 0

        try:
            logger.info(f"🌴 Ищем события в {self.display_name}...")

            # Получаем события из BaliForum
            raw_events = fetch_baliforum_events(limit=100)
            parsed = len(raw_events) if raw_events else 0

            if not raw_events:
                StructuredLogger.log_ingest(
                    source="baliforum",
                    region="bali",
                    parsed=0,
                    skipped_no_time=0,
                    skipped_no_coords=0,
                    upserted=0,
                    updated=0,
                    duration_ms=(time.time() - start_time) * 1000,
                    errors=0,
                )
                return []

            # Конвертируем RawEvent в формат для enhanced_event_search
            events = []
            for event in raw_events:
                try:
                    # Пропускаем события без времени
                    if not event.starts_at:
                        skipped_no_time_count += 1
                        continue

                    # Пропускаем события без координат
                    if not event.lat or not event.lng:
                        skipped_no_coords += 1
                        continue

                    # ВАЖНО: НЕ фильтруем по радиусу при парсинге!
                    # Все события с координатами сохраняются в БД, фильтрация по радиусу
                    # происходит при поиске пользователем. Это позволяет сохранять больше событий
                    # и показывать их пользователям с разными радиусами поиска.
                    distance = self._calculate_distance(lat, lng, event.lat, event.lng)

                    # Извлекаем venue и location_url из _raw_data если есть
                    venue_name = ""
                    location_url = ""
                    if hasattr(event, "_raw_data") and event._raw_data:
                        venue_name = event._raw_data.get("venue", "") or ""
                        location_url = event._raw_data.get("location_url", "") or ""

                    events.append(
                        {
                            "type": "source",
                            "title": event.title,
                            "description": event.description or "",
                            "time_local": event.starts_at.strftime("%Y-%m-%d %H:%M") if event.starts_at else "",
                            "start_time": event.starts_at,
                            "venue": {
                                "name": venue_name,  # Используем venue из парсера
                                "address": venue_name,  # Используем venue как address
                                "lat": event.lat,
                                "lon": event.lng,
                            },
                            "source_url": event.url or "",
                            "location_url": location_url,  # Сохраняем ссылку Google Maps
                            "lat": event.lat,
                            "lng": event.lng,
                            "source": self.name,
                            "distance_km": round(distance, 2),
                        }
                    )
                except Exception as e:
                    errors += 1
                    logger.warning(f"   ⚠️ Ошибка при обработке события '{event.title}': {e}")
                    continue

            # Логируем результат
            StructuredLogger.log_ingest(
                source="baliforum",
                region="bali",
                parsed=parsed,
                skipped_no_time=skipped_no_time_count,
                skipped_no_coords=skipped_no_coords,
                upserted=len(events),
                updated=0,
                duration_ms=(time.time() - start_time) * 1000,
                errors=errors,
            )

            if events:
                logger.info(f"   ✅ Найдено {len(events)} событий в {self.display_name}")
            else:
                logger.info(f"   ⚠️ {self.display_name} не вернул событий")

            return events

        except Exception as e:
            errors += 1
            StructuredLogger.log_ingest(
                source="baliforum",
                region="bali",
                parsed=parsed,
                skipped_no_time=skipped_no_time_count,
                skipped_no_coords=skipped_no_coords,
                upserted=0,
                updated=0,
                duration_ms=(time.time() - start_time) * 1000,
                errors=errors,
            )
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
