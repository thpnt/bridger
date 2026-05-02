## Product/domain overview

Bridger appears to support repository inspection and generation of repo-specific guidance for AI coding agents. The strongest evidence is in `src/cli/cli.ts`, `src/core/context-builder/build-repo-context.ts`, and the doc generators in `src/core/doc-generator/generators/*`. The repository seems centered on scanning a repo, building structured context, and generating markdown documents like `business-logic.md` and `AGENTS.md`.

## Observed domain concepts

- **Repository context**
  - Meaning: A structured snapshot of a target repo, including root path, generated timestamp, detected stack, commands, important files, and generated-doc paths.
  - Evidence: `src/core/models/repo-context.ts`, `src/core/context-builder/build-repo-context.ts`, `tests/build-repo-context.test.ts`
  - Confidence: high

- **File index**
  - Meaning: An inventory of files in the target repository, likely used to summarize and rank files for prompts.
  - Evidence: `src/core/models/file-index.ts`, `src/core/repo-scanner/build-file-index.ts`, `src/core/context-builder/file-index-summary.ts`, `tests/repo-scanner.test.ts`
  - Confidence: high

- **Important files**
  - Meaning: A curated subset of files considered significant for repo understanding.
  - Evidence: `src/core/models/important-file.ts`, `src/core/repo-scanner/read-important-files.ts`, `src/core/repo-scanner/important-file-rules.ts`, `tests/important-files.test.ts`
  - Confidence: high

- **Detected stack**
  - Meaning: Repo-level technology detection such as framework, language, package manager, styling, validation, database, and test framework.
  - Evidence: `src/core/models/config.ts`, `src/core/repo-scanner/detect-stack.ts`, `tests/core/models/generated-paths.test.ts`, `tests/cli/inspect.test.ts`
  - Confidence: high

- **Commands**
  - Meaning: Repo commands like install, dev, build, typecheck, and test, detected from `package.json` and similar sources.
  - Evidence: `src/core/repo-scanner/detect-commands.ts`, `package.json`, `tests/cli/inspect.test.ts`, `tests/fixtures/commands-*/package.json`
  - Confidence: high

- **Generated knowledge documents**
  - Meaning: Markdown docs generated to guide future agents, including repo analysis, architecture, business logic, conventions, testing, and agent rules.
  - Evidence: `src/core/doc-generator/doc-specs.ts`, `src/core/doc-generator/doc-filenames.ts`, `src/core/doc-generator/generators/*`, `src/core/doc-generator/renderers/render-agents-md.ts`
  - Confidence: high

- **Agent instructions**
  - Meaning: Repository-specific guidance intended for AI coding agents, rendered into `AGENTS.md`.
  - Evidence: `src/core/doc-generator/renderers/render-agents-md.ts`, `AGENTS.md`, `src/core/doc-generator/generators/generate-agent-rules-doc.ts`
  - Confidence: high

## Observed entities and models

- **`RepoContext`**
  - Meaning: The main validated model for repo metadata and generated-doc references.
  - Evidence: `src/core/models/repo-context.ts`, `src/core/context-builder/build-repo-context.ts`
  - Confidence: high

- **`RepoContextBuildArtifacts`**
  - Meaning: Composite output that packages the repo context together with the file index and important files.
  - Evidence: `src/core/models/repo-context-build.ts`, `src/core/context-builder/build-repo-context.ts`
  - Confidence: high

- **`FileIndex` / `FileIndexEntry`**
  - Meaning: Model for indexed repository files, including path, extension, size, tags, and possibly other metadata used for ranking and summarization.
  - Evidence: `src/core/models/file-index.ts`, `src/core/context-builder/file-index-summary.ts`
  - Confidence: high

- **`ImportantFile`**
  - Meaning: A file entry with a path and a reason it was selected as important.
  - Evidence: `src/core/models/important-file.ts`, `src/core/repo-scanner/read-important-files.ts`
  - Confidence: high

- **`RepoKnowledgeDocInput`**
  - Meaning: Input model for generating repository knowledge docs from repo context, file index, and important files.
  - Evidence: `src/core/models/repo-knowledge-doc.ts`, `src/core/doc-generator/knowledge-doc-input.ts`
  - Confidence: high

- **`GenerateAgentRulesDocInput`**
  - Meaning: Specific input for generating agent rules, likely a narrower schema than the general repo-knowledge input.
  - Evidence: `src/core/models/agent-rules-doc.ts`, `src/core/doc-generator/generators/generate-agent-rules-doc.ts`
  - Confidence: medium

