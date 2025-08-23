#!/usr/bin/env python3
"""
Тестовый скрипт для проверки подключения к базе данных Railway
"""

import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv('.env.local', encoding='utf-8-sig')

def test_database_connection():
    """Тестирует подключение к базе данных"""
    try:
        from database import init_engine, create_all
        
        # Получаем URL базы данных
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("❌ ОШИБКА: DATABASE_URL не найден в переменных окружения")
            return False
            
        print(f"🔗 Подключаемся к базе данных...")
        print(f"   URL: {database_url[:20]}...")
        
        # Инициализируем подключение
        init_engine(database_url)
        print("✅ Подключение к базе данных успешно!")
        
        # Создаём таблицы
        create_all()
        print("✅ Таблицы созданы/проверены!")
        
        return True
        
    except Exception as e:
        print(f"❌ ОШИБКА подключения к базе данных: {e}")
        return False

def test_telegram_token():
    """Проверяет наличие токена Telegram"""
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        print("⚠️  ПРЕДУПРЕЖДЕНИЕ: TELEGRAM_TOKEN не найден")
        return False
    else:
        print(f"✅ TELEGRAM_TOKEN найден: {token[:10]}...")
        return True

def main():
    print("🧪 Тестирование конфигурации для Railway...")
    print("=" * 50)
    
    # Проверяем переменные окружения
    print("\n📋 Проверка переменных окружения:")
    test_telegram_token()
    
    # Проверяем подключение к БД
    print("\n🗄️  Проверка базы данных:")
    db_ok = test_database_connection()
    
    print("\n" + "=" * 50)
    if db_ok:
        print("🎉 Всё готово для деплоя на Railway!")
        print("\n📝 Следующие шаги:")
        print("1. Переименуй env.local.railway в .env.local")
        print("2. Заполни TELEGRAM_TOKEN в Railway")
        print("3. Деплой на Railway!")
    else:
        print("❌ Есть проблемы с конфигурацией")
        sys.exit(1)

if __name__ == "__main__":
    main()
