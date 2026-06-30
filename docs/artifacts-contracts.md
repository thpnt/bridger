# Bridger Deterministic Discovery Artifact Contracts

Status: Accepted planning contract  
Scope: Bridger deterministic pre-requisites for the SOTA repo discovery agent  
Purpose: Define the deterministic artifacts that the agentic discovery layer will ingest, query, and rely on before producing a Context Plan.

---

## 1. Design Boundary

The deterministic layer is a substrate. It must produce facts, indexes, parsed declarations, structural relationships, and safe access tools.

It must not produce final repo understanding.

The deterministic layer should avoid:

- architecture interpretation
- business/domain interpretation
- code-area ownership claims
- semantic file roles such as `business_logic`, `core`, `auth`, `billing`, etc.
- natural-language summaries of symbols or files
- suggested first actions for the agent
- initial hypotheses about what the repo means
- confidence-scored stack claims unless directly derived from explicit configuration

The agentic layer owns:

- code area discovery
- architecture interpretation
- subsystem boundaries
- business/domain meaning
- testing strategy interpretation
- coding convention interpretation
- uncertainty analysis
- final Context Plan generation

The deterministic layer owns:

- safe file inventory
- skip/exclusion rules
- manifest/config/docs/instruction file discovery
- mechanical manifest parsing
- syntactic symbol extraction
- import and containment graph construction
- graph metrics
- artifact checksums
- path validation
- read/search/grep tooling over the safe file set

Canonical deterministic artifacts for v0:

```txt
.bridger/artifacts/file-index.json
.bridger/artifacts/repo-context.json
.bridger/artifacts/symbol-index.json
.bridger/artifacts/repo-graph.json
.bridger/artifacts/graph-summary.json
.bridger/artifacts/repo-discovery.json
```

Artifacts explicitly excluded from v0:

- `codebase-map.json`
- `substrate-diagnostics.json`

Rationale: in the agentic architecture, code areas and repo interpretation should be discovered by the agent, not precomputed deterministically. Diagnostics may be added later, but are not required for the v0 deterministic contract.

---

## 2. Global Artifact Rules

All artifacts must:

- be valid JSON
- include a `schema_version`
- include `generated_at`
- use repository-relative POSIX-style paths
- avoid absolute file paths in persisted public fields unless explicitly needed for internal debug output
- be deterministically ordered, usually sorted by path and then by stable identifier
- be validated before writing
- be written atomically
- be safe to inspect by an LLM agent

All persisted paths must refer only to files accepted by `file-index.json`, unless they appear in `skipped_files` or explicit skip/error sections.

All artifacts should be generated under:

```txt
.bridger/artifacts/
```

Recommended implementation principles:

- Use Pydantic models for every artifact schema.
- Use `pathlib.Path` internally.
- Use repository-relative strings in artifact output.
- Use `orjson` or standard JSON with stable sorting.
- Write to a temporary file first, then atomically replace the target file.
- Centralize artifact writing and validation in one module.

---

## 3. `file-index.json`

### Purpose

`file-index.json` is the safe repository inventory.

It answers:

```txt
What files exist?
Which files are safe to expose to the discovery layer?
Which files were skipped?
What are their basic measurable properties?
```

It must not classify files semantically.

### What it is used for by agents

The discovery agent uses `file-index.json` indirectly through tools to:

- list safe files
- search paths
- validate candidate paths
- avoid hallucinating files
- avoid reading skipped or sensitive files
- understand repository size and file distribution at a factual level

The agent should not infer architecture directly from `file-index.json`. It should treat this artifact as the file inventory and safety boundary.

### Format

JSON.

### Schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-18T00:00:00Z",
  "repo_root_name": "bridger",
  "files": [
    {
      "path": "src/bridger/cli.py",
      "extension": ".py",
      "size_bytes": 4210,
      "line_count": 128,
      "sha256": "...",
      "is_binary": false,
      "is_symlink": false,
      "detected_encoding": "utf-8"
    }
  ],
  "skipped_files": [
    {
      "path": ".env",
      "skip_reason": "sensitive_file"
    },
    {
      "path": "node_modules/example/index.js",
      "skip_reason": "ignored_directory"
    }
  ],
  "stats": {
    "files_seen": 0,
    "files_included": 0,
    "files_skipped": 0,
    "total_included_bytes": 0
  }
}
```

### Field rules

Allowed included-file fields:

- `path`
- `extension`
- `size_bytes`
- `line_count`
- `sha256`
- `is_binary`
- `is_symlink`
- `detected_encoding`

Allowed skipped-file fields:

- `path`
- `skip_reason`

Fields intentionally excluded:

- `roles`
- `signals`
- `include_reason`
- `source/test/config` classifications
- semantic labels
- natural-language summaries

`skip_reason` is allowed because it describes safety/exclusion mechanics, not repo interpretation.

### How it is built technically

Implementation approach:

1. Start from repo root.
2. Traverse files using `pathlib`.
3. Apply ignore rules.
4. Exclude sensitive files.
5. Exclude binary files.
6. Exclude excessive-size files.
7. Compute mechanical metadata.
8. Sort files by path.
9. Validate with Pydantic.
10. Write atomically to `.bridger/artifacts/file-index.json`.

Recommended dependencies:

- `pathlib`
- `hashlib`
- `pathspec`
- `pydantic`

Skip categories should include at least:

```txt
ignored_directory
ignored_file
sensitive_file
binary_file
large_file
outside_repo
symlink_unsupported
read_error
```

Initial ignored directories:

```txt
.git/
.bridger/
node_modules/
dist/
build/
coverage/
.turbo/
.next/
.venv/
venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
vendor/
```

Initial sensitive file patterns:

```txt
.env
.env.*
*.pem
*.key
*.p12
*.pfx
id_rsa
id_ed25519
*.sqlite
*.db
```

### How the agent interacts with it

Through deterministic tools, not by direct filesystem access.

Relevant tools:

```txt
list_files(filters)
search_paths(query)
validate_paths(paths)
read_file_excerpt(path, start_line?, end_line?)
grep_contents(query, filters)
```

---

## 4. `repo-context.json`

### Purpose

context derived from explicit files.

It answers:

```txt
Which manifests exist?
Which config files exist?
Which documentation files exist?
Which CI files exist?
Which agent instruction files exist?
What mechanically parsed facts can be extracted from manifests?
```

It must not say:

```txt
This is a Next.js app.
This is a Django app.
This is an auth service.
This repo uses clean architecture.
```

It may say:

```txt
next.config.ts exists.
package.json contains dependency "next".
pyproject.toml defines script "bridger = bridger.cli:app".
.github/workflows/test.yml exists.
```

### What it is used for by agents

The discovery agent uses `repo-context.json` to form its own understanding of:

- likely ecosystems
- package managers
- explicit scripts
- declared CLI entrypoints
- dependency names
- CI workflows
- documentation/instruction files
- framework evidence

The deterministic layer provides evidence; the agent performs interpretation.

### Format

JSON.

### Schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-18T00:00:00Z",
  "manifests": [
    {
      "path": "pyproject.toml",
      "kind": "python_pyproject",
      "parsed": {
        "project_name": "bridger",
        "dependencies": ["typer", "rich", "pydantic"],
        "optional_dependencies": {},
        "dev_dependencies": ["pytest", "ruff", "mypy"],
        "scripts": {
          "bridger": "bridger.cli:app"
        }
      }
    },
    {
      "path": "package.json",
      "kind": "node_package_json",
      "parsed": {
        "name": "example",
        "dependencies": {},
        "dev_dependencies": {},
        "scripts": {}
      }
    }
  ],
  "config_files": [
    {
      "path": "tsconfig.json",
      "kind": "typescript_config"
    },
    {
      "path": "vite.config.ts",
      "kind": "vite_config"
    }
  ],
  "ci_files": [
    {
      "path": ".github/workflows/test.yml",
      "kind": "github_actions_workflow"
    }
  ],
  "instruction_files": [
    {
      "path": "AGENTS.md",
      "kind": "agent_instructions"
    }
  ],
  "docs_files": [
    {
      "path": "README.md",
      "kind": "readme"
    }
  ],
  "parse_errors": [
    {
      "path": "package.json",
      "error": "invalid_json"
    }
  ]
}
```

