---
name: bridger-setup
description: Install, configure, verify, or troubleshoot Bridger for coding agents. Use when the user asks to install Bridger, set up Bridger, configure the Bridger MCP server, connect Bridger to Codex, Claude Code, or Cursor, or diagnose why Bridger MCP tools are unavailable.
---

---

# Bridger Setup

Set up the Bridger runtime and connect its local MCP server to the user's coding agent.

Bridger has two separately distributed parts:

```text
Runtime
→ installed with uv
→ provides the `bridger` executable and MCP server

Agent skills
→ installed through the Skills ecosystem
→ provide agent guidance
```

This skill handles runtime and MCP configuration.

## Target state

A successful setup has:

```text
`bridger` available on PATH

and

the current coding-agent host configured to launch:

    bridger mcp

and

the host can discover exactly these Bridger MCP tools:

    understand
    impact
```

The MCP server is local stdio.

There is no Bridger daemon, localhost port, HTTP service, or separate MCP package.

## Setup principles

Before changing anything:

1. Inspect the existing environment.
2. Do not reinstall working components.
3. Do not create duplicate MCP registrations.
4. Configure only the coding-agent host relevant to the user's request unless they explicitly request several.
5. Prefer the host's supported MCP management command over manually editing configuration.
6. Verify the result after changing configuration.

Keep setup idempotent.

## Step 1 — Check the Bridger runtime

First check whether Bridger is already available:

```bash
bridger --help
```

If it succeeds, do not reinstall Bridger merely to perform MCP setup.

If Bridger is missing, check for uv:

```bash
uv --version
```

If uv is installed, install Bridger:

```bash
uv tool install usebridger
```

The PyPI distribution is:

```text
usebridger
```

The installed executable is:

```text
bridger
```

They intentionally have different names.

After installation, verify:

```bash
bridger --help
```

The executable should expose commands including:

```text
init
understand
impact
mcp
```

If `uv tool install usebridger` succeeds but `bridger` is not found, check whether uv's tool executable directory is on `PATH`. Use uv's supported shell-path setup rather than inventing a custom symlink.

If uv itself is unavailable, use the current official uv installation procedure appropriate for the user's operating system before continuing. Do not silently substitute another Python installation mechanism.

## Step 2 — Identify the coding-agent host

Configure the host the user is actually using.

Supported initial targets:

```text
Codex
Claude Code
Cursor
```

If the current runtime clearly identifies the host, use that information.

Otherwise inspect available commands/configuration rather than guessing.

Do not register Bridger in every provider by default.

## Step 3 — Check for an existing Bridger MCP registration

Before adding anything, inspect the host's current MCP configuration.

If a working server named `bridger` already launches:

```text
bridger mcp
```

do not add another registration.

If an existing Bridger registration is stale or incorrect, update it rather than creating a duplicate.

The desired stdio server is:

```text
name: bridger
command: bridger
args:
  - mcp
```

Bridger normally resolves the target repository from the MCP subprocess working directory.

An explicit repository argument is available when a host does not launch the subprocess from the workspace:

```bash
bridger mcp --repository <repository-path>
```

Do not hard-code one repository path into a global MCP configuration unless the user explicitly wants a repository-specific registration.

# Codex

## Register

For a user-level/local Codex MCP registration, prefer the Codex MCP CLI:

```bash
codex mcp add bridger -- bridger mcp
```

Do not manually edit Codex configuration when the supported CLI command is available and working.

## Verify

Run:

```bash
codex mcp list
```

Confirm a server named:

```text
bridger
```

is configured.

When possible, verify from a Codex session that Bridger exposes:

```text
understand
impact
```

If Codex already has a different `bridger` registration, inspect it before replacing it.

If current Codex syntax differs from these instructions, inspect:

```bash
codex mcp add --help
```

and use the host's current supported stdio syntax while preserving the same server command:

```text
bridger mcp
```

# Claude Code

## Register

Prefer Claude Code's MCP CLI.

For a Bridger server available across the user's repositories:

```bash
claude mcp add --scope user bridger -- bridger mcp
```

The server is stdio because Claude launches the supplied local command.

Do not add environment variables or network configuration; Bridger's MCP server needs neither.

## Verify

Run:

```bash
claude mcp list
```

Confirm that `bridger` is configured and can connect.

Then verify that the connected server exposes:

```text
understand
impact
```

If the current Claude Code CLI rejects the documented command form, inspect:

```bash
claude mcp add --help
```

and use its current stdio syntax.

