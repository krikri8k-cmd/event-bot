# Makefile для удобного запуска EventBot

.PHONY: help dev api test clean install

# Показать справку
help:
	@echo "🚀 EventBot - Команды для разработки"
	@echo ""
	@echo "📋 Доступные команды:"
	@echo "  make dev     - Запустить бота в dev режиме (автоматический порт)"
	@echo "  make api     - Запустить API сервер (автоматический порт)"
	@echo "  make test    - Запустить тесты Baliforum"
	@echo "  make clean   - Очистить зависшие процессы"
	@echo "  make install - Установить зависимости"
	@echo ""
	@echo "💡 Все команды автоматически находят свободный порт!"

# Запуск бота в dev режиме
dev:
	@echo "🤖 Запуск бота в dev режиме..."
	powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1

# Запуск API сервера
api:
	@echo "🌐 Запуск API сервера..."
	powershell -ExecutionPolicy Bypass -File scripts/start-api.ps1

# Тестирование Baliforum
test:
	@echo "🧪 Запуск тестов Baliforum..."
	python test_baliforum_simple.py

# Очистка зависших процессов
clean:
	@echo "🧹 Очистка зависших процессов..."
	powershell -Command "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force"
	@echo "✅ Готово!"

# Установка зависимостей
install:
	@echo "📦 Установка зависимостей..."
	pip install -r requirements.txt
	@echo "✅ Готово!"

# Запуск с Python утилитой (альтернатива)
dev-python:
	@echo "🐍 Запуск через Python утилиту..."
	python utils/port_manager.py bot
	python bot_enhanced_v3.py

api-python:
	@echo "🐍 Запуск API через Python утилиту..."
	python utils/port_manager.py api
	python start_server.py