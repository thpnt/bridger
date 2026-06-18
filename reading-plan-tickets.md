# Bridger Graph v2 Sprint Backlog

## Context reminder

Bridger currently has a deterministic repo graph feature that can:

* scan a repo into a file index;
* build file and directory nodes;
* build filesystem `contains` edges;
* extract local TS/JS and Python imports;
* resolve local imports into `imports` edges;
* compute fan-in/fan-out stats;
* build a graph summary;
* generate `architectureFirstOrder` and `dependencyFirstOrder`;
* write `.bridger/repo-graph.json` and `.bridger/graph-summary.json`;
* use graph-ordered files during `bridger init`;
* inspect the graph with `bridger inspect --graph`.

The first implementation works structurally, but the Bridger repo output exposed several quality problems:

* entrypoints were empty, even though Bridger clearly has CLI entrypoints;
* tests and fixtures dominated early reading order;
* root files were too broad, with lockfiles/planning docs appearing too early;
* flat file order is not expressive enough for how a senior developer reads a repo;
* graph edges alone are not enough to produce meaningful LLM context;
* each documentation agent should eventually receive a **doc-specific reading plan**, not the same generic flat file list.

The new goal is to evolve from:

```txt
RepoGraph + GraphSummary + flat architectureFirstOrder
```

to:

```txt
RepoGraph + CodebaseMap + ReadingPlan
```

Where:

```txt
RepoGraph = deterministic structural facts
CodebaseMap = graph + roles + entrypoints + framework signals + clusters
ReadingPlan = deterministic senior-dev discovery batches, optionally doc-specific
```

## Final expected outcome

By the end of this sprint, Bridger should be able to:

1. Build a more meaningful graph summary with correct entrypoints and less noisy priority ordering.
2. Classify files with richer deterministic roles.
3. Detect common framework entrypoints in a structured way.
4. Detect important contract/model/schema files, including Zod and Pydantic usage.
5. Build subsystem clusters from folder structure and graph topology.
6. Build deterministic reading batches that approximate how a senior developer discovers a codebase.
7. Generate doc-specific reading plans for each documentation agent.
8. Use these doc-specific reading plans in `bridger init`.
9. Keep graph generation deterministic, API-key-free, and testable.
10. Preserve the current graph artifacts while extending them with higher-value reading-plan artifacts.

---

# Sprint tickets

## Ticket 45 — Add richer universal file role tagging

### Goal

Improve deterministic file role classification so graph ordering and future reading batches can distinguish source files, tests, fixtures, configs, lockfiles, docs, generated files, scripts, commands, models, schemas, utilities, services, routes, and writers/readers/builders.

### Dependencies

Depends on the existing graph utilities:

* `src/core/repo-graph/utils/path-tags.ts`
* `src/core/repo-graph/utils/detect-language.ts`
* `src/core/repo-graph/models/repo-graph.ts`

### Implementation guidelines

Extend the current path tagging logic with a compact universal taxonomy.

Recommended tags to support:

```txt
docs
config
project-config
fixture-config
lockfile
planning-doc
source
test
fixture
generated
entrypoint-candidate
command
route
api-route
script
model
schema
type
service
utility
component
builder
generator
resolver
extractor
reader
writer
migration
```

Keep the taxonomy meaningful and bounded. Do not add hundreds of hyper-specific tags.

Important distinctions:

