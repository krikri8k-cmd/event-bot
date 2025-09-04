.PHONY: db-apply db-apply-file test-db test-migration

# Применить главный скрипт (читает DATABASE_URL из окружения)
db-apply:
	python scripts/apply_sql.py sql/2025_ics_sources_and_indexes.sql

# Применить любой указанный файл: make db-apply-file FILE=path/to.sql
db-apply-file:
	python scripts/apply_sql.py $(FILE)

# Тест подключения к БД
test-db:
	python test_db_connection.py

# Тест миграции
test-migration:
	python test_migration.py

# Запуск Telegram бота
run-bot:
	python bot_enhanced_v3.py

# Запуск бота в Docker
run-bot-docker:
	docker build -f Dockerfile.bot -t event-bot .
	docker run -p 8000:8000 --env-file .env event-bot

# Деплой на Railway
deploy-railway:
	@echo "🚀 Деплой на Railway..."
	git add .
	git commit -m "feat: update bot deployment"
	git push
	@echo "✅ Код запушен! Теперь настрой Railway UI"

# Тестировать health check
test-health:
	python test_health.py

# Очистка
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf *.egg-info
