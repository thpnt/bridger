# Bridger

Bridger is a CLI-first context compiler and instruction generator for AI coding agents.
The current Python foundation exposes placeholder commands while the repository context
pipeline is rebuilt.

## Local development

```shell
uv sync
uv run bridger init
uv run bridger inspect
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy src
```

## CLI commands

```shell
uv run bridger init
uv run bridger init --fresh
uv run bridger update
uv run bridger prompt "Add feature X"
uv run bridger inspect
uv run bridger inspect --graph
```

These commands are intentionally lightweight. Repository scanning, context planning,
memory agents, and LLM calls are not implemented yet.
