# PowerShell скрипт для запуска API сервера
# Автоматически находит свободный порт

param(
    [int]$DefaultPort = 8000,
    [string]$ApiFile = "start_server.py"
)

Write-Host "🚀 Запуск EventBot API сервера..." -ForegroundColor Green

# 1. Убиваем зависшие процессы
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
    return $StartPort + 1000
}

# 3. Находим свободный порт
$FreePort = Find-FreePort -StartPort $DefaultPort
Write-Host "🔍 Найден свободный порт: $FreePort" -ForegroundColor Green

# 4. Устанавливаем переменные окружения
$env:PORT = $FreePort.ToString()
$env:DATABASE_URL = "postgresql://postgres:password@host:port/database?sslmode=require"
$env:ENABLE_BALIFORUM = "1"

Write-Host "📡 API URL: http://127.0.0.1:$FreePort" -ForegroundColor Cyan
Write-Host "🏥 Health: http://127.0.0.1:$FreePort/health" -ForegroundColor Cyan
Write-Host "🌴 Baliforum: включен" -ForegroundColor Cyan

# 5. Запускаем API сервер
Write-Host "🌐 Запускаем API сервер..." -ForegroundColor Green
Write-Host "   Для остановки нажми Ctrl+C" -ForegroundColor Yellow
Write-Host ""

try {
    python $ApiFile
} catch {
    Write-Host "Ошибка запуска: $_" -ForegroundColor Red
    exit 1
}
