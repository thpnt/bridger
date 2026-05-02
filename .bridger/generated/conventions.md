## TypeScript conventions

- Observed: Types are commonly defined with `type` aliases for unions and simple object shapes, while `interface` is used for named contracts in a few core helper types.
  - Evidence: `src/core/doc-generator/doc-types.ts` uses `type KnowledgeDocKey` and `type KnowledgeDocSpec`; `src/core/doc-generator/knowledge-doc-input.ts` uses `interface KnowledgeDocGenerationInput`; `src/core/doc-generator/knowledge-doc-prompt.ts` uses `interface KnowledgeDocPrompt`.
- Observed: Validation schemas are parsed at runtime at boundaries, and the parsed value is then passed onward.
  - Evidence: `src/core/context-builder/build-repo-context.ts` parses `RepoContextSchema` and `RepoContextBuildArtifactsSchema`; `src/core/doc-generator/generators/generate-agent-rules-doc.ts` and related generators parse input schemas before continuing; `src/core/llm/client.ts` parses structured output with Zod.
- Observed: Functions tend to return explicit `Promise<...>` or concrete string/object outputs, not implicit `any`.
  - Evidence: `buildRepoContextArtifacts`, `buildRepoContext`, `generateText`, `generateJson`, and doc generator functions all declare explicit return types in `src/core/...`.
- Observed: Error handling is explicit and string-message based, with `Error` thrown for missing config, empty responses, or validation failures.
  - Evidence: `src/core/llm/client.ts`, `src/core/doc-generator/generators/generate-knowledge-doc.ts`, `src/core/doc-generator/validation/markdown-section-validation.ts`.
- Unknown: The repo-wide stance on `interface` vs `type`, strictness flags, `unknown` handling, and whether assertion functions are preferred beyond the visible validation helpers.

## Component conventions

- Observed: Component evidence is limited, but React components appear to live under feature-oriented folders rather than a single global UI directory.
  - Evidence: `tests/fixtures/file-index-basic/components/Button.tsx`, `tests/fixtures/repo-context-basic/src/components/ui/button.tsx`, `tests/fixtures/file-index-basic/src/app/page.tsx`, `tests/fixtures/repo-context-basic/src/app/page.tsx`.
- Observed: The only concrete UI primitive evidence is a shadcn-style button path under `src/components/ui/button.tsx` in a fixture.
  - Evidence: `tests/fixtures/repo-context-basic/src/components/ui/button.tsx`, plus `tests/fixtures/nextjs-basic/components.json`.
- Observed: Naming suggests PascalCase for component files like `Button.tsx`.
  - Evidence: `tests/fixtures/file-index-basic/components/Button.tsx`.
- Unknown: Actual component composition patterns, prop conventions, client component usage, and whether there is a shared component library in the real repo are not visible in the provided source evidence.

## Server/client boundary conventions

- Observed: The repo has a clear server-side/core layer under `src/core/` and a CLI layer under `src/cli/`.
  - Evidence: `src/core/context-builder/build-repo-context.ts`, `src/core/llm/client.ts`, `src/core/output/write-markdown.ts`, `src/cli/cli.ts`, `src/cli/commands/*.ts`.
- Observed: The code shown does not include `use client`, route handlers, or Next.js server actions in the main repo source.
  - Evidence: File index summary and visible source files under `src/` do not show app router/server-action files.
- Observed: Shared utilities and models are separated from command logic.
  - Evidence: `src/shared/errors.ts`, `src/shared/logger.ts`, `src/core/models/*`, `src/core/utils/*`.
- Unknown: The actual server/client boundary rules for the product app are unclear because the provided repo source appears to be a CLI/tooling repo, while UI-like files only appear in fixtures.

## Validation conventions

- Observed: Zod is used for runtime validation at API-like and model boundaries.
  - Evidence: `src/core/context-builder/build-repo-context.ts`, `src/core/doc-generator/generators/*.ts`, `src/core/llm/client.ts`, and the stack summary noting `Validation: Zod`; also fixture model evidence in `tests/fixtures/repo-context-basic/src/domains/billing/schema.ts`.
- Observed: Validation failures are converted into explicit thrown errors with descriptive messages.
  - Evidence: `src/core/llm/client.ts` catches `z.ZodError` and rethrows; `src/core/doc-generator/validation/markdown-section-validation.ts` throws when required sections are missing.
