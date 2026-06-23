#!/usr/bin/env python3
"""
Канонические правки task_places перед/после backfill place_tags.

По умолчанию dry-run. Точечно: place_type, is_active, place_tags.

Production:
  TASK_PLACES_ALLOW_PRODUCTION_WRITE=1 railway run -e production -s event-bot \\
    python -m scripts.fix_task_place_canonical --production --apply
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from database import TaskPlace, get_session, init_engine  # noqa: E402
from utils.place_tags import _parse_place_tags_raw, normalize_tag_slug  # noqa: E402
from utils.task_places_export_db import database_host_hint, resolve_task_places_database_url  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class RowFix:
    name_pattern: str
    place_type: str | None = None
    is_active: bool | None = None
    place_tags: list[str] | None = None
    clear_place_tags: bool = False


# Точечные правки по имени (ilike %pattern%)
NAMED_FIXES: tuple[RowFix, ...] = (
    RowFix("HOME Cafe JATAYU", is_active=False, clear_place_tags=True),
    RowFix("The Jungle Club Ubud", place_type="club", place_tags=["dance", "river_club"]),
    RowFix("The Collective Club Pilates Studio", place_type="pilates", clear_place_tags=True),
    RowFix("POWER + REVIVE STUDIO", place_type="gym", clear_place_tags=True),
    RowFix("OBSIDIAN HYROX", place_type="gym", clear_place_tags=True),
    RowFix("Senses Spa", clear_place_tags=True),
    RowFix("Spa Factory Bali", clear_place_tags=True),
    RowFix("Pura Taman Ayun", clear_place_tags=True),
)

# Убрать из place_tags extras, избыточные для place_type (gym + activity и т.п.)
STRIP_TAGS_BY_PLACE_TYPE: dict[str, frozenset[str]] = {
    "gym": frozenset({"activity"}),
    "pilates": frozenset({"activity"}),
    "spa": frozenset({"activity"}),
    "sauna": frozenset({"activity"}),
    "yoga_studio": frozenset({"activity"}),
}


def _refuse_unsafe_apply(*, production: bool, apply: bool) -> None:
    if not apply:
        return
    if production and os.getenv("TASK_PLACES_ALLOW_PRODUCTION_WRITE") != "1":
        logger.error(
            "Запись в production заблокирована.\n"
            "  TASK_PLACES_ALLOW_PRODUCTION_WRITE=1 railway run -e production -s event-bot \\\n"
            "    python -m scripts.fix_task_place_canonical --production --apply"
        )
        raise SystemExit(1)


def _normalize_tags(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        slug = normalize_tag_slug(item)
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


def _strip_redundant_tags(place_type: str, raw_tags) -> list[str] | None:
    strip = STRIP_TAGS_BY_PLACE_TYPE.get((place_type or "").strip())
    if not strip:
        return None
    current = _parse_place_tags_raw(raw_tags)
    cleaned = [t for t in current if t not in strip]
    if cleaned == current:
        return None
    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser(description="Канонические правки task_places")
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--strip-fitness-activity",
        action="store_true",
        help="Убрать activity из place_tags у gym/pilates/spa/sauna/yoga_studio",
    )
    args = parser.parse_args()

    _refuse_unsafe_apply(production=args.production, apply=args.apply)

    db_url = resolve_task_places_database_url(production=args.production)
    tier = "production" if args.production else "develop/local"
    logger.info("БД (%s): %s", tier, database_host_hint(db_url))

    init_engine(db_url)
    planned: list[tuple[TaskPlace, dict]] = []

    with get_session() as session:
        if args.strip_fitness_activity:
            fitness_types = list(STRIP_TAGS_BY_PLACE_TYPE.keys())
            rows = session.query(TaskPlace).filter(TaskPlace.place_type.in_(fitness_types)).all()
            for row in rows:
                cleaned = _strip_redundant_tags(row.place_type or "", row.place_tags)
                if cleaned is not None:
                    planned.append((row, {"place_tags": cleaned}))
        else:
            beach_rows = (
                session.query(TaskPlace)
                .filter(TaskPlace.place_type == "beach_party")
                .filter(TaskPlace.name.not_ilike("%Jungle Club%"))
                .all()
            )
            for row in beach_rows:
                planned.append((row, {"place_type": "beach_club"}))

            for fix in NAMED_FIXES:
                rows = session.query(TaskPlace).filter(TaskPlace.name.ilike(f"%{fix.name_pattern}%")).all()
                if not rows:
                    logger.warning("Не найдено: %s", fix.name_pattern)
                    continue
                for row in rows:
                    updates: dict = {}
                    if fix.place_type is not None:
                        updates["place_type"] = fix.place_type
                    if fix.is_active is not None:
                        updates["is_active"] = fix.is_active
                    if fix.clear_place_tags:
                        updates["place_tags"] = []
                    elif fix.place_tags is not None:
                        updates["place_tags"] = _normalize_tags(fix.place_tags)
                    if updates:
                        planned.append((row, updates))

        if not planned:
            logger.info("Нечего менять")
            return 0

        for row, updates in planned:
            parts = []
            if "place_type" in updates:
                parts.append(f"place_type {row.place_type!r} -> {updates['place_type']!r}")
            if "is_active" in updates:
                parts.append(f"is_active {row.is_active} -> {updates['is_active']}")
            if "place_tags" in updates:
                parts.append(f"place_tags {row.place_tags!r} -> {updates['place_tags']!r}")
            logger.info("id=%s «%s» | %s", row.id, row.name, "; ".join(parts))

        if not args.apply:
            logger.info("DRY-RUN — для записи: --apply")
            return 0

        for row, updates in planned:
            for key, value in updates.items():
                setattr(row, key, value)
        session.commit()
        logger.info("OK — обновлено %s строк", len(planned))

    return 0


if __name__ == "__main__":
    sys.exit(main())
