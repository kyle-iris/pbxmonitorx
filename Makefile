# PBXMonitorX — Makefile
# Usage: make <target>

.PHONY: help dev prod down logs ps secrets

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── Development ─────────────────────────────────────────────
dev: ## Start development stack (localhost)
	docker compose up -d --build
	@echo ""
	@echo "API:    http://localhost:8000/api/docs"
	@echo "Health: http://localhost:8000/api/health"

# ── Production ──────────────────────────────────────────────
prod: ## Start production stack
	docker compose -f docker-compose.prod.yml up -d --build

# ── Common ──────────────────────────────────────────────────
down: ## Stop all containers
	docker compose down 2>/dev/null; docker compose -f docker-compose.prod.yml down 2>/dev/null

logs: ## Tail all logs
	docker compose -f docker-compose.prod.yml logs -f --tail=100

ps: ## Show running containers
	docker compose -f docker-compose.prod.yml ps

# ── Utilities ───────────────────────────────────────────────
secrets: ## Generate fresh secrets for .env
	@echo "DB_PASSWORD=$$(openssl rand -hex 24)"
	@echo "REDIS_PASSWORD=$$(openssl rand -hex 24)"
	@echo "MASTER_KEY=$$(openssl rand -hex 32)"
	@echo "JWT_SECRET=$$(openssl rand -base64 48 | tr -d '\n')"

shell-db: ## Open psql shell
	docker compose exec postgres psql -U pbxmonitorx

shell-backend: ## Open Python shell in backend container
	docker compose exec backend python

shell-redis: ## Open Redis CLI
	docker compose exec redis redis-cli

backup-db: ## Dump database to file
	docker compose exec postgres pg_dump -U pbxmonitorx pbxmonitorx > backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Database dumped"

deploy: ## Deploy latest from main branch (run on server)
	git pull origin main
	docker compose -f docker-compose.prod.yml build --quiet
	docker compose -f docker-compose.prod.yml up -d --remove-orphans
	docker image prune -f
