# PowerShell скрипт для применения миграции
param(
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [string]$SqlFile = "sql/2025_ics_sources_and_indexes.sql"
)

if (-not $DatabaseUrl) {
    Write-Host "❌ DATABASE_URL не найден в переменных окружения" -ForegroundColor Red
    Write-Host "   Установи: `$env:DATABASE_URL = 'postgresql://user:pass@host:port/db?sslmode=require'" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $SqlFile)) {
    Write-Host "❌ Файл $SqlFile не найден" -ForegroundColor Red
    exit 1
}

Write-Host "🔗 Подключаюсь к БД..." -ForegroundColor Cyan
Write-Host "📄 Применяю: $SqlFile" -ForegroundColor Cyan

try {
    python scripts/apply_sql.py $SqlFile
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Миграция применена успешно!" -ForegroundColor Green
    } else {
        Write-Host "❌ Ошибка применения миграции!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Ошибка выполнения: $_" -ForegroundColor Red
    exit 1
}
