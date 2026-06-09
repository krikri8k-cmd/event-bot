import pytest

from utils.event_category_manager import EventCategoryManager, dedupe_categories, normalize_tag
from utils.unified_events_service import _parse_categories_value, _search_row_to_event_dict


@pytest.mark.no_db
def test_normalize_tag():
    assert normalize_tag("  Фестиваль ") == "фестиваль"


@pytest.mark.no_db
def test_baliforum_festival_art_maps_to_exhibition():
    manager = EventCategoryManager()
    categories = manager.assign_categories({"tags": ["Фестиваль", "Искусство"]}, "baliforum")
    assert categories == ["Выставка"]


@pytest.mark.no_db
def test_baliforum_dedupes_categories():
    manager = EventCategoryManager()
    categories = manager.assign_categories({"tags": ["выставка", "искусство", "фестиваль"]}, "baliforum")
    assert categories == ["Выставка"]


@pytest.mark.no_db
def test_baliforum_multiple_categories():
    manager = EventCategoryManager()
    categories = manager.assign_categories({"tags": ["Бизнес", "еда"]}, "baliforum")
    assert categories == ["Бизнес", "Еда"]


@pytest.mark.no_db
def test_baliforum_unknown_tags_return_empty():
    manager = EventCategoryManager()
    categories = manager.assign_categories({"tags": ["Семья", "Игра"]}, "baliforum")
    assert categories == []


@pytest.mark.no_db
def test_user_and_community_return_empty():
    manager = EventCategoryManager()
    assert manager.assign_categories({"title": "Meetup"}, "user") == []
    assert manager.assign_categories({"title": "Group event"}, "community") == []


@pytest.mark.no_db
def test_future_api_source_uses_raw_api_category():
    manager = EventCategoryManager()
    categories = manager.assign_categories({"raw_api_category": "Nightlife"}, "megatix")
    assert categories == ["Nightlife"]


@pytest.mark.no_db
def test_resolve_raw_category_baliforum():
    manager = EventCategoryManager()
    raw = manager.resolve_raw_category({"tags": ["Фестиваль", "Искусство"]}, "baliforum")
    assert raw == "Фестиваль, Искусство"


@pytest.mark.no_db
def test_dedupe_categories_helper():
    assert dedupe_categories(["Выставка", "Бизнес", "Выставка"]) == ["Выставка", "Бизнес"]


@pytest.mark.no_db
def test_parse_categories_value():
    assert _parse_categories_value('["Выставка"]') == ["Выставка"]
    assert _parse_categories_value(["Бизнес", "Еда"]) == ["Бизнес", "Еда"]
    assert _parse_categories_value(None) == []


@pytest.mark.no_db
def test_search_row_to_event_dict_includes_categories():
    row = (
        "baliforum",
        1,
        "Fest",
        None,
        None,
        None,
        None,
        None,
        "bali",
        -8.5,
        115.2,
        "Venue",
        None,
        "https://example.com",
        None,
        None,
        None,
        0,
        "open",
        None,
        None,
        None,
        "Venue",
        "Venue",
        None,
        "",
        None,
        None,
        "start",
        ["Выставка"],
        "Фестиваль, Искусство",
    )
    event = _search_row_to_event_dict(row)
    assert event["categories"] == ["Выставка"]
    assert event["raw_category"] == "Фестиваль, Искусство"
