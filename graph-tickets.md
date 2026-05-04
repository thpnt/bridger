# Bridger repo graph feature — implementation tickets

## Feature objective

Build a deterministic, language-agnostic repo graph for Bridger.

The graph will be used by `bridger init` to feed codebase files to LLM doc generators in a stable, graph-aware order.

The feature should produce:

* `.bridger/repo-graph.json`
* `.bridger/graph-summary.json`
* graph-aware ordered file context for knowledge generation

Out of scope for this feature:

* AST parsing
* symbol graph
* call graph
* type graph
* semantic code understanding
* circular dependency reporting
* agentic graph navigation tools
* incremental knowledge updates

---

# Ticket 25 — Define repo graph models

## Goal

Add Zod models and TypeScript types for the repo graph and graph summary.

## Files

Create:

* `src/core/repo-graph/models/repo-graph.ts`
* `src/core/repo-graph/models/graph-summary.ts`

## Implementation guidelines

Define `RepoGraphSchema` with:

* `generatedAt`
* `graphVersion`
* `repoRoot`
* `nodes`
* `edges`
* `diagnostics`
* `stats`

Define node shape:

* `id`
* `path`
* `kind`: `file | directory`
* `extension`
* `language`
* `sizeBytes`
* `tags`

Define edge shape:

* `from`
* `to`
* `type`: `contains | imports`
* `confidence`: `high | medium | low`
* `source`: `filesystem | typescript-js-imports | python-imports`
* optional `importSpecifier`

Define diagnostic shape:

* `level`: `info | warning`
* `code`: `unresolved-import | unsupported-language | skipped-large-file | ambiguous-import`
* optional `file`
* `message`

Define `GraphSummarySchema` with:

* `generatedAt`
* `graphVersion`
* `entrypoints`
* `rootFiles`
* `configFiles`
* `docsFiles`
* `highFanInFiles`
* `highFanOutFiles`
* `leafFiles`
* `isolatedFiles`
* `architectureFirstOrder`
* `dependencyFirstOrder`
* `stats`

## Verifiable outcome

* Repo graph and graph summary schemas compile.
* Invalid node kinds fail validation.
* Invalid edge types fail validation.
* Invalid diagnostic codes fail validation.
* `pnpm typecheck` passes.

---

# Ticket 26 — Add graph path and language utilities

## Goal

Add small deterministic utilities used by all graph builders and extractors.

## Files

Create:

* `src/core/repo-graph/utils/normalize-path.ts`
* `src/core/repo-graph/utils/detect-language.ts`
* `src/core/repo-graph/utils/path-tags.ts`

## Implementation guidelines

`normalize-path.ts` should:

* convert Windows separators to `/`
* remove leading `./`
* keep repo-relative paths stable

`detect-language.ts` should map:

* `.ts` → `typescript`
* `.tsx` → `typescript`
* `.js` → `javascript`
* `.jsx` → `javascript`
* `.mjs` → `javascript`
* `.cjs` → `javascript`
* `.py` → `python`
* `.md` → `markdown`
* `.json` → `json`
* unknown extensions → `unknown`

`path-tags.ts` should derive simple graph tags from path patterns:

* `root`
* `config`
* `docs`
* `source`
* `test`
* `entrypoint-candidate`
* `component`
* `service`
* `utility`
* `route`
* `api-route`

Keep this heuristic and deterministic.

## Verifiable outcome

* Paths are normalized consistently.
* Languages are detected from extensions.
* Known path patterns receive expected tags.
* Unit tests cover path normalization and language detection.

---

# Ticket 27 — Build filesystem graph from file index

## Goal

Create graph nodes and `contains` edges from the existing `FileIndex`.

## Files

Create:

* `src/core/repo-graph/build-filesystem-graph.ts`

## Implementation guidelines

Input:

* `repoRoot`
* `fileIndex`

Output:

* partial `RepoGraph` data containing file nodes, directory nodes, and `contains` edges

For each file in `fileIndex.files`:

* create a file node
* create missing parent directory nodes
* create `contains` edges from directory to child directory/file

Example path:

* `src/app/page.tsx`

