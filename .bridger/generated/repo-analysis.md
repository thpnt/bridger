## Project overview

- **Observed:** The repository appears to be a TypeScript CLI/tooling project called `bridger` that scans a repository, builds a repo context, detects stack/commands, and generates markdown knowledge docs for AI coding agents.
- **Evidence:** `package.json` defines CLI-oriented scripts (`dev`, `build`, `typecheck`, `test`, `local`), and the core flow is visible in `src/core/context-builder/build-repo-context.ts`, `src/core/doc-generator/generators/generate-repo-analysis-doc.ts`, `src/core/doc-generator/generators/generate-agent-rules-doc.ts`, and `src/core/llm/client.ts`.
- **Observed:** The repository also contains an existing agent instruction file at `AGENTS.md`, and generation/rendering logic for `AGENTS.generated.md` and `.bridger/generated/*.md` paths is visible in `src/core/doc-generator/renderers/render-agents-md.ts` and `src/core/utils/paths.ts`.
- **Purpose:** It is not possible to confidently claim the product’s end-user business purpose from the provided evidence alone. The strongest evidence shows repository analysis/document generation, not a specific external domain.

## Detected stack

- **Language:** TypeScript
  - **Evidence:** `package.json`, `tsconfig.json`, and the `src/**/*.ts` / `src/**/*.tsx` files.
- **Framework:** Not detected with confidence
  - **Evidence:** There are React/TSX files in tests and fixtures, but no confirmed app framework from the main repo context.
- **Package manager:** pnpm
  - **Evidence:** `package.json` contains `"packageManager": "pnpm@10.33.2"` and scripts use `pnpm`.
- **Styling:** Not detected
  - **Evidence:** `AGENTS.md` mentions Tailwind CSS and shadcn/ui as preferences, but the main repo context does not confirm them.
- **Validation:** Zod
  - **Evidence:** `package.json` depends on `zod`; `src/core/llm/client.ts` and multiple model files use Zod schemas.
- **Database:** Not detected
  - **Evidence:** No confirmed database client or schema in the main repo context. A SQL file exists only in fixtures: `tests/fixtures/nextjs-basic/supabase/migrations/001_init.sql`.
- **Testing:** Vitest
  - **Evidence:** `package.json` uses `vitest`; test files under `tests/` import `vitest`.
- **Other notable runtime/library signals:**
  - `commander` for CLI command parsing (`src/cli/cli.ts`, tests in `tests/cli/bootstrap.test.ts`)
  - `openai` for text/structured generation (`src/core/llm/client.ts`)
  - `dotenv/config` for env loading (`src/core/llm/client.ts`)
  - `fs-extra`, `fast-glob`, `ignore`, `ora`, `picocolors`, `execa` in `package.json`

## File and folder evidence

- `src/core/context-builder/`
  - **Why it matters:** This appears to assemble the repository-level data used by later generation steps. `build-repo-context.ts` ties together stack detection, command detection, file indexing, and important-file selection.
- `src/core/repo-scanner/`
  - **Why it matters:** These files likely define the repo inspection model. Even without every file excerpt, names plus usage in `build-repo-context.ts` show this folder is central to repo analysis.
- `src/core/doc-generator/`
  - **Why it matters:** This is the doc-production layer. `doc-specs.ts`, `doc-filenames.ts`, generator files, and validation/rendering code show the repository’s main output artifacts and required markdown shapes.
- `src/core/llm/`
  - **Why it matters:** This is the LLM integration boundary. `client.ts` shows how text and structured outputs are produced and validated.
- `src/core/models/`
  - **Why it matters:** This folder is the strongest evidence for repository data contracts. It contains schemas/types for repo context, file index, generated paths, ticket/repo knowledge docs, and agent rules inputs.
- `src/core/output/`
  - **Why it matters:** This appears to handle filesystem persistence for generated outputs and markdown block updates.
- `src/cli/`
  - **Why it matters:** The entry points for user-facing commands are likely here. Tests confirm `init`, `inspect`, and `enrich-ticket` exist.
- `tests/`
  - **Why it matters:** The test suite is broad and gives direct evidence for expected behavior of context building, path helpers, output writing, prompt building, markdown validation, and CLI registration.
