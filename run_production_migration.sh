#!/bin/bash
# Скрипт для запуска продакшен миграции
# Включает все проверки и безопасность

set -e  # Остановка при ошибке

echo "🚀 ПРОДАКШЕН МИГРАЦИЯ: Объединение таблиц событий"
echo "=================================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для логирования
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Проверка переменных окружения
check_env() {
    log "Проверка переменных окружения..."
    
    if [ -z "$DATABASE_URL" ]; then
        error "DATABASE_URL не установлена!"
        echo "Установите переменную: export DATABASE_URL='postgresql://user:pass@host:port/db'"
        exit 1
    fi
    
    success "DATABASE_URL установлена"
}

# Создание резервной копии
create_backup() {
    log "Создание резервной копии..."
    
    BACKUP_FILE="backup_before_migration_$(date +%Y%m%d_%H%M%S).sql"
    
    if pg_dump "$DATABASE_URL" > "$BACKUP_FILE"; then
        success "Резервная копия создана: $BACKUP_FILE"
        echo "Размер: $(du -h "$BACKUP_FILE" | cut -f1)"
    else
        error "Ошибка создания резервной копии!"
        exit 1
    fi
}

# Предварительные проверки
pre_checks() {
    log "Выполнение предварительных проверок..."
    
    if python migrate_events_production.py --check-only; then
        success "Предварительные проверки пройдены"
    else
        error "Предварительные проверки не пройдены!"
        exit 1
    fi
}

# Dry-run тест
dry_run_test() {
    log "Выполнение dry-run теста..."
    
    if python migrate_events_production.py --dry-run; then
        success "Dry-run тест пройден"
    else
        error "Dry-run тест не пройден!"
        exit 1
    fi
}

# Основная миграция
run_migration() {
    log "Запуск продакшен миграции..."
    
    # Спрашиваем подтверждение
    echo ""
    warning "ВНИМАНИЕ: Будет изменена структура базы данных!"
    echo "Резервная копия создана в: $BACKUP_FILE"
    echo ""
    read -p "Продолжить миграцию? (yes/no): " -r
    
    if [[ $REPLY =~ ^[Yy]([Ee][Ss])?$ ]]; then
        if python migrate_events_production.py; then
            success "Миграция выполнена успешно!"
        else
            error "Ошибка миграции!"
            echo "Для отката выполните: psql \$DATABASE_URL -f migrations/rollback_merge_events.sql"
            exit 1
        fi
    else
        warning "Миграция отменена пользователем"
        exit 0
    fi
}

# Проверка результата
verify_result() {
    log "Проверка результата миграции..."
    
    # Проверяем статистику
    psql "$DATABASE_URL" -c "
        SELECT 
            source,
            COUNT(*) as count,
            MIN(created_at_utc) as earliest,
            MAX(created_at_utc) as latest
        FROM events 
        WHERE source IS NOT NULL
        GROUP BY source
        ORDER BY count DESC;
    "
    
    # Проверяем дубликаты
    DUPLICATES=$(psql "$DATABASE_URL" -t -c "
        SELECT COUNT(*) FROM (
            SELECT source, external_id, COUNT(*) 
            FROM events 
            WHERE source IS NOT NULL 
            GROUP BY source, external_id 
            HAVING COUNT(*) > 1
        ) duplicates;
    " | tr -d ' ')
    
    if [ "$DUPLICATES" -eq 0 ]; then
        success "Дубликатов не найдено"
    else
        warning "Найдено дубликатов: $DUPLICATES"
    fi
    
    # Проверяем индексы
    INDEX_COUNT=$(psql "$DATABASE_URL" -t -c "
        SELECT COUNT(*) 
        FROM pg_indexes 
        WHERE tablename = 'events' 
        AND indexname LIKE 'idx_events_%';
    " | tr -d ' ')
    
    success "Создано индексов: $INDEX_COUNT"
}

# Cleanup старых таблиц
cleanup_old_tables() {
    log "Предложение cleanup старых таблиц..."
    
    echo ""
    read -p "Удалить старые таблицы events_parser и events_user? (yes/no): " -r
    
    if [[ $REPLY =~ ^[Yy]([Ee][Ss])?$ ]]; then
        if python cleanup_old_events_tables.py; then
            success "Cleanup выполнен успешно!"
        else
            warning "Cleanup не удался, но миграция завершена"
        fi
    else
        warning "Cleanup пропущен"
    fi
}

# Финальный отчет
final_report() {
    echo ""
    success "=========================================="
    success "МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!"
    success "=========================================="
    echo ""
    echo "📊 Результат:"
    echo "  • Резервная копия: $BACKUP_FILE"
    echo "  • Таблицы объединены: events_parser + events_user → events"
    echo "  • events_community осталась отдельно"
    echo "  • Созданы нормализованные поля: geo_hash, starts_at_normalized"
    echo "  • Добавлены частичные индексы для дедупликации"
    echo ""
    echo "🔧 Следующие шаги:"
    echo "  • Обновите код для работы с новой структурой"
    echo "  • Протестируйте функциональность"
    echo "  • Обновите документацию"
    echo ""
    echo "🆘 Поддержка:"
    echo "  • Откат: psql \$DATABASE_URL -f migrations/rollback_merge_events.sql"
    echo "  • Логи: check logs/ directory"
    echo ""
}

# Главная функция
main() {
    echo "Начинаем продакшен миграцию..."
    echo ""
    
    check_env
    create_backup
    pre_checks
    dry_run_test
    run_migration
    verify_result
    cleanup_old_tables
    final_report
}

# Обработка сигналов
trap 'error "Миграция прервана пользователем"; exit 1' INT TERM

# Запуск
main "$@"
