"""PR0/PR1: telegram ingest foundation."""

import pytest

from utils.event_category_manager import EventCategoryManager

pytestmark = pytest.mark.no_db


def test_telegram_categories_from_llm():
    mgr = EventCategoryManager()
    cats = mgr.assign_categories({"categories": ["party", "Йога"]}, "telegram")
    assert "Вечеринка" in cats
    assert "Духовное" in cats


def test_telegram_categories_fallback_default():
    mgr = EventCategoryManager()
    cats = mgr.assign_categories(
        {"categories": [], "default_categories": ["Концерт"]},
        "telegram",
    )
    assert cats == ["Концерт"]


def test_telegram_raw_category():
    mgr = EventCategoryManager()
    raw = mgr.resolve_raw_category({"categories": ["Вечеринка", "Игра"]}, "telegram")
    assert raw == "Вечеринка, Игра"
