# Bridger

A local-first context compiler for software teams adopting AI coding agents.

Bridger scans a repository and builds deterministic codebase context for later memory compilation and instruction generation.

## What Bridger does

- deterministic repository scanning
- file index generation
- repo context generation
- deterministic repo graph generation
- codebase map generation
- batch-aware reading plans
- affected-file traversal

Bridger's repo graph is structural and deterministic. It does not semantically understand the codebase.

## CLI commands

### `bridger inspect`

Shows a human-readable summary of the repository context, including detected stack information, command hints, and indexed file counts.

### `bridger inspect --context`

Shows the deterministic selected-context preview.

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

Builds and writes the deterministic repository intelligence layer.

The current init pipeline:

1. scans the repo
2. builds a file index
3. builds repo context
4. builds the repo graph
5. builds the graph summary
6. builds the codebase map
7. builds five doc-specific reading plans
8. writes validated deterministic artifacts

`bridger init` generates:

- `.bridger/config.json`
- `.bridger/artifacts/repo-context.json`
- `.bridger/artifacts/file-index.json`
- `.bridger/artifacts/repo-graph.json`
- `.bridger/artifacts/graph-summary.json`
- `.bridger/artifacts/codebase-map.json`
- `.bridger/artifacts/reading-plans.json`

`bridger init` does not call an LLM and does not write final memory or agent export files.

## Repo graph feature

The repo graph is the deterministic structural layer that backs `bridger init`.

It records:

- file and directory nodes
- `contains` edges from filesystem structure
- `imports` edges from local import extraction
- diagnostics for unresolved or skipped inputs
- graph stats and derived ordering data

Bridger writes two graph artifacts:

- `.bridger/artifacts/repo-graph.json` for the full graph
- `.bridger/artifacts/graph-summary.json` for the derived summary

The summary includes:

- entrypoint candidates
- root, config, and docs files
- high fan-in and high fan-out files
- leaf and isolated files
- architecture-first order
- dependency-first order

## Graph-aware context ordering

The graph summary provides deterministic architecture-first and dependency-first file orderings for inspection and downstream context compilation.

That order starts with:

1. docs, config, and other root files
2. entrypoints
3. direct dependencies of entrypoints
4. feature or domain files
5. components, services, libraries, and shared utilities
6. test files

Large files, unreadable files, and binary-looking files are skipped with diagnostics.

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
3. inspect the JSON artifacts under `.bridger/artifacts`
4. verify `reading-plans.json` contains the five deterministic memory plans
