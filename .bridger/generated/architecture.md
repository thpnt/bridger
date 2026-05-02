## Project overview

Observed: This repository appears to be a TypeScript CLI/tooling project named `bridger` that scans a repository, builds a repo context, and generates repository knowledge docs such as `architecture.md`, `business-logic.md`, `testing.md`, and `AGENTS.md`.
Evidence: `package.json`, `src/cli/cli.ts`, `src/core/context-builder/build-repo-context.ts`, `src/core/doc-generator/doc-filenames.ts`, `src/core/doc-generator/generators/generate-architecture-doc.ts`, `src/core/doc-generator/renderers/render-agents-md.ts`.
Confidence: High.

## Detected stack

- Language: TypeScript
  - Evidence: `package.json`, `tsconfig.json`, `src/**/*.ts`, `tests/**/*.ts`
- Package manager: pnpm
  - Evidence: `package.json` (`packageManager: "pnpm@10.33.2"`), `pnpm-lock.yaml`
- Framework: Not detected
  - Evidence: no app framework config was clearly evidenced in repo root context
- Styling: Not detected
  - Evidence: no styling system was clearly evidenced in root code; shadcn/Tailwind appear only in fixture contexts, not as confirmed app stack
- Validation: Zod
  - Evidence: `package.json`, `src/core/llm/client.ts`, `src/core/models/*.ts` (schemas are referenced throughout)
- Database: Not detected
  - Evidence: only a fixture SQL file exists at `tests/fixtures/nextjs-basic/supabase/migrations/001_init.sql`
- Testing: Vitest
  - Evidence: `package.json`, `tests/**/*.test.ts`
- Other notable runtime/tooling:
  - `openai` in `package.json` and `src/core/llm/client.ts`
  - `commander` in `package.json` and `src/cli/cli.ts`
  - `tsx` for running TS scripts in `package.json`
  - `tsup` for build output in `package.json`

## App structure

Observed:
- `src/` is the application source tree and holds the main runtime code.
  - `src/cli/` contains the command-line entry point and command handlers.
  - `src/core/` contains the core pipeline: repo scanning, context building, doc generation, output writing, and LLM access.
  - `src/shared/` contains cross-cutting helpers such as logging and errors.
- `tests/` contains Vitest coverage for CLI, context building, doc generation, file-index summaries, output helpers, utilities, and repo scanner behavior.
- `scripts/` contains at least one utility script: `scripts/test-llm.ts`.
- Root config and metadata include `package.json`, `tsconfig.json`, `tsup.config.ts`, `pnpm-lock.yaml`, and `AGENTS.md`.
- Generated or output-related paths are modeled in code rather than stored in a visible output folder in the repo context.
  - Evidence: `src/core/models/generated-paths.ts`, `tests/core/utils/paths.test.ts`
- Fixture repositories under `tests/fixtures/` are used to exercise stack/command detection and repo-context behavior.
  - Evidence: `tests/fixtures/repo-context-basic/`, `tests/fixtures/nextjs-basic/`, `tests/fixtures/commands-*`

Why this matters:
- `src/cli/` is the entry point for user-facing behavior.
- `src/core/` is where most architectural changes will land.
- `tests/` is the main evidence base for expected behavior and edge cases.
- Root config affects build/test/runtime assumptions.

## Core domains

Observed:
- Repository analysis / repo-context building
  - Evidence: `src/core/context-builder/build-repo-context.ts`, `src/core/models/repo-context.ts`, `src/core/repo-scanner/*`
- File indexing and repository summarization
  - Evidence: `src/core/repo-scanner/build-file-index.ts`, `src/core/context-builder/file-index-summary.ts`, `src/core/models/file-index.ts`
- Knowledge document generation
  - Evidence: `src/core/doc-generator/*`
- CLI orchestration for inspection, init, and ticket enrichment
  - Evidence: `src/cli/commands/init.ts`, `src/cli/commands/inspect.ts`, `src/cli/commands/enrich-ticket.ts`, `tests/cli/bootstrap.test.ts`
- LLM-backed text/JSON generation
  - Evidence: `src/core/llm/client.ts`, `src/core/llm/prompts/docs/*`
- Generated markdown outputs and AGENTS rendering
  - Evidence: `src/core/doc-generator/renderers/render-agents-md.ts`, `src/core/output/*`

Unknown: No product/business domain beyond repository-analysis tooling is directly evidenced.

## Important folders

- `src/cli/` — CLI entry point and command wiring; useful for understanding user-facing flows.
- `src/core/context-builder/` — builds the central `RepoContext`; likely the main orchestration layer.
- `src/core/repo-scanner/` — detects stack, commands, and important files; central to repo analysis.
- `src/core/doc-generator/` — generation pipeline for markdown knowledge docs and validation.
- `src/core/llm/` — OpenAI client and prompt builders; high-impact for all generated docs.
- `src/core/models/` — Zod schemas and shared types; important for contracts and validation.
- `src/core/output/` — filesystem write helpers and generated block management.
- `src/shared/` — shared logger/errors used across CLI and core code.
- `tests/fixtures/` — concrete sample repositories and package manifests used to verify detection logic.
- `tests/` — behavioral tests; good source of expected command and context behavior.
- `scripts/` — auxiliary scripts, including `scripts/test-llm.ts`.

