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
