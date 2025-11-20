@echo off
echo Starting EventBot API server...

REM Kill hanging Python processes
echo Cleaning hanging processes...
taskkill /F /IM python.exe >nul 2>&1

REM Set environment variables
set PORT=8000
set DATABASE_URL=postgresql://postgres:password@host:port/database?sslmode=require
set ENABLE_BALIFORUM=1

echo API URL: http://127.0.0.1:8000
echo Health: http://127.0.0.1:8000/health
echo Baliforum: enabled
echo Starting API server...
echo Press Ctrl+C to stop
echo.

REM Start API server
python start_server.py
