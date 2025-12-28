#!/usr/bin/env python3
"""
Скрипт для миграции старых заданий: заполняет frozen_* поля для существующих UserTask

ВАЖНО: Запускать ПОСЛЕ применения миграции 035_add_frozen_fields_to_user_tasks.sql
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Устанавливаем UTF-8 для вывода в Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import Task, TaskPlace, UserTask, get_session, init_engine

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def migrate_old_tasks():
    """
    Заполняет frozen_* поля для существующих UserTask, у которых они пустые
    """
    with get_session() as session:
        # Находим все активные задания без frozen данных
        tasks_to_migrate = (
            session.query(UserTask)
            .filter(
                UserTask.status == "active",
                (UserTask.frozen_title.is_(None) | (UserTask.frozen_description.is_(None))),
            )
            .all()
        )

        logger.info(f"Найдено {len(tasks_to_migrate)} заданий для миграции")

        migrated_count = 0
        skipped_count = 0

        for user_task in tasks_to_migrate:
            try:
                # Получаем связанное задание (шаблон)
                task = session.get(Task, user_task.task_id)
                if not task:
                    logger.warning(f"[WARN] Task {user_task.task_id} not found for UserTask {user_task.id}")
                    skipped_count += 1
                    continue

                # Если у UserTask есть place_id, пытаемся получить место
                place = None
                if user_task.place_id:
                    place = session.get(TaskPlace, user_task.place_id)

                # Определяем frozen данные
                if place and place.task_hint:
                    # У места есть GPT-подсказка - используем её
                    frozen_title = place.task_hint
                    frozen_description = place.task_hint
                    frozen_task_hint = place.task_hint
                    frozen_category = place.category
                    logger.debug(f"[OK] UserTask {user_task.id}: using task_hint from place {place.id} ({place.name})")
                else:
                    # Нет места или нет task_hint - используем шаблон
                    frozen_title = task.title
                    frozen_description = task.description
                    frozen_task_hint = None
                    frozen_category = task.category
                    logger.debug(
                        f"[WARN] UserTask {user_task.id}: using task template {task.id} "
                        f"(place: {place.name if place else 'none'})"
                    )

                # Обновляем UserTask
                user_task.frozen_title = frozen_title
                user_task.frozen_description = frozen_description
                user_task.frozen_task_hint = frozen_task_hint
                user_task.frozen_category = frozen_category

                migrated_count += 1

                if migrated_count % 10 == 0:
                    session.commit()
                    logger.info(f"[SAVE] Saved {migrated_count} tasks...")

            except Exception as e:
                logger.error(f"[ERROR] Error migrating UserTask {user_task.id}: {e}", exc_info=True)
                skipped_count += 1
                continue

        # Финальный коммит
        session.commit()

        logger.info("=" * 60)
        logger.info("[OK] Migration completed:")
        logger.info(f"   - Migrated: {migrated_count}")
        logger.info(f"   - Skipped: {skipped_count}")
        logger.info(f"   - Total processed: {len(tasks_to_migrate)}")
        logger.info("=" * 60)


if __name__ == "__main__":
    print("Migration of old tasks to frozen format")
    print("=" * 60)
    print("IMPORTANT: Make sure migration 035 is applied to DB!")
    print("=" * 60)

    # Инициализируем базу данных
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[ERROR] DATABASE_URL not found in environment variables")
        sys.exit(1)

    try:
        init_engine(db_url)
        print("[OK] Database connection initialized\n")
        migrate_old_tasks()
        print("\n[OK] Migration completed successfully!")
    except Exception as e:
        logger.error(f"[ERROR] Critical error: {e}", exc_info=True)
        sys.exit(1)
