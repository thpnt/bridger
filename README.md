# Bridger

Bridger is a repository intelligence and knowledge system for AI coding agents.
The design is documented in [`docs/bridger`](docs/bridger).

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
bridger auth set-key
cd ~/my-project
bridger init --reasoning low
```

`bridger auth set-key` prompts for a hidden OpenAI API key and stores it in the
system credential store. Use `bridger auth status` to check the active source or
`bridger auth remove` to delete the stored key. For CI or a temporary override,
set `OPENAI_API_KEY` instead. It takes precedence over the stored credential.
Bridger does not store API keys in the repository, `.bridger/`, or `config.toml`.

Successful `bridger auth set-key` setup creates an editable, non-secret
`config.toml` in the platform-specific Bridger user config directory if one
does not exist. Its initial contents come from Bridger's bundled `config.toml`:

```toml
schema_version = 1

[openai]
model = "gpt-5.6"
reasoning = "xhigh"
```

`--reasoning` overrides the configured reasoning value. Existing
`BRIDGER_OPENAI_MODEL` environment settings continue to override the configured
model. Without a user config file, Bridger reads the bundled defaults and does
not create files in the home directory.

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
uv run bridger understand "How does repository initialization work?"
uv run bridger impact RepositoryLoader
uv run bridger understand "How does repository initialization work?" --json
```

Run consumption commands from inside an initialized repository. UNDERSTAND
combines Repository Brain knowledge with structural context. IMPACT accepts
exact repository symbols and reports potential structural impact. Use `--json`
for the canonical machine-readable result.
