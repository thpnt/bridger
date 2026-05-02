## Testing philosophy

**Observed:** Testing in this repo is mostly about verifying small, deterministic pieces of repository analysis, document generation, path handling, and CLI wiring.

**Evidence:** The visible tests in `tests/` focus on:
- pure helpers and model validation: `tests/core/utils/paths.test.ts`, `tests/core/utils/slug.test.ts`, `tests/core/models/generated-paths.test.ts`
- repo-scanning and context-building flows: `tests/repo-scanner.test.ts`, `tests/build-repo-context.test.ts`
- document generation and markdown validation: `tests/doc-generators.test.ts`, `tests/generated-doc-validation.test.ts`, `tests/render-agents-md.test.ts`
- CLI behavior and command registration: `tests/cli/bootstrap.test.ts`, `tests/cli/inspect.test.ts`
- OpenAI client behavior with mocked boundaries: `tests/llm-client.test.ts`, `tests/llm-client-mocked.test.ts`

**Inference:** The apparent philosophy is “test the repo-specific logic and boundaries, not just the happy path.” The codebase leans on schema validation (`zod`) and deterministic outputs, so tests should prefer exact assertions on generated paths, validated objects, and error cases.

**Recommendation:** For new work, verify the changed logic at the smallest reliable boundary first, then add broader coverage only if the change crosses file/module boundaries or affects CLI/output behavior.

## Test types and when to use them

- **Unit tests**
  - Use for pure functions, path helpers, formatting helpers, validators, and model/schema logic.
  - Good fit for code like `src/core/utils/*`, `src/core/models/*`, `src/core/context-builder/file-index-summary.ts`, and `src/core/doc-generator/validation/markdown-section-validation.ts`.

- **Integration tests**
  - Use when the change spans multiple internal modules or a workflow with real filesystem interaction.
  - Good fit for repo scanning, context building, output writing, CLI flows, and generation pipelines like `src/core/context-builder/build-repo-context.ts`, `src/core/output/*`, `src/cli/*`, and `src/core/doc-generator/generators/*`.

- **Regression tests**
  - Add when fixing a bug in file discovery, command detection, generated doc validation, markdown rendering, or any behavior that could silently drift.
  - This repo already shows regression-style coverage through targeted behavior tests in `tests/build-repo-context.test.ts`, `tests/generated-doc-validation.test.ts`, and `tests/core/output/write-files.test.ts`.

- **Component/UI tests**
  - **Unknown as an observed convention.** The repo has `react` files in fixtures such as `tests/fixtures/file-index-basic/src/app/page.tsx` and `tests/fixtures/repo-context-basic/src/app/page.tsx`, but no visible component/UI test suite or UI test framework evidence in the provided files.
  - Recommendation: add UI tests only if the repository change actually affects rendered UI, and only if there is an existing test pattern to follow in the repo.

- **Manual QA checks**
  - Use when changing CLI behavior, output generation, or repository scanning paths that are hard to fully prove with mocks alone.
  - Especially relevant for commands exposed in `package.json` such as `pnpm dev`, `pnpm build`, `pnpm typecheck`, `pnpm test`, and `pnpm local`.

## Unit testing conventions

**Observed:** Unit tests in this repo are small, explicit, and usually assert exact outputs or exact error behavior.

**Evidence:**
- `tests/core/utils/paths.test.ts` checks resolved paths and generated paths exactly.
- `tests/core/models/generated-paths.test.ts` checks stable doc path generation.
- `tests/core/output/write-files.test.ts` checks newline handling, pretty JSON formatting, and generated block replacement behavior.
- `tests/markdown-section-validation.test.ts` and `tests/prompt-formatting.test.ts` indicate a focus on string/validation helpers.

**When to add unit tests:**
- For any pure helper in `src/core/utils/`, `src/core/models/`, or `src/core/doc-generator/validation/`.
- For deterministic formatting functions in prompt builders and markdown renderers.
- For schema parsing or normalization logic that should fail fast on invalid input.