- Observed: Markdown outputs are validated against required sections after generation.
  - Evidence: `src/core/doc-generator/generators/generate-knowledge-doc.ts`, `src/core/doc-generator/doc-specs.ts`, `src/core/doc-generator/validation/markdown-section-validation.ts`.
- Unknown: No broader form/input validation patterns are visible beyond Zod schemas and markdown-section checks.

## Styling conventions

- Observed: Styling evidence is weak and comes mostly from fixture repositories, not the main codebase.
  - Evidence: `tests/fixtures/nextjs-basic/tailwind.config.ts`, `tests/fixtures/nextjs-basic/components.json`, `tests/fixtures/repo-context-basic/src/components/ui/button.tsx`.
- Observed: shadcn/ui is indicated by the detected stack and fixture config.
  - Evidence: repo context summary and `tests/fixtures/nextjs-basic/components.json`.
- Unknown: The real repo’s styling system, class composition helpers, theme tokens, or CSS module usage are not visible in the provided source.

## Data access conventions

- Observed: There is no clearly visible database access layer in the main source tree.
  - Evidence: `src/core/*` contains repo-scanning, doc-generation, output, and LLM logic; no `db/`, `prisma/`, `drizzle/`, or `supabase` source folder is shown in the main repo files.
- Observed: The repo does read and write local filesystem artifacts as part of its core workflow.
  - Evidence: `src/core/output/write-json.ts`, `src/core/output/write-markdown.ts`, `src/core/output/upsert-generated-markdown-block.ts`, `tests/core/output/write-files.test.ts`, `src/core/utils/paths.ts`.
- Recommendation: Before changing data-related behavior, inspect `src/core/models/*`, `src/core/output/*`, and the repo-scanner/core builder flow rather than adding a new persistence abstraction.
- Unknown: If the product includes a database or remote data layer outside the visible files, it is not evidenced here.

## Testing conventions

- Observed: Tests use Vitest.
  - Evidence: `package.json` scripts and `tests/*.test.ts`.
- Observed: Test files live under `tests/` and mirror the source area they exercise.
  - Evidence: `tests/core/models/generated-paths.test.ts`, `tests/core/output/write-files.test.ts`, `tests/cli/inspect.test.ts`, `tests/build-repo-context.test.ts`.
- Observed: Tests favor behavior-focused assertions and explicit fixture setup over snapshot-heavy patterns.
  - Evidence: `tests/build-repo-context.test.ts`, `tests/core/output/write-files.test.ts`, `tests/cli/inspect.test.ts`.
- Observed: Mocking is done with `vi.mock` for isolated unit tests.
  - Evidence: `tests/cli/inspect.test.ts`, `tests/llm-client-mocked.test.ts` (file index evidence), `tests/prompt-builders.test.ts` (file index evidence).
- Unknown: The split between unit, integration, and any manual QA expectations is not fully visible from the provided excerpts alone.

## Naming conventions

- Observed: Core model and spec files use `kebab-case` filenames with descriptive nouns, while component files in fixtures use `PascalCase`.
  - Evidence: `src/core/models/repo-context.ts`, `src/core/models/generated-paths.ts`, `src/core/doc-generator/doc-specs.ts`, `tests/fixtures/file-index-basic/components/Button.tsx`.
- Observed: Generator functions and prompt builders are named with imperative verbs and clear domain nouns.
  - Evidence: `generateRepoAnalysisDoc`, `generateConventionsDoc`, `buildArchitecturePrompt`, `buildAgentRulesPrompt` in `src/core/doc-generator/generators/*` and `src/core/llm/prompts/docs/*`.
- Observed: Model/schema names are paired with domain nouns and `Schema` suffixes.
  - Evidence: `RepoContextSchema`, `RepoContextBuildArtifactsSchema`, `GenerateRepoKnowledgeDocInputSchema`, `GenerateAgentRulesDocInputSchema`.
- Observed: Test files end in `.test.ts` and are named after the unit under test.
  - Evidence: `tests/core/utils/paths.test.ts`, `tests/doc-generators.test.ts`, `tests/cli/bootstrap.test.ts`.
- Unknown: Naming conventions for hooks, React props, CSS classes, or database entities are not visible in the evidence provided.

## Observed conventions

- Observed: Core flows validate inputs before proceeding.
  - Evidence: `src/core/context-builder/build-repo-context.ts`, `src/core/doc-generator/generators/generate-conventions-doc.ts`, `src/core/llm/client.ts`.
