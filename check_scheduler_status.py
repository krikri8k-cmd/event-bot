#!/usr/bin/env python3
"""
Скрипт для проверки статуса планировщика
"""

import sys

# Устанавливаем UTF-8 для вывода
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from modern_scheduler import get_modern_scheduler

print("Проверка статуса планировщика...\n")

try:
    scheduler = get_modern_scheduler()

    if scheduler.scheduler and scheduler.scheduler.running:
        print("✅ Планировщик запущен и работает")

        jobs = scheduler.scheduler.get_jobs()
        print(f"\nЗарегистрировано задач: {len(jobs)}")

        # Ключевые задачи, за которыми мы следим особенно
        IMPORTANT_IDS = {
            "community-reminders": "Напоминания за 24 часа (каждые 30 минут)",
            "event-start-notifications": "Уведомления о начале событий (каждые 5 минут)",
            "backfill-translations-user": "Backfill переводов (user, каждые 15 минут)",
            "backfill-translations-parser": "Backfill переводов (parser, каждые 60 минут)",
            "task-places-hint-backfill": "Перевод подсказок task_places (каждые 6 часов)",
        }

        print("\nКлючевые задачи планировщика:")
        for job_id, description in IMPORTANT_IDS.items():
            job = next((j for j in jobs if j.id == job_id), None)
            if not job:
                print(f"  ❌ {job_id}: НЕ НАЙДЕНА ({description})")
                continue
            next_run = job.next_run_time
            print(
                f"  ✅ {job.id}: {description}\n" f"     trigger={job.trigger} | next_run={next_run or 'не определено'}"
            )

        # Показываем все задачи
        print("\nВсе зарегистрированные задачи:")
        for job in jobs:
            next_run = job.next_run_time
            status = "✅" if next_run else "⚠️"
            print(f"  {status} {job.id}: {job.trigger} (следующий запуск: {next_run or 'не определено'})")
    else:
        print("❌ Планировщик не запущен или остановлен")
        print("   Это нормально, если скрипт запускается локально (не на Railway)")
        print("   На Railway планировщик запускается автоматически при старте приложения")

except Exception as e:
    print(f"❌ Ошибка при проверке планировщика: {e}")
    import traceback

    traceback.print_exc()
