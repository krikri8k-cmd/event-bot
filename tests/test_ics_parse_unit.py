import datetime as dt

import pytest

from sources.ics import parse_ics

ICS_SAMPLE = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Beach Cleanup
DTSTART:20251001T080000Z
DTEND:20251001T100000Z
LOCATION:Kuta Beach
URL:https://example.org/events/cleanup
END:VEVENT
END:VCALENDAR
"""


@pytest.mark.unit
def test_parse_ics_sample():
    items = list(
        parse_ics(
            ICS_SAMPLE, source_prefix="ics.test", calendar_url="https://example.org/calendar.ics"
        )
    )
    assert len(items) == 1
    e = items[0]
    assert e["title"] == "Beach Cleanup"
    assert e["starts_at"].tzinfo is dt.UTC
    assert e["url"] == "https://example.org/events/cleanup"
    assert e["external_id"]