**Recommendation:** Prefer unit tests for logic that can be exercised without filesystem setup, mocked network calls, or command execution. Keep assertions precise: exact strings, exact paths, exact object shapes, and exact thrown errors.

**Unknown:** No explicit repo-wide unit test naming convention beyond `*.test.ts` is visible, and no separate `unit/` folder is shown.

## Integration testing conventions

**Observed:** The repo tests multi-step flows by combining real filesystem fixtures with mocked boundaries.

**Evidence:**
- `tests/build-repo-context.test.ts` uses a fixture repo at `tests/fixtures/repo-context-basic` and validates the assembled context/artifacts.
- `tests/repo-scanner.test.ts` suggests integration coverage for scanning and file indexing.
- `tests/cli/inspect.test.ts` mocks scanner pieces and verifies the CLI command wiring and exit behavior.
- `tests/core/output/write-files.test.ts` verifies actual file creation/update behavior on disk.

**When to add integration tests:**
- If a change affects more than one internal module, especially across scanning → context building → doc generation → file output.
- If the change touches `src/cli/cli.ts` or command modules under `src/cli/commands/`.
- If filesystem behavior changes: ignored files, fixture discovery, output directories, generated markdown blocks, or JSON output.
- If command detection or stack detection logic changes in `src/core/repo-scanner/*`.

**Recommendation:** Use fixture repositories under `tests/fixtures/` when a change depends on real repo shape. This repo already uses fixtures for package-manager detection and repo-context building, so matching that style is the safest verification path.

**Unknown:** No evidence of networked integration tests, database integration tests, or real OpenAI end-to-end tests in the provided material.

## Regression testing conventions

**Observed:** Regression coverage is already used for risky deterministic behavior, especially where output stability matters.

**Evidence:**
- `tests/generated-doc-validation.test.ts` and `src/core/doc-generator/validation/markdown-section-validation.ts` imply enforcement of required Markdown sections.
- `tests/render-agents-md.test.ts` implies guardrails around generated `AGENTS.md` composition.
- `tests/core/output/write-files.test.ts` protects block replacement and file formatting behavior.
- `tests/build-repo-context.test.ts` protects generated repo context shape and fallback behavior for minimal repos.

**When to add regression tests:**
- For bug fixes in file indexing, command detection, path generation, output formatting, markdown section validation, or CLI error handling.
- For any change that could silently alter generated docs, paths under `.bridger/`, or the contents of `AGENTS.md` / `AGENTS.generated.md`.
- For validation changes in `zod`-based models or prompt inputs.

**Recommendation:** If a ticket mentions “fix”, “handle missing”, “avoid regression”, or “incorrect output”, add a test that reproduces the broken case first, then make it pass.

## Component and UI testing conventions

**Observed:** UI code exists in the fixture set and the source tree contains React/TSX files, but no visible component/UI test convention is evidenced in the provided repo context.

**Evidence:** 
- `tests/fixtures/file-index-basic/src/app/page.tsx`
- `tests/fixtures/repo-context-basic/src/app/page.tsx`
- `tests/fixtures/repo-context-basic/src/components/ui/button.tsx`
- `src/app/page.tsx`-style files are not listed in the actual source tree, so the visible UI evidence is mostly in fixtures.

**Unknown:** No UI test folder, component test files, or framework-specific UI runner is visible in the provided context.

**Recommendation:** If you change UI-facing code and there is no existing UI test pattern to follow, verify behavior manually and keep logic covered by unit/integration tests where possible.

## Manual QA expectations

**Observed:** This repo exposes CLI-oriented commands and generated-file workflows, so manual QA should focus on command output and file generation.

**Practical checks:**
- Run `pnpm typecheck` after changes touching types, models, or prompt/data-shape code.
- Run `pnpm test` after changes to scanners, generators, output writers, or CLI wiring.
- Use `pnpm build` before relying on `pnpm local`-style packaged execution.
- If relevant to your change, run `pnpm dev` to inspect the CLI behavior interactively.
- For CLI changes, confirm the command still registers correctly and prints expected summaries, similar to what `tests/cli/bootstrap.test.ts` and `tests/cli/inspect.test.ts` cover.
- For output changes, inspect generated `.bridger/` files and `AGENTS.generated.md` / `AGENTS.md` formatting directly.

