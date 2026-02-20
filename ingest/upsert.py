import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

UPSERT_SQL = text("""
INSERT INTO events (
    source, external_id, url, title, title_en, description, description_en,
    starts_at, ends_at, lat, lng,
    location_name, location_name_en, location_url, current_participants, status,
    created_at_utc, updated_at_utc, is_generated_by_ai, city, country,
    referral_code, referral_param
)
VALUES (
    :source, :external_id, :url, :title, :title_en, :description, :description_en,
    :starts_at, :ends_at, :lat, :lng,
    :location_name, :location_name_en, :location_url, 0, 'active', NOW(), NOW(), false, :city, :country,
    :referral_code, :referral_param
)
ON CONFLICT (source, external_id) DO UPDATE SET
  url = EXCLUDED.url,
  title = COALESCE(EXCLUDED.title, events.title),
  title_en = COALESCE(EXCLUDED.title_en, events.title_en),
  description = COALESCE(EXCLUDED.description, events.description),
  description_en = COALESCE(EXCLUDED.description_en, events.description_en),
  starts_at = COALESCE(EXCLUDED.starts_at, events.starts_at),
  ends_at = COALESCE(EXCLUDED.ends_at, events.ends_at),
  lat = COALESCE(EXCLUDED.lat, events.lat),
  lng = COALESCE(EXCLUDED.lng, events.lng),
  location_name = COALESCE(EXCLUDED.location_name, events.location_name),
  location_name_en = COALESCE(EXCLUDED.location_name_en, events.location_name_en),
  location_url = COALESCE(EXCLUDED.location_url, events.location_url),
  city = COALESCE(EXCLUDED.city, events.city),
  country = COALESCE(EXCLUDED.country, events.country),
  referral_code = COALESCE(EXCLUDED.referral_code, events.referral_code),
  referral_param = COALESCE(EXCLUDED.referral_param, events.referral_param),
  updated_at_utc = NOW()
""")


def upsert_event(engine: Engine, row: dict[str, Any]) -> None:
    """Upsert события в таблицу events с поддержкой реферальных кодов и перевода RU→EN."""
    title = (row.get("title") or "").strip()
    description = row.get("description")
    if description is not None and not isinstance(description, str):
        description = str(description)
    location_name = (
        row.get("location_name") or row.get("venue_name") or row.get("venue_address") or row.get("raw_location")
    )
    if location_name is not None and not isinstance(location_name, str):
        location_name = str(location_name)

    title_en = row.get("title_en")
    description_en = row.get("description_en")
    location_name_en = row.get("location_name_en")

    # Перевод при сохранении: только если ещё не передан (или пустая строка) и есть что переводить
    need_translation = (title_en is None or (title_en or "").strip() == "") and (title or description or location_name)
    if need_translation:
        try:
            from utils.event_translation import translate_event_to_english

            trans = translate_event_to_english(
                title=title or "",
                description=(description or "").strip() or None,
                location_name=(location_name or "").strip() or None,
            )
            if trans.get("title_en"):
                title_en = trans["title_en"]
            if trans.get("description_en"):
                description_en = trans["description_en"]
            # location_name не переводим — в _en пишем оригинал (Google Maps style)
        except Exception as e:
            logger.warning("ingest/upsert: перевод не выполнен для %r: %s", (title or "")[:50], e)

    # ICS/Nexudus отдают venue_address или raw_location, SQL ожидает location_name
    location_name_value = row.get("location_name") or row.get("venue_address") or row.get("raw_location")
    # Локация не переводится: location_name_en = оригинал (или NULL), для вывода в боте всегда location_name
    if location_name_en is None and location_name_value:
        location_name_en = location_name_value

    row_with_defaults = {
        "referral_code": None,
        "referral_param": "ref",
        "city": None,
        "country": None,
        **row,
    }
    row_with_defaults["title_en"] = title_en
    row_with_defaults["description_en"] = description_en
    row_with_defaults["location_name_en"] = location_name_en
    row_with_defaults["description"] = row.get("description")
    row_with_defaults["location_name"] = location_name_value
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, row_with_defaults)
