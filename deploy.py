#!/usr/bin/env python3
"""
Скрипт для деплоя на Railway с автоматизацией
"""

import subprocess
from datetime import datetime


def run_command(cmd, description):
    """Выполняет команду и выводит результат"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} - успешно")
            if result.stdout.strip():
                print(f"📄 Вывод: {result.stdout.strip()}")
        else:
            print(f"❌ {description} - ошибка")
            print(f"📄 Ошибка: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ {description} - исключение: {e}")
        return False
    return True


def main():
    print("🚀 === ДЕПЛОЙ EVENT-BOT С АВТОМАТИЗАЦИЕЙ ===")
    print(f"⏰ Время: {datetime.now()}")
    print()

    print("📋 Что будет задеплоено:")
    print("   🤖 Telegram бот")
    print("   🚀 Автоматизация парсинга (каждые 12 часов)")
    print("   🧹 Автоочистка старых событий")
    print("   📊 Правильная архитектура (events_parser → events)")
    print()

    # Проверяем git статус
    if not run_command("git status --porcelain", "Проверка git статуса"):
        return

    # Добавляем файлы
    if not run_command("git add .", "Добавление файлов в git"):
        return

    # Коммитим изменения
    commit_msg = f"Deploy: Add automation scheduler - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if not run_command(f'git commit -m "{commit_msg}"', "Создание коммита"):
        print("ℹ️ Возможно, нет изменений для коммита")

    # Пушим на main
    if not run_command("git push origin main", "Push на GitHub"):
        print("⚠️ Ошибка push, но продолжаем...")

    # Деплоим на Railway
    print("\n🚂 Деплой на Railway...")
    if not run_command("railway up", "Деплой на Railway"):
        print("❌ Ошибка деплоя на Railway")
        print("💡 Убедитесь что:")
        print("   • Railway CLI установлен")
        print("   • Вы залогинены: railway login")
        print("   • Проект подключен: railway link")
        return

    print("\n🎉 === ДЕПЛОЙ ЗАВЕРШЕН ===")
    print("✅ Бот задеплоен с автоматизацией!")
    print("📊 Мониторинг:")
    print("   • railway logs - логи приложения")
    print("   • railway status - статус сервиса")
    print("   • railway open - открыть в браузере")
    print()
    print("⏰ Автоматизация работает:")
    print("   • Парсинг: каждые 12 часов")
    print("   • Очистка: каждые 6 часов")
    print("   • Архитектура: events_parser → events")


if __name__ == "__main__":
    main()