**Recommendation:** Manual QA should validate the repo-specific files and outputs that are easiest to inspect by eye: `.bridger/generated/*.md`, `.bridger/repo-context.json`, `.bridger/file-index.json`, and `AGENTS.md`.

## Existing test evidence

**Detected framework:** Vitest.

**Evidence:**
- `package.json` contains `"test": "vitest"` and `"check": "pnpm typecheck && pnpm test"`.
- Test files are present under `tests/` and use `vitest` APIs such as `describe`, `expect`, `it`, `beforeEach`, `afterEach`, and `vi`.

**Detected test files/folders:**
- `tests/build-repo-context.test.ts`
- `tests/cli/bootstrap.test.ts`
- `tests/cli/inspect.test.ts`
- `tests/core/output/write-files.test.ts`
- `tests/core/utils/paths.test.ts`
- `tests/core/models/generated-paths.test.ts`
- plus additional visible test files in `tests/` such as `tests/doc-generators.test.ts`, `tests/generated-doc-validation.test.ts`, `tests/important-files.test.ts`, `tests/llm-client.test.ts`, `tests/llm-client-mocked.test.ts`, `tests/markdown-section-validation.test.ts`, `tests/models.test.ts`, `tests/prompt-builders.test.ts`, `tests/prompt-formatting.test.ts`, `tests/render-agents-md.test.ts`, and `tests/repo-scanner.test.ts`

**Commands available from repo context:**
- `pnpm install`
- `pnpm dev`
- `pnpm build`
- `pnpm typecheck`
- `pnpm test`
- Also present in `package.json`: `pnpm test:llm`, `pnpm check`, `pnpm local`

**What this evidence does and does not prove:**
- It proves there is an established Vitest-based test suite with coverage across core logic, CLI, and output helpers.
- It does **not** prove UI testing, end-to-end testing, CI behavior, or coverage thresholds.

## Testing gaps and unknowns

- **Unknown:** No visible UI/component test framework or test folder convention for React/TSX rendering.
- **Unknown:** No evidence of database integration tests, even though the detected stack mentions a database category as `unknown`.
- **Unknown:** No evidence of end-to-end tests for CLI commands against a real repository.
- **Unknown:** No evidence of OpenAI live-network tests; `tests/llm-client-mocked.test.ts` suggests mocked boundary tests are more likely.
- **Unknown:** Fixture strategy is visible, but the repo does not show whether there are shared factories, snapshots, or golden files.
- **Unknown:** No CI/test matrix information is provided, so agents should not assume which commands are enforced automatically.
- **Unknown:** No explicit lint command is present in `package.json`, so do not assume `pnpm lint` exists.
- **Unknown:** Coverage expectations are not visible.

## Things agents should avoid

- **Avoid inventing test commands.** Only use commands actually shown in repo context or `package.json`; for example, `pnpm lint` is not listed and should not be assumed.
- **Avoid assuming UI testing exists.** There is React/TSX evidence in fixtures, but no visible UI test suite to follow.
- **Avoid writing broad tests that assert on unrelated implementation details.** Existing tests focus on stable outputs and boundaries, not internals.
- **Avoid skipping regression tests for risky output changes.** Files like `src/core/doc-generator/generators/generate-knowledge-doc.ts` and `src/core/doc-generator/renderers/render-agents-md.ts` affect generated docs and should be protected when changed.
- **Avoid claiming networked or end-to-end LLM coverage.** The visible evidence only proves mocked/isolated client tests, not live API verification.
- **Avoid relying on package scripts alone as proof of conventions.** The presence of `vitest` in `package.json` is corroborated by real tests in `tests/`, but other frameworks or test types are not evidenced.
