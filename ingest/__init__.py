"""
Модуль для инжеста событий в базу данных.
Использует ingest.upsert.upsert_event (с переводом RU→EN через OpenAI).
"""

from sqlalchemy import Engine

from event_apis import RawEvent, fingerprint
from ingest.upsert import upsert_event


def _raw_event_to_row(event: RawEvent) -> dict:
    """Преобразует RawEvent в словарь для upsert_event."""
    external_id = event.external_id or event.fingerprint()
    raw_data = getattr(event, "_raw_data", None) or {}
    return {
        "source": event.source,
        "external_id": external_id,
        "url": event.url,
        "title": event.title,
        "description": event.description,
        "starts_at": event.starts_at,
        "ends_at": None,
        "lat": event.lat,
        "lng": event.lng,
        "location_name": raw_data.get("venue"),
        "location_url": raw_data.get("location_url"),
        "city": None,
        "country": None,
    }


def upsert_events(events: list[RawEvent], engine: Engine) -> int:
    """
    Вставляет события в базу с идемпотентным upsert и переводом title_en/description_en.
    Делегирует в ingest.upsert.upsert_event.
    """
    if not events:
        return 0
    for event in events:
        row = _raw_event_to_row(event)
        upsert_event(engine, row)
    return len(events)