Should create nodes:

* `src`
* `src/app`
* `src/app/page.tsx`

And edges:

* `src -> src/app`
* `src/app -> src/app/page.tsx`

Use stable IDs:

* for files: repo-relative path
* for directories: repo-relative directory path
* root directory can be represented as `.` if needed

Do not rescan the repo. Use only `FileIndex`.

## Verifiable outcome

* Given a fixture `FileIndex`, graph nodes are created.
* Parent directories are created exactly once.
* `contains` edges are created correctly.
* Output validates against the relevant repo graph node/edge schemas.

---

# Ticket 28 — Add dependency extractor interface

## Goal

Define a common interface for language-specific import extractors.

## Files

Create:

* `src/core/repo-graph/extractors/dependency-extractor.ts`

## Implementation guidelines

Define a `DependencyExtractor` interface:

* `language`
* `extensions`
* `extractImports(input)`

The extractor should return raw import records:

* `specifier`
* `kind`: `static | dynamic | require | reexport`
* `source`
* optional `line`

Do not resolve imports in this ticket.

Keep extraction separate from resolution.

Suggested type:

* `ExtractedImport`

  * `specifier`
  * `kind`
  * `line?`

Input should include:

* `filePath`
* `content`

## Verifiable outcome

* Extractor interface is reusable for TS/JS and Python.
* Types compile.
* No graph construction logic is included in this ticket.

---

# Ticket 29 — Implement TS/JS import extractor

## Goal

Extract import specifiers from TypeScript and JavaScript files.

## Files

Create:

* `src/core/repo-graph/extractors/typescript-js-import-extractor.ts`

## Implementation guidelines

Support these patterns:

* `import x from "./x"`
* `import { x } from "../x"`
* `import type { X } from "./x"`
* `export * from "./x"`
* `export { x } from "./x"`
* `const x = require("./x")`
* `await import("./x")`

Use conservative regex-based extraction.

Do not parse AST.

Do not resolve imports.

Do not include package imports as errors. Just extract all specifiers and let the resolver decide whether they are local.

Mark import kind:

* regular imports → `static`
* `import type` → `static`
* `export ... from` → `reexport`
* `require(...)` → `require`
* `import(...)` → `dynamic`

## Verifiable outcome

* Extractor returns expected specifiers for `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`.
* Relative imports are extracted.
* Package imports are extracted but not resolved in this ticket.
* Tests cover static imports, reexports, require, and dynamic imports.

---

# Ticket 30 — Implement Python import extractor

## Goal

Extract import specifiers from Python files.

## Files

Create:

* `src/core/repo-graph/extractors/python-import-extractor.ts`

## Implementation guidelines

Support these patterns:

* `import foo`
* `import foo.bar`
* `from foo import bar`
* `from . import local_module`
* `from .local_module import thing`
* `from ..domain import service`

Use conservative line-based extraction.

Ignore commented lines.

Do not resolve imports.

Represent Python imports as specifiers such as:

* `foo`
* `foo.bar`
* `.local_module`
* `..domain.service` or an equivalent structured form

If needed, use an internal shape with:

* `module`
* `names`
* `level`

But expose a normalized `specifier`.

## Verifiable outcome

* Extractor returns expected imports from simple Python files.
* Relative Python imports are captured.
* Commented imports are ignored.
* Tests cover `import`, `from import`, and relative imports.

---

# Ticket 31 — Implement TS/JS local import resolver

## Goal

Resolve TS/JS import specifiers to local repo files.

## Files

Create:

* `src/core/repo-graph/resolution/resolve-typescript-js-import.ts`

## Implementation guidelines

Input:

* importer path
* import specifier
* list/set of repo files

Only resolve local imports for v1:

* `./x`
* `../x`
* optionally `@/x` if simple baseUrl or path alias support already exists

For relative imports, resolve candidate paths:

* `x.ts`
* `x.tsx`
* `x.js`
* `x.jsx`
* `x.mjs`
* `x.cjs`
* `x/index.ts`
* `x/index.tsx`
* `x/index.js`
* `x/index.jsx`
* `x/index.mjs`
* `x/index.cjs`

