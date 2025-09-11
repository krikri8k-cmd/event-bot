@echo off
echo 🚀 Запуск EventBot API сервера...

REM Очищаем зависшие процессы
echo 🧹 Очищаем зависшие процессы...
taskkill /F /IM python.exe >nul 2>&1

REM Устанавливаем переменные окружения
set PORT=8000
set DATABASE_URL=postgresql://postgres:GHeScaRnEXJEPRRXpFGJCdTPgcQOtzlw@interchange.proxy.rlwy.net:23764/railway?sslmode=require
set ENABLE_BALIFORUM=1

echo 📡 API URL: http://127.0.0.1:8000
echo 🏥 Health: http://127.0.0.1:8000/health
echo 🌴 Baliforum: включен
echo 🌐 Запускаем API сервер...
echo    Для остановки нажми Ctrl+C
echo.

REM Запускаем API сервер
python start_server.py
