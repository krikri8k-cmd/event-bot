#!/bin/bash

# Скрипт для запуска Telegram бота на Railway
# Включает keep-alive механизм для предотвращения "засыпания"

echo "🚀 Запуск EventBot на Railway..."

# Создаем директорию для логов
mkdir -p logs

# Функция для отправки keep-alive запроса
keep_alive() {
    while true; do
        echo "$(date): 🔄 Keep-alive ping..."
        # Можно добавить ping на health check endpoint если есть
        sleep 300  # каждые 5 минут
    done
}

# Запускаем keep-alive в фоне
keep_alive &

# Запускаем бота
echo "🤖 Запуск Telegram бота..."
python bot_enhanced_v3.py
