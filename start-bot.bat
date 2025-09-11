@echo off
echo 🚀 Запуск EventBot в dev режиме...

REM Очищаем зависшие процессы
echo 🧹 Очищаем зависшие процессы...
taskkill /F /IM python.exe >nul 2>&1

REM Устанавливаем переменные окружения
set PORT=8000
set WEBHOOK_URL=http://127.0.0.1:8000/webhook
set TELEGRAM_TOKEN=dummy
set ENABLE_BALIFORUM=1

echo 📡 Webhook URL: %WEBHOOK_URL%
echo 🌴 Baliforum: включен
echo 🤖 Запускаем бота...
echo    Для остановки нажми Ctrl+C
echo.

REM Запускаем бота
python bot_enhanced_v3.py
