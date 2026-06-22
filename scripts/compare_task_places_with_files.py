#!/usr/bin/env python3
"""Сверка *_places_example.txt с task_places в Postgres (без вывода секретов)."""

from __future__ import annotations

import argparse
import re
import sys
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
from utils.task_places_export_db import database_host_hint, resolve_task_places_database_url  # noqa: E402

PLACE_FILES = [
    "food_places_example.txt",
    "health_places_example.txt",
    "entertainment_places_example.txt",
    "interesting_places_example.txt",
]


def _normalize_url(url: str) -> str:
    u = (url or "").strip().split("|")[0].strip().rstrip("/")
    u = re.sub(r"[?&]utm_[^&]+", "", u)
    u = u.replace("maps.google.com", "google.com/maps")
    return u.lower()


def _extract_maps_id(url: str) -> str | None:
    u = url or ""
    for pat in (
        r"maps\.app\.goo\.gl/([A-Za-z0-9_-]+)",
        r"goo\.gl/maps/([A-Za-z0-9_-]+)",
        r"cid=(\d+)",
        r"place_id:([A-Za-z0-9_-]+)",
        r"/place/([^/@?]+)",
    ):
        m = re.search(pat, u)
        if m:
            return m.group(1).lower()
    return None


def _match_key(url: str) -> str:
    mid = _extract_maps_id(url)
    if mid:
        return f"id:{mid}"
    return f"url:{_normalize_url(url)}"


def parse_simple_file_quiet(file_path: Path) -> list[dict]:
    result: list[dict] = []
    current_category = current_place_type = current_region = current_promo_code = None
    pending_name = None

    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line and not line.startswith("http"):
                parts = line.split(":")
                if len(parts) >= 2:
                    current_category = parts[0].strip()
                    current_place_type = parts[1].strip()
                    current_region = parts[2].strip() if len(parts) > 2 else "auto"
                    current_promo_code = parts[3].strip() if len(parts) > 3 else None
                    pending_name = None
                continue
            if line.startswith(("http://", "https://")):
                if not current_category or not current_place_type:
                    continue
                url = line
                promo_code = current_promo_code
                if "|" in line:
                    url_part, promo_part = line.split("|", 1)
                    url = url_part.strip()
                    promo_code = promo_part.strip() or current_promo_code
                result.append(
                    {
                        "file": file_path.name,
                        "category": current_category,
                        "place_type": current_place_type,
                        "region": current_region,
                        "url": url,
                        "promo_code": promo_code,
                        "name": pending_name,
                    }
                )
                pending_name = None
            else:
                pending_name = line
    return result


def load_db_places(*, production: bool) -> list[TaskPlace]:
    db_url = resolve_task_places_database_url(production=production)
    tier = "production" if production else "develop/local"
    print(f"БД ({tier}): {database_host_hint(db_url)}")
    init_engine(db_url)
    with get_session() as session:
        return session.query(TaskPlace).order_by(TaskPlace.id).all()


def main() -> int:
    parser = argparse.ArgumentParser(description="Сверка *_places_example.txt с task_places")
    parser.add_argument(
        "--production",
        action="store_true",
        help="production Postgres (@MyGuide), не develop из APP_ENV=dev",
    )
    args = parser.parse_args()

    file_entries: list[dict] = []
    for fname in PLACE_FILES:
        path = project_root / fname
        if path.exists():
            file_entries.extend(parse_simple_file_quiet(path))

    db_places = load_db_places(production=args.production)
    active_db = [p for p in db_places if p.is_active]
    inactive_db = [p for p in db_places if not p.is_active]

    db_by_key: dict[str, TaskPlace] = {}
    for p in db_places:
        if p.google_maps_url:
            db_by_key[_match_key(p.google_maps_url)] = p

    file_keys: dict[str, dict] = {}
    for e in file_entries:
        file_keys[_match_key(e["url"])] = e

    in_file_not_db: list[dict] = []
    for key, e in file_keys.items():
        if key not in db_by_key:
            in_file_not_db.append(e)

    in_db_active_not_file: list[TaskPlace] = []
    for p in active_db:
        if not p.google_maps_url:
            in_db_active_not_file.append(p)
            continue
        if _match_key(p.google_maps_url) not in file_keys:
            in_db_active_not_file.append(p)

    field_mismatches: list[str] = []
    for key, e in file_keys.items():
        p = db_by_key.get(key)
        if not p:
            continue
        if e["category"] != p.category:
            field_mismatches.append(f"  [{p.id}] {p.name}: category file={e['category']} db={p.category} ({e['file']})")
        if e["place_type"] != (p.place_type or ""):
            field_mismatches.append(
                f"  [{p.id}] {p.name}: place_type file={e['place_type']} db={p.place_type} ({e['file']})"
            )
        file_region = (e["region"] or "").strip()
        if file_region and file_region != "auto" and file_region != (p.region or ""):
            field_mismatches.append(f"  [{p.id}] {p.name}: region file={file_region} db={p.region} ({e['file']})")
        file_promo = (e.get("promo_code") or "").strip()
        db_promo = (p.promo_code or "").strip()
        if file_promo and file_promo != db_promo:
            field_mismatches.append(f"  [{p.id}] {p.name}: promo file={file_promo!r} db={db_promo!r} ({e['file']})")

    print("=== Сверка task_places ↔ *_places_example.txt ===\n")
    print(f"БД всего: {len(db_places)} (active={len(active_db)}, inactive={len(inactive_db)})")
    print(f"Записей в файлах (по URL): {len(file_keys)}\n")

    print(f"--- В файлах, но НЕТ в task_places ({len(in_file_not_db)}) ---")
    for e in in_file_not_db[:50]:
        label = e.get("name") or e["url"][:60]
        print(f"  {label} | {e['category']}:{e['place_type']}:{e['region']} | {e['file']}")
    if len(in_file_not_db) > 50:
        print(f"  ... и ещё {len(in_file_not_db) - 50}")

    print(f"\n--- В task_places (active), но НЕТ в файлах ({len(in_db_active_not_file)}) ---")
    for p in in_db_active_not_file[:50]:
        print(f"  [{p.id}] {p.name} | {p.category}:{p.place_type}:{p.region}")
    if len(in_db_active_not_file) > 50:
        print(f"  ... и ещё {len(in_db_active_not_file) - 50}")

    print(f"\n--- Расхождения полей при совпадении URL ({len(field_mismatches)}) ---")
    for line in field_mismatches[:80]:
        print(line)
    if len(field_mismatches) > 80:
        print(f"  ... и ещё {len(field_mismatches) - 80}")

    if inactive_db:
        print(f"\n--- inactive в БД ({len(inactive_db)}) — могут отсутствовать в файлах намеренно ---")
        for p in inactive_db[:20]:
            print(f"  [{p.id}] {p.name} | {p.category}:{p.region}")
        if len(inactive_db) > 20:
            print(f"  ... и ещё {len(inactive_db) - 20}")

    ok = not in_file_not_db and not in_db_active_not_file and not field_mismatches
    print("\n" + ("OK: файлы и active task_places совпадают." if ok else "ЕСТЬ РАСХОЖДЕНИЯ — см. выше."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
