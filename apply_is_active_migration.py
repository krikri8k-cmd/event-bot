#!/usr/bin/env python3
"""
Скрипт для применения миграции is_active в moments
"""

import os
import sys
import logging
from pathlib import Path

# Добавляем корневую папку проекта в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import get_engine, init_engine
from config import load_settings
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def apply_is_active_migration():
    """Применяет миграцию добавления is_active в moments"""
    try:
        # Читаем SQL миграцию
        migration_file = project_root / "migrations" / "004_add_is_active_to_moments.sql"
        
        if not migration_file.exists():
            logger.error(f"❌ Файл миграции не найден: {migration_file}")
            return False
            
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        logger.info("📄 Читаем миграцию добавления is_active...")
        
        # Инициализируем и подключаемся к БД
        settings = load_settings()
        init_engine(settings.database_url)
        engine = get_engine()
        
        with engine.connect() as conn:
            # Выполняем миграцию
            logger.info("🔧 Применяем миграцию добавления is_active...")
            conn.execute(text(migration_sql))
            conn.commit()
            
        logger.info("✅ Миграция is_active успешно применена!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка применения миграции: {e}")
        return False

def check_is_active_field():
    """Проверяет наличие поля is_active в таблице moments"""
    try:
        settings = load_settings()
        init_engine(settings.database_url)
        engine = get_engine()
        
        with engine.connect() as conn:
            # Проверяем наличие поля is_active
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'moments' AND column_name = 'is_active'
                );
            """))
            
            field_exists = result.scalar()
            
            if field_exists:
                logger.info("✅ Поле is_active существует в таблице moments")
                
                # Проверяем структуру поля
                result = conn.execute(text("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns 
                    WHERE table_name = 'moments' AND column_name = 'is_active';
                """))
                
                field_info = result.fetchone()
                if field_info:
                    logger.info(f"📋 Поле is_active: {field_info[1]} {'NULL' if field_info[2] == 'YES' else 'NOT NULL'} {f'DEFAULT {field_info[3]}' if field_info[3] else ''}")
                
                return True
            else:
                logger.warning("⚠️ Поле is_active не существует в таблице moments")
                return False
                
    except Exception as e:
        logger.error(f"❌ Ошибка проверки поля is_active: {e}")
        return False

if __name__ == "__main__":
    logger.info("🚀 Запуск применения миграции is_active...")
    
    # Применяем миграцию
    if apply_is_active_migration():
        logger.info("✅ Миграция применена успешно!")
        
        # Проверяем результат
        logger.info("🔍 Проверяем поле is_active...")
        check_is_active_field()
        
    else:
        logger.error("❌ Не удалось применить миграцию")
        sys.exit(1)
