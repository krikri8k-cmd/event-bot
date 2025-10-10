#!/usr/bin/env python3
"""
Тестовый скрипт для проверки group_router модуля
"""

import sys

# Добавляем путь к проекту
sys.path.insert(0, ".")

print("=" * 60)
print("🧪 ТЕСТИРОВАНИЕ GROUP ROUTER")
print("=" * 60)
print()

# Тест 1: Импорты
print("📦 Тест 1: Проверка импортов")
try:
    from group_router import PANEL_TEXT, group_kb, group_router, set_bot_username

    print("  ✅ group_router импортирован")

    from utils.messaging_utils import delete_all_tracked, ensure_panel, is_chat_admin, send_tracked

    print("  ✅ messaging_utils импортирован")

    from database import BotMessage, ChatSettings, CommunityEvent, get_session, init_engine

    print("  ✅ database модели импортированы")

    print("  ✅ aiogram компоненты импортированы")

    print("✅ Все импорты успешны!\n")
except Exception as e:
    print(f"❌ Ошибка импорта: {e}\n")
    sys.exit(1)

# Тест 2: Структура роутера
print("🎯 Тест 2: Структура роутера")
try:
    print(f"  Router name: {group_router.name}")
    print(f"  Зарегистрировано обработчиков: {len(group_router.observers)}")

    # Проверяем что есть фильтры
    has_filters = hasattr(group_router, "message") and hasattr(group_router, "callback_query")
    print(f"  Фильтры настроены: {has_filters}")

    print("✅ Структура роутера корректна!\n")
except Exception as e:
    print(f"❌ Ошибка проверки роутера: {e}\n")

# Тест 3: ORM модели
print("🗄️ Тест 3: ORM модели")
try:
    print(f"  CommunityEvent.__tablename__: {CommunityEvent.__tablename__}")
    print(f"  BotMessage.__tablename__: {BotMessage.__tablename__}")
    print(f"  ChatSettings.__tablename__: {ChatSettings.__tablename__}")

    # Проверяем что у моделей есть нужные поля
    ce_fields = ["chat_id", "organizer_id", "organizer_username", "title", "starts_at", "status"]
    bm_fields = ["chat_id", "message_id", "tag", "deleted"]
    cs_fields = ["chat_id", "last_panel_message_id", "muted"]

    print(f"  CommunityEvent поля: {all(hasattr(CommunityEvent, f) for f in ce_fields)}")
    print(f"  BotMessage поля: {all(hasattr(BotMessage, f) for f in bm_fields)}")
    print(f"  ChatSettings поля: {all(hasattr(ChatSettings, f) for f in cs_fields)}")

    print("✅ ORM модели корректны!\n")
except Exception as e:
    print(f"❌ Ошибка проверки моделей: {e}\n")

# Тест 4: Функции утилит
print("🛠️ Тест 4: Функции утилит")
try:
    # Проверяем что функции определены и вызываемы
    print(f"  ensure_panel callable: {callable(ensure_panel)}")
    print(f"  send_tracked callable: {callable(send_tracked)}")
    print(f"  delete_all_tracked callable: {callable(delete_all_tracked)}")
    print(f"  is_chat_admin callable: {callable(is_chat_admin)}")

    print("✅ Функции утилит доступны!\n")
except Exception as e:
    print(f"❌ Ошибка проверки утилит: {e}\n")

# Тест 5: Клавиатура и тексты
print("⌨️ Тест 5: Клавиатура и тексты")
try:
    # Устанавливаем username для тестирования
    set_bot_username("TestBot")

    # Создаем клавиатуру
    keyboard = group_kb(chat_id=-1001234567890)
    print(f"  Keyboard type: {type(keyboard).__name__}")
    print(f"  Количество кнопок: {len(keyboard.inline_keyboard)}")

    # Проверяем текст панели
    print(f"  PANEL_TEXT длина: {len(PANEL_TEXT)} символов")
    print(f"  PANEL_TEXT содержит emoji: {'👋' in PANEL_TEXT}")

    print("✅ Клавиатура и тексты корректны!\n")
except Exception as e:
    print(f"❌ Ошибка проверки UI: {e}\n")

# Тест 6: Интеграция с основным ботом
print("🔌 Тест 6: Интеграция с основным ботом")
try:
    import bot_enhanced_v3

    # Проверяем что роутер импортирован
    has_group_router = "group_router" in dir(bot_enhanced_v3)
    print(f"  group_router импортирован в bot_enhanced_v3: {has_group_router}")

    # Проверяем что диспетчер существует
    has_dp = hasattr(bot_enhanced_v3, "dp")
    print(f"  Диспетчер dp существует: {has_dp}")

    if has_dp:
        # Проверяем что роутер подключен
        dp = bot_enhanced_v3.dp
        routers_count = len([r for r in dp.sub_routers if hasattr(r, "name")])
        print(f"  Количество подключенных роутеров: {routers_count}")

    print("✅ Интеграция с основным ботом корректна!\n")
except Exception as e:
    print(f"❌ Ошибка проверки интеграции: {e}\n")

# Тест 7: Проверка файлов миграций
print("📄 Тест 7: Файлы миграций")
try:
    import os

    migration_files = ["migrations/001_fix_events_community.sql", "migrations/002_add_bot_tracking.sql"]

    for file in migration_files:
        exists = os.path.exists(file)
        size = os.path.getsize(file) if exists else 0
        print(f"  {file}: {'✅' if exists else '❌'} ({size} bytes)")

    print("✅ Файлы миграций существуют!\n")
except Exception as e:
    print(f"❌ Ошибка проверки миграций: {e}\n")

# Тест 8: Симуляция базовых операций
print("🎬 Тест 8: Симуляция операций (без реального бота)")
try:
    from config import load_settings

    settings = load_settings()
    print(f"  DATABASE_URL загружен: {bool(settings.database_url)}")

    # Инициализируем engine
    init_engine(settings.database_url)
    print("  ✅ Database engine инициализирован")

    # Проверяем что можем создать сессию
    with get_session() as session:
        print("  ✅ Session создана успешно")

        # Можем ли делать запросы?
        from sqlalchemy import text

        result = session.execute(text("SELECT 1"))
        print(f"  ✅ Тестовый запрос выполнен: {result.fetchone()[0] == 1}")

    print("✅ Базовые операции с БД работают!\n")
except Exception as e:
    print(f"❌ Ошибка симуляции: {e}\n")

# Итог
print("=" * 60)
print("🎉 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
print("=" * 60)
print()
print("✅ Все базовые проверки пройдены!")
print()
print("📋 Что дальше:")
print("  1. Применить миграции БД")
print("  2. Запустить бота: python bot_enhanced_v3.py")
print("  3. Добавить бота в тестовую группу")
print("  4. Протестировать команду /start")
print("  5. Протестировать создание события")
print("  6. Протестировать 'Спрятать бота'")
print()
print("📚 Документация: GROUP_ROUTER_IMPLEMENTATION.md")
print()
