#!/usr/bin/env python3
"""
Скрипт для деплоя в Railway
"""

import os
import subprocess
import sys


def check_git_status():
    """Проверяет статус git"""
    print("🔍 Проверяем статус git...")

    try:
        # Проверяем что мы в git репозитории
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)

        if result.stdout.strip():
            print("📝 Изменения в файлах:")
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")

            # Проверяем есть ли неотслеживаемые файлы
            result = subprocess.run(
                ["git", "status", "--untracked-files=all"], capture_output=True, text=True, check=True
            )

            print("\n📋 Полный статус:")
            print(result.stdout)

            return True
        else:
            print("✅ Нет изменений для коммита")
            return False

    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка git: {e}")
        return False


def commit_changes():
    """Коммитит изменения"""
    print("\n💾 Коммитим изменения...")

    try:
        # Добавляем все файлы
        subprocess.run(["git", "add", "."], check=True)
        print("✅ Файлы добавлены в staging")

        # Коммитим
        commit_message = """
🚀 Deploy: Separate tables architecture + KudaGo integration

✅ Changes:
- Created separate tables: events_parser, events_user
- Migrated all data from old events table
- Integrated KudaGo parser with new architecture
- Cleaned up unused tables
- Updated EventsService for regional routing
- Added Railway environment variables for KudaGo

🏗️ Architecture:
- events_parser: Parser events (baliforum, kudago)
- events_user: User-created events
- Regional routing by country/city
- Clean database structure (4 tables only)

🎯 Ready for production deployment
        """.strip()

        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        print("✅ Изменения закоммичены")

        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка коммита: {e}")
        return False


def push_to_railway():
    """Пушит в Railway"""
    print("\n🚀 Пушим в Railway...")

    try:
        # Пушим в main ветку (Railway обычно отслеживает main)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("✅ Изменения отправлены в Railway")

        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка push: {e}")
        print("💡 Возможно нужно настроить remote для Railway")
        return False


def check_railway_deployment():
    """Проверяет статус деплоя в Railway"""
    print("\n📊 Проверяем статус деплоя...")

    try:
        # Проверяем Railway CLI если установлен
        result = subprocess.run(["railway", "status"], capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ Railway CLI доступен")
            print(result.stdout)
        else:
            print("ℹ️ Railway CLI не установлен или не настроен")
            print("💡 Проверь деплой в веб-интерфейсе Railway")

    except FileNotFoundError:
        print("ℹ️ Railway CLI не найден")
        print("💡 Проверь деплой в веб-интерфейсе Railway")


def main():
    """Основная функция деплоя"""
    print("🚀 ЗАПУСК ДЕПЛОЯ В RAILWAY")
    print("=" * 50)

    # Проверяем что мы в правильной директории
    if not os.path.exists(".git"):
        print("❌ Не найден .git директория")
        print("💡 Убедись что ты в корне проекта")
        return False

    # Проверяем статус git
    has_changes = check_git_status()

    if has_changes:
        # Коммитим изменения
        if not commit_changes():
            print("❌ Не удалось закоммитить изменения")
            return False

    # Пушим в Railway
    if not push_to_railway():
        print("❌ Не удалось отправить в Railway")
        return False

    # Проверяем статус деплоя
    check_railway_deployment()

    print("\n🎉 ДЕПЛОЙ ЗАПУЩЕН!")
    print("\n📋 Что дальше:")
    print("  1. Проверь деплой в Railway Dashboard")
    print("  2. Убедись что переменные окружения настроены")
    print("  3. Протестируй бота после деплоя")
    print("  4. Проверь работу KudaGo парсера")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
