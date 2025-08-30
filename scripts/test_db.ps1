# PowerShell скрипт для тестирования подключения к БД
param(
    [string]$DatabaseUrl = $env:DATABASE_URL
)

if (-not $DatabaseUrl) {
    Write-Host "❌ DATABASE_URL не найден в переменных окружения" -ForegroundColor Red
    Write-Host "   Установи: `$env:DATABASE_URL = 'postgresql://user:pass@host:port/db?sslmode=require'" -ForegroundColor Yellow
    exit 1
}

Write-Host "🔗 Подключаюсь к БД..." -ForegroundColor Cyan
Write-Host "   URL: $($DatabaseUrl.Split('@')[1])" -ForegroundColor Gray

try {
    python test_db_connection.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Тест подключения успешен!" -ForegroundColor Green
    } else {
        Write-Host "❌ Тест подключения провален!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Ошибка выполнения: $_" -ForegroundColor Red
    exit 1
}
