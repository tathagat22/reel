.PHONY: install sync lint format types test check clean run

install: ## Install all dependencies including dev
	uv sync

sync: install

lint: ## Run ruff lint
	uv run ruff check src tests

format: ## Run ruff format
	uv run ruff format src tests

types: ## Run pyright type check
	uv run pyright

test: ## Run pytest
	uv run pytest

check: lint types test ## Run lint, types, and tests

clean:
	rm -rf .ruff_cache .pytest_cache .pyright dist build *.egg-info

run: ## Run the reel CLI (Sprint 1+)
	uv run reel
