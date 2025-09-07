import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_dotenv_with_bom(path: Path):
    """Load .env file with BOM handling"""
    if path and path.exists():
        load_dotenv(dotenv_path=path, encoding="utf-8-sig", override=True)


# Load environment files with priority: ENV_FILE > .env.local > .env
_BASE_DIR = Path(__file__).resolve().parent
env_file = os.getenv("ENV_FILE")
if env_file:
    _load_dotenv_with_bom(Path(env_file))

# Then load .env.local, app.local.env and .env
for fn in (".env.local", "app.local.env", ".env"):
    _load_dotenv_with_bom(_BASE_DIR / fn)


@dataclass
class Settings:
    telegram_token: str
    database_url: str
    openai_api_key: str | None
    openai_organization: str | None
    eventbrite_api_key: str | None
    meetup_api_key: str | None
    google_maps_api_key: str | None
    default_radius_km: float
    radius_step_km: float
    max_radius_km: float
    admin_ids: set[int]
    google_application_credentials: str | None
    env_file: str | None


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


def load_settings(require_bot: bool = False) -> Settings:
    # Environment files are already loaded at module level
    # Just get the current ENV_FILE value for reference

    telegram_token = (os.getenv("TELEGRAM_TOKEN") or "").strip()
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_organization = os.getenv("OPENAI_ORGANIZATION")
    eventbrite_api_key = os.getenv("EVENTBRITE_API_KEY")
    meetup_api_key = os.getenv("MEETUP_API_KEY")
    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    default_radius_km_str = (os.getenv("DEFAULT_RADIUS_KM") or "5").strip()
    radius_step_km_str = (os.getenv("RADIUS_STEP_KM") or "5").strip()
    max_radius_km_str = (os.getenv("MAX_RADIUS_KM") or "15").strip()
    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS"))

    try:
        default_radius_km = float(default_radius_km_str)
    except ValueError:
        default_radius_km = 4.0

    try:
        radius_step_km = float(radius_step_km_str)
    except ValueError:
        radius_step_km = 5.0

    try:
        max_radius_km = float(max_radius_km_str)
    except ValueError:
        max_radius_km = 15.0

    # Требовать токен только в режиме бота
    if require_bot and not telegram_token:
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
        meetup_api_key=meetup_api_key,
        google_maps_api_key=google_maps_api_key,
        default_radius_km=default_radius_km,
        radius_step_km=radius_step_km,
        max_radius_km=max_radius_km,
        admin_ids=admin_ids,
        google_application_credentials=gcp_path,
        env_file=env_file,
    )
