@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo ВЫПОЛНЕНИЕ GIT КОМАНД
echo ========================================
echo.

echo 1. Текущий статус:
git status
echo.

echo 2. Добавление файла миграции:
git add migrations/029_add_task_hint_to_task_places.sql
echo.

echo 3. Создание коммита:
git commit -m "feat: Add task_hint column to task_places table"
echo.

echo 4. Отправка в GitHub:
git push origin main
echo.

echo 5. Финальная проверка:
git status
echo.
git log --oneline -3
echo.

echo ========================================
echo ГОТОВО!
echo ========================================
pause



