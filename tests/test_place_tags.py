"""Подкатегории мест для карточек."""

from types import SimpleNamespace

import pytest

from utils.place_tags import format_place_categories_line_html, get_place_tag_slugs, parse_tags_comment_line

pytestmark = pytest.mark.no_db


def test_place_type_only():
    p = SimpleNamespace(place_type="cafe", place_tags=[])
    assert get_place_tag_slugs(p) == ["cafe"]


def test_place_type_plus_extra_tags():
    p = SimpleNamespace(place_type="gym", place_tags=["cafe", "sauna"])
    assert get_place_tag_slugs(p) == ["gym", "cafe", "sauna"]


def test_legacy_beach_party_maps_to_beach_club():
    p = SimpleNamespace(place_type="beach_party", place_tags=[])
    assert get_place_tag_slugs(p) == ["beach_club"]


def test_dedupe_place_type_in_tags():
    p = SimpleNamespace(place_type="cafe", place_tags=["cafe", "restaurant"])
    assert get_place_tag_slugs(p) == ["cafe", "restaurant"]


def test_format_line_ru():
    p = SimpleNamespace(place_type="gym", place_tags=["cafe"])
    line = format_place_categories_line_html(p, "ru")
    assert line == "🎭 Спортзал / Кафе"


def test_format_line_en():
    p = SimpleNamespace(place_type="gym", place_tags=["cafe"])
    line = format_place_categories_line_html(p, "en")
    assert line == "🎭 Gym / Cafe"


def test_parse_tags_comment():
    assert parse_tags_comment_line("# tags gym, cafe") == ["gym", "cafe"]
