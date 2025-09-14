@echo off
echo 🚀 ДЕПЛОЙ В GITHUB
echo ==================

echo 📝 Добавляем все изменения...
git add .

echo 💾 Коммитим изменения...
git commit -m "feat: fix AI parser and improve event search - ready for deployment"

echo 🚀 Пушим в GitHub...
git push origin main

echo ✅ Деплой завершен!
echo 🌐 Проверь GitHub Actions для автоматического деплоя
echo 📱 Или используй Railway/GitHub integration

pause