Ignore external package imports:

* `react`
* `next`
* `zod`
* `@supabase/supabase-js`

Return:

* resolved path with confidence `high`
* unresolved result for local imports that cannot be matched
* ignored result for external imports

Do not throw on unresolved imports.

## Verifiable outcome

* Relative TS/JS imports resolve to existing files.
* Directory index imports resolve.
* External package imports are ignored.
* Missing local imports return unresolved.
* Tests cover all supported resolution cases.

---

# Ticket 32 — Implement Python local import resolver

## Goal

Resolve Python import specifiers to local repo files conservatively.

## Files

Create:

* `src/core/repo-graph/resolution/resolve-python-import.ts`

## Implementation guidelines

Input:

* importer path
* import specifier
* list/set of repo files

Resolve candidates:

* `foo.py`
* `foo/__init__.py`
* `foo/bar.py`
* `foo/bar/__init__.py`

For relative imports, resolve based on importer directory and relative level.

Examples:

* from `src/app/main.py`, `from . import service` → `src/app/service.py`
* from `src/app/routes/user.py`, `from ..domain import users` → `src/app/domain/users.py`

Keep behavior conservative.

If uncertain, return unresolved instead of guessing.

Do not resolve installed packages.

## Verifiable outcome

* Simple absolute local imports resolve.
* Package-style imports resolve to `__init__.py` when present.
* Relative imports resolve when unambiguous.
* External packages are ignored.
* Unresolved imports do not throw.
* Tests cover absolute, package, and relative cases.

---

# Ticket 33 — Build repo graph import edges

## Goal

Run import extractors and resolvers to add `imports` edges and diagnostics to the repo graph.

## Files

Create:

* `src/core/repo-graph/build-import-edges.ts`

## Implementation guidelines

Input:

* `repoRoot`
* existing filesystem graph
* `fileIndex`

For each supported file:

* skip files over configured size limit
* read content
* choose extractor by language
* extract imports
* resolve each import
* add `imports` edge when resolved
* add diagnostic when local import cannot be resolved
* ignore external package imports

Use source:

* TS/JS edges → `typescript-js-imports`
* Python edges → `python-imports`

Do not add duplicate import edges.

Do not crash on read errors. Emit diagnostic if needed.

## Verifiable outcome

* Import edges are added for TS/JS fixture files.
* Import edges are added for Python fixture files.
* External package imports do not create diagnostics.
* Unresolved local imports create diagnostics.
* Duplicate imports do not create duplicate edges.

---

# Ticket 34 — Add full `buildRepoGraph` orchestrator

## Goal

Create the main repo graph builder that composes filesystem graph and import edges.

## Files

Create:

* `src/core/repo-graph/build-repo-graph.ts`

## Implementation guidelines

Function signature:

* `buildRepoGraph(input: { repoRoot: string; fileIndex: FileIndex }): Promise<RepoGraph>`

Pipeline:

1. Build filesystem graph from `fileIndex`
2. Add import edges
3. Compute stats
4. Validate with `RepoGraphSchema`
5. Return graph

Stats should include:

* file count
* directory count
* import edge count
* unresolved import count
* supported language file count

The function should be deterministic.

Sort nodes, edges, and diagnostics before returning.

Recommended stable sorting:

* nodes by `path`
* edges by `from`, then `to`, then `type`
* diagnostics by `file`, then `code`, then `message`

## Verifiable outcome

* Full graph builds from a fixture file index.
* Output validates with `RepoGraphSchema`.
* Output order is stable across runs.
* Stats are correct.
* `pnpm test` passes.

---

# Ticket 35 — Add graph traversal helpers

## Goal

Add deterministic traversal utilities over the repo graph.

## Files

Create:

* `src/core/repo-graph/traversal/build-adjacency-map.ts`
* `src/core/repo-graph/traversal/get-dependencies.ts`
* `src/core/repo-graph/traversal/get-consumers.ts`
* `src/core/repo-graph/traversal/get-neighborhood.ts`

## Implementation guidelines

Implement:

* `buildAdjacencyMap(graph)`
* `getDependencies(graph, filePath, depth?)`
* `getConsumers(graph, filePath, depth?)`
* `getNeighborhood(graph, filePath, depth?)`

Definitions:

* dependencies = outgoing `imports` edges
* consumers = incoming `imports` edges
* neighborhood = dependencies + consumers, with configurable depth

Do not include `contains` edges in dependency traversal unless explicitly requested.

Return stable ordered paths.

Avoid infinite loops by tracking visited files.

## Verifiable outcome

* Dependencies are returned for files with outgoing imports.
* Consumers are returned for files with incoming imports.
* Neighborhood includes both directions.
* Depth limit works.
* Cycles do not cause infinite loops.

---

# Ticket 36 — Implement graph file classification helpers

## Goal

Classify important graph node categories for summaries and ordering.

## Files

Create:

* `src/core/repo-graph/traversal/get-entrypoints.ts`
* `src/core/repo-graph/traversal/get-root-files.ts`
* `src/core/repo-graph/traversal/get-graph-file-ranks.ts`

## Implementation guidelines

Detect entrypoint candidates with path heuristics:

For Next.js / web projects:

* `app/page.tsx`
* `app/**/page.tsx`
* `app/**/route.ts`
* `pages/**/*.tsx`
* `src/app/**/page.tsx`
* `src/pages/**/*.tsx`

For CLIs / Node apps:

* `src/cli/index.ts`
* `src/index.ts`
* `src/main.ts`
* `bin/**`

For Python:

* `main.py`
* `app.py`
* `src/main.py`
* files containing `if __name__ == "__main__"` if cheap to detect

Root files:

* `README.md`
* `AGENTS.md`
* `CLAUDE.md`
* `package.json`
* `tsconfig.json`
* `pyproject.toml`
* config files

Ranks should include:

* fan-in count
* fan-out count
* is leaf
* is isolated
* is entrypoint
* is config
* is docs

## Verifiable outcome

* Entrypoints are detected in TS/JS fixtures.
* Entrypoints are detected in Python fixtures.
* Root/config/docs files are classified.
* Fan-in and fan-out counts are correct.
* Leaf and isolated files are detected.

---

# Ticket 37 — Implement graph ordering algorithms

## Goal

Generate architecture-first and dependency-first file orders.

## Files

Create:

* `src/core/repo-graph/traversal/get-architecture-order.ts`
* `src/core/repo-graph/traversal/get-dependency-order.ts`

## Implementation guidelines

Architecture-first order priority:

1. root docs/config files
2. entrypoint candidates
3. direct dependencies of entrypoints
4. feature/domain files
5. components/services/lib files
6. shared utilities
7. tests
8. remaining files by stable path order

Dependency-first order priority:

1. leaf files
2. low fan-out utility files
3. service/helper files
4. feature/component files
5. entrypoints
6. tests
7. remaining files by stable path order

These do not need to be perfect topological sorts.

They need to be:

* deterministic
* useful
* stable
* explainable

Every file should appear at most once.

Every source file should eventually appear unless excluded by file index.

## Verifiable outcome

* Architecture-first order starts with root/config docs and entrypoints.
* Dependency-first order prioritizes leaf/shared files.
* Orders are stable across runs.
* No duplicate paths are returned.
* All eligible files are included.

---

# Ticket 38 — Build graph summary

## Goal

Create the LLM-friendly `graph-summary.json` from the full repo graph.

## Files

Create:

* `src/core/repo-graph/build-graph-summary.ts`

## Implementation guidelines

Input:

* `RepoGraph`

Output:

* `GraphSummary`

Include:

* `entrypoints`
* `rootFiles`
* `configFiles`
* `docsFiles`
* `highFanInFiles`
* `highFanOutFiles`
* `leafFiles`
* `isolatedFiles`
* `architectureFirstOrder`
* `dependencyFirstOrder`
* `stats`

For high fan-in / fan-out:

* include path
* count
* short reason

Keep summary compact.

Sort all arrays deterministically.

Validate with `GraphSummarySchema`.

## Verifiable outcome