- `AGENTS.md`
  - **Why it matters:** It is an explicit agent-instructions file and may strongly influence later agent behavior, especially around scope, change size, and caution areas.
- `package.json`
  - **Why it matters:** It is the clearest source for scripts, dependency categories, and package manager.
- `tests/fixtures/`
  - **Why it matters:** Fixtures reveal supported scenarios and detection behavior, including alternate package manager/script layouts and example app structures, but should be treated as test evidence rather than main-repo architecture.

## Important files

- `package.json` — primary source for scripts, package manager, and dependency signals.
- `AGENTS.md` — repository-specific operating rules and constraints for agents.
- `src/core/context-builder/build-repo-context.ts` — shows the top-level repo analysis pipeline and what artifacts are assembled.
- `src/core/repo-scanner/detect-stack.ts` — likely defines how stack detection is inferred.
- `src/core/repo-scanner/detect-commands.ts` — likely defines command detection rules.
- `src/core/repo-scanner/build-file-index.ts` — likely defines file inventorying and tagging.
- `src/core/repo-scanner/read-important-files.ts` — likely defines which files become “important” and why.
- `src/core/doc-generator/doc-specs.ts` — defines required sections for generated knowledge docs, including `repo-analysis.md`.
- `src/core/doc-generator/generators/generate-repo-analysis-doc.ts` — shows how repo analysis markdown is produced.
- `src/core/doc-generator/generators/generate-agent-rules-doc.ts` — shows how agent instructions are derived from repo context.
- `src/core/doc-generator/renderers/render-agents-md.ts` — shows how generated docs are composed into `AGENTS.md`.
- `src/core/llm/client.ts` — evidence for OpenAI usage, error handling, and structured output validation.
- `src/core/models/repo-context.ts` — likely defines the central generated repo context schema.
- `src/core/models/generated-paths.ts` — evidence for output file locations under `.bridger/generated/` and `AGENTS.generated.md`.
- `tests/build-repo-context.test.ts` — strong behavioral evidence for repo context contents and stable output paths.
- `tests/cli/bootstrap.test.ts` — confirms CLI command names and at least one option.
- `tests/core/utils/paths.test.ts` — confirms output path conventions.
- `tests/core/output/write-files.test.ts` — confirms output directory behavior and markdown/json writing conventions.

## Observed structure

- **Observed:** The repository is organized around a `src/core/` implementation layer, a `src/cli/` command layer, and a broad `tests/` suite.
- **Evidence:** `src/core/context-builder/`, `src/core/repo-scanner/`, `src/core/doc-generator/`, `src/core/llm/`, `src/core/models/`, `src/core/output/`, and `src/shared/` are all visible in the file index summary and excerpts.
- **Observed:** The codebase appears layered around:
  - repository scanning and indexing
  - context/model construction
  - document generation
  - output writing/rendering
  - CLI entry points
- **Evidence:** `buildRepoContextArtifacts()` in `src/core/context-builder/build-repo-context.ts` combines scanner outputs and validates them into `RepoContext`; generator files then consume that context.
- **Observed:** Output paths are centralized and predictable.
  - **Evidence:** `src/core/models/generated-paths.ts` is referenced in tests, and `tests/core/utils/paths.test.ts` asserts `.bridger/repo-context.json`, `.bridger/file-index.json`, `.bridger/generated/*.md`, `AGENTS.generated.md`, and `AGENTS.md`.
- **Observed:** The repo includes fixture repositories under `tests/fixtures/` to exercise scanning and detection logic.
  - **Evidence:** The file index summary includes multiple fixture package manifests and example app files.

## Observed domains

- **Repository analysis / repo knowledge generation**
  - **Meaning:** The codebase visibly models a process for inspecting repositories and producing structured knowledge documents.
  - **Evidence:** `src/core/context-builder/build-repo-context.ts`, `src/core/doc-generator/doc-specs.ts`, `src/core/doc-generator/generators/generate-repo-analysis-doc.ts`, `src/core/doc-generator/renderers/render-agents-md.ts`.
  - **Confidence:** High
- **Command/CLI orchestration**
  - **Meaning:** There is a user-facing command layer for invoking repo inspection and generation tasks.
  - **Evidence:** `src/cli/cli.ts`, `src/cli/commands/init.ts`, `src/cli/commands/inspect.ts`, `src/cli/commands/enrich-ticket.ts`, `tests/cli/bootstrap.test.ts`, `tests/cli/inspect.test.ts`.
  - **Confidence:** High
