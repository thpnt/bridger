# Bridger

Bridger is a CLI-first context compiler and instruction generator for AI coding agents.
The current Python foundation exposes placeholder commands while the repository context
pipeline is rebuilt.

The provider-independent LLM execution boundary lives in
[`docs/llm-client.md`](docs/llm-client.md). It supports one async model turn,
OpenAI Responses API execution, structured outputs, tool-call normalization,
bounded transient retries, and a deterministic scripted dummy client for tests.

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

These commands are intentionally lightweight. Agentic repository discovery,
context planning, memory agents, and prompt-generation workflows are not
implemented yet.
