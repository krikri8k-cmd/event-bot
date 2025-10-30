import json
import os
import sys
from datetime import datetime

from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


def load_env():
    # Prefer explicit app.local.env to match project setup
    env_path = os.path.join(os.path.dirname(__file__), "..", "app.local.env")
    env_path = os.path.abspath(env_path)
    if load_dotenv and os.path.exists(env_path):
        load_dotenv(env_path)


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set. Ensure app.local.env is configured.")
    return db_url


def fetch_counts(engine, user_id: int):
    with engine.connect() as conn:
        world_count = conn.execute(
            text("""
                SELECT COUNT(*) AS c
                FROM events
                WHERE organizer_id = :uid
            """),
            {"uid": user_id},
        ).scalar_one()

        community_count = conn.execute(
            text("""
                SELECT COUNT(*) AS c
                FROM events_community
                WHERE organizer_id = :uid
            """),
            {"uid": user_id},
        ).scalar_one()

        users_row = (
            conn.execute(
                text(
                    """
                SELECT rockets_balance, total_sessions, tasks_accepted_total, tasks_completed_total,
                       events_created_world, events_created_community
                FROM users
                WHERE id = :uid
                """
                ),
                {"uid": user_id},
            )
            .mappings()
            .first()
        )

    return world_count, community_count, users_row


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/check_user_counters.py <user_id>")
        sys.exit(1)

    user_id = int(sys.argv[1])
    load_env()
    engine = create_engine(get_db_url())

    world_count, community_count, users_row = fetch_counts(engine, user_id)

    result = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "events_world_actual": int(world_count or 0),
        "events_community_actual": int(community_count or 0),
        "events_total_actual": int((world_count or 0) + (community_count or 0)),
        "users_table": dict(users_row) if users_row else None,
        "diff": {
            "world": int(world_count or 0) - int((users_row or {}).get("events_created_world", 0) if users_row else 0),
            "community": int(community_count or 0)
            - int((users_row or {}).get("events_created_community", 0) if users_row else 0),
        },
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