- **`KnowledgeDocSpec` / `KnowledgeDocKey`**
  - Meaning: Configuration for generated document types and their required section sets.
  - Evidence: `src/core/doc-generator/doc-types.ts`, `src/core/doc-generator/doc-specs.ts`
  - Confidence: high

## Observed business rules

- **Repo context must validate against a schema before use**
  - Observed: `buildRepoContextArtifacts` parses the constructed context with `RepoContextSchema.parse(...)` before returning it.
  - Evidence: `src/core/context-builder/build-repo-context.ts`
  - Unknown: The full validation constraints are not visible here.

- **Generated docs must contain required top-level sections**
  - Observed: `generateKnowledgeDoc` validates generated markdown against the required section list for each doc type.
  - Evidence: `src/core/doc-generator/generators/generate-knowledge-doc.ts`, `src/core/doc-generator/doc-specs.ts`, `src/core/doc-generator/validation/markdown-section-validation.ts`
  - Unknown: Whether section order matters beyond inclusion is not enforced in the shown validator.

- **Empty generated markdown is rejected**
  - Observed: `generateKnowledgeDoc` throws if the trimmed markdown is empty.
  - Evidence: `src/core/doc-generator/generators/generate-knowledge-doc.ts`
  - Unknown: No evidence of retry or fallback behavior.

- **OpenAI API key is required for text generation**
  - Observed: `generateText` throws if `OPENAI_API_KEY` is missing.
  - Evidence: `src/core/llm/client.ts`
  - Unknown: No evidence of alternate auth or local fallback.

- **Generated doc paths are stable and repo-relative**
  - Observed: `buildGeneratedDocPaths()` returns fixed `.bridger/generated/*.md` paths and `getTicketTemplateRelativePath()` returns a stable ticket template path.
  - Evidence: `tests/core/models/generated-paths.test.ts`
  - Unknown: The implementation details are not in the excerpt, but the behavior is tested.

- **`AGENTS.md` rendering requires non-empty agent rules markdown**
  - Observed: `renderAgentsMd` throws when the agent rules markdown is empty.
  - Evidence: `src/core/doc-generator/renderers/render-agents-md.ts`
  - Unknown: No evidence of whether it overwrites or merges with existing `AGENTS.md` content beyond the renderer itself.

## Observed workflows

- **Repository context building**
  - Observed: The repo is scanned to detect stack, detect commands, build a file index, read important files, and assemble a validated `RepoContext` plus build artifacts.
  - Evidence: `src/core/context-builder/build-repo-context.ts`
  - Confidence: high

- **Knowledge document generation**
  - Observed: A generator builds a prompt from repo context + file index + important files, sends it to OpenAI, trims the result, and validates that required sections are present.
  - Evidence: `src/core/doc-generator/knowledge-doc-input.ts`, `src/core/doc-generator/generators/generate-knowledge-doc.ts`, `src/core/llm/client.ts`, `src/core/doc-generator/validation/markdown-section-validation.ts`
  - Confidence: high

- **Business-logic doc generation**
  - Observed: `generateBusinessLogicDoc` parses repo knowledge input, builds a knowledge-doc generation input, and routes it through the business-logic prompt/spec.
  - Evidence: `src/core/doc-generator/generators/generate-business-logic-doc.ts`, `src/core/llm/prompts/docs/business-logic-prompt.ts`
  - Confidence: high

- **Agent-rules doc generation and AGENTS rendering**
  - Observed: Agent rules are generated from a dedicated input and then rendered into an `AGENTS.md` format that cites other generated docs as source documents.
  - Evidence: `src/core/doc-generator/generators/generate-agent-rules-doc.ts`, `src/core/doc-generator/renderers/render-agents-md.ts`, `src/core/llm/prompts/docs/agent-rules-prompt.ts`
  - Confidence: high

- **CLI inspection flow**
  - Observed: The CLI can inspect a repo by resolving the root, detecting stack/commands, building a file index, and logging a summary.
  - Evidence: `tests/cli/inspect.test.ts`, `src/cli/commands/inspect.ts`
  - Confidence: high

## Data ownership and persistence

- **Repo-generated output appears to live under `.bridger/`**
  - Observed: Helper paths point to `.bridger/repo-context.json`, `.bridger/file-index.json`, `.bridger/generated/*.md`, and `.bridger/generated/ticket-template.md`.
  - Evidence: `tests/core/utils/paths.test.ts`, `tests/core/models/generated-paths.test.ts`
  - Confidence: high

