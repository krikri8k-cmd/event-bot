"""GPT place_tag_llm — фильтрация и парсинг ответа."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from utils.place_tag_llm import _filter_llm_extras, propose_extra_tags_llm
from utils.place_tags import format_place_tag_label

pytestmark = pytest.mark.no_db


def test_filter_llm_extras_respects_whitelist_and_place_type():
    place = SimpleNamespace(place_type="cafe", place_tags=[])
    allowed = frozenset({"bar", "restaurant", "coffee_shop"})
    assert _filter_llm_extras(place, ["bar", "cafe", "restaurant", "invalid"], allowed) == [
        "bar",
        "restaurant",
    ]


def test_filter_llm_extras_max_two():
    place = SimpleNamespace(place_type="bar", place_tags=[])
    allowed = frozenset({"restaurant", "lounge", "acoustic_music"})
    assert _filter_llm_extras(place, ["restaurant", "lounge", "acoustic_music"], allowed) == [
        "restaurant",
        "lounge",
    ]


@patch("utils.place_tag_llm._make_client")
def test_propose_extra_tags_llm_parses_json(mock_client):
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({"extras": ["dance"], "reason": "salsa nights"})))
    ]
    mock_client.return_value.chat.completions.create.return_value = mock_response

    place = SimpleNamespace(
        category="entertainment",
        place_type="club",
        place_tags=[],
        name="Salsa Spot",
        name_en=None,
        description=None,
        task_hint="Танцы salsa по пятницам",
        task_hint_en=None,
    )
    proposed, reasons = propose_extra_tags_llm(place)
    assert proposed == ["dance"]
    assert any("salsa" in r for r in reasons)


@patch("utils.place_tag_llm._make_client")
def test_propose_extra_tags_llm_empty_when_no_client(mock_client):
    mock_client.return_value = None
    place = SimpleNamespace(
        category="food",
        place_type="cafe",
        place_tags=[],
        name="Test",
        name_en=None,
        description=None,
        task_hint=None,
        task_hint_en=None,
    )
    assert propose_extra_tags_llm(place) == ([], [])


@patch("utils.place_tag_llm._make_client")
def test_llm_remaps_gym_to_activity_for_cafe(mock_client):
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({"extras": ["gym"], "reason": "after workout"})))
    ]
    mock_client.return_value.chat.completions.create.return_value = mock_response

    place = SimpleNamespace(
        category="health",
        place_type="cafe",
        place_tags=[],
        name="Smoothie Spot",
        name_en=None,
        description=None,
        task_hint="После тренировки загляни на смузи",
        task_hint_en=None,
    )
    proposed, _ = propose_extra_tags_llm(place)
    assert proposed == ["activity"]
    assert "gym" not in proposed


def test_new_tag_labels_i18n():
    assert format_place_tag_label("acoustic_music", "ru") == "Acoustic music"
    assert format_place_tag_label("dance", "en") == "Dance"
    assert format_place_tag_label("activity", "ru") == "Activity"
