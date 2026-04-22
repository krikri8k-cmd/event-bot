#!/usr/bin/env python3
"""
Добавляет тестового партнера и привязывает к нему одно место в текущей БД окружения.

Запуск:
  python scripts/seed_test_partner.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    from config import load_settings
    from database import Partner, TaskPlace, get_session, init_engine

    settings = load_settings(require_bot=False)
    init_engine(settings.database_url)

    with get_session() as session:
        partner = session.query(Partner).filter(Partner.slug.ilike("test")).first()
        if not partner:
            partner = Partner(
                slug="test",
                display_name="Test Blogger",
                main_url="https://instagram.com",
                is_active=True,
            )
            session.add(partner)
            session.flush()

        place = (
            session.query(TaskPlace)
            .filter(TaskPlace.is_active == True)  # noqa: E712
            .order_by(TaskPlace.id.asc())
            .first()
        )
        if not place:
            raise RuntimeError("В task_places нет активных мест для привязки.")

        place.partner_id = partner.id
        place.review_url = place.review_url or "https://instagram.com/reel/test-review"
        session.commit()

        print("OK Test partner seeded")
        print(f"partner_id={partner.id} slug={partner.slug}")
        print(f"place_id={place.id} name={place.name}")


if __name__ == "__main__":
    main()
