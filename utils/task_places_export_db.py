"""Выбор Postgres для export/compare task_places (production vs develop).

Локально config.py грузит app.local.env с APP_ENV=dev → DEV_DB_URL.
Пустой DATABASE_URL= в app.local.env затирает URL из `railway run`.
Флаг --production берёт PROD_DB_URL / URL, сохранённый до dotenv.
"""

from __future__ import annotations

import os
import sys

# До import config: railway run -e production подставляет DATABASE_URL сюда
_RAILWAY_DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip() or None


def database_host_hint(url: str) -> str:
    if "@" in url:
        return url.split("@", 1)[1].split("/")[0]
    return "?"


def resolve_task_places_database_url(*, production: bool) -> str:
    """URL для export/compare. production=True → @MyGuide Postgres, иначе develop/local."""
    if production:
        from config import load_settings

        load_settings(require_bot=False)
        for candidate in (
            _RAILWAY_DATABASE_URL,
            os.environ.get("PROD_DB_URL"),
            os.environ.get("DATABASE_URL"),
        ):
            url = (candidate or "").strip()
            if url:
                return url
        print(
            "ERROR: --production: нужен PROD_DB_URL или DATABASE_URL.\n"
            "  Локально: PROD_DB_URL в app.local.env или\n"
            "  railway run -e production -s event-bot "
            "python scripts/export_task_places_to_example_files.py --production",
            file=sys.stderr,
        )
        raise SystemExit(1)

    from config import load_settings

    settings = load_settings(require_bot=False)
    url = (settings.database_url or "").strip()
    if not url:
        print(
            "ERROR: DATABASE_URL не задан (APP_ENV=dev → DEV_DB_URL в app.local.env).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return url
