# IDP Makefile
# Common operations for the Internal Developer Platform
# Usage: make <target>

# Detect python: python3 on macOS/Linux, python on Windows
PYTHON := $(shell python3 --version > /dev/null 2>&1 && echo python3 || echo python)

.PHONY: help up down restart rebuild logs ps scaffold scaffold-demo demo pr-open pr-close pr-list ask test test-install clean clean-scaffolds

help: ## Show this help
	@$(PYTHON) -c "import re; f=open('Makefile'); lines=f.readlines(); f.close(); print(); print('Available commands:'); print(); [print('  '+m.group(1).ljust(22)+m.group(2)) for line in lines if (m:=re.match(r'^([a-zA-Z_-]+):.*?## (.+)', line))]; print()"

up: ## Start the full stack
	docker compose up -d
	@echo ""
	@echo "Stack is up:"
	@echo "  Webhook Server  -> http://localhost:8080"
	@echo "  Traefik         -> http://localhost:8081"
	@echo "  Demo App        -> http://localhost:8082"
	@echo "  Prometheus      -> http://localhost:9090"
	@echo "  Grafana         -> http://localhost:3000  (admin/admin)"
	@echo "  LocalStack      -> http://localhost:4566"

down: ## Stop and remove all containers
	docker compose down --remove-orphans

restart: ## Restart the full stack
	docker compose down --remove-orphans
	docker compose up -d

rebuild: ## Rebuild images and restart (use after code changes)
	docker compose down --remove-orphans
	docker compose build --no-cache
	docker compose up -d

logs: ## Follow logs for all services
	docker compose logs -f

ps: ## Show status of all services
	docker compose ps

scaffold: ## Scaffold a new service. Usage: make scaffold NAME=my-service TYPE=api
	$(PYTHON) scaffold_cli/scaffold.py --name $(NAME) --type $(TYPE)

scaffold-demo: ## Generate three example services to demo Module 1
	$(PYTHON) scaffold_cli/scaffold.py --name payments-service --type api      --output /tmp/idp-demo
	$(PYTHON) scaffold_cli/scaffold.py --name audit-worker     --type worker   --output /tmp/idp-demo
	$(PYTHON) scaffold_cli/scaffold.py --name daily-report     --type scheduler --output /tmp/idp-demo

demo: ## Run the full PR lifecycle demo (Module 2)
	$(PYTHON) modules/module2/simulate_pr.py demo

pr-open: ## Open a preview env. Usage: make pr-open ID=42 BRANCH=feature/x
	$(PYTHON) modules/module2/simulate_pr.py open $(ID) $(BRANCH) demo-app

pr-close: ## Close a preview env. Usage: make pr-close ID=42
	$(PYTHON) modules/module2/simulate_pr.py close $(ID)

pr-list: ## List all active preview environments
	$(PYTHON) modules/module2/simulate_pr.py list

ask: ## Ask the ops assistant. Usage: make ask Q="Is everything healthy?"
	$(PYTHON) modules/module4/ops_assistant.py

test-install: ## Install test dependencies
	$(PYTHON) -m pip install -r tests/requirements-test.txt

test: ## Run all tests
	$(PYTHON) -m pytest tests/ -v

clean: ## Remove containers, volumes, and preview env compose files
	docker compose down --remove-orphans --volumes
	@echo "Cleaned up."

clean-scaffolds: ## Remove demo scaffolds from /tmp/idp-demo
	-rm -rf /tmp/idp-demo
	@echo "Demo scaffolds removed."
