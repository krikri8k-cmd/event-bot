#!/usr/bin/env python3
"""
Show which places are linked to which partner.

Examples:
  python scripts/show_partner_places.py
  python scripts/show_partner_places.py --slug test
  python scripts/show_partner_places.py --only-linked
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect partner-place links from database.")
    parser.add_argument("--slug", default=None, help="Filter by partner slug")
    parser.add_argument("--only-linked", action="store_true", help="Show only places with partner_id")
    return parser


def main() -> None:
    from config import load_settings
    from database import Partner, TaskPlace, get_session, init_engine

    args = _build_parser().parse_args()
    settings = load_settings(require_bot=False)
    init_engine(settings.database_url)

    with get_session() as session:
        partner_filter = []
        if args.slug:
            partner_filter.append(func.lower(Partner.slug) == args.slug.lower())

        partners = (
            session.query(Partner).filter(*partner_filter).order_by(Partner.priority.desc(), Partner.id.asc()).all()
        )
        if args.slug and not partners:
            print(f"Partner with slug '{args.slug}' not found")
            return

        print("=== PARTNER SUMMARY ===")
        for partner in partners:
            places_count = (
                session.query(func.count(TaskPlace.id)).filter(TaskPlace.partner_id == partner.id).scalar() or 0
            )
            active_places_count = (
                session.query(func.count(TaskPlace.id))
                .filter(TaskPlace.partner_id == partner.id, TaskPlace.is_active == True)  # noqa: E712
                .scalar()
                or 0
            )
            places_with_promo_count = (
                session.query(func.count(TaskPlace.id))
                .filter(
                    TaskPlace.partner_id == partner.id,
                    TaskPlace.promo_code.isnot(None),
                    func.length(func.trim(TaskPlace.promo_code)) > 0,
                )
                .scalar()
                or 0
            )
            print(
                f"- {partner.display_name} (@{partner.slug}) "
                f"[id={partner.id}, featured={partner.is_featured}, "
                f"priority={partner.priority}, active={partner.is_active}]"
            )
            print(
                f"  places_count={places_count}, active_places_count={active_places_count}, "
                f"places_with_promo_count={places_with_promo_count}"
            )
            print(f"  main_url={partner.main_url or '-'} telegram_contact={partner.telegram_contact or '-'}")

        print("\n=== PLACE LINKS ===")
        query = (
            session.query(TaskPlace, Partner)
            .outerjoin(Partner, TaskPlace.partner_id == Partner.id)
            .order_by(TaskPlace.id.asc())
        )
        if args.only_linked:
            query = query.filter(TaskPlace.partner_id.isnot(None))
        if args.slug:
            query = query.filter(func.lower(Partner.slug) == args.slug.lower())

        rows = query.all()
        for place, partner in rows:
            partner_name = partner.display_name if partner else "-"
            partner_slug = partner.slug if partner else "-"
            print(
                f"place_id={place.id} | category={place.category} | region={place.region} | "
                f"name={place.name} | partner={partner_name} (@{partner_slug}) | "
                f"promo={place.promo_code or '-'} | review={place.review_url or '-'}"
            )

        if not rows:
            print("No places matched current filters.")


if __name__ == "__main__":
    main()
