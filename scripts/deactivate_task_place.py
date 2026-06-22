#!/usr/bin/env python3
"""Deactivate a place by name in task_places."""

import sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_settings
from database import TaskPlace, get_session, init_engine

NAME = sys.argv[1] if len(sys.argv) > 1 else "SECRET SPOT"

settings = load_settings()
init_engine(settings.database_url)
with get_session() as session:
    rows = session.query(TaskPlace).filter(TaskPlace.name.ilike(f"%{NAME}%")).all()
    print(f"found={len(rows)}")
    for row in rows:
        print(f"id={row.id} name={row.name!r} is_active={row.is_active} -> False")
        row.is_active = False
    session.commit()
print("ok")
