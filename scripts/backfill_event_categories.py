#!/usr/bin/env python3
"""
Backfill categories/raw_category для парсерных событий BaliForum.

Перечитывает теги с BaliForum и обновляет events.categories (JSONB).

Запуск:
  python -m scripts.backfill_event_categories --dry-run
  APP_ENV=prod python -m scripts.backfill_event_categories
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine
from sources.baliforum import fetch_baliforum_events
from utils.event_category_manager import EventCategoryManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _base_external_id(external_id: str) -> str:
    return external_id.split("#", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill event categories for BaliForum parser events")
    parser.add_argument("--dry-run", action="store_true", help="Only log planned updates")
    parser.add_argument("--limit", type=int, default=200, help="Max BaliForum cards to parse")
    args = parser.parse_args()

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()
    manager = EventCategoryManager()

    logger.info("Fetching BaliForum events (limit=%s)...", args.limit)
    parsed_events = fetch_baliforum_events(limit=args.limit)
    by_external_id: dict[str, dict] = {}
    for event in parsed_events:
        ext_id = event.get("external_id")
        if ext_id:
            by_external_id[ext_id] = event

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, external_id, title, categories
                FROM events
                WHERE source = 'baliforum'
                ORDER BY id
            """)
        ).fetchall()

    updated = 0
    skipped = 0
    for row_id, external_id, title, current_categories in rows:
        base_id = _base_external_id(external_id)
        source_event = by_external_id.get(base_id)
        if not source_event:
            skipped += 1
            logger.debug("Skip id=%s external_id=%s (not on BaliForum list)", row_id, external_id)
            continue

        tags = source_event.get("tags") or []
        categories = manager.assign_categories({"tags": tags}, "baliforum")
        raw_category = manager.resolve_raw_category({"tags": tags}, "baliforum")
        categories_json = json.dumps(categories, ensure_ascii=False)

        if args.dry_run:
            logger.info(
                "DRY-RUN id=%s '%s' tags=%s -> categories=%s raw=%s",
                row_id,
                (title or "")[:50],
                tags,
                categories,
                raw_category,
            )
            updated += 1
            continue

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE events
                    SET categories = CAST(:categories AS jsonb),
                        raw_category = :raw_category,
                        updated_at_utc = NOW()
                    WHERE id = :id
                """),
                {
                    "id": row_id,
                    "categories": categories_json,
                    "raw_category": raw_category,
                },
            )
        updated += 1
        logger.info(
            "Updated id=%s '%s' -> categories=%s",
            row_id,
            (title or "")[:50],
            categories,
        )

    logger.info("Done: updated=%s skipped=%s total=%s", updated, skipped, len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
