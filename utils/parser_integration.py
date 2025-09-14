"""
Интеграция парсеров с базой данных
"""

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from database import get_engine
from utils.simple_timezone import get_city_from_coordinates
from utils.unified_events_service import UnifiedEventsService

logger = logging.getLogger(__name__)


class ParserIntegration:
    """Интеграция парсеров с базой данных"""

    def __init__(self):
        self.engine = get_engine()
        self.events_service = UnifiedEventsService(self.engine)

    async def save_parser_events(self, events: list[dict[str, Any]], source: str) -> int:
        """
        Сохраняет парсерные события в БД

        Args:
            events: Список событий от парсера
            source: Источник событий (baliforum, kudago, ai)

        Returns:
            Количество сохраненных событий
        """
        saved_count = 0

        for event in events:
            try:
                # Извлекаем данные события
                title = event.get("title", "")
                description = event.get("description", "")
                lat = event.get("lat")
                lng = event.get("lng")
                url = event.get("source_url", event.get("url", ""))

                # Пропускаем события без координат
                if not lat or not lng:
                    logger.debug(f"Пропускаем событие без координат: {title}")
                    continue

                # Определяем город по координатам
                city = get_city_from_coordinates(lat, lng)

                # Извлекаем external_id из URL
                external_id = self._extract_external_id(url, source)

                # Конвертируем время в UTC
                starts_at_utc = self._convert_time_to_utc(event, city)

                # Извлекаем место
                venue = event.get("venue", {})
                location_name = venue.get("name", "")
                location_url = venue.get("address", "")

                # Сохраняем событие
                event_id = self.events_service.save_parser_event(
                    source=source,
                    external_id=external_id,
                    title=title,
                    description=description,
                    starts_at_utc=starts_at_utc,
                    city=city,
                    lat=lat,
                    lng=lng,
                    location_name=location_name,
                    location_url=location_url,
                    url=url,
                )

                saved_count += 1
                logger.info(f"Сохранено событие ID {event_id}: {title}")

            except Exception as e:
                logger.error(f"Ошибка при сохранении события '{event.get('title', 'Unknown')}': {e}")
                continue

        logger.info(f"Сохранено {saved_count} событий из источника {source}")
        return saved_count

    def _extract_external_id(self, url: str, source: str) -> str:
        """Извлекает external_id из URL"""
        if not url:
            return f"{source}_unknown_{datetime.now().timestamp()}"

        try:
            # Для BaliForum извлекаем ID из пути
            if source == "baliforum":
                parsed = urlparse(url)
                path_parts = parsed.path.strip("/").split("/")
                if len(path_parts) >= 2 and path_parts[0] == "events":
                    return path_parts[1]  # ID события

            # Для других источников используем хэш URL
            import hashlib

            return hashlib.md5(url.encode()).hexdigest()[:16]

        except Exception:
            return f"{source}_{datetime.now().timestamp()}"

    def _convert_time_to_utc(self, event: dict[str, Any], city: str) -> datetime:
        """Конвертирует время события в UTC"""
        try:
            # Пробуем разные поля времени
            start_time = event.get("start_time")
            time_local = event.get("time_local")

            if start_time and isinstance(start_time, datetime):
                # Если уже datetime, проверяем timezone
                if start_time.tzinfo is None:
                    # Нет timezone, считаем что это локальное время города
                    from utils.simple_timezone import get_timezone_for_city

                    tz = get_timezone_for_city(city)
                    start_time = start_time.replace(tzinfo=tz)

                return start_time.astimezone(UTC)

            elif time_local:
                # Парсим строку времени
                from utils.simple_timezone import get_timezone_for_city

                tz = get_timezone_for_city(city)

                # Пробуем разные форматы
                for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        dt = datetime.strptime(time_local, fmt)
                        dt = dt.replace(tzinfo=tz)
                        return dt.astimezone(UTC)
                    except ValueError:
                        continue

            # Если не удалось распарсить, используем текущее время
            logger.warning(f"Не удалось распарсить время для события: {event.get('title', 'Unknown')}")
            return datetime.now(UTC)

        except Exception as e:
            logger.error(f"Ошибка при конвертации времени: {e}")
            return datetime.now(UTC)

    async def run_parsers_and_save(self, lat: float, lng: float, radius_km: float = 15) -> dict[str, int]:
        """
        Запускает все парсеры и сохраняет события в БД

        Args:
            lat: Широта
            lng: Долгота
            radius_km: Радиус поиска

        Returns:
            Словарь с количеством сохраненных событий по источникам
        """
        results = {}

        # BaliForum парсер
        try:
            from sources.baliforum_source import BaliForumSource

            baliforum_source = BaliForumSource()
            if baliforum_source.is_enabled():
                logger.info("🌴 Запускаем BaliForum парсер...")
                events = await baliforum_source.fetch_events(lat, lng, radius_km)
                saved_count = await self.save_parser_events(events, "baliforum")
                results["baliforum"] = saved_count
            else:
                logger.info("🌴 BaliForum отключен")
                results["baliforum"] = 0

        except Exception as e:
            logger.error(f"Ошибка при парсинге BaliForum: {e}")
            results["baliforum"] = 0

        # AI парсер (если включен)
        try:
            import os

            if os.getenv("AI_GENERATE_SYNTHETIC", "0").strip() == "1":
                from ai_utils import fetch_ai_events_nearby

                logger.info("🤖 Запускаем AI парсер...")
                events = await fetch_ai_events_nearby(lat, lng)
                saved_count = await self.save_parser_events(events, "ai")
                results["ai"] = saved_count
            else:
                logger.info("🤖 AI генерация отключена")
                results["ai"] = 0

        except Exception as e:
            logger.error(f"Ошибка при AI парсинге: {e}")
            results["ai"] = 0

        # KudaGo парсер (если есть)
        try:
            from sources.kudago_source import KudaGoSource

            kudago_source = KudaGoSource()
            if kudago_source.is_enabled():
                logger.info("🎭 Запускаем KudaGo парсер...")
                events = await kudago_source.fetch_events(lat, lng, radius_km)
                saved_count = await self.save_parser_events(events, "kudago")
                results["kudago"] = saved_count
            else:
                logger.info("🎭 KudaGo отключен")
                results["kudago"] = 0

        except Exception as e:
            logger.error(f"Ошибка при парсинге KudaGo: {e}")
            results["kudago"] = 0

        total_saved = sum(results.values())
        logger.info(f"🎯 Всего сохранено {total_saved} парсерных событий")

        return results
