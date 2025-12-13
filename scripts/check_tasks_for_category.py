"""Проверка заданий для категории food и типа island"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import Task, get_session, init_engine  # noqa: E402

env_path = project_root / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL not found")
    sys.exit(1)

init_engine(database_url)

print("Checking tasks for category 'food' and task_type 'island'...")
print()

with get_session() as session:
    tasks = (
        session.query(Task)
        .filter(
            Task.category == "food",
            Task.task_type == "island",
            Task.is_active == True,  # noqa: E712
        )
        .order_by(Task.order_index)
        .all()
    )

    print(f"Found {len(tasks)} tasks for food/island")
    if tasks:
        print("\nTasks:")
        for task in tasks:
            title = task.title[:50] if task.title else "No title"
            print(f"  - ID {task.id}: {title}... (order={task.order_index})")
    else:
        print("\nERROR: No tasks found for food/island!")
        print("\nChecking all food tasks:")
        all_food = session.query(Task).filter(Task.category == "food").all()
        for t in all_food:
            title = t.title[:50] if t.title else "No title"
            print(f"  - ID {t.id}: type={t.task_type}, order={t.order_index}")
