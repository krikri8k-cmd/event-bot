#!/usr/bin/env python3
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """Выполняет команду и выводит результат"""
    print(f"\n{'='*70}")
    print(f"▶ {description}")
    print(f"Команда: {cmd}")
    print("=" * 70)

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, encoding="utf-8", cwd=Path(__file__).parent, check=False
        )

        if result.stdout:
            print("STDOUT:")
            print(result.stdout)

        if result.stderr:
            print("STDERR:")
            print(result.stderr)

        print(f"Exit code: {result.returncode}")

        if result.returncode == 0:
            print("✅ Успешно")
        else:
            print("❌ Ошибка")

        return result.returncode == 0

    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False


print("=" * 70)
print("ВЫПОЛНЕНИЕ GIT КОМАНД ДЛЯ МИГРАЦИИ 029")
print("=" * 70)

# Проверяем текущий статус
print("\n📋 Текущий статус:")
run_command("git status", "Проверка статуса")

# Добавляем файл
print("\n📝 Добавление файла в git...")
success = run_command(
    "git add migrations/029_add_task_hint_to_task_places.sql", "git add migrations/029_add_task_hint_to_task_places.sql"
)

if success:
    # Коммитим
    print("\n💾 Создание коммита...")
    success = run_command('git commit -m "feat: Add task_hint column to task_places table"', "git commit")

    if success:
        # Пушим
        print("\n🚀 Отправка в GitHub...")
        success = run_command("git push origin main", "git push origin main")

        if success:
            print("\n" + "=" * 70)
            print("✅ ВСЕ КОМАНДЫ ВЫПОЛНЕНЫ УСПЕШНО!")
            print("=" * 70)
        else:
            print("\n" + "=" * 70)
            print("⚠️ git push не выполнен")
            print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("⚠️ git commit не выполнен (возможно, нет изменений)")
        print("=" * 70)
else:
    print("\n" + "=" * 70)
    print("⚠️ git add не выполнен")
    print("=" * 70)

# Финальная проверка
print("\n📊 Финальная проверка:")
run_command("git status", "Финальный статус")
run_command("git log --oneline -3", "Последние 3 коммита")

print("\n" + "=" * 70)
print("ГОТОВО!")
print("=" * 70)
