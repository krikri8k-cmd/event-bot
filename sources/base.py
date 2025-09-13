#!/usr/bin/env python3
"""
Базовый интерфейс для источников событий
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseSource(ABC):
    """Базовый интерфейс для всех источников событий"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Уникальное имя источника"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Человекочитаемое название источника"""
        pass

    @property
    @abstractmethod
    def country_code(self) -> str:
        """Код страны источника (RU, ID, etc.)"""
        pass

    @abstractmethod
    async def fetch_events(self, lat: float, lng: float, radius_km: float) -> list[dict[str, Any]]:
        """
        Получает события из источника

        Args:
            lat: Широта пользователя
            lng: Долгота пользователя
            radius_km: Радиус поиска в км

        Returns:
            Список событий в стандартном формате
        """
        pass

    def normalize_event(self, raw_event: dict[str, Any]) -> dict[str, Any]:
        """
        Нормализует событие из источника в стандартный формат

        Args:
            raw_event: Сырое событие из источника

        Returns:
            Нормализованное событие
        """
        # Базовая нормализация
        normalized = {
            "type": "source",
            "source": self.name,
            "country_code": self.country_code,
            "title": str(raw_event.get("title", "")).strip(),
            "description": str(raw_event.get("description", "")).strip(),
            "time_local": raw_event.get("time_local", ""),
            "start_time": raw_event.get("start_time"),
            "lat": raw_event.get("lat"),
            "lng": raw_event.get("lng"),
            "venue": {
                "name": str(raw_event.get("venue_name", "")).strip(),
                "address": str(raw_event.get("address", "")).strip(),
                "lat": raw_event.get("lat"),
                "lon": raw_event.get("lng"),
            },
            "source_url": raw_event.get("source_url", ""),
            "distance_km": raw_event.get("distance_km"),
        }

        return normalized

    def is_enabled(self) -> bool:
        """
        Проверяет, включен ли источник
        По умолчанию проверяет ENV переменную {NAME}_ENABLED
        """
        import os

        env_var = f"{self.name.upper()}_ENABLED"
        return os.getenv(env_var, "false").lower() == "true"

    def get_metrics(self) -> dict[str, Any]:
        """
        Возвращает метрики источника
        По умолчанию пустой словарь
        """
        return {}


class SourceRegistry:
    """Реестр источников событий"""

    def __init__(self):
        self._sources: dict[str, BaseSource] = {}

    def register(self, source: BaseSource) -> None:
        """Регистрирует источник"""
        self._sources[source.name] = source

    def get_source(self, name: str) -> BaseSource | None:
        """Получает источник по имени"""
        return self._sources.get(name)

    def get_enabled_sources(self) -> list[BaseSource]:
        """Возвращает список включенных источников"""
        return [source for source in self._sources.values() if source.is_enabled()]

    def get_sources_by_country(self, country_code: str) -> list[BaseSource]:
        """Возвращает источники для конкретной страны"""
        return [
            source for source in self._sources.values() if source.country_code == country_code and source.is_enabled()
        ]

    def list_sources(self) -> list[str]:
        """Возвращает список всех зарегистрированных источников"""
        return list(self._sources.keys())

    def get_metrics(self) -> dict[str, dict[str, Any]]:
        """Возвращает метрики всех источников"""
        return {name: source.get_metrics() for name, source in self._sources.items()}


# Глобальный реестр источников
registry = SourceRegistry()


def register_source(source: BaseSource) -> None:
    """Удобная функция для регистрации источника"""
    registry.register(source)


def get_registry() -> SourceRegistry:
    """Возвращает глобальный реестр источников"""
    return registry
