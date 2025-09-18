#!/usr/bin/env pwsh
# 🚀 ДЕПЛОЙ ИСПРАВЛЕНИЯ ДУБЛИРОВАНИЯ

Write-Host "🚀 ДЕПЛОЙ ИСПРАВЛЕНИЯ ДУБЛИРОВАНИЯ" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Green

Write-Host "📝 Добавляем все изменения..." -ForegroundColor Yellow
git add .

Write-Host "💾 Коммитим изменения..." -ForegroundColor Yellow  
git commit -m "fix: устранено дублирование фразы Выберите действие в боте"

Write-Host "🚀 Пушим в GitHub..." -ForegroundColor Yellow
git push origin main

Write-Host "✅ Деплой завершен!" -ForegroundColor Green
Write-Host "🌐 Проверь GitHub для подтверждения" -ForegroundColor Cyan
Write-Host "📱 Бот обновлен с исправлением дублирования" -ForegroundColor Cyan

Read-Host "Нажми Enter для выхода"
