import pytest

from utils.event_category_manager import (
    BALIFORUM_KNOWN_TAGS,
    BALIFORUM_TAG_EN_MAP,
    EventCategoryManager,
    dedupe_categories,
    format_source_display_tags,
    localize_baliforum_tags,
    normalize_tag,
    parse_source_display_tags,
)
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
def test_baliforum_dukhovnoe_and_meditation_map_to_spiritual():
    manager = EventCategoryManager()
    assert manager.assign_categories({"tags": ["Духовное"]}, "baliforum") == ["Духовное"]
    assert manager.assign_categories({"tags": ["Медитация", "Тренинг"]}, "baliforum") == ["Духовное"]


@pytest.mark.no_db
def test_localize_baliforum_tags_en():
    assert localize_baliforum_tags(["Фестиваль", "Музыка"], "en") == ["Festival", "Music"]
    assert localize_baliforum_tags(["Фестиваль", "Музыка"], "ru") == ["Фестиваль", "Музыка"]
    assert localize_baliforum_tags(["Неизвестный тег"], "en") == ["Неизвестный тег"]
    assert localize_baliforum_tags(["Йога", "Здоровье"], "en") == ["Yoga", "Health"]
    assert localize_baliforum_tags(["Духовное", "Здоровье"], "en") == ["Spiritual", "Health"]


@pytest.mark.no_db
def test_all_known_baliforum_tags_have_en_translation():
    missing = sorted(tag for tag in BALIFORUM_KNOWN_TAGS if tag not in BALIFORUM_TAG_EN_MAP)
    assert missing == [], f"Missing EN map for BaliForum tags: {missing}"


@pytest.mark.no_db
def test_format_source_display_tags_baliforum_en():
    event = {
        "source": "baliforum",
        "tags": ["Вечеринка", "Йога"],
        "categories": ["Вечеринка", "Духовное"],
    }
    assert format_source_display_tags(event, "ru") == ["Вечеринка", "Йога"]
    assert format_source_display_tags(event, "en") == ["Party", "Yoga"]


@pytest.mark.no_db
def test_format_source_display_tags_non_baliforum_not_translated():
    event = {"source": "user", "tags": ["Custom"]}
    assert format_source_display_tags(event, "en") == ["Custom"]


@pytest.mark.no_db
def test_parse_source_display_tags_prefers_tags_over_internal_categories():
    assert parse_source_display_tags({"tags": ["Фестиваль", "Музыка"], "categories": ["Выставка"]}) == [
        "Фестиваль",
        "Музыка",
    ]
    assert parse_source_display_tags({"raw_category": "Концерт, Живая музыка"}) == [
        "Концерт",
        "Живая музыка",
    ]
    assert parse_source_display_tags({"categories": ["Выставка"]}) == []


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
    assert event["tags"] == ["Фестиваль", "Искусство"]
