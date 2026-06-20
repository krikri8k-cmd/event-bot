#!/usr/bin/env python3
"""Подсказки: Google-запросы для ручного поиска TikTok-обзоров (site:tiktok.com).

Не пишет в БД — только печатает ссылки для браузера.
Пропускает места, у которых review_url уже заполнен.

Пример:
  python scripts/export_tiktok_search_queries.py --region bali --category food
  python scripts/export_tiktok_search_queries.py --region bali --limit 20

Зависимость для fetch-скрипта: pip install -e \".[scripts]\"
"""

from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import load_settings  # noqa: E402
from database import TaskPlace, get_session, init_engine  # noqa: E402


def _google_url(place_name: str, region: str) -> str:
    query = f'site:tiktok.com "{place_name}" "{region.title()}"'
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Google TikTok search URLs for empty review_url")
    parser.add_argument("--region", default="bali", help="task_places.region filter (default: bali)")
    parser.add_argument("--category", help="optional category filter: food, health, places, entertainment")
    parser.add_argument("--limit", type=int, default=0, help="max rows (0 = all)")
    parser.add_argument("--skip-placeholder", action="store_true", default=True, help="skip 'Место на карте'")
    args = parser.parse_args()

    init_engine(load_settings(require_bot=False).database_url)

    with get_session() as session:
        q = session.query(TaskPlace).filter(TaskPlace.is_active.is_(True))
        if args.region:
            q = q.filter(TaskPlace.region == args.region)
        if args.category:
            q = q.filter(TaskPlace.category == args.category)
        rows = q.order_by(TaskPlace.category, TaskPlace.name).all()

        missing = [p for p in rows if not (p.review_url or "").strip()]
        if args.skip_placeholder:
            missing = [p for p in missing if (p.name or "").strip() != "Место на карте"]
        if args.limit:
            missing = missing[: args.limit]

        print(f"# TikTok search queries | region={args.region} | empty review_url: {len(missing)}\n")
        for place in missing:
            url = _google_url(place.name, args.region or place.region or "Bali")
            print(f"# id={place.id} | {place.category} | {place.name}")
            print(url)
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
