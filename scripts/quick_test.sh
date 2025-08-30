#!/bin/bash
# Быстрая проверка "готов к бою"

set -e

echo "🚀 Быстрая проверка Event Bot системы..."

# Проверяем что DATABASE_URL установлен
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL не установлен"
    exit 1
fi

echo "✅ DATABASE_URL установлен"

# Применяем индексы и уникальные констрейнты
echo "📊 Применяем индексы и констрейнты..."
psql "$DATABASE_URL" -f migrations/add_meetup_columns.sql

echo "✅ Индексы применены"

# Проверяем что API работает
echo "🌐 Проверяем API..."
curl -s "http://localhost:8000/health" | grep -q "ok" || {
    echo "❌ API не отвечает на /health"
    exit 1
}

echo "✅ API работает"

# Тестовые координаты (Джакарта)
LAT=-6.2
LNG=106.8
RADIUS=5

echo "🔄 Запускаем синк Meetup для координат ($LAT, $LNG)..."
SYNC_RESPONSE=$(curl -s -X POST "http://localhost:8000/events/sources/meetup/sync?lat=$LAT&lng=$LNG&radius_km=$RADIUS")

echo "📅 Ответ синка: $SYNC_RESPONSE"

# Проверяем nearby
echo "🔍 Проверяем /events/nearby..."
NEARBY_RESPONSE=$(curl -s "http://localhost:8000/events/nearby?lat=$LAT&lng=$LNG&radius_km=$RADIUS&limit=20")

echo "📍 Ответ nearby: $NEARBY_RESPONSE"

echo "🎉 Проверка завершена!"
echo ""
echo "Для ручного тестирования:"
echo "curl -X POST 'http://localhost:8000/events/sources/meetup/sync?lat=$LAT&lng=$LNG&radius_km=$RADIUS'"
echo "curl 'http://localhost:8000/events/nearby?lat=$LAT&lng=$LNG&radius_km=$RADIUS&limit=20'"
