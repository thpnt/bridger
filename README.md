# Bridger

Bridger is a repository intelligence and knowledge system for AI coding agents.
The new design is documented in [`docs/bridger`](docs/bridger). The repository
currently retains only the LLM boundary, artifact writer, and CLI command shell.

The provider-independent LLM execution boundary lives in
[`docs/bridger/llm-client.md`](docs/bridger/llm-client.md). It supports one async model turn,
OpenAI Responses API execution, structured outputs, tool-call normalization,
bounded transient retries, and a deterministic scripted dummy client for tests.

## Local development

```shell
uv sync
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
```

These commands intentionally perform no work while the new architecture is
implemented.
