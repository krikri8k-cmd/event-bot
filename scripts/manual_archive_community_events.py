#!/usr/bin/env python3
"""
Скрипт для ручной архивации прошедших событий сообществ
Отправляет в архив события, которые должны быть заархивированы по текущей логике
"""

import os
import sys

from dotenv import load_dotenv

# Настройка кодировки для Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.community_events_service import CommunityEventsService


def main():
    """Ручная архивация прошедших событий"""
    print("🧹 Запуск ручной архивации событий сообществ...")
    print()

    try:
        # Загружаем переменные окружения
        env_path = "app.local.env"
        if not os.path.exists(env_path):
            print(f"❌ Файл {env_path} не найден!")
            print("💡 Убедитесь, что вы запускаете скрипт из корневой директории проекта")
            sys.exit(1)

        load_dotenv(env_path)

        # Создаем сервис
        community_service = CommunityEventsService()

        # Запускаем архивацию
        # days_old=1 означает события старше 1 дня
        deleted_count = community_service.cleanup_expired_events(days_old=1)

        print()
        if deleted_count > 0:
            print(f"✅ Успешно заархивировано и удалено {deleted_count} событий")
        else:
            print("ℹ️ Событий для архивации не найдено")
            print("   (Все события либо свежие, либо уже заархивированы)")

        print()
        print("📋 Логика архивации:")
        print("   • Открытые события: если дата начала прошла более 1 дня назад")
        print("   • Закрытые события: если закрыты более 24 часов назад")

    except Exception as e:
        print(f"❌ Ошибка при архивации: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
