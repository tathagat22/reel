.PHONY: install sync lint format format-check types test check clean run

install: ## Install all dependencies including dev
	uv sync

sync: install

lint: ## Run ruff lint
	uv run ruff check src tests

format: ## Run ruff format (in-place)
	uv run ruff format src tests

format-check: ## Run ruff format in check mode (CI mirror)
	uv run ruff format --check src tests

types: ## Run pyright type check
	uv run pyright

test: ## Run pytest
	uv run pytest

check: lint format-check types test ## Mirror of CI: lint, format-check, types, tests

clean:
	rm -rf .ruff_cache .pytest_cache .pyright dist build *.egg-info

run: ## Run the reel CLI (Sprint 1+)
	uv run reel
