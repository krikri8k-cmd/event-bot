@echo off
chcp 65001 >nul
echo ========================================
echo Применение миграции 029: task_hint
echo ========================================
echo.

cd /d "%~dp0"
python scripts\apply_migration.py migrations\029_add_task_hint_to_task_places.sql

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo ✅ Миграция применена успешно!
    echo ========================================
    echo.
    echo Теперь проверьте в веб-интерфейсе БД, что столбец task_hint появился
    pause
) else (
    echo.
    echo ========================================
    echo ❌ Ошибка при применении миграции
    echo ========================================
    pause
    exit /b 1
)