- **Repo metadata and file indexing**
  - **Meaning:** The project tracks files, tags, and “important” files as part of its knowledge pipeline.
  - **Evidence:** `src/core/repo-scanner/build-file-index.ts`, `src/core/repo-scanner/read-important-files.ts`, `src/core/context-builder/file-index-summary.ts`, `tests/build-repo-context.test.ts`.
  - **Confidence:** High
- **LLM-assisted document generation**
  - **Meaning:** Some generated docs are produced by calling OpenAI and validated against required markdown sections.
  - **Evidence:** `src/core/llm/client.ts`, `src/core/doc-generator/generators/generate-knowledge-doc.ts`, `src/core/doc-generator/validation/markdown-section-validation.ts`.
  - **Confidence:** High
- **Ticket-related output**
  - **Meaning:** There is at least one ticket-oriented model and path convention.
  - **Evidence:** `src/core/models/ticket.ts`, `src/core/models/generated-paths.ts`, `src/cli/commands/enrich-ticket.ts`, `src/core/context-builder/build-repo-context.ts` (ticket template path).
  - **Confidence:** Medium
- **App/business domain:** Unknown
  - **Meaning:** No concrete product domain beyond repo-analysis/generation is evidenced.
  - **Evidence:** The main code excerpts do not expose a business domain model beyond tooling itself.
  - **Confidence:** High that the domain is not visible from current evidence.

## Assumptions

- **Assumption:** The main product value is repository analysis and document generation for AI coding agents.
  - **Evidence:** `src/core/doc-generator/doc-specs.ts` names `repo-analysis`, `architecture`, `business-logic`, `conventions`, `testing`, and `agent-rules`; `src/core/doc-generator/renderers/render-agents-md.ts` combines these into `AGENTS.md`.
- **Assumption:** Generated outputs are intended to live under `.bridger/` and in `AGENTS.generated.md`.
  - **Evidence:** `tests/core/utils/paths.test.ts` and `tests/core/models/generated-paths.test.ts`.
- **Assumption:** The repo treats repo context as a validated schema object rather than an ad hoc JSON blob.
  - **Evidence:** `RepoContextSchema.parse(...)` in `src/core/context-builder/build-repo-context.ts` and schema assertions in `tests/build-repo-context.test.ts`.
- **Assumption:** The CLI is meant to run directly from TypeScript in development and from built output in a packaged/local mode.
  - **Evidence:** `package.json` scripts `dev`, `build`, and `local`.
- **Assumption:** `inspect` is a lightweight, non-LLM repo scan command.
  - **Evidence:** `tests/cli/inspect.test.ts` shows it calls stack detection, command detection, and file indexing, and explicitly “without requiring the LLM.”

## Unknowns

- **Unknown:** The external product or end-user domain the repo is meant to support beyond internal repository analysis tooling.
- **Unknown:** Whether there is a frontend application, web app framework, or server runtime in the main repo; no strong evidence is present in the provided context.
- **Unknown:** The persistence model for generated JSON/markdown beyond path conventions; the code shows output writing, but not a full storage or sync strategy.
- **Unknown:** The full behavior of `src/core/repo-scanner/detect-stack.ts` and `src/core/repo-scanner/detect-commands.ts`; the excerpt shows usage, not the detection rules.
- **Unknown:** The exact shape and semantics of `RepoContext`, `FileIndex`, `ImportantFile`, and other models beyond their role in the pipeline.
- **Unknown:** Whether there are additional domains or business workflows hidden outside the provided excerpts and tests.
- **Unknown:** The depth of test coverage for command execution, LLM failure modes, and generated document content beyond section validation and representative behavior.
- **Unknown:** Auth, user management, database access, external integrations, and deployment concerns are not evidenced in the main repo context.
- **Unknown:** Whether `AGENTS.md` is generated, manually maintained, or intended to be merged with generated content in all cases.
- **Unknown:** Whether `src/cli/commands/init.ts` and `src/cli/commands/enrich-ticket.ts` modify files, call the LLM, or orchestrate workflows beyond their names; their behavior is not shown in the excerpts.
