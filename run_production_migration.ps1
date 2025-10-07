# PowerShell скрипт для запуска продакшен миграции
# Включает все проверки и безопасность

param(
    [switch]$Force,
    [switch]$DryRun,
    [switch]$CheckOnly
)

# Остановка при ошибке
$ErrorActionPreference = "Stop"

Write-Host "🚀 ПРОДАКШЕН МИГРАЦИЯ: Объединение таблиц событий" -ForegroundColor Blue
Write-Host "==================================================" -ForegroundColor Blue

# Функция для логирования
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    switch ($Level) {
        "ERROR" { Write-Host "[$timestamp] [ERROR] $Message" -ForegroundColor Red }
        "SUCCESS" { Write-Host "[$timestamp] [SUCCESS] $Message" -ForegroundColor Green }
        "WARNING" { Write-Host "[$timestamp] [WARNING] $Message" -ForegroundColor Yellow }
        default { Write-Host "[$timestamp] [INFO] $Message" -ForegroundColor Cyan }
    }
}

# Проверка переменных окружения
function Test-Environment {
    Write-Log "Проверка переменных окружения..."
    
    if (-not $env:DATABASE_URL) {
        Write-Log "DATABASE_URL не установлена!" "ERROR"
        Write-Host "Установите переменную: `$env:DATABASE_URL='postgresql://user:pass@host:port/db'"
        exit 1
    }
    
    Write-Log "DATABASE_URL установлена" "SUCCESS"
}

# Создание резервной копии
function New-Backup {
    Write-Log "Создание резервной копии..."
    
    $backupFile = "backup_before_migration_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql"
    
    try {
        & pg_dump $env:DATABASE_URL | Out-File -FilePath $backupFile -Encoding UTF8
        $fileSize = (Get-Item $backupFile).Length
        $fileSizeMB = [math]::Round($fileSize / 1MB, 2)
        
        Write-Log "Резервная копия создана: $backupFile (${fileSizeMB} MB)" "SUCCESS"
        return $backupFile
    }
    catch {
        Write-Log "Ошибка создания резервной копии: $_" "ERROR"
        exit 1
    }
}

# Предварительные проверки
function Test-PreChecks {
    Write-Log "Выполнение предварительных проверок..."
    
    try {
        & python migrate_events_production.py --check-only
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Предварительные проверки пройдены" "SUCCESS"
        } else {
            throw "Предварительные проверки не пройдены"
        }
    }
    catch {
        Write-Log "Предварительные проверки не пройдены: $_" "ERROR"
        exit 1
    }
}

# Dry-run тест
function Test-DryRun {
    Write-Log "Выполнение dry-run теста..."
    
    try {
        & python migrate_events_production.py --dry-run
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Dry-run тест пройден" "SUCCESS"
        } else {
            throw "Dry-run тест не пройден"
        }
    }
    catch {
        Write-Log "Dry-run тест не пройден: $_" "ERROR"
        exit 1
    }
}

# Основная миграция
function Start-Migration {
    param([string]$BackupFile)
    
    Write-Log "Запуск продакшен миграции..."
    
    if (-not $Force) {
        Write-Host ""
        Write-Host "⚠️ ВНИМАНИЕ: Будет изменена структура базы данных!" -ForegroundColor Yellow
        Write-Host "Резервная копия создана в: $BackupFile" -ForegroundColor Yellow
        Write-Host ""
        
        $response = Read-Host "Продолжить миграцию? (yes/no)"
        
        if ($response -notmatch "^[Yy]([Ee][Ss])?$") {
            Write-Log "Миграция отменена пользователем" "WARNING"
            exit 0
        }
    }
    
    try {
        if ($DryRun) {
            & python migrate_events_production.py --dry-run
        } else {
            & python migrate_events_production.py
        }
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Миграция выполнена успешно!" "SUCCESS"
        } else {
            throw "Ошибка миграции"
        }
    }
    catch {
        Write-Log "Ошибка миграции: $_" "ERROR"
        Write-Host "Для отката выполните: psql `$env:DATABASE_URL -f migrations/rollback_merge_events.sql" -ForegroundColor Yellow
        exit 1
    }
}

