@echo off
echo Starting EventBot...

REM Kill Python processes
taskkill /F /IM python.exe >nul 2>&1

REM Set variables
set PORT=8000
set WEBHOOK_URL=http://127.0.0.1:8000/webhook
set TELEGRAM_TOKEN=dummy
set ENABLE_BALIFORUM=1

echo Port: %PORT%
echo Webhook: %WEBHOOK_URL%
echo.

REM Start bot
python bot_enhanced_v3.py
