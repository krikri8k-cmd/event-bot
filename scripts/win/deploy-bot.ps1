# PowerShell скрипт для деплоя Telegram бота на Railway

Write-Host "🚀 Деплой EventBot на Railway..." -ForegroundColor Green

# Проверяем что мы в правильной директории
if (-not (Test-Path "bot_enhanced_v3.py")) {
    Write-Host "❌ Ошибка: запусти скрипт из корневой директории проекта!" -ForegroundColor Red
    exit 1
}

# Проверяем что все файлы на месте
$requiredFiles = @(
    "Dockerfile.bot",
    "railway-bot-start.sh", 
    "bot_health.py",
    "requirements.txt"
)

foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        Write-Host "❌ Отсутствует файл: $file" -ForegroundColor Red
        exit 1
    }
}

Write-Host "✅ Все необходимые файлы найдены" -ForegroundColor Green

# Коммитим изменения
Write-Host "📝 Коммитим изменения..." -ForegroundColor Yellow
git add .
git commit -m "feat: add Railway bot deployment with health check and keep-alive"

# Пушим в репозиторий
Write-Host "📤 Пушим в репозиторий..." -ForegroundColor Yellow
git push

Write-Host "✅ Код запушен в репозиторий!" -ForegroundColor Green
Write-Host ""
Write-Host "🎯 Следующие шаги:" -ForegroundColor Cyan
Write-Host "1. Открой Railway.app" -ForegroundColor White
Write-Host "2. Создай новый сервис" -ForegroundColor White
Write-Host "3. Выбери 'Build via Dockerfile'" -ForegroundColor White
Write-Host "4. Укажи Dockerfile.bot как путь к Dockerfile" -ForegroundColor White
Write-Host "5. Добавь переменные окружения:" -ForegroundColor White
Write-Host "   - TELEGRAM_TOKEN=твой_токен_бота" -ForegroundColor White
Write-Host "   - DATABASE_URL=твой_url_базы" -ForegroundColor White
Write-Host "6. Нажми Deploy!" -ForegroundColor White
Write-Host ""
Write-Host "📖 Подробная инструкция в файле RAILWAY_BOT_DEPLOY.md" -ForegroundColor Cyan
