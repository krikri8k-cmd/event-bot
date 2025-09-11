# PowerShell скрипт для автоматического запуска бота
# Автоматически находит свободный порт и убивает зависшие процессы

param(
    [int]$DefaultPort = 8000,
    [string]$BotFile = "bot_enhanced_v3.py"
)

Write-Host "🚀 Запуск EventBot в dev режиме..." -ForegroundColor Green

# 1. Убиваем все зависшие Python процессы
Write-Host "🧹 Очищаем зависшие процессы..." -ForegroundColor Yellow
try {
    Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host "   ✅ Python процессы очищены" -ForegroundColor Green
} catch {
    Write-Host "   ℹ️  Python процессы не найдены" -ForegroundColor Blue
}

# 2. Функция для поиска свободного порта
function Find-FreePort {
    param([int]$StartPort)
    
    for ($port = $StartPort; $port -le $StartPort + 100; $port++) {
        try {
            $connection = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
            if (-not $connection) {
                return $port
            }
        } catch {
            return $port
        }
    }
    return $StartPort + 1000  # Fallback
}

# 3. Находим свободный порт
$FreePort = Find-FreePort -StartPort $DefaultPort
Write-Host "🔍 Найден свободный порт: $FreePort" -ForegroundColor Green

# 4. Устанавливаем переменные окружения
$env:PORT = $FreePort.ToString()
$env:WEBHOOK_URL = "http://127.0.0.1:$FreePort/webhook"
$env:TELEGRAM_TOKEN = "dummy"  # Для локальной разработки
$env:ENABLE_BALIFORUM = "1"

Write-Host "📡 Webhook URL: $env:WEBHOOK_URL" -ForegroundColor Cyan
Write-Host "🌴 Baliforum: включен" -ForegroundColor Cyan

# 5. Запускаем бота
Write-Host "🤖 Запускаем бота..." -ForegroundColor Green
Write-Host "   Для остановки нажми Ctrl+C" -ForegroundColor Yellow
Write-Host ""

try {
    python $BotFile
} catch {
    Write-Host "Ошибка запуска: $_" -ForegroundColor Red
    exit 1
}
