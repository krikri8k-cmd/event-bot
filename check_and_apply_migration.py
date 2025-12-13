#!/usr/bin/env python3
"""Проверка и применение миграции через GitHub"""

import subprocess
import sys
from pathlib import Path


def run_cmd(cmd, check=True):
    """Выполняет команду и возвращает результат"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, encoding="utf-8", cwd=Path(__file__).parent
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print(result.stderr, file=sys.stderr)
        if check and result.returncode != 0:
            sys.exit(result.returncode)
        return result
    except Exception as e:
        print(f"Ошибка выполнения команды: {e}", file=sys.stderr)
        if check:
            sys.exit(1)
        return None


print("=" * 60)
print("ПРОВЕРКА И ПРИМЕНЕНИЕ МИГРАЦИИ 029")
print("=" * 60)

# 1. Проверяем статус git
print("\n1. Проверка статуса git...")
result = run_cmd("git status --short", check=False)
if result and result.stdout.strip():
    print("   Есть незакоммиченные изменения:")
    print(result.stdout)
    print("\n   Добавляю все изменения...")
    run_cmd("git add -A")
    print("   Коммичу...")
    run_cmd('git commit -m "feat: Add task_hint column migration for AI-generated place hints"')
else:
    print("   ✅ Все изменения закоммичены")

# 2. Проверяем, есть ли коммиты для пуша
print("\n2. Проверка коммитов для пуша...")
result = run_cmd("git log origin/HEAD..HEAD --oneline", check=False)
if result and result.stdout.strip():
    print("   Найдено коммитов для пуша:")
    print(result.stdout)
    print("\n   Пушим в GitHub...")
    run_cmd("git push origin HEAD")
    print("   ✅ Изменения запушены!")
else:
    print("   ✅ Все изменения уже запушены")

# 3. Проверяем наличие файла миграции
print("\n3. Проверка файла миграции...")
migration_file = Path(__file__).parent / "migrations" / "029_add_task_hint_to_task_places.sql"
if migration_file.exists():
    print(f"   ✅ Файл найден: {migration_file}")
    with open(migration_file, encoding="utf-8") as f:
        content = f.read()
        lines = len(content.split("\n"))
        print(f"   Размер: {lines} строк")
else:
    print(f"   ❌ Файл не найден: {migration_file}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ГОТОВО!")
print("=" * 60)
print("\n📋 Следующие шаги:")
print("1. Откройте https://github.com/krikri8k-cmd/event-bot/actions")
print("2. Найдите workflow 'DB Apply (manual)'")
print("3. Нажмите 'Run workflow'")
print("4. В поле 'SQL file path' укажите: migrations/029_add_task_hint_to_task_places.sql")
print("5. Нажмите 'Run workflow'")
print("\n✨ После выполнения workflow столбец task_hint появится в БД!")