# Проверка результата
function Test-Result {
    Write-Log "Проверка результата миграции..."
    
    try {
        # Проверяем статистику
        Write-Host "📊 Статистика событий по источникам:" -ForegroundColor Blue
        & psql $env:DATABASE_URL -c "
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
        $duplicates = & psql $env:DATABASE_URL -t -c "
            SELECT COUNT(*) FROM (
                SELECT source, external_id, COUNT(*) 
                FROM events 
                WHERE source IS NOT NULL 
                GROUP BY source, external_id 
                HAVING COUNT(*) > 1
            ) duplicates;
        " | ForEach-Object { $_.Trim() }
        
        if ([int]$duplicates -eq 0) {
            Write-Log "Дубликатов не найдено" "SUCCESS"
        } else {
            Write-Log "Найдено дубликатов: $duplicates" "WARNING"
        }
        
        # Проверяем индексы
        $indexCount = & psql $env:DATABASE_URL -t -c "
            SELECT COUNT(*) 
            FROM pg_indexes 
            WHERE tablename = 'events' 
            AND indexname LIKE 'idx_events_%';
        " | ForEach-Object { $_.Trim() }
        
        Write-Log "Создано индексов: $indexCount" "SUCCESS"
    }
    catch {
        Write-Log "Ошибка проверки результата: $_" "WARNING"
    }
}

# Cleanup старых таблиц
function Remove-OldTables {
    Write-Log "Предложение cleanup старых таблиц..."
    
    if (-not $Force) {
        Write-Host ""
        $response = Read-Host "Удалить старые таблицы events_parser и events_user? (yes/no)"
        
        if ($response -notmatch "^[Yy]([Ee][Ss])?$") {
            Write-Log "Cleanup пропущен" "WARNING"
            return
        }
    }
    
    try {
        & python cleanup_old_events_tables.py
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Cleanup выполнен успешно!" "SUCCESS"
        } else {
            Write-Log "Cleanup не удался, но миграция завершена" "WARNING"
        }
    }
    catch {
        Write-Log "Ошибка cleanup: $_" "WARNING"
    }
}

# Финальный отчет
function Show-FinalReport {
    param([string]$BackupFile)
    
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "📊 Результат:" -ForegroundColor Blue
    Write-Host "  • Резервная копия: $BackupFile"
    Write-Host "  • Таблицы объединены: events_parser + events_user → events"
    Write-Host "  • events_community осталась отдельно"
    Write-Host "  • Созданы нормализованные поля: geo_hash, starts_at_normalized"
    Write-Host "  • Добавлены частичные индексы для дедупликации"
    Write-Host ""
    Write-Host "🔧 Следующие шаги:" -ForegroundColor Blue
    Write-Host "  • Обновите код для работы с новой структурой"
    Write-Host "  • Протестируйте функциональность"
    Write-Host "  • Обновите документацию"
    Write-Host ""
    Write-Host "🆘 Поддержка:" -ForegroundColor Blue
    Write-Host "  • Откат: psql `$env:DATABASE_URL -f migrations/rollback_merge_events.sql"
    Write-Host "  • Логи: check logs/ directory"
    Write-Host ""
}

# Главная функция
function Main {
    Write-Host "Начинаем продакшен миграцию..." -ForegroundColor Blue
    Write-Host ""
    
    if ($CheckOnly) {
        Test-Environment
        Test-PreChecks
        return
    }
    
    Test-Environment
    $backupFile = New-Backup
    Test-PreChecks
    
    if (-not $DryRun) {
        Test-DryRun
    }
    
    Start-Migration -BackupFile $backupFile
    Test-Result
    Remove-OldTables
    Show-FinalReport -BackupFile $backupFile
}

# Обработка Ctrl+C
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    Write-Host "`nМиграция прервана пользователем" -ForegroundColor Red
    exit 1
}

# Запуск
try {
    Main
}
catch {
    Write-Log "Критическая ошибка: $_" "ERROR"
    exit 1
}
