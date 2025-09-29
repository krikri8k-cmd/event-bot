# tests/test_prepare_events.py

# ⚠️ Подкорректируй импорты под твои файлы:
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_enhanced_v3 import (
    build_maps_url,
    get_source_url,
    group_by_type,
    make_counts,
    prepare_events_for_feed,
    render_event_html,
    sanitize_url,
)


def _sample_events():
    return [
        # 1) валидный источник (должен сохраниться, ссылка остаётся)
        dict(
            type="source",
            title="Открытая лекция",
            when_str="2025-09-05 19:00",
            distance_km=1.2,
            venue_name="Dojo Bali",
            source_url="https://dojobali.org/events/open-lecture",
        ),
        # 2) источник без URL, но есть локация + время (должен сохраниться, источник None)
        dict(
            type="source",
            title="Митап без ссылки",
            when_str="2025-09-05 18:00",
            distance_km=0.8,
            address="Sanur Co-working",
            source_url=None,
        ),
        # 3) источник с мусорным календарём (без eid) и без локации (должен быть отброшен)
        dict(
            type="source",
            title="Calendar Junk",
            when_str="2025-09-05 18:00",
            distance_km=0.8,
            source_url="https://calendar.google.com/",
        ),
        # 4) AI c example.com (источник должен стать None, но событие остаётся)
        dict(
            type="ai_generated",
            title="Йога на пляже",
            when_str="2025-09-05 07:00",
            distance_km=2.4,
            venue_name="Sanur Beach",
            location_url="https://example.com/sanur",
        ),
        # 5) Пользовательское событие с ссылкой на автора
        dict(
            type="user",
            title="Иду пить кофе",
            when_str="2025-09-05 16:00",
            distance_km=0.3,
            venue_name="Revolver Espresso",
            author_url="https://t.me/username",
        ),
    ]


def test_prepare_keeps_sources_without_url_if_location_present():
    prepared, diag = prepare_events_for_feed(_sample_events(), with_diag=True)
    titles = [e["title"] for e in prepared]

    # 3-й (Calendar Junk) должен быть отброшен
    assert "Calendar Junk" not in titles
    # 2-й (Митап без ссылки) должен остаться
    assert "Митап без ссылки" in titles

    # проверим причины отбрасывания
    assert diag["in"] == 5
    assert diag["kept"] == 4
    assert diag["dropped"] == 1
    assert "source_without_url_and_location" in diag["reasons"]


def test_sanitize_filters_example_and_blank_calendar():
    assert sanitize_url("https://example.com/x") is None
    assert sanitize_url("https://calendar.google.com/") is None
    assert sanitize_url("https://calendar.google.com/calendar/u/0/r?eid=AAA") is not None
    assert sanitize_url("https://dojobali.org/event") == "https://dojobali.org/event"


def test_get_source_url_behaviour():
    prepared, _ = prepare_events_for_feed(_sample_events(), with_diag=True)

    src_by_title = {e["title"]: get_source_url(e) for e in prepared}
    # валидный источник остался
    assert src_by_title["Открытая лекция"].startswith("https://dojobali.org/")
    # митап без ссылки — None
    assert src_by_title["Митап без ссылки"] is None
    # AI с example.com — None
    assert src_by_title["Йога на пляже"] is None


def test_render_event_html_without_source_shows_placeholder():
    prepared, _ = prepare_events_for_feed(_sample_events(), with_diag=True)
    e = next(x for x in prepared if x["title"] == "Митап без ссылки")
    html = render_event_html(e, idx=1)
    # есть заглушка «Источник не указан»
    assert "Источник не указан" in html
    # есть рабочий «Маршрут»
    assert "Маршрут" in html
    # не должно быть example.com
    assert "example.com" not in html


def test_build_maps_url_prefers_venue_name_then_address_then_coords():
    # venue_name
    e1 = dict(venue_name="Dojo Bali", address="Some Addr", lat=-8.5, lng=115.2)
    # address
    e2 = dict(address="Sanur Beach", lat=-8.5, lng=115.2)
    # coords
    e3 = dict(lat=-8.5, lng=115.2)

    u1 = build_maps_url(e1)
    u2 = build_maps_url(e2)
    u3 = build_maps_url(e3)

    assert "query=Dojo+Bali" in u1
    assert "query=Sanur+Beach" in u2
    assert "query=-8.5,115.2" in u3


def test_counts_and_grouping_on_prepared():
    prepared, _ = prepare_events_for_feed(_sample_events(), with_diag=True)
    groups = group_by_type(prepared)
    counts = make_counts(groups)

    assert counts["all"] == 4
    # 2 source + 1 ai_generated = 3 источника, 1 user событие
    assert counts["sources"] == 3  # 2 source + 1 ai_generated
    assert counts["user"] == 1  # 1 user событие
    # assert counts["moments"] == 1  # моменты удалены - функция Moments отключена