## Data flow assumptions

Observed:
- `buildRepoContextArtifacts()` in `src/core/context-builder/build-repo-context.ts` orchestrates the initial repository analysis:
  1. `detectStack(repoRoot)`
  2. `detectCommands(repoRoot, stack.packageManager)`
  3. `buildFileIndex(repoRoot)`
  4. `readImportantFiles({ repoRoot, fileIndex })`
  5. validate/assemble a `RepoContext` with generated doc paths
- `buildKnowledgeDocGenerationInput()` in `src/core/doc-generator/knowledge-doc-input.ts` converts repo context plus file index into prompt-ready input, including a summarized file index.
- `generateKnowledgeDoc()` in `src/core/doc-generator/generators/generate-knowledge-doc.ts` sends a system/prompt pair to the LLM client, trims the result, checks it is non-empty, and validates required markdown sections.
- `renderAgentsMd()` in `src/core/doc-generator/renderers/render-agents-md.ts` combines `AGENTS.md` source doc links with generated agent rules markdown.
- `src/core/output/*` and `src/core/utils/paths.ts` imply writing repo-local artifacts under `.bridger/` and `AGENTS.generated.md`, but the write sequence is not fully visible from the provided excerpts.

Assumption: The overall flow is analysis → prompt preparation → LLM generation → markdown validation → filesystem output.
Evidence: `src/core/context-builder/build-repo-context.ts`, `src/core/doc-generator/generators/*`, `src/core/llm/client.ts`, `src/core/output/*`.
Confidence: Medium, because the final command handlers that stitch all of these together were not fully shown.

## Commands

Detected commands from `package.json`:

- `pnpm install` — install dependencies.
- `pnpm dev` — run the CLI in development mode via `tsx src/cli/cli.ts`.
- `pnpm build` — build the package with `tsup`.
- `pnpm typecheck` — run TypeScript type checking with `tsc --noEmit`.
- `pnpm test` — run the Vitest suite.
- `pnpm check` — run typecheck and tests together.
- `pnpm local` — build, then run `node dist/cli.js`.
- `pnpm test:llm` — run `tsx scripts/test-llm.ts` for LLM-related testing.

When to use:
- `pnpm dev` for iterating on CLI behavior.
- `pnpm build` when checking bundled output.
- `pnpm typecheck` before/after type-sensitive edits.
- `pnpm test` for verification across repo behavior.
- `pnpm check` for a combined local gate.
- `pnpm local` to exercise the built CLI.
- `pnpm test:llm` for the dedicated LLM script path.

Not detected:
- Separate lint or format commands were not evidenced in `package.json`.

## Risky areas

- `src/core/llm/client.ts`
  - Risk: central external dependency on OpenAI; failures here affect all generated docs.
  - Also enforces env var presence (`OPENAI_API_KEY`) and structured output parsing.
- `src/core/doc-generator/generators/generate-knowledge-doc.ts`
  - Risk: enforces non-empty output and markdown section validation; changes can break all doc generation.
- `src/core/doc-generator/validation/markdown-section-validation.ts`
  - Risk: required-section checks are strict and can fail on formatting changes.
- `src/core/context-builder/build-repo-context.ts`
  - Risk: orchestrates the core analysis pipeline and validates the final context shape.
- `src/core/repo-scanner/*`
  - Risk: detection logic here drives stack/commands/file-index results; subtle changes can cascade into generated docs.
- `src/core/models/*`
  - Risk: schemas are the contract boundary for all downstream generation and output.
- `src/core/output/*`
  - Risk: writes files and mutates generated markdown blocks; errors here affect repo output artifacts.
- `AGENTS.md`
  - Risk: existing agent instructions are treated as important repo guidance and should not be modified casually.
- `tests/fixtures/*`
  - Risk: detection behavior appears anchored by fixture repos; changing fixtures can change expected outputs and test intent.

## Unknowns

- Unknown: The actual end-user purpose beyond repository analysis and doc generation is not fully evidenced. The code suggests CLI tooling, but the main workflow beyond `inspect`, `init`, and `enrich-ticket` is not fully shown.
- Unknown: Whether a web app exists is not evidenced; the repo context shows CLI/core tooling rather than a confirmed frontend app.
- Unknown: Styling stack is not confirmed for this repo root. `shadcn`/`Tailwind` appear in fixture paths, but not as confirmed application dependencies or runtime code in the provided context.
- Unknown: Database usage is not confirmed in the main repo. A SQL migration exists only in fixture data.
- Unknown: Exact file output flow and all generated artifact paths are only partially evidenced. `.bridger/` and `AGENTS.generated.md` are inferred from path helpers and tests, but the command handlers that write them were not shown.
- Unknown: Lint/format commands were not detected in the provided `package.json`.
- Unknown: Full domain boundaries inside `src/core/repo-scanner/*` and `src/core/doc-generator/*` are not fully visible; agents should not assume a one-to-one mapping between file names and responsibilities beyond the shown excerpts.
- Unknown: Whether `enrich-ticket` writes tickets, modifies generated docs, or both is not directly evidenced by the provided excerpts.
- Unknown: Any external services beyond OpenAI are not clearly evidenced.
