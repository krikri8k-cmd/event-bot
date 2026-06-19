from datetime import UTC, datetime

import pytest

from utils.event_dedupe import (
    compute_dedupe_key,
    dedupe_events_for_display,
    normalize_event_title,
    pick_preferred_event,
)

pytestmark = pytest.mark.no_db


def test_normalize_event_title_strips_punctuation():
    assert normalize_event_title("Tokoyo в Atlas Super Club!!!") == "tokoyo atlas super club"


def test_compute_dedupe_key_stable_for_same_event():
    starts = datetime(2026, 6, 20, 19, 15, tzinfo=UTC)
    key1 = compute_dedupe_key("Tokoyo в Atlas", starts, -8.678, 115.123, "bali")
    key2 = compute_dedupe_key("Tokoyo at Atlas Super Club", starts, -8.6781, 115.1234, "bali")
    assert key1 == key2


def test_compute_dedupe_key_differs_for_different_time():
    starts_a = datetime(2026, 6, 20, 19, 15, tzinfo=UTC)
    starts_b = datetime(2026, 6, 20, 21, 15, tzinfo=UTC)
    key_a = compute_dedupe_key("Yoga Day", starts_a, -8.5, 115.2, "bali")
    key_b = compute_dedupe_key("Yoga Day", starts_b, -8.5, 115.2, "bali")
    assert key_a != key_b


def test_dedupe_events_for_display_keeps_referral():
    starts = datetime(2026, 6, 20, 20, 0, tzinfo=UTC)
    events = [
        {
            "id": 10,
            "title": "Atlas Party Night",
            "starts_at": starts,
            "lat": -8.6,
            "lng": 115.2,
            "city": "bali",
            "source": "baliforum",
        },
        {
            "id": 11,
            "title": "Atlas Party Night",
            "starts_at": starts,
            "lat": -8.6005,
            "lng": 115.2005,
            "city": "bali",
            "source": "telegram",
            "referral_code": "PARTNER10",
        },
    ]
    deduped = dedupe_events_for_display(events)
    assert len(deduped) == 1
    assert deduped[0]["id"] == 11


def test_pick_preferred_event_prefers_referral():
    winner = pick_preferred_event(
        [
            {"id": 1, "referral_code": None, "source": "baliforum"},
            {"id": 2, "referral_code": "ABC", "source": "telegram"},
        ]
    )
    assert winner["id"] == 2
