# Bridger

A context and ticket-readiness layer for software teams adopting AI coding agents.

Bridger scans a repository, builds deterministic codebase context, generates agent-ready documentation, and prepares the foundation for ticket enrichment grounded in the actual codebase.

## What Bridger does

- deterministic repository scanning
- file index generation
- repo context generation
- deterministic repo graph generation
- graph-aware file ordering for LLM context
- generated Markdown documentation for AI coding agents

Bridger's repo graph is structural and deterministic. It does not semantically understand the codebase.

## CLI commands

### `bridger inspect`

Shows a human-readable summary of the repository context, including detected stack information, command hints, and indexed file counts.

### `bridger inspect --context`

Shows the deterministic context preview used before LLM document generation.

### `bridger inspect --important-files`

Shows the selected important files and the reason each file was chosen.

### `bridger inspect --json`

Prints the inspect result as JSON for scripting or downstream tooling.

### `bridger inspect --graph`

Prints graph inspection output without requiring an API key.

It:

- prints graph stats
- prints entrypoint candidates
- prints high fan-in and high fan-out files
- prints the first 10 architecture-first files
- does not write graph artifacts

### `bridger init`

Builds the repository knowledge layer and writes the generated artifacts.

The current init pipeline:

1. scans the repo
2. builds a file index
3. builds repo context
4. builds the repo graph
5. writes deterministic graph artifacts
6. reads graph-ordered file context
7. generates the Markdown docs used by agents
8. optionally updates `AGENTS.md` when `--write-agents-md` is passed

`bridger init` generates:

- `.bridger/repo-context.json`
- `.bridger/file-index.json`
- `.bridger/repo-graph.json`
- `.bridger/graph-summary.json`
- `.bridger/generated/repo-analysis.md`
- `.bridger/generated/architecture.md`
- `.bridger/generated/conventions.md`
- `.bridger/generated/business-logic.md`
- `.bridger/generated/testing.md`
- `.bridger/generated/agent-rules.md`
- `AGENTS.generated.md`

### `bridger enrich-ticket "<request>"`

Expands a rough product or engineering request into a ticket-shaped handoff. It is part of the broader product direction, but it is separate from the repo graph feature.

## Repo graph feature

The repo graph is the deterministic structural layer that backs `bridger init`.

It records:

- file and directory nodes
- `contains` edges from filesystem structure
- `imports` edges from local import extraction
- diagnostics for unresolved or skipped inputs
- graph stats and derived ordering data

Bridger writes two graph artifacts:

- `.bridger/repo-graph.json` for the full graph
- `.bridger/graph-summary.json` for the derived summary used by context generation

The summary includes:

- entrypoint candidates
- root, config, and docs files
- high fan-in and high fan-out files
- leaf and isolated files
- architecture-first order
- dependency-first order

## Graph-aware context ordering

`bridger init` uses the graph summary to read files in a deterministic architecture-first order when generating docs.

That order starts with:

1. docs, config, and other root files
2. entrypoints
3. direct dependencies of entrypoints
4. feature or domain files
5. components, services, libraries, and shared utilities
6. test files

Large files, unreadable files, and binary-looking files are skipped with diagnostics instead of being forced into the generated context.

## Current limitations

- no AST parsing
- no symbol graph
- no call graph
- no semantic code understanding
- import extraction is conservative
- only local imports become graph edges
- Python resolution is best-effort
- unresolved imports are reported, not guessed

The graph helps Bridger choose better context, but it does not replace code review or domain understanding.

## Evaluating output

Use [docs/evaluation.md](docs/evaluation.md) for a manual checklist.

For a quick pass:

1. run `bridger inspect --graph`
2. run `bridger init`
3. inspect `.bridger/repo-graph.json`, `.bridger/graph-summary.json`, and the generated Markdown docs
4. compare the graph-ordered context against a naive file order

