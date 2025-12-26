#!/usr/bin/env python3
"""
Скрипт для миграции старых заданий: заполняет frozen_* поля для существующих UserTask

ВАЖНО: Запускать ПОСЛЕ применения миграции 035_add_frozen_fields_to_user_tasks.sql
"""

import logging
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import Task, TaskPlace, UserTask, get_session

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
                    logger.warning(f"⚠️ Задание {user_task.task_id} не найдено для UserTask {user_task.id}")
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
                    logger.debug(
                        f"✅ UserTask {user_task.id}: используем task_hint из места {place.id} " f"({place.name})"
                    )
                else:
                    # Нет места или нет task_hint - используем шаблон
                    frozen_title = task.title
                    frozen_description = task.description
                    frozen_task_hint = None
                    frozen_category = task.category
                    logger.debug(
                        f"⚠️ UserTask {user_task.id}: используем шаблон задания {task.id} "
                        f"(место: {place.name if place else 'нет'})"
                    )

                # Обновляем UserTask
                user_task.frozen_title = frozen_title
                user_task.frozen_description = frozen_description
                user_task.frozen_task_hint = frozen_task_hint
                user_task.frozen_category = frozen_category

                migrated_count += 1

                if migrated_count % 10 == 0:
                    session.commit()
                    logger.info(f"💾 Сохранено {migrated_count} заданий...")

            except Exception as e:
                logger.error(f"❌ Ошибка при миграции UserTask {user_task.id}: {e}", exc_info=True)
                skipped_count += 1
                continue

        # Финальный коммит
        session.commit()

        logger.info("=" * 60)
        logger.info("✅ Миграция завершена:")
        logger.info(f"   - Мигрировано: {migrated_count}")
        logger.info(f"   - Пропущено: {skipped_count}")
        logger.info(f"   - Всего обработано: {len(tasks_to_migrate)}")
        logger.info("=" * 60)


if __name__ == "__main__":
    print("🚀 Миграция старых заданий в frozen формат")
    print("=" * 60)
    print("ВАЖНО: Убедитесь, что миграция 035 применена к БД!")
    print("=" * 60)

    try:
        migrate_old_tasks()
        print("\n✅ Миграция успешно завершена!")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
