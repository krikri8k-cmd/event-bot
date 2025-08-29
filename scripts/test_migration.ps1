# PowerShell скрипт для тестирования миграции
param(
    [string]$DatabaseUrl = $env:DATABASE_URL
)

if (-not $DatabaseUrl) {
    Write-Host "❌ DATABASE_URL не найден в переменных окружения" -ForegroundColor Red
    Write-Host "   Установи: `$env:DATABASE_URL = 'postgresql://user:pass@host:port/db?sslmode=require'" -ForegroundColor Yellow
    exit 1
}

Write-Host "🔗 Подключаюсь к БД..." -ForegroundColor Cyan
Write-Host "📄 Применяю: sql/2025_ics_sources_and_indexes.sql" -ForegroundColor Cyan

try {
    python test_migration.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Тест миграции успешен!" -ForegroundColor Green
    } else {
        Write-Host "❌ Тест миграции провален!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Ошибка выполнения: $_" -ForegroundColor Red
    exit 1
}