* Summary builds from fixture graph.
* Summary validates with `GraphSummarySchema`.
* Architecture and dependency orders are included.
* High fan-in and high fan-out files are correct.
* Output is stable across runs.

---

# Ticket 39 — Add graph output writers

## Goal

Write `repo-graph.json` and `graph-summary.json` to `.bridger/`.

## Files

Create:

* `src/core/repo-graph/write-repo-graph.ts`

Or reuse existing output utilities and add constants in:

* `src/core/utils/paths.ts`

## Implementation guidelines

Add path helpers:

* `getRepoGraphPath(repoRoot)`
* `getGraphSummaryPath(repoRoot)`

Write:

* `.bridger/repo-graph.json`
* `.bridger/graph-summary.json`

Use existing stable JSON writer.

Do not create a new writing abstraction unless needed.

## Verifiable outcome

* Graph files are written to expected paths.
* Parent directories are created if needed.
* JSON output is stable and pretty formatted.
* Existing output helpers are reused.

---

# Ticket 40 — Implement graph-ordered file reader

## Goal

Read file contents in graph-aware order for LLM doc generation.

## Files

Create:

* `src/core/repo-graph/read-graph-ordered-files.ts`

## Implementation guidelines

This is the graph-aware replacement for the current important-file reader.

Input:

* `repoRoot`
* `graph`
* `summary`
* `mode`: `architecture-first | dependency-first`
* `maxFiles`
* `maxSingleFileBytes`
* `maxTotalBytes`
* optional `includeTags`
* optional `excludeTags`

Output:

* ordered file context entries:

  * `path`
  * `reason`
  * `order`
  * `content`

Use `architectureFirstOrder` for `bridger init`.

Respect byte limits:

* skip files over `maxSingleFileBytes`
* stop before exceeding `maxTotalBytes`

Reasons should be deterministic and useful:

* `Root documentation file`
* `Project config file`
* `Entrypoint candidate`
* `Dependency of entrypoint`
* `Shared utility or leaf file`
* `Test file`
* `Included by graph order`

Do not read binary files.

Do not throw for unreadable files; skip and optionally return diagnostics.

## Verifiable outcome

* Files are read in architecture-first order.
* Byte limits are enforced.
* Large files are skipped.
* Reasons are included.
* Output is stable across runs.
* Tests cover ordering and byte limits.

---

# Ticket 41 — Integrate repo graph into `init`

## Goal

Update `bridger init` to generate graph artifacts and use graph-ordered file context.

## Files

Modify:

* `src/cli/commands/init.ts`
* possibly `src/core/context-builder/build-repo-context.ts`
* doc generator call sites if they currently consume important files directly

Use:

* `buildRepoGraph`
* `buildGraphSummary`
* `readGraphOrderedFiles`
* `writeJson`

## Implementation guidelines

New `init` flow:

1. Resolve repo root
2. Ensure output dirs
3. Build file index
4. Build repo context
5. Build repo graph
6. Build graph summary
7. Write `repo-context.json`
8. Write `file-index.json`
9. Write `repo-graph.json`
10. Write `graph-summary.json`
11. Read graph-ordered file context
12. Generate docs with ordered context
13. Write generated docs

Keep LLM behavior unchanged except for the context ordering.

Do not remove existing important-file logic immediately unless it can be safely replaced.

Preferred transition:

* keep important config/root docs always included
* use graph order for source file selection

## Verifiable outcome

* `pnpm dev init` writes `repo-graph.json`.
* `pnpm dev init` writes `graph-summary.json`.
* Existing generated docs are still produced.
* Init still fails clearly if LLM config is missing.
* Graph generation itself does not require LLM/API key.
* Init summary prints graph output paths.

---

# Ticket 42 — Add graph inspection output

## Goal

Make graph generation debuggable without running full LLM doc generation.

## Files

Modify:

* `src/cli/commands/inspect.ts`

## Implementation guidelines

Add optional flag:

* `bridger inspect --graph`

When used, print:

* file count
* directory count
* import edge count
* unresolved import count
* entrypoint candidates
* top high fan-in files
* top high fan-out files
* first 10 files in architecture-first order

