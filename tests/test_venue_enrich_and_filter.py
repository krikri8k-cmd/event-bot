import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_helpers import DropStats
from venue_enrich import enrich_venue_from_text


# Заглушки для тестирования
def get_source_url(e):
    return e.get("source_url")


def is_blacklisted_url(url):
    return url and "example.com" in url


def prepare_events_for_feed(events, user_point=(0, 0)):
    """Упрощенная версия prepare_events_for_feed для тестирования"""
    from collections import Counter

    prepared, drop = [], DropStats()
    kept_by = Counter(ai=0, user=0, source=0)

    for e in events:
        # Обогащаем локацию
        e = enrich_venue_from_text(e)

        title = (e.get("title") or "").strip() or "—"

        # Проверяем URL
        if not get_source_url(e):
            drop.add("no_url", title)
            continue

        # Проверяем локацию
        if not (e.get("venue_name") or e.get("address") or e.get("coords") or (e.get("lat") and e.get("lng"))):
            drop.add("no_venue_or_location", title)
            continue

        # Проверяем черный список
        if is_blacklisted_url(get_source_url(e)):
            drop.add("blacklist_domain", title)
            continue

        prepared.append(e)
        kept_by[e.get("type", "source")] += 1

    # Печатаем сводку (в реальном коде logger.info)
    print(drop.summary(kept_by, total=len(events)))
    return prepared


def base_event(**kw):
    """Создает базовое событие для тестирования"""
    ev = dict(
        id="1",
        type="source",
        title="Test",
        start=dt.datetime.now(dt.UTC),
        source_url="https://valid.example/item",
    )
    ev.update(kw)
    return ev


def test_enrich_from_venue_name():
    """Тест извлечения названия места из текста"""
    e = base_event(raw_description="Встреча в Cafe Moka на закате")
    print(f"До обогащения: {e}")
    out = prepare_events_for_feed([e])
    print(f"После обогащения: {out[0] if out else 'None'}")
    assert out and out[0].get("venue_name") == "Cafe Moka"
    print("✅ test_enrich_from_venue_name passed")


def test_enrich_from_address_hint():
    """Тест извлечения адреса по подсказкам"""
    e = base_event(raw_description="Собираемся по адресу: ул. Пушкина, дом 10")
    out = prepare_events_for_feed([e])
    assert out and out[0].get("address")
    print("✅ test_enrich_from_address_hint passed")


def test_enrich_from_coords():
    """Тест извлечения координат из текста"""
    e = base_event(raw_description="На карте: -8.670000, 115.250000")
    out = prepare_events_for_feed([e])
    assert out and out[0].get("coords") == (-8.67, 115.25)
    print("✅ test_enrich_from_coords passed")


def test_google_calendar_url():
    """Тест обработки Google Calendar ссылок"""
    e = base_event(
        source_url="https://calendar.google.com/calendar/event?eid=abc123",
        venue_name="Test Venue",  # Добавляем локацию
    )
    out = prepare_events_for_feed([e])
    assert out  # Должно пройти фильтр
    print("✅ test_google_calendar_url passed")


def test_blacklist_domain():
    """Тест фильтрации доменов из черного списка"""
    e = base_event(source_url="https://example.com/event")
    out = prepare_events_for_feed([e])
    assert not out  # Должно быть отфильтровано
    print("✅ test_blacklist_domain passed")


def test_no_url_filter():
    """Тест фильтрации событий без URL"""
    e = base_event(source_url=None)
    out = prepare_events_for_feed([e])
    assert not out  # Должно быть отфильтровано
    print("✅ test_no_url_filter passed")


def test_no_location_filter():
    """Тест фильтрации событий без локации"""
    e = base_event(venue_name=None, address=None, lat=None, lng=None)
    out = prepare_events_for_feed([e])
    assert not out  # Должно быть отфильтровано
    print("✅ test_no_location_filter passed")


if __name__ == "__main__":
    print("🧪 Запуск тестов обогащения локации и фильтрации...")

    test_enrich_from_venue_name()
    test_enrich_from_address_hint()
    test_enrich_from_coords()
    test_google_calendar_url()
    test_blacklist_domain()
    test_no_url_filter()
    test_no_location_filter()

    print("\n🎉 Все тесты прошли успешно!")