* `package.json` at repo root should be `project-config`.
* `tests/fixtures/**/package.json` should be `fixture-config`, not high-priority project config.
* `pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `bun.lock*` should be `lockfile`.
* files under `tests/fixtures/**` should be `fixture`.
* test files should be `test`.
* root planning docs like `mvp-tickets.md`, `graph-tickets.md`, `prd.md` can be `planning-doc`.
* generated files should be tagged when path/name clearly indicates generated output.

Avoid making every tag high-confidence. The role tags are deterministic hints, not semantic truth.

### Verifiable outcome

Tests should prove:

* root `package.json` is tagged as `project-config`;
* fixture `package.json` is tagged as `fixture-config`;
* lockfiles are tagged as `lockfile`;
* `tests/**` files are tagged as `test`;
* `tests/fixtures/**` files are tagged as `fixture`;
* `src/cli/commands/init.ts` is tagged as `command`;
* `src/core/repo-graph/build-repo-graph.ts` is tagged as `builder`;
* `src/core/repo-graph/models/repo-graph.ts` is tagged as model/schema/type-like according to the selected taxonomy;
* existing graph model validation still passes.

---

## Ticket 46 — Improve entrypoint detection with a detector registry

### Goal

Replace the overly narrow entrypoint heuristic with a deterministic detector registry that supports multiple frameworks and runtime styles.

### Dependencies

Depends on Ticket 45 role tags and current graph classification helpers:

* `get-entrypoints.ts`
* `path-tags.ts`
* repo stack detection if available
* file index / repo graph nodes

### Implementation guidelines

Create or refactor toward an entrypoint detector registry.

Suggested output type:

```ts
type EntrypointCandidate = {
  path: string;
  kind:
    | "cli"
    | "command"
    | "web-page"
    | "api-route"
    | "server"
    | "script"
    | "job"
    | "unknown";
  framework?: string;
  confidence: "high" | "medium" | "low";
  reasons: string[];
};
```

Keep existing `getEntrypoints(graph): string[]` for compatibility, but internally derive it from richer candidates.

Add a new helper if useful:

```ts
getEntrypointCandidates(graph, context?): EntrypointCandidate[]
```

Minimum detectors for this ticket:

### Node / TypeScript CLI

Detect:

```txt
src/cli/cli.ts
src/cli/index.ts
src/cli/commands/*.ts
cli.ts
bin/**
package.json bin field if available
package.json scripts referencing src/cli or cli.ts if available
```

### Next.js

Detect:

```txt
app/**/page.tsx
src/app/**/page.tsx
app/**/route.ts
src/app/**/route.ts
pages/**/*.tsx
pages/api/**/*.ts
src/pages/**/*.tsx
src/pages/api/**/*.ts
```

### Vite / React

Detect:

```txt
src/main.tsx
src/main.ts
src/App.tsx
index.html as app shell/config-like context
vite.config.*
```

### Python scripts

Detect:

```txt
main.py
app.py
src/main.py
src/app.py
scripts/*.py
```

### FastAPI, conservative first pass

Use deterministic path/content signals only if content is already available or cheaply inspectable in the graph pipeline later. If content is not available in this ticket, support path conventions:

```txt
app/main.py
src/main.py
api/*.py
routers/*.py
```

Do not overfit yet.

### Django, conservative first pass

Detect:

```txt
manage.py
*/urls.py
*/asgi.py
*/wsgi.py
```

### Verifiable outcome

On the Bridger repo, `graph-summary.json` should no longer have empty entrypoints. It should include at least:

```txt
src/cli/cli.ts
src/cli/commands/init.ts
src/cli/commands/inspect.ts
```

Tests should cover:

* Bridger-style CLI entrypoints;
* Next.js route/page entrypoints;
* Vite React entrypoint;
* Python `main.py`;
* Django `manage.py`/`urls.py`;
* no false positive for random utility files.

---

## Ticket 47 — Add external import and schema/model signals

### Goal

Capture useful non-edge signals from imports/content, especially framework/library usage and schema/model conventions, without turning external packages into graph edges.

### Dependencies

Depends on current import extractors and graph building:

* TS/JS import extractor
* Python import extractor
* build import edges
* repo graph models

### Implementation guidelines

External imports should remain ignored for graph edges, but they should be available as file-level signals.

Add file metadata or a new map in the graph/summary layer, depending on current model constraints.

Signals to capture:

```txt
externalImports
frameworkSignals
roleHints
```

Examples:

### Zod

Detect:

```txt
from "zod"
import { z } from "zod"
z.object(
z.enum(
z.infer<
```

Map to:

```txt
frameworkSignals: ["zod"]
roleHints: ["schema", "validation", "contract"]
```

### Pydantic

Detect:

```txt
from pydantic import BaseModel
class X(BaseModel)
Field(
```

Map to:

```txt
frameworkSignals: ["pydantic"]
roleHints: ["schema", "model", "validation", "contract"]
```

### Framework/library hints

Capture external imports such as:

```txt
next
react
fastapi
django
zod
pydantic
cac
commander
typer
click
```

Do not require perfect coverage. The goal is to make deterministic role inference better.

### Verifiable outcome

Tests should prove:

* external imports do not create `imports` edges;
* external imports are captured as file signals;
* Zod files are identified as schema/contract files;
* Pydantic files are identified as schema/model files;
* current graph tests still pass.

---

## Ticket 48 — Add codebase cluster detection

### Goal

Group files into deterministic subsystem clusters so Bridger can reason about codebase areas, not only individual files.

### Dependencies

Depends on:

* RepoGraph
* file role tags
* import edges
* fan-in/fan-out ranks
* entrypoint detection

### Implementation guidelines

Create a new module, for example:

```txt
src/core/repo-graph/clustering/build-codebase-clusters.ts
```

Suggested type:

```ts
type CodebaseCluster = {
  id: string;
  rootPath: string;
  title: string;
  kind:
    | "cli"
    | "feature"
    | "domain"
    | "infrastructure"
    | "shared"
    | "models"
    | "tests"
    | "docs"
    | "fixtures"
    | "unknown";
  files: string[];
  entrypoints: string[];
  centralFiles: string[];
  orchestrators: string[];
  contracts: string[];
  tests: string[];
  dependencies: string[];
  consumers: string[];
};
```

Cluster rules should be deterministic and path-first.

Recommended cluster roots:

For TypeScript/Node-style repos:

```txt
src/cli
src/core/<name>
src/shared
src/<name>
tests
docs
scripts
```

For Next/Nuxt-style repos:

```txt
src/app
app
pages
src/pages
server
components
lib
```

For Python-style repos:

```txt
app/<name>
src/<package>/<name>
scripts
tests
```

Cluster dependency graph:

* if a file in cluster A imports a file in cluster B, add cluster A → cluster B dependency;
* dedupe and sort cluster dependencies.

Cluster central files:

* high fan-in files inside the cluster;
* model/schema/contract files;
* orchestrator/high fan-out files.

### Verifiable outcome

On Bridger, clusters should include something close to:

```txt
src/cli
src/core/repo-scanner
src/core/context-builder
src/core/repo-graph
src/core/doc-generator
src/core/output
src/core/llm
src/core/models
src/shared
tests
docs
```

Tests should verify:

* files are assigned to stable clusters;
* cluster dependencies are derived from import edges;
* each cluster has sorted unique files;
* central files and entrypoints are populated when relevant;
* fixtures/tests are separated from source clusters.

---

## Ticket 49 — Add CodebaseMap model and builder

### Goal

Introduce a higher-level deterministic codebase map that combines graph facts, entrypoints, role signals, external signals, and clusters.

### Dependencies

Depends on Tickets 45–48.

### Implementation guidelines

Create model and builder files, for example:

```txt
src/core/repo-graph/models/codebase-map.ts
src/core/repo-graph/build-codebase-map.ts
```

Suggested shape:

```ts
type CodebaseMap = {
  generatedAt: string;
  graphVersion: 1;
  entrypoints: EntrypointCandidate[];
  clusters: CodebaseCluster[];
  fileRoles: Array<{
    path: string;
    tags: string[];
    roleHints: string[];
    frameworkSignals: string[];
    fanIn: number;
    fanOut: number;
    clusterId?: string;
  }>;
  stats: {
    clusterCount: number;
    entrypointCount: number;
    sourceFileCount: number;
    testFileCount: number;
    fixtureFileCount: number;
    unresolvedImportCount: number;
  };
};
```

Use Zod validation consistent with existing models.

This model should not replace `RepoGraph`. It is an interpretation layer over the graph.

### Verifiable outcome

Tests should verify:

* `CodebaseMapSchema` validates;
* every source file has a file role entry;
* entrypoints are richer than string paths;
* clusters are included;
* stats are correct;
* output is deterministic except `generatedAt`.

---

## Ticket 50 — Build generic reading batch model

### Goal

Define the structured reading batch model used to represent senior-developer-style reading plans.

### Dependencies

Depends on CodebaseMap and GraphSummary models, but this ticket can be mostly model-only.

### Implementation guidelines

Create:

```txt
src/core/repo-graph/models/reading-plan.ts
```

Suggested types:

```ts
type ReadingPlan = {
  generatedAt: string;
  graphVersion: 1;
  planKind: "architecture" | "dependency" | "doc-specific";
  targetDoc?: string;
  batches: ReadingBatch[];
  flatOrder: string[];
  stats: {
    batchCount: number;
    uniqueFileCount: number;
    repeatedFileCount: number;
  };
};

type ReadingBatch = {
  id: string;
  title: string;
  purpose: string;
  kind:
    | "orientation"
    | "entrypoint-flow"
    | "subsystem"
    | "contracts"
    | "verification"
    | "remaining";
  files: ReadingBatchFile[];
};

type ReadingBatchFile = {
  path: string;
  reason: string;
  roleInBatch:
    | "orientation"
    | "entrypoint"
    | "direct-dependency"
    | "orchestrator"
    | "contract"
    | "implementation"
    | "utility"
    | "test"
    | "fixture"
    | "supporting-context";
};
```

Important: files may appear in multiple batches. `flatOrder` should dedupe for compatibility, but `batches` should preserve contextual repetition.

### Verifiable outcome

Tests should verify:

* model validates;
* repeated files are allowed in batches;
* `flatOrder` dedupes;
* stats count unique and repeated files correctly.

---

## Ticket 51 — Build architecture reading plan

### Goal

Generate a deterministic architecture-oriented reading plan that replaces the current flat architecture-first order as the main context strategy.

### Dependencies

Depends on:

* CodebaseMap
* ReadingPlan model
* clusters
* entrypoint candidates
* graph ranks

### Implementation guidelines

Create:

```txt
src/core/repo-graph/reading-plans/build-architecture-reading-plan.ts
```

Batch strategy:

### Batch 1 — Project orientation

High-priority root docs/config only:

```txt
README.md
AGENTS.md
package.json
tsconfig.json
tsup/vite/next config
pyproject.toml
docs/evaluation.md if relevant
```

Exclude or de-prioritize:

```txt
lockfiles
tests/fixtures/**
planning-docs unless no README exists
```

### Batch 2 — Entrypoints and user-facing flows

Include:

```txt
entrypoint candidates
direct dependencies of high-confidence entrypoints
command/router/page/server files
```

### Batch 3+ — Subsystem batches

One batch per major source cluster:

```txt
CLI
repo scanner
context builder
repo graph
doc generator
output
LLM
models
shared
```

Inside each cluster:

1. orchestrators/high fan-out files;
2. contracts/models/schemas;
3. core implementation;
4. utilities;
5. related tests only if the plan explicitly includes tests, otherwise omit.

### Batch N — Shared contracts and primitives

Include:

```txt
high fan-in files
models/schemas/types
Zod/Pydantic contract files
shared utilities
```

### Batch final — Remaining source files

Include source files not already represented, excluding tests/fixtures unless needed.

### Verifiable outcome

On Bridger, architecture reading plan should start roughly with:

```txt
README.md / AGENTS.md / package.json / tsconfig.json
src/cli/cli.ts
src/cli/commands/init.ts
src/cli/commands/inspect.ts
```

It should not start with:

```txt
tests/**
tests/fixtures/**
pnpm-lock.yaml
graph-tickets.md
```

Tests should verify:

* orientation batch contains high-value root context;
* entrypoint batch is populated;
* source clusters produce subsystem batches;
* tests/fixtures do not dominate architecture plan;
* `flatOrder` is deterministic;
* files may repeat in batches but `flatOrder` is deduped.

---

## Ticket 52 — Build testing reading plan

### Goal

Generate a deterministic test-focused reading plan for the `testing.md` agent.

### Dependencies

Depends on:

* CodebaseMap
* ReadingPlan model
* clusters
* test/fixture tags
* graph import edges

### Implementation guidelines

Create:

```txt
src/core/repo-graph/reading-plans/build-testing-reading-plan.ts
```

Batch strategy:

### Batch 1 — Test setup and conventions

Include:

```txt
package.json test scripts
vitest/jest/playwright config
test-suite.md
docs/evaluation.md if relevant
```

### Batch 2 — Representative test files

Include high-signal tests:

```txt
tests/cli/init.test.ts
tests/repo-graph.test.ts
tests/build-*.test.ts
```

Use fan-out and naming to select representative tests.

### Batch 3 — Fixtures

Include representative fixture files, but keep bounded.

### Batch 4 — Source files under test

Use test import edges:

```txt
test file imports source file => source file under test
```

### Batch 5 — Remaining test files

Include lower-priority test files if budget allows.

### Verifiable outcome

For Bridger, testing reading plan should prioritize:

```txt
test config/package scripts
tests/cli/init.test.ts
tests/repo-graph.test.ts
tests/build-import-edges.test.ts
tests/fixtures/graph-*
source files imported by those tests
```

Tests should verify:

* test files are included intentionally;
* fixtures are included in a fixture batch, not mixed into architecture orientation;
* source files under test are linked through imports;
* architecture plan and testing plan differ.

---

## Ticket 53 — Build doc-specific reading plan dispatcher

### Goal

Create a dispatcher that returns the right reading plan for each generated documentation agent.

### Dependencies

Depends on Tickets 51 and 52.

### Implementation guidelines

Create:

```txt
src/core/repo-graph/reading-plans/build-doc-reading-plan.ts
```

Supported docs:

```txt
repo-analysis.md
architecture.md
business-logic.md
conventions.md
testing.md
```

Suggested behavior:

### `repo-analysis.md`

Use:

```txt
orientation
cluster overview
top fan-in/fan-out
entrypoints
diagnostics
```

### `architecture.md`

Use:

```txt
architecture reading plan
entrypoint flows
cluster batches
shared contracts
```

### `business-logic.md`

Use:

```txt
feature/domain/service clusters
entrypoint flows
models/schemas
exclude low-level writer/output utilities unless relevant
```

### `conventions.md`

Use:

```txt
representative files by role
models/schemas
services
utilities
tests
config
```

### `testing.md`

Use:

```txt
testing reading plan
```

### Verifiable outcome

Tests should verify:

* each doc type gets a plan;
* `testing.md` receives a test-heavy plan;
* `architecture.md` receives an architecture-heavy plan;
* `business-logic.md` de-prioritizes tests and fixtures;
* all plans validate with `ReadingPlanSchema`.

---

## Ticket 54 — Extend graph summary with CodebaseMap and ReadingPlan references

### Goal

Expose codebase map and reading plan outputs in graph summary/artifacts without breaking existing fields.

### Dependencies

Depends on:

* CodebaseMap
* ReadingPlan builders
* GraphSummary

### Implementation guidelines

Do not remove existing fields:

```txt
architectureFirstOrder
dependencyFirstOrder
```

Add compatible new fields if schema evolution allows:

```ts
codebaseMap?: {
  entrypointCount: number;
  clusterCount: number;
  clusters: Array<{
    id: string;
    rootPath: string;
    title: string;
    kind: string;
    fileCount: number;
  }>;
};

readingPlans?: {
  architecture: ReadingPlanSummary;
  testing: ReadingPlanSummary;
  docs: Record<string, ReadingPlanSummary>;
};
```

Or create separate artifacts if preferred:

```txt
.bridger/codebase-map.json
.bridger/reading-plan.json
```

Recommended: separate artifacts are cleaner and avoid bloating `graph-summary.json`.

Suggested new artifacts:

```txt
.bridger/codebase-map.json
.bridger/reading-plans.json
```

### Verifiable outcome

Artifacts validate and include:

* entrypoint candidates;
* clusters;
* architecture reading plan;
* testing reading plan;
* doc-specific plan summaries;
* existing graph summary remains backward-compatible.

---

## Ticket 55 — Update artifact writers for CodebaseMap and ReadingPlans

### Goal

Write the new interpretation-layer artifacts to `.bridger/`.

### Dependencies

Depends on Ticket 54.

### Implementation guidelines

Add path helpers:

```ts
getCodebaseMapPath(repoRoot)
getReadingPlansPath(repoRoot)
```

Write:

```txt
.bridger/codebase-map.json
.bridger/reading-plans.json
```

Reuse existing stable JSON writer.

Validate artifacts before writing.

Return paths from the writer.

### Verifiable outcome

Tests should verify:

* path helpers return expected paths;
* files are written under `.bridger/`;
* JSON validates;
* existing graph artifact writer still works.

---

## Ticket 56 — Integrate doc-specific reading plans into `bridger init`

### Goal

Replace the current single graph-ordered context with doc-specific reading plans for each documentation generator.

### Dependencies

Depends on:

* doc-specific reading plan dispatcher;
* graph-ordered file reader or a new batch-aware reader;
* current init integration.

### Implementation guidelines

Current behavior likely uses one `graphOrderedFileContext` for all docs.

New behavior:

1. Build repo graph.
2. Build graph summary.
3. Build codebase map.
4. Build doc-specific reading plans.
5. For each generated doc, read files from its plan.
6. Pass that doc-specific context into the generator.

Important:

* `testing.md` should receive test/fixture-focused context.
* `architecture.md` should receive architecture/subsystem context.
* `business-logic.md` should receive feature/domain/service context.
* Do not remove generated docs.
* Do not redesign prompts unless required by context shape.
* Keep LLM config behavior unchanged.

If current generator input only accepts flat files, flatten the selected plan for that doc first.

Later we can pass batch structure directly to prompts. For this ticket, minimal integration is acceptable.

### Verifiable outcome

Tests or manual inspection should prove:

* different docs receive different file context;
* `testing.md` context includes tests/fixtures;
* `architecture.md` context starts with orientation/entrypoint/subsystem files;
* graph/codebase/reading artifacts are written before LLM calls;
* init still works with valid LLM config;
* missing LLM config still fails clearly after deterministic artifacts.

---

## Ticket 57 — Make graph-ordered file reader batch-aware

### Goal

Allow file reading from structured reading batches while preserving batch metadata and allowing repeated files across batches.

### Dependencies

Depends on ReadingPlan model and current `readGraphOrderedFiles`.

### Implementation guidelines

Create or extend reader:

```ts
readReadingPlanFiles(input: {
  repoRoot: string;
  graph: RepoGraph;
  plan: ReadingPlan;
  maxFilesPerBatch?: number;
  maxSingleFileBytes: number;
  maxTotalBytes: number;
  excludeTags?: RepoGraphNodeTag[];
}): Promise<ReadingPlanFileReadResult>
```

Output should preserve:

```txt
batch id
batch title
file path
roleInBatch
reason
content
```

Important:

* a file may be read in multiple batches;
* optionally cache file contents internally to avoid repeated disk reads;
* repeated file content should be allowed in result if batch context requires it;
* total byte limit should apply to emitted content.

### Verifiable outcome

Tests should verify:

* batch structure is preserved;
* repeated files across batches are allowed;
* file contents are read once internally if cached;
* byte limits work;
* diagnostics work;
* output is deterministic.

---

## Ticket 58 — Update doc prompt context rendering for reading batches

### Goal

Render reading batch context into LLM prompts in a way that explains why files are grouped.

### Dependencies

Depends on batch-aware reader.

### Implementation guidelines

Current prompts likely receive a flat “important files” section.

Add a new renderer such as:

```txt
renderReadingPlanContext.ts
```

Format should be compact and explicit:

```txt
## Reading batch: CLI execution flow
Purpose: Understand how users enter the CLI.

### File: src/cli/cli.ts
Role in batch: entrypoint
Reason: CLI entrypoint detected from src/cli/cli.ts.

<content>
```

Do not over-expand if budget is limited.

Keep existing prompt rules intact.

### Verifiable outcome

Tests should verify:

* batch titles are rendered;
* purposes are rendered;
* file reasons and roles are rendered;
* content is included;
* output is deterministic;
* existing generators can consume the rendered context.

---

## Ticket 59 — Update `inspect --graph` to show CodebaseMap and ReadingPlan preview

### Goal

Make graph inspection useful for the new Graph v2 outputs.

### Dependencies

Depends on CodebaseMap and ReadingPlan artifacts.

### Implementation guidelines

Extend:

```txt
bridger inspect --graph
```

Output should include:

```txt
entrypoint candidates with kind/confidence
cluster overview
top cluster dependencies
architecture reading plan batches
testing reading plan batches
first files per batch
```

Keep output concise.

Do not write artifacts.

Do not require API key.

### Verifiable outcome

Manual command:

```bash
bridger inspect --graph
```

Should show:

```txt
Entrypoints
- src/cli/cli.ts [cli, high]

Clusters
- src/core/repo-graph ...

Architecture reading plan
1. Project orientation
2. CLI execution flow
3. Repo graph subsystem
...
```

Tests should cover formatting if formatter is exported.

---

## Ticket 60 — Add fixture tests for Graph v2 reading plans

### Goal

Add deterministic fixture tests for the full Graph v2 pipeline.

### Dependencies

Depends on all previous Graph v2 tickets.

### Implementation guidelines

Use existing fixtures and add one richer fixture if needed.

Test:

* entrypoint detection per framework/style;
* role tagging;
* cluster detection;
* codebase map validation;
* architecture reading plan;
* testing reading plan;
* doc-specific plans;
* batch-aware file reading;
* artifact writing;
* stable output across repeated builds.

No LLM calls.

### Verifiable outcome

`pnpm test` should prove:

* Bridger-style CLI repos produce CLI entrypoints;
* tests/fixtures do not dominate architecture reading plan;
* tests/fixtures do appear in testing reading plan;
* clusters are stable;
* reading batches validate and are deterministic;
* all graph artifacts validate.

---

# Implementation order summary

Recommended sprint order:

```txt
45. Richer universal file role tagging
46. Entrypoint detector registry
47. External import and schema/model signals
48. Codebase cluster detection
49. CodebaseMap model and builder
50. ReadingPlan model
51. Architecture reading plan
52. Testing reading plan
53. Doc-specific reading plan dispatcher
54. Extend summary/artifacts with CodebaseMap and ReadingPlan references
55. Artifact writers for CodebaseMap and ReadingPlans
56. Integrate doc-specific reading plans into init
57. Batch-aware file reader
58. Prompt context rendering for reading batches
59. inspect --graph v2 output
60. Fixture tests for Graph v2 reading plans
```

A possible adjustment: implement Ticket 57 before Ticket 56 if we decide `init` should consume batch structure immediately rather than flattening doc-specific plans.

---

# Expected sprint outcome

At the end of this sprint, Bridger should no longer only produce a flat graph order. It should produce a deterministic senior-developer-style reading strategy.

The generated documentation agents should receive better-grounded context:

```txt
architecture.md
  gets orientation + entrypoints + subsystem batches + contracts

testing.md
  gets test setup + representative tests + fixtures + source under test

business-logic.md
  gets entrypoint flows + feature/domain/service clusters + models

conventions.md
  gets representative patterns by role
```

This should make generated docs more stable, less random, less polluted by fixtures, and closer to how a senior engineer would actually understand the codebase.
