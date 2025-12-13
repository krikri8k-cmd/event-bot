#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def run(cmd, check=True):
    """Выполняет команду и выводит результат"""
    print(f"▶ {cmd}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, encoding="utf-8", cwd=Path(__file__).parent
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if check and result.returncode != 0:
            print(f"❌ Ошибка (код {result.returncode})")
            sys.exit(1)
        return result
    except Exception as e:
        print(f"❌ Исключение: {e}")
        if check:
            sys.exit(1)
        return None


print("=" * 70)
print("ПРИМЕНЕНИЕ МИГРАЦИИ 029 - ПОЛНАЯ ПРОВЕРКА И ДЕПЛОЙ")
print("=" * 70)

# 1. Проверяем файл миграции
print("\n1️⃣ Проверка файла миграции...")
migration_file = Path("migrations/029_add_task_hint_to_task_places.sql")
if migration_file.exists():
    print(f"   ✅ Файл существует: {migration_file}")
    size = migration_file.stat().st_size
    print(f"   📏 Размер: {size} байт")
else:
    print("   ❌ Файл не найден!")
    sys.exit(1)

# 2. Проверяем git статус
print("\n2️⃣ Проверка git статуса...")
result = run("git status --short", check=False)
if result and result.stdout.strip():
    print("   📝 Есть незакоммиченные изменения:")
    print("   " + result.stdout.replace("\n", "\n   "))
    print("\n   ➕ Добавляю в git...")
    run("git add migrations/029_add_task_hint_to_task_places.sql")
    run("git add -A")
    print("   💾 Коммичу...")
    run('git commit -m "feat: Add task_hint column to task_places for AI hints"')
else:
    print("   ✅ Все изменения закоммичены")

# 3. Проверяем, есть ли что пушить
print("\n3️⃣ Проверка коммитов для пуша...")
result = run("git log origin/HEAD..HEAD --oneline", check=False)
if result and result.stdout.strip():
    print("   📤 Найдено коммитов для пуша:")
    print("   " + result.stdout.replace("\n", "\n   "))
    print("\n   🚀 Пушим в GitHub...")
    run("git push origin HEAD")
    print("   ✅ Изменения запушены!")
else:
    print("   ✅ Все изменения уже в GitHub")

# 4. Проверяем текущую ветку
print("\n4️⃣ Текущая ветка:")
result = run("git branch --show-current", check=False)
if result and result.stdout:
    branch = result.stdout.strip()
    print(f"   🌿 Ветка: {branch}")

# 5. Показываем последний коммит
print("\n5️⃣ Последний коммит:")
result = run("git log -1 --oneline", check=False)
if result and result.stdout:
    print("   " + result.stdout.strip())

print("\n" + "=" * 70)
print("✅ ВСЕ ГОТОВО!")
print("=" * 70)
print("\n📋 Следующий шаг:")
print("   1. Откройте: https://github.com/krikri8k-cmd/event-bot/actions")
print("   2. Найдите 'DB Apply (manual)'")
print("   3. Нажмите 'Run workflow'")
print("   4. Укажите путь: migrations/029_add_task_hint_to_task_places.sql")
print("   5. Запустите workflow")
print("\n✨ После этого столбец task_hint появится в БД!")
