#!/usr/bin/env python3
"""
Реестр источников событий
"""

import logging

from sources.base import BaseSource, registry

logger = logging.getLogger(__name__)


def register_all_sources() -> None:
    """Регистрирует все доступные источники"""

    # Регистрируем существующие источники
    try:
        from sources.baliforum_source import BaliForumSource

        baliforum = BaliForumSource()
        registry.register(baliforum)
        logger.info(f"✅ Зарегистрирован источник: {baliforum.display_name}")
    except ImportError as e:
        logger.warning(f"⚠️ Не удалось загрузить BaliForum: {e}")

    # Регистрируем KudaGo (если доступен)
    try:
        from sources.kudago_source import KudaGoSource

        kudago = KudaGoSource()
        registry.register(kudago)
        logger.info(f"✅ Зарегистрирован источник: {kudago.display_name}")
    except ImportError as e:
        logger.debug(f"KudaGo недоступен: {e}")

    # Здесь можно добавить другие источники
    # try:
    #     from sources.russia_source import RussiaSource
    #     russia = RussiaSource()
    #     registry.register(russia)
    #     logger.info(f"✅ Зарегистрирован источник: {russia.display_name}")
    # except ImportError as e:
    #     logger.debug(f"Russia источник недоступен: {e}")


def get_enabled_sources() -> list[BaseSource]:
    """Возвращает список включенных источников"""
    return registry.get_enabled_sources()


def get_sources_by_country(country_code: str) -> list[BaseSource]:
    """Возвращает источники для конкретной страны"""
    return registry.get_sources_by_country(country_code)


def get_source_metrics() -> dict[str, dict]:
    """Возвращает метрики всех источников"""
    return registry.get_metrics()


def list_available_sources() -> list[str]:
    """Возвращает список всех доступных источников"""
    return registry.list_sources()


def is_source_enabled(source_name: str) -> bool:
    """Проверяет, включен ли источник"""
    source = registry.get_source(source_name)
    return source.is_enabled() if source else False


# Автоматическая регистрация при импорте
register_all_sources()