### File detection scope

Python files to detect:

```txt
pyproject.toml
uv.lock
poetry.lock
requirements.txt
requirements-dev.txt
setup.py
setup.cfg
tox.ini
pytest.ini
mypy.ini
ruff.toml
Dockerfile
docker-compose.yml
```

TypeScript/JavaScript files to detect:

```txt
package.json
pnpm-lock.yaml
pnpm-workspace.yaml
yarn.lock
package-lock.json
tsconfig.json
jsconfig.json
vite.config.*
next.config.*
nuxt.config.*
svelte.config.*
eslint.config.*
jest.config.*
vitest.config.*
playwright.config.*
turbo.json
```

Go files to detect:

```txt
go.mod
go.sum
Makefile
cmd/*/main.go
```

PHP files to detect:

```txt
composer.json
composer.lock
artisan
symfony.lock
phpunit.xml
.env.example
```

General docs/instruction files to detect:

```txt
README.md
CONTRIBUTING.md
CHANGELOG.md
AGENTS.md
CLAUDE.md
.cursor/rules/*
docs/**/*
adr/**/*
```

CI files to detect:

```txt
.github/workflows/*
.gitlab-ci.yml
circle.yml
.circleci/config.yml
```

### How it is built technically

Implementation approach:

1. Read `file-index.json`.
2. Match known manifest/config/docs/CI/instruction patterns against included files.
3. Parse supported manifest files mechanically:
   - TOML via `tomllib`
   - JSON via `orjson` or standard `json`
   - YAML can be listed but not deeply parsed in v0 unless a YAML dependency is already accepted
4. Extract explicit facts only.
5. Record parse errors without failing the entire run unless a required artifact cannot be produced.
6. Sort entries by path.
7. Validate and write atomically.

### How the agent interacts with it

Relevant tools:

```txt
inspect_repo_context()
inspect_manifest(path)
list_config_files()
list_docs_files()
list_instruction_files()
```

The agent may use this artifact to decide which files to inspect next, but the artifact itself must not recommend actions.

---

## 5. `symbol-index.json`

### Purpose

`symbol-index.json` records syntactic symbols extracted from source files.

It answers:

```txt
Which classes, functions, methods, variables, types, interfaces, and exports are declared?
Where are they declared?
What is the declaration text or signature?
What parser extracted them?
```

It must not explain what symbols mean.

### What it is used for by agents

The discovery agent uses `symbol-index.json` to:

- search for symbols
- inspect declarations before reading full files
- identify likely public surfaces
- understand file structure mechanically
- navigate Python and TypeScript/JavaScript repos

The agent should infer responsibility and meaning from code inspection, not from symbol summaries.

### Format

JSON.

### Schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-18T00:00:00Z",
  "symbols": [
    {
      "id": "sym:src/bridger/cli.py:8:app",
      "path": "src/bridger/cli.py",
      "name": "app",
      "kind": "variable",
      "line_start": 8,
      "line_end": 8,
      "declaration": "app = typer.Typer(...) | app = typer.Typer(no_args_is_help=True)",
      "parent": null,
      "decorators": [],
      "modifiers": [],
      "is_exported": null,
      "extractor": "tree_sitter_python"
    },
    {
      "id": "sym:src/app/page.tsx:12:HomePage",
      "path": "src/app/page.tsx",
      "name": "HomePage",
      "kind": "function",
      "line_start": 12,
      "line_end": 34,
      "declaration": "export default function HomePage()",
      "parent": null,
      "decorators": [],
      "modifiers": ["export", "default"],
      "is_exported": true,
      "extractor": "tree_sitter_typescript"
    }
  ],
  "parse_errors": [
    {
      "path": "src/broken.ts",
      "extractor": "tree_sitter_typescript",
      "error": "parse_error"
    }
  ]
}
```

### Allowed symbol facts

Allowed fields:

- `id`
- `path`
- `name`
- `kind`
- `line_start`
- `line_end`
- `declaration`
- `parent`
- `decorators`
- `modifiers`
- `is_exported`
- `extractor`

Fields intentionally excluded:

- `symbol_summary`
- `responsibility`
- `domain_role`
- `architectural_role`
- semantic tags such as `controller`, `service`, `repository`, unless purely syntactic and explicitly justified later

### Language support for v0

Required:

```txt
Python
TypeScript
JavaScript
TSX
JSX
```

### How it is built technically

Recommended approach:

- Use Tree-sitter as the main parsing architecture.
- Use separate query modules for Python and TypeScript/JavaScript.
- Use ripgrep for search tooling, not as the primary symbol extractor.
- Use ast-grep later or optionally for structural search, not as the core symbol index builder.

Python extraction should support at least:

```txt
function_definition
class_definition
decorated_definition
module-level assignments where useful
import_statement
import_from_statement, if reused by graph builder
```

TypeScript/JavaScript extraction should support at least:

```txt
function_declaration
class_declaration
method_definition
arrow function assigned to const
lexical declarations for exported constants
interface_declaration
type_alias_declaration
enum_declaration
import_statement, if reused by graph builder
export_statement, if reused by graph builder
```

Recommended implementation components:

```txt
src/bridger/deterministic/symbols/base.py
src/bridger/deterministic/symbols/python.py
src/bridger/deterministic/symbols/typescript.py
src/bridger/deterministic/symbols/indexer.py
```

Implementation notes:

- Use the file index as the source of files to parse.
- Only parse included files.
- Skip files above the configured size limit.
- Store parse errors without stopping the run.
- Keep declaration text short and syntactic.
- Use line numbers from the parser.
- Generate stable IDs from path, line, and symbol name.

### How the agent interacts with it

Relevant tools:

```txt
search_symbols(query)
list_symbols(path)
get_symbol(symbol_id)
```

The agent should use symbol search to decide what file excerpts to inspect, not as a replacement for reading code.

---

## 6. `repo-graph.json`

### Purpose

`repo-graph.json` records factual structural relationships between directories, files, symbols, imports, manifests, and explicit framework/config path facts.

It answers:

```txt
Which directories contain which files?
Which files import which files?
Which files declare which symbols?
Which imports are unresolved?
Which explicit manifest declarations point to files?
Which files match well-known framework path/config patterns?
```

It must stay relationship-based and factual.

### What it is used for by agents

The discovery agent uses `repo-graph.json` to:

- inspect file neighborhoods
- follow imports
- find reverse imports
- understand dependency structure mechanically
- locate files connected to explicit entrypoints
- inspect graph-central files without relying on semantic summaries

### Format

JSON graph.

### Schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-18T00:00:00Z",
  "nodes": [
    {
      "id": "file:src/bridger/cli.py",
      "kind": "file",
      "path": "src/bridger/cli.py"
    },
    {
      "id": "dir:src/bridger",
      "kind": "directory",
      "path": "src/bridger"
    },
    {
      "id": "symbol:sym:src/bridger/cli.py:8:app",
      "kind": "symbol",
      "symbol_id": "sym:src/bridger/cli.py:8:app"
    },
    {
      "id": "manifest:pyproject.toml:project.scripts.bridger",
      "kind": "manifest_entry",
      "path": "pyproject.toml",
      "key": "project.scripts.bridger"
    }
  ],
  "edges": [
    {
      "from": "dir:src/bridger",
      "to": "file:src/bridger/cli.py",
      "kind": "contains"
    },
    {
      "from": "file:src/bridger/cli.py",
      "to": "symbol:sym:src/bridger/cli.py:8:app",
      "kind": "declares_symbol"
    },
    {
      "from": "file:src/bridger/cli.py",
      "to": "file:src/bridger/project.py",
      "kind": "imports",
      "import_text": "from bridger.project import ProjectConfig"
    },
    {
      "from": "manifest:pyproject.toml:project.scripts.bridger",
      "to": "file:src/bridger/cli.py",
      "kind": "declares_entrypoint"
    }
  ],
  "unresolved_imports": [
    {
      "from_path": "src/bridger/cli.py",
      "import_text": "from bridger.missing import Example",
      "reason": "no_matching_file"
    }
  ]
}
```

