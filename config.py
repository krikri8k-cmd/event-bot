import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local relative to this file to avoid CWD issues
_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env.local", encoding="utf-8-sig")


@dataclass
class Settings:
    telegram_token: str
    database_url: str
    openai_api_key: str | None
    openai_organization: str | None
    eventbrite_api_key: str | None
    google_maps_api_key: str | None
    default_radius_km: float
    admin_ids: set[int]
    google_application_credentials: str | None


def _parse_admin_ids(value: str | None) -> set[int]:
    if not value:
        return set()
    ids: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def load_settings() -> Settings:
    # Ensure .env.local is loaded even if called from different CWD
    load_dotenv(_BASE_DIR / ".env.local", encoding="utf-8-sig")

    telegram_token = (os.getenv("TELEGRAM_TOKEN") or "").strip()
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_organization = os.getenv("OPENAI_ORGANIZATION")
    eventbrite_api_key = os.getenv("EVENTBRITE_API_KEY")
    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    default_radius_km_str = (os.getenv("DEFAULT_RADIUS_KM") or "5").strip()
    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS"))

    try:
        default_radius_km = float(default_radius_km_str)
    except ValueError:
        default_radius_km = 4.0

    if not telegram_token:
        raise RuntimeError("TELEGRAM_TOKEN is required")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required (e.g. postgres://user:pass@host:port/db)")

    gcp_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if gcp_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gcp_path

    return Settings(
        telegram_token=telegram_token,
        database_url=database_url,
        openai_api_key=openai_api_key,
        openai_organization=openai_organization,
        eventbrite_api_key=eventbrite_api_key,
        google_maps_api_key=google_maps_api_key,
        default_radius_km=default_radius_km,
        admin_ids=admin_ids,
        google_application_credentials=gcp_path,
    )
