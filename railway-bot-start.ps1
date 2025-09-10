# PowerShell скрипт для запуска Telegram бота на Railway

Write-Host "🚀 Запуск EventBot на Railway..." -ForegroundColor Green

# Создаем директорию для логов
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

# Функция для keep-alive
function Keep-Alive {
    while ($true) {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Write-Host "$timestamp 🔄 Keep-alive ping..." -ForegroundColor Yellow
        Start-Sleep -Seconds 300  # каждые 5 минут
    }
}

# Запускаем keep-alive в фоне
Start-Job -ScriptBlock { Keep-Alive } | Out-Null

# Запускаем бота
Write-Host "🤖 Запуск Telegram бота..." -ForegroundColor Green
python bot_enhanced_v3.py
