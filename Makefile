.PHONY: setup ingest serve evaluate
setup:
	uv sync --frozen
ingest:
	uv run python -m runbook ingest
serve:
	uv run python -m runbook serve
evaluate:
	uv run python -m runbook evaluate --answers

