.PHONY: up down logs ps build test test-api test-web

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

build:
	docker compose build

test: test-api test-web

test-api:
	cd services/api && python -m pytest tests/ -v

test-web:
	cd apps/web && npm test