- Observed: Generated markdown documents are validated against required section lists.
  - Evidence: `src/core/doc-generator/doc-specs.ts`, `src/core/doc-generator/validation/markdown-section-validation.ts`, `src/core/doc-generator/generators/generate-knowledge-doc.ts`.
- Observed: File and path helpers are centralized in `src/core/utils/paths.ts` and `src/core/models/generated-paths.ts`.
  - Evidence: `tests/core/utils/paths.test.ts`, `tests/core/models/generated-paths.test.ts`.
- Observed: The repo favors explicit error messages over silent fallback behavior.
  - Evidence: `src/core/llm/client.ts`, `src/core/doc-generator/renderers/render-agents-md.ts`, `src/core/output/upsert-generated-markdown-block.ts` (from test coverage in `tests/core/output/write-files.test.ts`).
- Observed: Tests directly target CLI orchestration, output helpers, and model validation.
  - Evidence: `tests/cli/bootstrap.test.ts`, `tests/cli/inspect.test.ts`, `tests/core/output/write-files.test.ts`, `tests/build-repo-context.test.ts`.

## Recommended conventions

- Recommendation: When changing core generation flows, keep schema parsing at the boundary and pass parsed values inward, matching `src/core/context-builder/build-repo-context.ts` and `src/core/doc-generator/generators/*.ts`.
- Recommendation: When adding new generated docs, follow the existing pattern in `src/core/doc-generator/doc-specs.ts`, `src/core/doc-generator/generators/*`, and `src/core/doc-generator/validation/markdown-section-validation.ts` rather than inventing a new validation path.
- Recommendation: Prefer explicit, descriptive error messages that include the affected artifact or schema name, as seen in `src/core/llm/client.ts` and `src/core/doc-generator/generators/generate-knowledge-doc.ts`.
- Recommendation: Put file/path logic behind helpers in `src/core/utils/paths.ts` or model helpers rather than inlining path strings across commands and tests.
- Recommendation: Keep tests near the behavior they verify and prefer small focused Vitest cases with mocks for external dependencies, as in `tests/cli/inspect.test.ts`.
- Recommendation: If component work is needed in the real app, inspect actual source folders first; the only concrete component evidence here is from fixtures, so component guidance should be treated cautiously.

## Things agents should avoid

- Avoid: Adding a new validation or schema style when Zod parsing already exists at the boundary.
  - Evidence: `src/core/context-builder/build-repo-context.ts`, `src/core/llm/client.ts`, `src/core/doc-generator/generators/*.ts`.
- Avoid: Changing generated output formats casually without updating the section validation spec.
  - Evidence: `src/core/doc-generator/doc-specs.ts`, `src/core/doc-generator/validation/markdown-section-validation.ts`.
- Avoid: Introducing an alternate path/filename convention for generated artifacts.
  - Evidence: `tests/core/utils/paths.test.ts`, `tests/core/models/generated-paths.test.ts`.
- Avoid: Assuming database, app-router, or client-component patterns that are not visible in the main source tree.
  - Evidence: main source files under `src/core/` and `src/cli/` do not show those boundaries.
- Avoid: Treating fixture-only evidence as proof of the main repo’s UI or styling architecture.
  - Evidence: `tests/fixtures/nextjs-basic/*`, `tests/fixtures/repo-context-basic/src/components/ui/button.tsx`.
- Avoid: Making broad refactors in `src/core/models/*`, `src/core/doc-generator/*`, or `src/core/llm/client.ts` without explicit scope, since these appear central to generation and validation.
  - Evidence: those files are used across repo-context building and doc generation flows.

## Unknowns

- Unknown: The repo’s real component architecture is not visible beyond fixture examples.
- Unknown: The actual styling stack in the main source tree is not evidenced; Tailwind/shadcn appear in stack detection and fixtures, not in the main app source.
- Unknown: There is no visible database access layer in the main source, so persistence conventions are unclear.
- Unknown: Testing scope beyond Vitest unit-style coverage is unclear; no explicit integration/e2e/test fixture strategy is visible from the provided source excerpts.
- Unknown: Server/client boundaries for any UI app are ambiguous because the main repo source shown is primarily CLI and core tooling.
- Unknown: Team preferences for `interface` vs `type`, file naming outside the shown folders, and error-handling style outside core utilities are not fully evidenced.
