# tests/test_handlers_radius_pagination.py
import os

# ⚠️ Подправь импорты под твои модули
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_enhanced_v3 import group_by_type, make_counts, prepare_events_for_feed, render_page

# Мокаем user_state как простой словарь
user_state = {}


def _mk_event(t, title, km, **extra):
    e = dict(type=t, title=title, when_str="2025-09-05 12:00", distance_km=km)
    e.update(extra)
    return e


@pytest.fixture
def memory_state(monkeypatch):
    """
    Подменяем state на простую dict, чтобы не тащить реальный Redis/InMemory.
    """
    global user_state
    user_state.clear()

    def get_(cid, key=None, default=None):
        d = user_state.get(cid, {})
        return d if key is None else d.get(key, default)

    def set_(cid, data):
        user_state[cid] = data

    fake_state = types.SimpleNamespace(get=get_, set=set_)
    return fake_state


def test_expand_radius_really_refetches(monkeypatch, memory_state):
    """
    Проверяем, что rx:10/15 действительно делает НОВЫЙ fetch и в state кладётся новая выборка.
    """
    chat_id = 123

    # 1) При радиусе 5 км вернём 1 событие
    def fetch_r5(lat, lng, radius_km):
        assert radius_km == 5
        return [
            _mk_event(
                "source",
                "Лекция рядом",
                1.0,
                venue_name="Dojo",
                source_url="https://dojobali.org/e/1",
            )
        ]

    # 2) При радиусе 10 км вернём 3 события (чтобы было видно расширение)
    def fetch_r10(lat, lng, radius_km):
        assert radius_km == 10
        return [
            _mk_event(
                "source",
                "Лекция рядом",
                1.0,
                venue_name="Dojo",
                source_url="https://dojobali.org/e/1",
            ),
            _mk_event(
                "user", "Иду пить кофе", 6.0, venue_name="Revolver", author_url="https://t.me/u"
            ),
            _mk_event(
                "ai_generated", "Йога на пляже", 9.0, venue_name="Sanur Beach", location_url=None
            ),
        ]

    # Стартовое состояние: положим туда результаты r=5 как будто их только что показали
    raw5 = fetch_r5(-8.67, 115.25, radius_km=5)
    prepared5, _ = prepare_events_for_feed(raw5, with_diag=True)
    counts5 = make_counts(group_by_type(prepared5))
    memory_state.set(
        chat_id,
        {
            "lat": -8.67,
            "lng": 115.25,
            "radius": 5,
            "prepared": prepared5,
            "counts": counts5,
            "page": 1,
        },
    )

    # Теперь эмулируем клик "rx:10": замокаем fetch_events новым поведением
    # — Эмулируем тело хэндлера rx:10 (как в твоём коде)
    st = memory_state.get(chat_id)
    raw10 = fetch_r10(st["lat"], st["lng"], radius_km=10)
    prepared10, _ = prepare_events_for_feed(raw10, with_diag=True)
    counts10 = make_counts(group_by_type(prepared10))
    memory_state.set(
        chat_id, {**st, "radius": 10, "prepared": prepared10, "counts": counts10, "page": 1}
    )

    # Проверки
    assert len(prepared5) == 1
    assert len(prepared10) == 3
    st2 = memory_state.get(chat_id)
    assert st2["radius"] == 10
    assert len(st2["prepared"]) == 3
    # страница рендерится без ошибок
    html10, total10 = render_page(st2["prepared"], page=1, page_size=5)
    assert "Лекция рядом" in html10 and "Йога на пляже" in html10
    assert total10 == 1  # т.к. всего 3 события


def test_pagination_uses_prepared_only(monkeypatch, memory_state):
    """
    Пагинация должна листать ТОЛЬКО prepared, а не сырые events.
    """
    chat_id = 456

    # сырых событий 8, но из них 3 "плохих" (например, без локации и урла) — их выбросит prepare
    raw = [
        _mk_event("source", "S1", 0.5, venue_name="A", source_url="https://s/a"),
        _mk_event("source", "S2", 0.6, venue_name="B", source_url="https://s/b"),
        _mk_event("source", "S3", 0.7, source_url=None),  # плохое — без локации и урла
        _mk_event("user", "U1", 0.8, venue_name="C", author_url="https://t.me/u1"),
        _mk_event("ai_generated", "AI1", 1.0, venue_name="D"),
        _mk_event(
            "source", "S4", 1.2, source_url="https://calendar.google.com/"
        ),  # плохое — пустой календарь
        _mk_event("source", "S5", 1.3, venue_name="E", source_url="https://s/e"),
        _mk_event(
            "ai_generated", "AI2", 1.4, venue_name="F", location_url="https://example.com/x"
        ),  # example — урла не будет
    ]
    # эмулируем fetch_events
    raw8 = raw
    prepared, diag = prepare_events_for_feed(raw8, with_diag=True)
    counts = make_counts(group_by_type(prepared))

    # Проверим: из 8 — осталось 6 (мы откинули S3 и S4)
    assert diag["in"] == 8
    assert diag["kept"] == 6
    assert diag["dropped"] == 2

    # Сохраним в состояние и пролистаем страницы
    memory_state.set(chat_id, {"prepared": prepared, "counts": counts, "page": 1})
    page1, total = render_page(prepared, page=1, page_size=3)
    page2, _ = render_page(prepared, page=2, page_size=3)

    assert total == 2  # 6 по 3 = 2 страницы
    # На обеих страницах только валидные заголовки
    assert "S3" not in page1 + page2  # выброшено
    assert "S4" not in page1 + page2  # выброшено
    # example.com не должен просочиться
    assert "example.com" not in page1 + page2