Do not blindly edit multiple Claude MCP configuration files as a workaround. Prefer the CLI-managed configuration unless there is a concrete reason not to.

# Cursor

Cursor supports local stdio MCP configuration through `mcp.json`.

For a personal Bridger installation available across projects, use:

```text
~/.cursor/mcp.json
```

For a repository-specific configuration, use:

```text
.cursor/mcp.json
```

Prefer global configuration unless the user explicitly wants the MCP declaration committed with the repository.

## Global configuration

Merge a `bridger` entry into the existing `mcpServers` object.

Do not overwrite other MCP servers.

Use:

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

`${workspaceFolder}` binds the server explicitly to the active Cursor workspace.

If an existing valid `mcp.json` contains other fields or servers, preserve them.

## Verify

If the Cursor CLI is installed, inspect MCP status with:

```bash
agent mcp list
```

Otherwise verify through Cursor's MCP configuration/status interface.

Confirm that the Bridger server becomes connected and exposes:

```text
understand
impact
```

Do not consider merely writing `mcp.json` sufficient verification if a runtime check is available.

# Step 4 — Verify Bridger from a repository

MCP registration and repository initialization are separate concerns.

Inside the repository the user wants to work on, Bridger requires a published Repository Brain.

If the repository is already initialized, do not rebuild it merely as part of setup.

If Bridger consumption reports that no current Repository Brain exists, the repository needs initialization:

```bash
bridger init
```

`bridger init` can perform substantial repository analysis and model work.

Do not silently start a full initialization merely because it is missing.

Run it when:

- the user explicitly asked to initialize the repository; or
- the user explicitly asked for complete Bridger setup including initialization.

Otherwise report that initialization is the remaining step and provide the command.

## Repository resolution

Normal Bridger commands resolve the Git repository containing the current working directory.

These are valid workflows:

```bash
cd /path/to/repository
bridger understand "How does authentication work?"
```

and from a nested directory:

```bash
cd /path/to/repository/packages/api
bridger understand "How does authentication work?"
```

For MCP, the normal server command is:

```bash
bridger mcp
```

Use:

```bash
bridger mcp --repository <path>
```

only when explicit workspace binding is necessary.

# Step 5 — End-to-end verification

After setup, verify as much of the actual chain as the current host permits:

```text
1. `bridger --help` works.

2. MCP registration named `bridger` exists.

3. MCP server connects successfully.

4. Server exposes:
   - understand
   - impact

5. In an initialized repository, an UNDERSTAND query can execute.
```

Do not claim setup is complete solely because an installation command returned success.

# Troubleshooting

## `bridger` not found

Check:

```bash
uv tool list
```

and confirm `usebridger` is installed.

Then verify uv's tool executable directory is available on `PATH`.

Do not create ad-hoc aliases unless the user explicitly wants one.

## MCP process exits immediately

Run the server manually from the target repository:

```bash
bridger mcp
```

Remember that a successful stdio MCP server normally waits silently for protocol input.

Do not interpret the absence of terminal output as a failure.

If repository resolution fails, run from inside the repository or test:

```bash
bridger mcp --repository /path/to/repository
```

## MCP connects but queries fail

Check whether the repository has been initialized.

Try:

```bash
bridger understand "What is the role of this repository?"
```

If Bridger reports that no current Repository Brain publication exists, initialization is required.

## Server exists but tools are not visible

The Bridger MCP server should expose exactly:

```text
understand
impact
```

Inspect the host's MCP status and restart or open a new coding-agent session if the host does not reload MCP configuration dynamically.

Do not add low-level Bridger tools as a workaround.

## Repository mismatch

The MCP process is bound to one repository for its lifetime.

If a host reused a process after switching workspaces, restart the MCP connection/session so Bridger launches for the correct repository.

Do not attempt to switch repositories through the `understand` or `impact` tool arguments.

# Do not

Do not:

- install a separate `bridger-mcp` package;
- launch a persistent Bridger daemon;
- configure an HTTP or SSE endpoint;
- add host-specific behavior to the Bridger runtime;
- expose repository paths as MCP tool arguments;
- duplicate an existing working MCP registration;
- overwrite unrelated MCP configuration;
- silently run an expensive `bridger init`;
- claim success without verifying the MCP connection when verification is possible.

# Final setup model

```text
Runtime
    uv tool install usebridger
        ↓
    bridger executable

Host integration
    coding agent launches:
        bridger mcp
        ↓
    local stdio MCP

Repository
    bridger init
        ↓
    published Repository Brain

Agent usage
    understand
    impact
```

Keep these responsibilities separate.
