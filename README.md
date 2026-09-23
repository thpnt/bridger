# Bridger

Bridger is a repository intelligence and knowledge system for AI coding agents.
The design is documented in [`docs/bridger`](docs/bridger).

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

## Install and connect a coding agent

Install Bridger once, then initialize each repository you want it to serve:

```shell
uv tool install bridger
cd ~/code/my-project
bridger init
```

Register a local stdio MCP server in your coding agent. For Codex, a minimal
configuration is:

```toml
[mcp_servers.bridger]
command = "bridger"
args = ["mcp"]
```

For a project-local Cursor configuration, pass the workspace explicitly:

```json
{
  "mcpServers": {
    "bridger": {
      "type": "stdio",
      "command": "bridger",
      "args": ["mcp", "--repository", "${workspaceFolder}"]
    }
  }
}
```

`bridger mcp` uses the coding agent's subprocess working directory by default.
It resolves nested directories to the Git repository root. Use
`bridger mcp --repository /path/to/repository` when the host starts the process
elsewhere. Each server process serves one repository and stops with its host
session. It exposes only `understand` and `impact`.

## CLI commands

```shell
uv run bridger init
uv run bridger init --fresh
uv run bridger update
uv run bridger prompt "Add feature X"
uv run bridger inspect
uv run bridger mcp
```
