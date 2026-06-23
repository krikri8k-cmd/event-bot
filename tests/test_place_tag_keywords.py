"""Эвристики place_tag_keywords."""

from types import SimpleNamespace

import pytest

from utils.place_tag_keywords import merge_place_tags, place_tags_is_empty, propose_extra_tags

pytestmark = pytest.mark.no_db


def test_propose_sauna_for_gym_with_hint():
    p = SimpleNamespace(
        category="health",
        place_type="gym",
        place_tags=[],
        name="Fit Club",
        name_en=None,
        description=None,
        task_hint="После тренировки загляни в сауну",
        task_hint_en=None,
    )
    proposed, reasons = propose_extra_tags(p)
    assert "sauna" in proposed
    assert any("sauna" in r for r in reasons)


def test_skip_tag_already_displayed_via_place_type():
    p = SimpleNamespace(
        category="food",
        place_type="cafe",
        place_tags=[],
        name="Coffee House",
        name_en=None,
        description="Specialty coffee and brunch",
        task_hint=None,
        task_hint_en=None,
    )
    proposed, _ = propose_extra_tags(p)
    assert "cafe" not in proposed
    assert "coffee_shop" in proposed


def test_spa_not_in_espresso():
    p = SimpleNamespace(
        category="food",
        place_type="restaurant",
        place_tags=[],
        name="Espresso Bar",
        name_en=None,
        description="Specialty espresso drinks",
        task_hint=None,
        task_hint_en=None,
    )
    proposed, _ = propose_extra_tags(p)
    assert "spa" not in proposed


def test_merge_keeps_existing_extras():
    p = SimpleNamespace(place_type="gym", place_tags=["cafe"])
    assert merge_place_tags(p, ["sauna"]) == ["cafe", "sauna"]


def test_place_tags_is_empty():
    assert place_tags_is_empty(None) is True
    assert place_tags_is_empty([]) is True
    assert place_tags_is_empty(["cafe"]) is False


def test_skip_redundant_beach_for_beach_club():
    p = SimpleNamespace(
        category="entertainment",
        place_type="beach_party",
        place_tags=[],
        name="Atlas Beach Club",
        name_en=None,
        description="Sunset on the beach",
        task_hint=None,
        task_hint_en=None,
    )
    proposed, _ = propose_extra_tags(p)
    assert "beach" not in proposed


def test_park_workout_gets_activity_not_gym():
    p = SimpleNamespace(
        category="health",
        place_type="park",
        place_tags=[],
        name="Место на карте",
        name_en=None,
        description=None,
        task_hint="Пройдись по парку и сделай зарядку на свежем воздухе",
        task_hint_en=None,
    )
    proposed, _ = propose_extra_tags(p)
    assert "gym" not in proposed
    assert "activity" in proposed


def test_cafe_after_workout_gets_activity_not_gym():
    p = SimpleNamespace(
        category="health",
        place_type="cafe",
        place_tags=[],
        name="Smoothie Bar",
        name_en=None,
        description=None,
        task_hint="Загляни в кафе после тренировки, выпей смузи",
        task_hint_en=None,
    )
    proposed, _ = propose_extra_tags(p)
    assert "gym" not in proposed
    assert "activity" in proposed


def test_coworking_blocks_bar_from_hint():
    p = SimpleNamespace(
        category="food",
        place_type="coworking",
        place_tags=[],
        name="Outpost Coworking",
        name_en=None,
        description=None,
        task_hint="Насладись свежим коктейлем на террасе",
        task_hint_en=None,
    )
    proposed, _ = propose_extra_tags(p)
    assert "bar" not in proposed


def test_gym_does_not_get_activity_extra():
    p = SimpleNamespace(
        category="health",
        place_type="gym",
        place_tags=[],
        name="CrossFit Canggu",
        name_en=None,
        description=None,
        task_hint="Запишись на групповую тренировку",
        task_hint_en=None,
    )
    proposed, _ = propose_extra_tags(p)
    assert "activity" not in proposed