### Allowed edge kinds

Initial edge kinds:

```txt
contains
declares_symbol
imports
declares_entrypoint
matches_path_pattern
```

Optional later edge kinds:

```txt
test_near_source
configures
references_symbol
```

Avoid edge kinds that imply semantic ownership, such as:

```txt
owns_business_logic
implements_auth
belongs_to_area
core_architecture
```

### Python import resolution

Support at least:

```txt
import x
import x.y
from x import y
from . import x
from .x import y
from ..x import y
```

Resolution should account for:

```txt
src/ layout
package root
__init__.py
module.py
package/module.py
package/module/__init__.py
```

### TypeScript/JavaScript import resolution

Support at least:

```txt
import ... from "..."
export ... from "..."
require("...")
dynamic import("...")
```

Resolution should account for:

```txt
relative imports
.ts / .tsx / .js / .jsx extensions
index.ts / index.tsx / index.js / index.jsx
tsconfig/jsconfig path aliases where easy and explicit
```

### Framework/path facts

For popular frameworks, do not model deep framework semantics in the graph.

Instead, emit explicit pattern facts only when reliable, for example:

```json
{
  "from": "file:app/api/users/route.ts",
  "to": "framework_pattern:next_app_route",
  "kind": "matches_path_pattern"
}
```

This tells the agent that the file matches a known path pattern. It does not tell the agent what architecture means.

### How it is built technically

Implementation approach:

1. Read `file-index.json`.
2. Read `repo-context.json`.
3. Read `symbol-index.json`.
4. Create directory/file containment nodes and edges.
5. Create file-to-symbol edges from the symbol index.
6. Parse imports using Tree-sitter queries or extractor output.
7. Resolve local imports where possible.
8. Record unresolved imports.
9. Add explicit manifest entrypoint edges where directly declared.
10. Add explicit framework path-pattern facts where mechanically matched.
11. Sort nodes and edges deterministically.
12. Validate and write atomically.

NetworkX can be used internally to compute graph metrics, but the persisted artifact should remain plain JSON.

### How the agent interacts with it

Relevant tools:

```txt
get_graph_neighbors(path)
get_reverse_imports(path)
list_file_imports(path)
list_declared_entrypoints()
```

The agent should use this graph for navigation, not as final architecture.

---

## 7. `graph-summary.json`

### Purpose

`graph-summary.json` is the compact deterministic summary of `repo-graph.json`.

It answers:

```txt
What are the main graph metrics?
Which files have high fan-in or fan-out?
Which entrypoints are explicitly declared?
How many imports are unresolved?
```

It should be small enough to include in the agent bootstrap context.

### What it is used for by agents

The discovery agent uses it to:

- quickly inspect structural facts
- identify files that may be worth investigating
- see explicit entrypoint declarations
- understand graph completeness limits

It must not recommend first actions or interpret architecture.

### Format

JSON.

### Schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-18T00:00:00Z",
  "counts": {
    "directory_nodes": 0,
    "file_nodes": 0,
    "symbol_nodes": 0,
    "manifest_entry_nodes": 0,
    "contains_edges": 0,
    "declares_symbol_edges": 0,
    "import_edges": 0,
    "declares_entrypoint_edges": 0,
    "matches_path_pattern_edges": 0,
    "unresolved_imports": 0
  },
  "top_fan_in_files": [
    {
      "path": "src/bridger/project.py",
      "incoming_edges": 9
    }
  ],
  "top_fan_out_files": [
    {
      "path": "src/bridger/cli.py",
      "outgoing_edges": 7
    }
  ],
  "declared_entrypoints": [
    {
      "path": "src/bridger/cli.py",
      "source": "pyproject.toml:project.scripts.bridger"
    }
  ],
  "unresolved_imports_sample": [
    {
      "from_path": "src/bridger/cli.py",
      "import_text": "from bridger.missing import Example",
      "reason": "no_matching_file"
    }
  ]
}
```

### Fields intentionally excluded

Do not include:

- candidate code areas
- architecture summary
- semantic importance ranking
- recommended first actions
- business/domain interpretation

### How it is built technically

Implementation approach:

1. Read `repo-graph.json`.
2. Count nodes and edges by kind.
3. Compute file fan-in and fan-out.
4. Extract declared entrypoint edges.
5. Include a bounded sample of unresolved imports.
6. Sort outputs deterministically.
7. Validate and write atomically.

Use NetworkX internally if helpful, but do not expose a NetworkX-specific format.

### How the agent interacts with it

Relevant tools:

```txt
inspect_graph_summary()
list_declared_entrypoints()
```

This artifact can also be embedded directly inside `repo-discovery.json` as compact context.

---

## 8. `repo-discovery.json`

### Purpose

`repo-discovery.json` is the compact bootstrap artifact for the agentic discovery layer.

It is not a repo interpretation. It is an artifact manifest and factual briefing.

It answers:

```txt
Which deterministic artifacts exist?
What are their checksums?
What compact factual context can the agent read before using tools?
Which tools are available?
What budgets apply?
```

### What it is used for by agents

The discovery agent should load this first.

Then it should use tools to inspect the underlying artifacts and selected files.

This artifact is the bridge between deterministic substrate and agentic discovery.

### Format

JSON.

### Schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-18T00:00:00Z",
  "repo": {
    "root_name": "bridger",
    "revision": "HEAD"
  },
  "artifacts": {
    "file_index": ".bridger/artifacts/file-index.json",
    "repo_context": ".bridger/artifacts/repo-context.json",
    "symbol_index": ".bridger/artifacts/symbol-index.json",
    "repo_graph": ".bridger/artifacts/repo-graph.json",
    "graph_summary": ".bridger/artifacts/graph-summary.json"
  },
  "artifact_checksums": {
    "file-index.json": "...",
    "repo-context.json": "...",
    "symbol-index.json": "...",
    "repo-graph.json": "...",
    "graph-summary.json": "..."
  },
  "compact_context": {
    "file_count": 120,
    "skipped_file_count": 14,
    "manifest_files": ["pyproject.toml"],
    "config_files": ["ruff.toml", "mypy.ini"],
    "instruction_files": ["AGENTS.md"],
    "docs_files": ["README.md"],
    "declared_entrypoints": [
      {
        "path": "src/bridger/cli.py",
        "source": "pyproject.toml:project.scripts.bridger"
      }
    ],
    "graph_counts": {
      "file_nodes": 120,
      "symbol_nodes": 430,
      "import_edges": 210,
      "unresolved_imports": 12
    }
  },
  "available_tools": [
    "list_files",
    "search_paths",
    "grep_contents",
    "read_file_excerpt",
    "inspect_manifest",
    "search_symbols",
    "list_symbols",
    "get_graph_neighbors",
    "validate_paths"
  ],
  "budgets": {
    "max_files_read": 80,
    "max_excerpts": 200
  }
}
```

### Fields intentionally excluded

Do not include:

- suggested first actions
- initial hypotheses
- code areas
- architecture summaries
- semantic warnings
- business/domain conclusions

