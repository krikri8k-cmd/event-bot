from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

UPSERT_SQL = text("""
INSERT INTO events (
    source, external_id, url, title, starts_at, ends_at, lat, lng,
    location_name, location_url, current_participants, status,
    created_at_utc, updated_at_utc, is_generated_by_ai, city, country,
    referral_code, referral_param
)
VALUES (
    :source, :external_id, :url, :title, :starts_at, :ends_at, :lat, :lng,
    :location_name, :location_url, 0, 'active', NOW(), NOW(), false, :city, :country,
    :referral_code, :referral_param
)
ON CONFLICT (source, external_id) DO UPDATE SET
  url = EXCLUDED.url,
  title = COALESCE(EXCLUDED.title, events.title),
  starts_at = COALESCE(EXCLUDED.starts_at, events.starts_at),
  ends_at = COALESCE(EXCLUDED.ends_at, events.ends_at),
  lat = COALESCE(EXCLUDED.lat, events.lat),
  lng = COALESCE(EXCLUDED.lng, events.lng),
  location_name = COALESCE(EXCLUDED.location_name, events.location_name),
  location_url = COALESCE(EXCLUDED.location_url, events.location_url),
  city = COALESCE(EXCLUDED.city, events.city),
  country = COALESCE(EXCLUDED.country, events.country),
  referral_code = COALESCE(EXCLUDED.referral_code, events.referral_code),
  referral_param = COALESCE(EXCLUDED.referral_param, events.referral_param),
  updated_at_utc = NOW()
""")


def upsert_event(engine: Engine, row: dict[str, Any]) -> None:
    """Upsert события в таблицу events с поддержкой реферальных кодов"""
    # Убеждаемся, что referral_code и referral_param есть в row (даже если None)
    # Это нужно для обратной совместимости со старым кодом
    row_with_defaults = {
        "referral_code": None,
        "referral_param": "ref",
        **row,  # Переопределяем значениями из row, если они есть
    }
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, row_with_defaults)
