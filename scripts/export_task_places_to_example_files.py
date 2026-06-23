#!/usr/bin/env python3
"""Экспорт task_places → *_places_example.txt (источник правды: Postgres)."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import TaskPlace, get_session, init_engine  # noqa: E402
from utils.place_tags import get_place_tag_slugs  # noqa: E402
from utils.task_places_export_db import database_host_hint, resolve_task_places_database_url  # noqa: E402
from utils.task_places_safety import MIRROR_HEADER  # noqa: E402

CATEGORY_FILES = {
    "food": "food_places_example.txt",
    "health": "health_places_example.txt",
    "entertainment": "entertainment_places_example.txt",
    "places": "interesting_places_example.txt",
}

REGION_LABELS = {
    "moscow": "МОСКВА",
    "spb": "САНКТ-ПЕТЕРБУРГ",
    "bali": "БАЛИ",
}

FILE_HEADER = {
    "food": MIRROR_HEADER + "# Формат секций: food:place_type:region:promo_code\n",
    "health": MIRROR_HEADER + "# Формат секций: health:place_type:region:promo_code\n",
    "entertainment": MIRROR_HEADER + "# Формат секций: entertainment:place_type:region:promo_code\n",
    "places": MIRROR_HEADER + "# Формат секций: places:place_type:region:promo_code\n",
}

REGION_ORDER = ["moscow", "spb", "bali", "jakarta", "unknown"]


def _line_for_place(p: TaskPlace) -> list[str]:
    lines: list[str] = []
    tag_slugs = get_place_tag_slugs(p)
    if tag_slugs:
        lines.append(f"# tags {', '.join(tag_slugs)}")
    if p.review_url:
        lines.append(f"# review {p.review_url}")
    name = (p.name or "").strip()
    url = (p.google_maps_url or "").strip()
    if not url:
        return lines
    if name and name.lower() not in {"место на карте", "place on map"}:
        lines.append(name)
    promo = (p.promo_code or "").strip()
    lines.append(f"{url}|{promo}" if promo else url)
    return lines


def _build_category_content(category: str, places: list[TaskPlace]) -> str:
    parts = [FILE_HEADER[category].rstrip(), ""]

    by_region: dict[str, list[TaskPlace]] = defaultdict(list)
    for p in places:
        by_region[p.region or "unknown"].append(p)

    regions = sorted(by_region.keys(), key=lambda r: REGION_ORDER.index(r) if r in REGION_ORDER else 99)

    for region in regions:
        label = REGION_LABELS.get(region, region.upper())
        parts.append("# ============================================")
        parts.append(f"# {label}")
        parts.append("# ============================================")
        parts.append("")

        region_places = by_region[region]
        by_type: dict[str, list[TaskPlace]] = defaultdict(list)
        for p in region_places:
            by_type[p.place_type or "unknown"].append(p)

        for place_type in sorted(by_type.keys()):
            group = sorted(by_type[place_type], key=lambda x: (x.name or "").lower())
            parts.append(f"{category}:{place_type}:{region}:")
            parts.append("")
            for p in group:
                parts.extend(_line_for_place(p))
                parts.append("")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Экспорт task_places → *_places_example.txt")
    parser.add_argument(
        "--production",
        action="store_true",
        help="production Postgres (@MyGuide), не develop из APP_ENV=dev",
    )
    parser.add_argument("--dry-run", action="store_true", help="не записывать файлы")
    args = parser.parse_args()

    db_url = resolve_task_places_database_url(production=args.production)
    tier = "production" if args.production else "develop/local"
    print(f"БД ({tier}): {database_host_hint(db_url)}")

    init_engine(db_url)
    with get_session() as session:
        places = session.query(TaskPlace).filter(TaskPlace.is_active.is_(True)).order_by(TaskPlace.id).all()

    by_category: dict[str, list[TaskPlace]] = defaultdict(list)
    for p in places:
        if p.category in CATEGORY_FILES:
            by_category[p.category].append(p)

    print(f"Экспорт {len(places)} active мест из task_places")
    for cat, fname in CATEGORY_FILES.items():
        content = _build_category_content(cat, by_category.get(cat, []))
        out = project_root / fname
        count = len(by_category.get(cat, []))
        print(f"  {fname}: {count} мест")
        if args.dry_run:
            continue
        out.write_text(content, encoding="utf-8")

    if args.dry_run:
        print("DRY RUN — файлы не записаны")
    else:
        print("OK — файлы обновлены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
