#!/usr/bin/env pwsh
# 🚀 ДЕПЛОЙ В GITHUB

Write-Host "🚀 ДЕПЛОЙ В GITHUB" -ForegroundColor Green
Write-Host "==================" -ForegroundColor Green

Write-Host "📝 Добавляем все изменения..." -ForegroundColor Yellow
git add .

Write-Host "💾 Коммитим изменения..." -ForegroundColor Yellow
git commit -m "feat: fix AI parser and improve event search - ready for deployment"

Write-Host "🚀 Пушим в GitHub..." -ForegroundColor Yellow
git push origin main

Write-Host "✅ Деплой завершен!" -ForegroundColor Green
Write-Host "🌐 Проверь GitHub Actions для автоматического деплоя" -ForegroundColor Cyan
Write-Host "📱 Или используй Railway/GitHub integration" -ForegroundColor Cyan

Read-Host "Нажми Enter для выхода"
