# Быстрая проверка "готов к бою" для Windows

Write-Host "🚀 Быстрая проверка Event Bot системы..." -ForegroundColor Green

# Проверяем что DATABASE_URL установлен
if (-not $env:DATABASE_URL) {
    Write-Host "❌ DATABASE_URL не установлен" -ForegroundColor Red
    exit 1
}

Write-Host "✅ DATABASE_URL установлен" -ForegroundColor Green

# Применяем индексы и уникальные констрейнты
Write-Host "📊 Применяем индексы и констрейнты..." -ForegroundColor Yellow
try {
    psql $env:DATABASE_URL -f migrations/add_meetup_columns.sql
    Write-Host "✅ Индексы применены" -ForegroundColor Green
} catch {
    Write-Host "❌ Ошибка применения индексов: $_" -ForegroundColor Red
    exit 1
}

# Проверяем что API работает
Write-Host "🌐 Проверяем API..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
    if ($healthResponse.status -eq "ok") {
        Write-Host "✅ API работает" -ForegroundColor Green
    } else {
        Write-Host "❌ API не отвечает корректно" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ API не отвечает на /health" -ForegroundColor Red
    exit 1
}

# Тестовые координаты (Джакарта)
$LAT = -6.2
$LNG = 106.8
$RADIUS = 5

Write-Host "🔄 Запускаем синк Meetup для координат ($LAT, $LNG)..." -ForegroundColor Yellow
try {
    $syncResponse = Invoke-RestMethod -Uri "http://localhost:8000/events/sources/meetup/sync?lat=$LAT&lng=$LNG&radius_km=$RADIUS" -Method Post
    Write-Host "📅 Ответ синка: $($syncResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "❌ Ошибка синка: $_" -ForegroundColor Red
}

# Проверяем nearby
Write-Host "🔍 Проверяем /events/nearby..." -ForegroundColor Yellow
try {
    $nearbyResponse = Invoke-RestMethod -Uri "http://localhost:8000/events/nearby?lat=$LAT&lng=$LNG&radius_km=$RADIUS&limit=20" -Method Get
    Write-Host "📍 Ответ nearby: $($nearbyResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "❌ Ошибка nearby: $_" -ForegroundColor Red
}

Write-Host "🎉 Проверка завершена!" -ForegroundColor Green
Write-Host ""
Write-Host "Для ручного тестирования:" -ForegroundColor Yellow
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8000/events/sources/meetup/sync?lat=$LAT&lng=$LNG&radius_km=$RADIUS' -Method Post"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8000/events/nearby?lat=$LAT&lng=$LNG&radius_km=$RADIUS&limit=20' -Method Get"
