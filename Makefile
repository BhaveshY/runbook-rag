.PHONY: setup ingest serve evaluate test lint
setup:
	uv sync --frozen
ingest:
	uv run python -m runbook ingest
serve:
	uv run python -m runbook serve
evaluate:
	uv run python -m runbook evaluate --answers
test:
	uv run pytest -q
lint:
	uv run ruff check .
	uv run ruff format --check .
