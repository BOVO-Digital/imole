.PHONY: up down build logs prod prod-down smoke

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f api

# VPS Hostinger — HTTPS via Caddy
prod:
	docker compose -f docker-compose.prod.yml up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml down

smoke:
	./scripts/smoke-test.sh
