"""
PlaceResolver - сервис для получения названий мест через Google Places API

Использует новый Places API (New) вместо legacy API.
Поддерживает кэширование результатов.
"""

import logging

import httpx
from sqlalchemy import text

from config import load_settings

logger = logging.getLogger(__name__)


class PlaceResolver:
    """
    Резолвер для получения информации о местах через Google Places API
    """

    def __init__(self, engine=None):
        self.settings = load_settings()
        self.api_key = self.settings.google_maps_api_key
        self.base_url = "https://places.googleapis.com/v1"
        self.engine = engine  # Для доступа к кэшу

    async def _get_from_cache(self, place_id: str) -> dict | None:
        """Получает данные из кэша"""
        if not self.engine or not place_id:
            return None

        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT name, lat, lng
                    FROM places_cache
                    WHERE place_id = :place_id
                """)
                result = conn.execute(query, {"place_id": place_id}).fetchone()
                if result:
                    return {
                        "name": result[0],
                        "lat": result[1],
                        "lng": result[2],
                        "place_id": place_id,
                        "from_cache": True,
                    }
        except Exception as e:
            logger.debug(f"Ошибка при чтении из кэша для {place_id}: {e}")
        return None

    async def _save_to_cache(self, place_id: str, name: str, lat: float | None = None, lng: float | None = None):
        """Сохраняет данные в кэш"""
        if not self.engine or not place_id or not name:
            return

        try:
            with self.engine.begin() as conn:
                query = text("""
                    INSERT INTO places_cache (place_id, name, lat, lng, updated_at)
                    VALUES (:place_id, :name, :lat, :lng, NOW())
                    ON CONFLICT (place_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        lat = EXCLUDED.lat,
                        lng = EXCLUDED.lng,
                        updated_at = NOW()
                """)
                conn.execute(query, {"place_id": place_id, "name": name, "lat": lat, "lng": lng})
        except Exception as e:
            logger.debug(f"Ошибка при сохранении в кэш для {place_id}: {e}")

    async def get_place_details(self, place_id: str, use_cache: bool = True) -> dict | None:
        """
        Получает детали места через новый Places API (New)

        Args:
            place_id: Google Place ID (например, ChIJ5-9aH_dH0i0RpGbL2MaAp9k)
            use_cache: Использовать кэш (по умолчанию True)

        Returns:
            dict с ключами: name, lat, lng, place_id или None если не удалось получить
        """
        if not self.api_key:
            logger.warning("Google Maps API key не установлен")
            return None

        if not place_id:
            return None

        # Проверяем кэш
        if use_cache:
            cached = await self._get_from_cache(place_id)
            if cached:
                logger.debug(f"Получено из кэша для place_id {place_id}: {cached.get('name')}")
                return cached

        try:
            url = f"{self.base_url}/places/{place_id}"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
            }
            params = {
                "fields": "displayName,location",
            }

            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                # Новый API возвращает данные в другом формате
                name = None
                if "displayName" in data:
                    display_name = data["displayName"]
                    if isinstance(display_name, dict):
                        name = display_name.get("text", "")
                    else:
                        name = str(display_name)

                lat = None
                lng = None
                if "location" in data:
                    location = data["location"]
                    lat = location.get("latitude")
                    lng = location.get("longitude")

                if name:
                    result = {"name": name, "place_id": place_id}
                    if lat is not None and lng is not None:
                        result["lat"] = lat
                        result["lng"] = lng
                    # Сохраняем в кэш
                    await self._save_to_cache(place_id, name, lat, lng)
                    return result
                else:
                    logger.warning(f"Places API вернул данные без названия для place_id {place_id}")
                    return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Место с place_id {place_id} не найдено")
            else:
                logger.warning(f"HTTP ошибка при получении деталей места {place_id}: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении деталей места {place_id}: {e}")
            return None

    async def nearby_search(
        self, lat: float, lng: float, radius_meters: int = 50, types: str = "establishment"
    ) -> dict | None:
        """
        Ищет ближайшее заведение через Nearby Search API

        Args:
            lat: Широта
            lng: Долгота
            radius_meters: Радиус поиска в метрах (по умолчанию 50м)
            types: Типы заведений (establishment, restaurant, bar и т.д.)

        Returns:
            dict с ключами: name, lat, lng, place_id ближайшего заведения или None
        """
        if not self.api_key:
            logger.warning("Google Maps API key не установлен")
            return None

        try:
            # Используем legacy Nearby Search API (он работает и включен)
            # Новый API требует другой формат и может быть не включен
            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                "location": f"{lat},{lng}",
                "radius": radius_meters,
                "type": types,
                "key": self.api_key,
            }

            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("status") == "OK" and data.get("results"):
                    # Берем ближайшее заведение
                    place = data["results"][0]
                    name = place.get("name", "")
                    place_id = place.get("place_id", "")

                    if name and place_id:
                        result = {"name": name, "place_id": place_id}
                        geometry = place.get("geometry", {})
                        location = geometry.get("location", {})
                        if location:
                            result["lat"] = location.get("lat")
                            result["lng"] = location.get("lng")
                        # Сохраняем в кэш
                        await self._save_to_cache(place_id, name, result.get("lat"), result.get("lng"))
                        return result
                else:
                    logger.debug(
                        f"Nearby Search не нашел заведений для ({lat}, {lng}): " f"status={data.get('status')}"
                    )
                    return None

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP ошибка при Nearby Search для ({lat}, {lng}): {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при Nearby Search для ({lat}, {lng}): {e}")
            return None

    async def resolve(
        self, place_id: str | None = None, lat: float | None = None, lng: float | None = None
    ) -> dict | None:
        """
        Универсальный метод для получения названия места

        Приоритет:
        1. Если есть place_id → Place Details API
        2. Если есть координаты → Nearby Search
        3. Иначе → None

        Args:
            place_id: Google Place ID
            lat: Широта
            lng: Долгота

        Returns:
            dict с ключами: name, lat, lng, place_id или None
        """
        # Приоритет 1: Place Details по place_id
        if place_id:
            result = await self.get_place_details(place_id)
            if result:
                result["place_id"] = place_id
                return result

        # Приоритет 2: Nearby Search по координатам
        if lat is not None and lng is not None:
            # Пробуем разные типы заведений
            types_list = ["establishment", "restaurant", "bar", "cafe", "point_of_interest"]
            for place_type in types_list:
                result = await self.nearby_search(lat, lng, radius_meters=50, types=place_type)
                if result:
                    return result

        return None
