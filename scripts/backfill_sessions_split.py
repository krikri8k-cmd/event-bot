"""
Heuristic backfill for total_sessions_world / total_sessions_community.

Strategy:
 - Use user-created events as signals of historic sessions.
 - Estimate sessions as number of distinct days a user created events
   in each scope (world/community), capped by total_sessions.
 - Remainder goes to world (safer default), unless user has only community activity.

This is a best-effort estimator and logs a CSV preview. Run with --apply to persist.
"""

import argparse
import os
from collections import defaultdict

from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def load_env():
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.local.env"))
    if load_dotenv and os.path.exists(env_path):
        load_dotenv(env_path)


def fetch_data(engine):
    with engine.connect() as conn:
        users = (
            conn.execute(
                text(
                    """
                SELECT id, total_sessions,
                       COALESCE(total_sessions_world, 0) AS ts_world,
                       COALESCE(total_sessions_community, 0) AS ts_comm
                FROM users
                """
                )
            )
            .mappings()
            .all()
        )

        # distinct creation days by user for each scope
        world_days = defaultdict(set)
        for row in conn.execute(
            text(
                """
                SELECT organizer_id AS user_id, DATE(starts_at) AS d
                FROM events
                WHERE source = 'user' AND organizer_id IS NOT NULL AND starts_at IS NOT NULL
                """
            )
        ):
            world_days[row[0]].add(row[1])

        community_days = defaultdict(set)
        for row in conn.execute(
            text(
                """
                SELECT organizer_id AS user_id, DATE(starts_at) AS d
                FROM events_community
                WHERE organizer_id IS NOT NULL AND starts_at IS NOT NULL
                """
            )
        ):
            community_days[row[0]].add(row[1])

    return users, world_days, community_days


def estimate(users, world_days, community_days):
    estimations = []
    for u in users:
        user_id = u["id"]
        total = int(u["total_sessions"] or 0)
        already_world = int(u["ts_world"] or 0)
        already_comm = int(u["ts_comm"] or 0)

        if total == 0:
            continue

        w_est = len(world_days.get(user_id, set()))
        c_est = len(community_days.get(user_id, set()))

        # Cap by total
        w_cap = max(0, min(w_est, total))
        c_cap = max(0, min(c_est, total - w_cap))

        # If both zero but total>0, default all to world
        if w_cap == 0 and c_cap == 0:
            w_cap = total

        # Respect existing non-zero values; only fill zeros
        final_world = already_world if already_world > 0 else w_cap
        remaining = max(0, total - final_world)
        final_comm = already_comm if already_comm > 0 else min(c_cap, remaining)

        # If still sum < total, put remainder to world
        s = final_world + final_comm
        if s < total:
            final_world += total - s

        estimations.append((user_id, total, final_world, final_comm))

    return estimations


def apply_updates(engine, estimations, dry_run=True):
    changed = 0
    with engine.begin() as conn:
        for user_id, total, w, c in estimations:
            if dry_run:
                continue
            conn.execute(
                text(
                    """
                    UPDATE users
                    SET total_sessions_world = :w,
                        total_sessions_community = :c,
                        updated_at_utc = NOW()
                    WHERE id = :uid
                    """
                ),
                {"w": int(w), "c": int(c), "uid": int(user_id)},
            )
            changed += 1
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist changes to DB")
    args = parser.parse_args()

    load_env()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL not set")
        return

    engine = create_engine(db_url, future=True)
    users, w_days, c_days = fetch_data(engine)
    estimations = estimate(users, w_days, c_days)

    # Print preview CSV
    print("user_id,total_sessions,world_est,community_est")
    for uid, total, w, c in estimations:
        print(f"{uid},{total},{w},{c}")

    if args.apply:
        changed = apply_updates(engine, estimations, dry_run=False)
        print(f"✅ Applied updates for {changed} users")
    else:
        print("ℹ️ Dry run. Use --apply to persist.")


if __name__ == "__main__":
    main()
