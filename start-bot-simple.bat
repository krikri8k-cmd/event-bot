@echo off
echo Starting EventBot in dev mode...

REM Kill hanging Python processes
echo Cleaning hanging processes...
taskkill /F /IM python.exe >nul 2>&1

REM Set environment variables
set PORT=8000
set WEBHOOK_URL=http://127.0.0.1:8000/webhook
set TELEGRAM_TOKEN=dummy
set ENABLE_BALIFORUM=1

echo Webhook URL: %WEBHOOK_URL%
echo Baliforum: enabled
echo Starting bot...
echo Press Ctrl+C to stop
echo.

REM Start bot
python bot_enhanced_v3.py