- **File system persistence is used for output artifacts**
  - Observed: Output helpers create directories and write JSON/markdown files to disk.
  - Evidence: `tests/core/output/write-files.test.ts`, `src/core/output/ensure-output-dirs.ts`, `src/core/output/write-json.ts`, `src/core/output/write-markdown.ts`
  - Confidence: high

- **Business-domain data is not persisted in an application database in the visible code**
  - Observed: The visible repository centers on repo scanning, generation, and file output rather than app-domain storage.
  - Evidence: `src/core/context-builder/build-repo-context.ts`, `src/core/output/*`, `src/core/llm/client.ts`
  - Confidence: medium
  - Unknown: There may be other persistence not shown in the provided excerpts.

## External integrations

- **OpenAI**
  - Observed: Text and structured JSON generation use the `openai` SDK, with `responses.create` and `responses.parse`.
  - Evidence: `src/core/llm/client.ts`
  - Unknown: Which models are expected in practice beyond the default `gpt-5.4-mini`, and whether any organization-specific settings are required.

- **Environment variables**
  - Observed: `OPENAI_API_KEY` is required; `BRIDGER_MODEL` can override the default model.
  - Evidence: `src/core/llm/client.ts`
  - Unknown: No other env vars are visible in the excerpt.

- **Zod structured-output formatting**
  - Observed: The OpenAI structured output path uses Zod schemas via `zodTextFormat`.
  - Evidence: `src/core/llm/client.ts`
  - Unknown: No business-domain integration is implied; this is a tooling dependency.

## Assumptions

- **Assumption:** The repo’s practical business purpose is to analyze a target repository and generate agent-facing documentation rather than to manage end-user business entities.
  - Evidence: `src/core/doc-generator/generators/*`, `src/core/context-builder/build-repo-context.ts`, `AGENTS.md`
  - Missing info: There is no product-facing UI or customer domain model visible in the provided excerpts.

- **Assumption:** The generated docs are intended to be consumed by downstream AI coding workflows.
  - Evidence: `src/core/doc-generator/renderers/render-agents-md.ts`, `src/core/doc-generator/generators/generate-agent-rules-doc.ts`
  - Missing info: The exact consuming system or runtime is not shown.

- **Assumption:** `.bridger/` is the canonical local output area for generated artifacts.
  - Evidence: `tests/core/utils/paths.test.ts`, `tests/core/models/generated-paths.test.ts`
  - Missing info: No explicit persistence policy file is shown.

## Unknowns

- The exact business-domain entities beyond “repo context,” “file index,” and “important files” are not visible.
- Whether generated docs are meant to be committed, kept local, or both is not shown.
- The lifecycle/order of generation across repo-analysis, architecture, business-logic, conventions, testing, and agent-rules is only partly visible.
- Validation rules inside model schemas such as `RepoContextSchema` and `RepoContextBuildArtifactsSchema` are not fully visible.
- Whether there are any permissions, roles, billing concepts, user accounts, or tickets in the actual product domain is not evidenced in the excerpts.
- Whether any background jobs, caching, or incremental rebuild behavior exists is unknown.
- Whether `AGENTS.md` is meant to be regenerated automatically or manually is not shown.
- Whether other external integrations exist beyond OpenAI is unknown.
- The full behavior of command detection, stack detection, and important-file selection is only partially evidenced by tests and call sites.

## Evidence map

- `src/core/context-builder/build-repo-context.ts` — builds validated repo context, file index, and important-file artifacts.
- `src/core/models/repo-context.ts` — core schema/model for repo metadata and generated-doc paths.
- `src/core/models/file-index.ts` — file inventory representation used for summaries and prompts.
- `src/core/models/important-file.ts` — selected file + reason model for significant repo files.
- `src/core/doc-generator/doc-specs.ts` — defines generated document types and required sections.
- `src/core/doc-generator/generators/generate-knowledge-doc.ts` — enforces non-empty output and required markdown sections.
- `src/core/doc-generator/generators/generate-business-logic-doc.ts` — business-logic doc generation entry point.
- `src/core/llm/client.ts` — OpenAI generation, API key requirement, and model selection.
- `src/core/doc-generator/renderers/render-agents-md.ts` — renders `AGENTS.md` from generated docs and agent rules.
- `tests/build-repo-context.test.ts` — confirms repo context fields, generated paths, and important-file behavior.
- `tests/cli/inspect.test.ts` — confirms CLI inspection flow and command/stack detection behavior.
- `tests/core/models/generated-paths.test.ts` — confirms `.bridger/generated/*` output paths.