Do not write files unless current inspect behavior already writes files.

Do not require LLM/API key.

## Verifiable outcome

* `pnpm dev inspect --graph` runs without API key.
* Output includes graph stats.
* Output includes entrypoint candidates.
* Output includes graph ordering preview.
* Command exits non-zero only on real errors.

---

# Ticket 43 — Add graph unit fixtures and tests

## Goal

Cover graph generation with deterministic tests.

## Files

Create/update:

* `tests/repo-graph.test.ts`
* `tests/fixtures/graph-ts-basic/`
* `tests/fixtures/graph-python-basic/`
* `tests/fixtures/graph-mixed-basic/`

## Implementation guidelines

TS fixture should include:

* root `package.json`
* `src/index.ts`
* relative imports
* directory index imports
* unresolved local import
* external package import

Python fixture should include:

* `main.py`
* package folder with `__init__.py`
* relative imports
* external package import
* unresolved local import

Mixed fixture should include:

* TS files
* Python files
* Markdown/config files

Test:

* graph nodes
* `contains` edges
* `imports` edges
* unresolved diagnostics
* summary generation
* ordering stability
* byte-limit behavior in graph reader

Do not test LLM generation here.

## Verifiable outcome

* `pnpm test` passes without API key.
* TS import graph works.
* Python import graph works.
* Mixed repo graph works.
* Graph output is stable across repeated builds.

---

# Ticket 44 — Update README and evaluation docs for repo graph

## Goal

Document the graph feature and how to evaluate it.

## Files

Modify:

* `README.md`
* `docs/evaluation.md`

## Implementation guidelines

README should mention:

* `.bridger/repo-graph.json`
* `.bridger/graph-summary.json`
* graph-aware init context ordering
* current limitations

Evaluation doc should add graph-specific checks:

* Did entrypoint detection make sense?
* Did import edges look correct?
* Did architecture-first order look useful?
* Were important source files included early?
* Were unresolved imports reported clearly?
* Did generated docs improve compared to heuristic file ordering?

Known limitations:

* conservative import extraction
* no AST parsing
* no semantic code understanding
* no symbol/call graph
* Python resolution is best-effort
* only local imports become graph edges

## Verifiable outcome

* README explains graph artifacts.
* Evaluation doc includes graph checks.
* A developer can understand what the graph does and does not do.

---

# Recommended implementation order

1. Ticket 25 — Define repo graph models
2. Ticket 26 — Add graph path and language utilities
3. Ticket 27 — Build filesystem graph from file index
4. Ticket 28 — Add dependency extractor interface
5. Ticket 29 — Implement TS/JS import extractor
6. Ticket 31 — Implement TS/JS local import resolver
7. Ticket 30 — Implement Python import extractor
8. Ticket 32 — Implement Python local import resolver
9. Ticket 33 — Build repo graph import edges
10. Ticket 34 — Add full `buildRepoGraph` orchestrator
11. Ticket 35 — Add graph traversal helpers
12. Ticket 36 — Implement graph file classification helpers
13. Ticket 37 — Implement graph ordering algorithms
14. Ticket 38 — Build graph summary
15. Ticket 39 — Add graph output writers
16. Ticket 40 — Implement graph-ordered file reader
17. Ticket 41 — Integrate repo graph into `init`
18. Ticket 42 — Add graph inspection output
19. Ticket 43 — Add graph unit fixtures and tests
20. Ticket 44 — Update README and evaluation docs

---

# Minimum useful cut line

The smallest useful version is:

1. Ticket 25 — Models
2. Ticket 26 — Utils
3. Ticket 27 — Filesystem graph
4. Ticket 29 — TS/JS import extractor
5. Ticket 31 — TS/JS resolver
6. Ticket 33 — Import edges
7. Ticket 34 — `buildRepoGraph`
8. Ticket 38 — `buildGraphSummary`
9. Ticket 40 — Graph-ordered file reader
10. Ticket 41 — Init integration

That gives us:

* deterministic repo graph
* TS/JS import edges
* graph summary
* graph-aware `init`

Python support and inspect/debugging can follow immediately after.
