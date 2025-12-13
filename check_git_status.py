#!/usr/bin/env python3
import subprocess
from pathlib import Path


def run_git(cmd):
    """Выполняет git команду и возвращает результат"""
    try:
        result = subprocess.run(
            f"git {cmd}", shell=True, capture_output=True, text=True, encoding="utf-8", cwd=Path(__file__).parent
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1


print("=" * 70)
print("ПРОВЕРКА GIT СТАТУСА")
print("=" * 70)

# 1. Статус
print("\n1. git status:")
stdout, stderr, code = run_git("status")
if stdout:
    print(stdout)
if stderr:
    print("STDERR:", stderr)

# 2. Последние коммиты
print("\n2. Последние 5 коммитов:")
stdout, stderr, code = run_git("log --oneline -5")
if stdout:
    print(stdout)

# 3. Коммиты для пуша
print("\n3. Коммиты, которых нет в origin/main:")
stdout, stderr, code = run_git("log origin/main..HEAD --oneline")
if stdout:
    print(stdout if stdout else "Нет коммитов для пуша")
else:
    print("✅ Все коммиты уже в origin/main")

# 4. Проверка файла миграции
print("\n4. Файл миграции в git:")
stdout, stderr, code = run_git("ls-files migrations/029_add_task_hint_to_task_places.sql")
if stdout:
    print(f"✅ Файл отслеживается: {stdout}")
else:
    print("❌ Файл не отслеживается git")

# 5. Текущая ветка
print("\n5. Текущая ветка:")
stdout, stderr, code = run_git("branch --show-current")
if stdout:
    print(f"🌿 {stdout}")

print("\n" + "=" * 70)