### How it is built technically

Implementation approach:

1. Read all previous deterministic artifacts.
2. Compute checksums for each artifact.
3. Extract compact factual context:
   - file counts
   - manifest file paths
   - config file paths
   - instruction file paths
   - docs file paths
   - declared entrypoints from graph summary
   - graph counts
4. List available deterministic tools.
5. Attach current agent budgets.
6. Validate and write atomically.

### How the agent interacts with it

The agent loads this artifact first.

Expected agent startup flow:

```txt
1. Load repo-discovery.json.
2. Inspect repo-context.json through tools.
3. Inspect graph-summary.json through tools.
4. Search symbols and paths as needed.
5. Read selected file excerpts.
6. Build its own interpretation.
7. Produce the Context Plan.
```

---

## 9. Agent Tool Contract

The deterministic artifacts are persisted truth. The tools are the agent interface.

The agent should not receive unlimited filesystem access. It should use bounded deterministic tools backed by the artifacts and the safe file index.

Required v0 tools:

```txt
inspect_repo_discovery()
list_files(filters)
search_paths(query)
grep_contents(query, filters)
read_file_excerpt(path, start_line?, end_line?)
inspect_manifest(path)
list_config_files()
list_docs_files()
list_instruction_files()
search_symbols(query)
list_symbols(path)
get_symbol(symbol_id)
get_graph_neighbors(path)
get_reverse_imports(path)
list_file_imports(path)
list_declared_entrypoints()
inspect_graph_summary()
validate_paths(paths)
```

Tool rules:

- Every path argument must be validated against `file-index.json`.
- Tools must reject absolute paths.
- Tools must reject paths outside the repository.
- Tools must reject skipped files.
- File reads should support excerpts, not only full-file reads.
- Grep/search tools should be budgeted.
- Tool outputs should be compact and structured.
- Tool outputs should include enough provenance for the final Context Plan.

---

## 10. Build Order for Step 1

Recommended implementation sequence:

```txt
1. Artifact base models, writer, checksum, atomic write helpers
2. file-index.json
3. repo-context.json
4. symbol-index.json
5. repo-graph.json
6. graph-summary.json
7. repo-discovery.json
8. Agent-facing deterministic tools over the artifacts
9. CLI integration for `bridger init` and/or `bridger inspect`
10. Tests and fixture repos
```

Minimum fixture coverage:

```txt
fixtures/python-cli/
fixtures/typescript-app/
fixtures/mixed-minimal/
```

Minimum tests:

- artifact schema validation
- file index excludes sensitive/generated files
- repo context detects known manifest/config/docs files
- symbol index extracts Python functions/classes
- symbol index extracts TypeScript functions/classes/types/interfaces
- repo graph resolves simple Python imports
- repo graph resolves simple TypeScript relative imports
- graph summary counts nodes/edges
- repo discovery references all expected artifacts
- tools reject invalid/skipped/outside paths

---

## 11. Final DoD for Deterministic Pre-Requisites

The deterministic pre-requisite step is complete when:

- all six artifacts are generated under `.bridger/artifacts/`
- every artifact has a Pydantic schema
- every artifact validates before writing
- artifact writes are atomic
- paths are repository-relative and deterministic
- `file-index.json` contains only factual inventory and skip data
- `repo-context.json` contains only manifest/config/docs/instruction evidence and parsed explicit facts
- `symbol-index.json` contains only syntactic symbol facts
- `repo-graph.json` contains only factual structural relationships
- `graph-summary.json` contains only graph metrics and explicit entrypoint facts
- `repo-discovery.json` contains only artifact references, checksums, compact factual context, tools, and budgets
- no deterministic artifact contains code areas, architecture interpretation, business/domain interpretation, or suggested first actions
- agent-facing tools can query the artifacts safely
- tests cover Python and TypeScript/JavaScript basics
- the agentic discovery layer can start from `repo-discovery.json` and tool calls without direct raw filesystem access
