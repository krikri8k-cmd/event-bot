import datetime as dt
from collections.abc import Iterable
from typing import Any

import icalendar
import requests

from sources.common import make_external_id, norm_text


def _to_utc(dt_like) -> dt.datetime | None:
    if not dt_like:
        return None
    if isinstance(dt_like, dt.date) and not isinstance(dt_like, dt.datetime):
        # целые даты без времени — принимаем полночь локальной зоны → UTC
        return dt.datetime(dt_like.year, dt_like.month, dt_like.day, tzinfo=dt.UTC)
    if dt_like.tzinfo is None:
        # без таймзоны — считаем UTC
        return dt_like.replace(tzinfo=dt.UTC)
    return dt_like.astimezone(dt.UTC)


def fetch_ics(url: str, *, etag: str | None = None, last_modified: str | None = None, timeout=20):
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    resp = requests.get(url, headers=headers, timeout=timeout)
    return resp


def parse_ics(content: bytes, *, source_prefix: str, calendar_url: str) -> Iterable[dict[str, Any]]:
    cal = icalendar.Calendar.from_ical(content)
    for comp in cal.walk("vevent"):
        title = norm_text(str(comp.get("summary")))
        starts = comp.get("dtstart")
        ends = comp.get("dtend")
        location = norm_text(str(comp.get("location")))
        url = str(comp.get("url") or calendar_url)

        starts_dt = _to_utc(starts.dt if starts else None)
        ends_dt = _to_utc(ends.dt if ends else None)

        external_id = make_external_id(source_prefix, url=url, title=title, starts_at_utc=starts_dt)

        yield {
            "source": source_prefix,
            "external_id": external_id,
            "url": url,
            "title": title or None,
            "starts_at": starts_dt,
            "ends_at": ends_dt,
            "venue_name": None,
            "venue_address": location or None,
            "lat": None,  # при желании — геокодинг по location (отложим)
            "lng": None,
            "raw_location": location or None,
        }
