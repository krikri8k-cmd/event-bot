#!/usr/bin/env python3
"""
Create/update partner and link places in one run.

What this script can do:
1) Create (or update) a partner in `partners`
2) Link one or many places via `task_places.partner_id`
3) Optionally set per-place:
   - review_url
   - promo_code
   - task_hint (RU)
   - task_hint_en (EN)
   - name_en (EN title)
4) Optionally set partner metadata:
   - telegram_contact (internal communication)
   - default_promo_code
   - priority
   - is_featured
   - notes

Usage examples:

  # Quick mode: same values for all places
  python scripts/add_partner.py \
    --slug anya \
    --display-name "Anya" \
    --main-url "https://instagram.com/anya" \
    --telegram-contact "@anya_manager" \
    --default-promo-code "ANYA10" \
    --priority 50 \
    --is-featured \
    --place-ids 12,15,18 \
    --review-url "https://instagram.com/reel/abc" \
    --task-hint-ru "Попробуй фирменный десерт и поделись впечатлениями!" \
    --task-hint-en "Try the signature dessert and share your impression!"

  # CSV mode: per-place values
  python scripts/add_partner.py \
    --slug anya \
    --display-name "Anya" \
    --main-url "https://instagram.com/anya" \
    --csv scripts/partner_places_anya.csv

CSV columns (header):
  place_id,review_url,promo_code,task_hint_ru,task_hint_en,name_en
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _parse_place_ids(raw: str) -> list[int]:
    items = [x.strip() for x in raw.split(",") if x.strip()]
    if not items:
        raise ValueError("--place-ids is empty")
    place_ids: list[int] = []
    for item in items:
        place_ids.append(int(item))
    return place_ids


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create/update partner and link places with optional RU/EN task text.")
    parser.add_argument("--slug", required=True, help="Partner slug, e.g. anya")
    parser.add_argument("--display-name", required=True, help="Partner display name")
    parser.add_argument("--main-url", default=None, help="Partner profile URL")
    parser.add_argument("--telegram-contact", default=None, help="Internal partner contact (e.g. @manager)")
    parser.add_argument("--default-promo-code", default=None, help="Default promo code for this partner")
    parser.add_argument("--priority", type=int, default=None, help="Partner priority in selections (higher first)")
    parser.add_argument("--notes", default=None, help="Internal notes about this partner")
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Mark partner as inactive (default is active)",
    )
    featured = parser.add_mutually_exclusive_group()
    featured.add_argument(
        "--is-featured",
        action="store_true",
        help="Mark partner as featured",
    )
    featured.add_argument(
        "--not-featured",
        action="store_true",
        help="Mark partner as not featured",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--place-ids",
        help="Comma-separated place ids, e.g. 1,2,3",
    )
    mode.add_argument(
        "--csv",
        help="Path to CSV with columns: place_id,review_url,promo_code,task_hint_ru,task_hint_en,name_en",
    )

    parser.add_argument("--review-url", default=None, help="Default review URL for places")
    parser.add_argument("--promo-code", default=None, help="Default promo code for places")
    parser.add_argument(
        "--use-default-promo-for-places",
        action="store_true",
        help="If place promo is not provided, set partner default promo code to linked places",
    )
    parser.add_argument("--task-hint-ru", default=None, help="Default RU task hint")
    parser.add_argument("--task-hint-en", default=None, help="Default EN task hint")
    parser.add_argument(
        "--name-en",
        default=None,
        help="Default EN place name (useful mainly for single place updates)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without commit",
    )
    return parser


def _load_rows_from_csv(path_str: str) -> list[dict[str, str]]:
    csv_path = Path(path_str)
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"place_id"}
        got = set(reader.fieldnames or [])
        missing = required - got
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")

        for raw_row in reader:
            row = {k: (v or "").strip() for k, v in raw_row.items() if k}
            if not row.get("place_id"):
                continue
            rows.append(row)
    return rows


def main() -> None:
    from sqlalchemy import func

    from config import load_settings
    from database import Partner, TaskPlace, get_session, init_engine

    args = _build_parser().parse_args()
    settings = load_settings(require_bot=False)
    init_engine(settings.database_url)

    if args.csv:
        csv_rows = _load_rows_from_csv(args.csv)
        updates: list[dict[str, str | int | None]] = []
        for row in csv_rows:
            updates.append(
                {
                    "place_id": int(row["place_id"]),
                    "review_url": row.get("review_url") or args.review_url,
                    "promo_code": row.get("promo_code") or args.promo_code,
                    "task_hint_ru": row.get("task_hint_ru") or args.task_hint_ru,
                    "task_hint_en": row.get("task_hint_en") or args.task_hint_en,
                    "name_en": row.get("name_en") or args.name_en,
                }
            )
    else:
        place_ids = _parse_place_ids(args.place_ids)
        updates = [
            {
                "place_id": pid,
                "review_url": args.review_url,
                "promo_code": args.promo_code,
                "task_hint_ru": args.task_hint_ru,
                "task_hint_en": args.task_hint_en,
                "name_en": args.name_en,
            }
            for pid in place_ids
        ]

    with get_session() as session:
        partner = session.query(Partner).filter(func.lower(Partner.slug) == args.slug.lower()).first()
        if not partner:
            partner = Partner(
                slug=args.slug,
                display_name=args.display_name,
                main_url=args.main_url,
                telegram_contact=args.telegram_contact,
                default_promo_code=args.default_promo_code,
                priority=args.priority or 0,
                is_featured=bool(args.is_featured),
                notes=args.notes,
                is_active=not args.inactive,
            )
            session.add(partner)
            session.flush()
            partner_state = "created"
        else:
            partner.slug = args.slug
            partner.display_name = args.display_name
            partner.main_url = args.main_url
            partner.is_active = not args.inactive
            if args.telegram_contact is not None:
                partner.telegram_contact = args.telegram_contact
            if args.default_promo_code is not None:
                partner.default_promo_code = args.default_promo_code
            if args.priority is not None:
                partner.priority = args.priority
            if args.notes is not None:
                partner.notes = args.notes
            if args.is_featured:
                partner.is_featured = True
            elif args.not_featured:
                partner.is_featured = False
            partner_state = "updated"

        changed_places = 0
        for upd in updates:
            place_id = int(upd["place_id"])
            place = session.query(TaskPlace).filter(TaskPlace.id == place_id).first()
            if not place:
                raise RuntimeError(f"Place with id={place_id} not found")

            place.partner_id = partner.id
            if upd["review_url"] is not None:
                place.review_url = str(upd["review_url"])
            if upd["promo_code"] is not None:
                place.promo_code = str(upd["promo_code"])
            elif args.use_default_promo_for_places and partner.default_promo_code:
                place.promo_code = str(partner.default_promo_code)
            if upd["task_hint_ru"] is not None:
                place.task_hint = str(upd["task_hint_ru"])
            if upd["task_hint_en"] is not None:
                place.task_hint_en = str(upd["task_hint_en"])
            if upd["name_en"] is not None:
                place.name_en = str(upd["name_en"])

            changed_places += 1

        if args.dry_run:
            session.rollback()
            print("DRY RUN")
        else:
            session.commit()
            print("OK")

        print(
            f"partner {partner_state}: id={partner.id} slug={partner.slug} "
            f"display_name={partner.display_name} active={partner.is_active} "
            f"featured={partner.is_featured} priority={partner.priority}"
        )
        print(f"partner main_url={partner.main_url or '-'} telegram_contact={partner.telegram_contact or '-'}")
        print(f"partner default_promo_code={partner.default_promo_code or '-'}")
        print(f"places linked/updated: {changed_places}")
        for upd in updates:
            print(f"- place_id={upd['place_id']}")


if __name__ == "__main__":
    main()
