# Codex Task — Test suite audit before implementing ``init``

## Context recap — Bridger

``bridger`` is a local TypeScript CLI POC for making repositories AI-agent ready.

The target POC flow is:

``cd target-repo``
``bridger inspect``
``bridger init``
``bridger enrich-ticket "Improve onboarding error handling"``

The product scans a Next.js/TypeScript repository, builds repo context, generates AI-ready documentation, and later enriches rough product/dev requests into implementation-ready tickets grounded in the actual codebase.

The expected generated outputs include:

``.bridger/repo-context.json``
``.bridger/file-index.json``
``.bridger/generated/repo-analysis.md``
``.bridger/generated/architecture.md``
``.bridger/generated/business-logic.md``
``.bridger/generated/conventions.md``
``.bridger/generated/testing.md``
``.bridger/generated/agent-rules.md``
``AGENTS.generated.md``

We are about to implement the ``init`` command, but before that we need to make sure the existing test suite still validates the core business logic from tickets 1 to 14.

This task is a **test suite audit and gap-closing task**. It should verify that the current tests cover the deterministic and mockable parts of the pipeline before ``init`` wires everything together.

Do **not** implement ``init`` in this task.

---

# Objective

Inspect the current test suite and evaluate whether it correctly covers Bridger’s existing pipeline pieces from tickets 1 to 14.

Then, where coverage gaps are clear and low-risk, add or improve tests.

The goal is to ensure we can safely implement ``init`` afterward without discovering that foundational modules are untested or broken.

---

# Scope

Evaluate tests for the following areas:

1. CLI bootstrap and command registration
2. Core Zod models
3. Path and output utilities
4. Gitignore-aware file indexing
5. Stack detection
6. Command detection
7. ``inspect`` command behavior
8. Important file reading
9. LLM client behavior
10. Repo context building
11. Generated document metadata/specs
12. Generated document pipeline
13. Prompt formatting and prompt builders
14. AGENTS.md rendering

This corresponds to the current implementation state before the ``init`` command.

---

# Important constraints

Do not:

- implement ``init``
- call the real OpenAI API
- require ``OPENAI_API_KEY`` for tests
- add embeddings
- add ticket enrichment logic
- rewrite the architecture
- change business behavior just to make tests pass
- add broad snapshots of full LLM prompts unless already used in the project
- introduce heavy mocking frameworks unless already present
- add deterministic tests
- add mocked LLM tests
- add fixture repos

Allowed:

- inspect tests
- improve test names
- improve test organization
- fix broken imports caused by previous refactors
- add small test utilities
- update existing tests to match the current intended structure

---

# First step — Inventory the current test suite

Inspect:

``tests/``

and any test files colocated under:

``src/**/*.test.ts``

or:

``src/**/*.spec.ts``

Create a brief internal map of what exists.

Look for tests covering:

- repo scanner
- stack detection
- command detection
- file index
- path helpers
- output writers
- Zod schemas
- repo context builder
- generated doc specs
- doc generators
- prompt formatting
- AGENTS renderer
- CLI commands

Do not assume the tests are correct. Read them against the current business logic.

---

# Second step — Build a coverage matrix

Evaluate the test suite against the following matrix.

## Ticket 1 — CLI bootstrap

Expected coverage:

- CLI help command works.
- ``inspect`` command is registered.
- ``init`` command is registered, even if still placeholder.
- ``enrich-ticket`` command is registered, even if incomplete.
- Command files import without crashing.

Suggested tests:

``pnpm dev --help`` can be checked manually, but unit tests may inspect Commander registration if easy.

Do not over-test Commander internals.

---

## Ticket 2 — Core Zod models

Expected coverage:
- Zod models are strictly defined, no optional values for core business fields
- ``RepoContextSchema`` validates a valid object.
- ``FileIndexSchema`` validates a valid object.
- ``EnrichedTicketSchema`` validates a valid object if already implemented.

Suggested test file:

``tests/models.test.ts``

or extend an existing model test file.

---

## Ticket 3 — Path and output utilities

Expected coverage:

- ``resolveRepoRoot`` resolves to an absolute path.
- ``getBridgerDir`` returns ``<repo>/.bridger``.
- ``getGeneratedDir`` returns ``<repo>/.bridger/generated``.
- ``getTicketsDir`` returns ``<repo>/.bridger/tickets``.
- ``getRepoContextPath`` returns ``<repo>/.bridger/repo-context.json``.
- ``getFileIndexPath`` returns ``<repo>/.bridger/file-index.json``.
- ``getGeneratedDocPath`` joins generated dir and filename.
- ``getAgentsGeneratedPath`` returns root ``AGENTS.generated.md``.
- ``getAgentsMdPath`` returns root ``AGENTS.md``.
- ``ensureOutputDirs`` creates expected folders.
- ``writeJson`` writes stable pretty JSON.
- ``writeMarkdown`` creates parent folders and writes Markdown.
- ``toSlug`` creates filesystem-safe slugs.

Suggested test file:

``tests/utils-output.test.ts``

Use temporary directories.

---

## Ticket 4 — Gitignore-aware file discovery

Expected coverage:

- ``buildFileIndex`` excludes:
  - ``node_modules``
  - ``.next``
  - ``dist``
  - ``build``
  - ``coverage``
  - ``.git``
  - ``.env``
  - ``.env.*``
  - binary/media/font assets
- ``.gitignore`` is respected.
- important source/config/doc paths are indexed.
- file entries include:
  - relative path
  - extension
  - sizeBytes
  - tags
  - optional reason
- output validates against ``FileIndexSchema``.

Suggested fixture:

``tests/fixtures/nextjs-basic/``

Add fixture files only if needed.

---

## Ticket 5 — Stack detection

Expected coverage:

- detects ``pnpm`` from ``pnpm-lock.yaml``.
- detects ``npm`` from ``package-lock.json``.
- detects ``yarn`` from ``yarn.lock``.
- detects ``bun`` from ``bun.lock`` or ``bun.lockb``.
- detects Next.js from dependency or config/app structure.
- detects TypeScript from ``tsconfig.json`` or dependency.
- detects Tailwind from dependency or config.
- detects shadcn/ui from ``components.json``.
- detects Zod from dependency.
- detects Supabase/Prisma/Drizzle if fixture has those.
- detects Vitest/Jest/Playwright/Cypress if fixture has those.
- handles missing ``package.json`` gracefully.
- returns ``unknown`` where appropriate instead of throwing.

Suggested test file:

``tests/repo-scanner.test.ts``

---

## Ticket 6 — Command detection

Expected coverage:

- detects install command based on package manager.
- detects ``dev``.
- detects ``build``.
- detects ``lint``.
- detects ``typecheck`` from:
  - ``typecheck``
  - ``check-types``
  - ``tsc``
- detects ``test`` from:
  - ``test``
  - ``test:unit``
- detects ``format`` from:
  - ``format``
  - ``prettier``
- handles missing scripts gracefully.
- uses the detected package manager prefix.

Suggested tests:

Use multiple fixture ``package.json`` variants or temporary directories.

---

## Ticket 7 — Inspect command

Expected coverage:

- ``inspect`` runs without requiring an API key.
- ``inspect`` calls deterministic repo scanner pieces.
- printed output includes:
  - repo path
  - framework
  - language
  - package manager
  - styling
  - validation
  - database
  - testing
  - commands
  - indexed file count
- exits non-zero only on real errors.

Do not over-test exact formatting unless current tests already do this.

A CLI integration test is acceptable if it is stable and fast.

---

## Ticket 8 — Important file reader

Expected coverage:

- reads priority files:
  - ``README.md``
  - docs Markdown
  - ``AGENTS.md``
  - ``CLAUDE.md``
  - ``package.json``
  - ``tsconfig.json``
  - Next/Tailwind/shadcn config
- reads representative files from:
  - ``app/``
  - ``src/``
  - ``components/``
  - ``lib/``
- skips huge files.
- skips binary/media files.
- respects max single file size.
- respects max total selected content.
- returns relative paths.
- includes reason per file.
- handles missing files gracefully.

Suggested test file:

``tests/important-files.test.ts``

---

## Ticket 9 — LLM client

Expected coverage:

- missing API key produces a clear actionable error.
- ``generateText`` can be tested with mocked provider/client if the current implementation allows it.
- ``generateJson`` validates structured output with Zod.
- invalid JSON fails with useful error.
- schema-invalid JSON fails with useful error.
- no real network request is made in unit tests.

If the current LLM client is hard to mock, do not redesign it in this task unless the change is small and improves testability.

Preferred approach:

- dependency injection for low-level provider call, if already easy
- or mock OpenAI SDK if existing test setup supports it

Do not call the real OpenAI API.

---

## Ticket 10 — Repo context builder

Expected coverage:

- ``buildRepoContext``:
  - detects stack
  - detects commands
  - builds file index
  - includes important files metadata
  - sets generated doc paths
  - sets ``generatedAt``
- output validates against ``RepoContextSchema``.
- does not call the LLM.
- generated doc paths are stable relative paths.
- handles missing optional files gracefully.

Suggested test:

Use ``tests/fixtures/nextjs-basic/``.

---

## Ticket 11 — Repo analysis / architecture prompt-generation layer

Depending on current naming, cover:

- repo analysis prompt builder returns:
  - ``system``
  - ``prompt``
- prompt includes required sections from ``KNOWLEDGE_DOC_SPECS.repoAnalysis``.
- prompt includes grounding rules.
- prompt includes file index summary.
- prompt includes important files.
- prompt does not require API key.

For architecture:

- ``buildArchitecturePrompt`` includes required sections.
- architecture doc generator calls shared ``generateKnowledgeDoc`` or equivalent.
- generator does not write files directly.

Do not snapshot full prompt unless there is already a snapshot strategy. Prefer targeted assertions.

---

## Ticket 12 — Conventions prompt-generation layer

Expected coverage:

- reuses the same utilisies and logic as the previous ticket 11 for architechture.md and repo-analysis.md

---

## Ticket 13 — Testing prompt-generation layer

Expected coverage:

- ``buildTestingPrompt`` includes required sections from spec.
- uses detected commands from ``repoContext.commands``.
- includes detected test frameworks from stack.
- handles no detected test framework.
- does not invent test commands.
- generator does not write files directly.
-   reuses the same utilisies and logic as the previous ticket 11 for architechture.md and repo-analysis.md

---

## Ticket 14 — Agent rules and AGENTS renderer

Expected coverage:

- ``buildAgentRulesPrompt`` includes required sections from spec.
- includes commands.
- includes risky areas/scoping guidance instruction.
- ``generateAgentRulesDoc`` does not write files directly.
- ``renderAgentsMd``:
  - renders a useful root-level AGENTS document
  - includes project overview
  - includes commands
  - includes coding/testing/risky-area/scoping sections
  - uses generated agent rules content
  - does not call LLM
  - does not write files directly
- behavior for existing ``AGENTS.md`` should be handled later by ``init``; renderer should stay pure.

---

# Third step — Evaluate test organization

Assess whether tests are organized in a maintainable way.

Recommended structure:

``tests/fixtures/nextjs-basic/``

``tests/models.test.ts``

``tests/paths-output.test.ts``

``tests/repo-scanner.test.ts``

``tests/important-files.test.ts``

``tests/repo-context.test.ts``

``tests/doc-generator.test.ts``

``tests/prompts.test.ts``

``tests/render-agents-md.test.ts``

``tests/cli-inspect.test.ts``

Do not force this exact structure if the current one is already clean. Use it as a guide.

---

# Fourth step — Identify gaps

Produce a test coverage gap report before making changes.

The report should include:

1. Existing test files.
2. What each test file covers.
3. Which tickets from 1 to 14 are covered.
4. Which tickets are partially covered.
5. Which tickets are not covered.
6. High-risk untested areas.
7. Suggested missing tests.

Prioritize gaps that could break ``init`` later:

- generated paths
- repo context builder
- file index
- important file reader
- prompt builders
- shared doc generator pipeline
- AGENTS renderer
- LLM client error behavior

---

# Fifth step — Add or improve tests for clear gaps

After the audit, add tests only where the expected behavior is clear.

Highest-priority tests to add if missing:

## 1. Repo context builder

Test that ``buildRepoContext`` returns a valid schema object for fixture repo and includes generated doc paths.

## 2. File index

Test exclusions, gitignore, tags, and schema validation.

## 3. Important file reader

Test priority files, content limits, relative paths, and reasons.

## 4. Generated doc specs

Test that each knowledge doc spec exists and has:

- key
- filename
- displayName
- requiredSections

Also test that no ``ticketTemplate`` or ``AGENTS.generated.md`` is accidentally included as a knowledge doc.

## 5. Shared doc generator pipeline

Using mocked LLM client:

- returns trimmed Markdown
- throws on empty output
- validates required sections
- passes prompt builder output to ``generateText``

## 6. Prompt builders

Use targeted assertions:

- includes required section names
- includes grounding rules
- includes stack/commands/file summary
- returns ``{ system, prompt }``

## 7. AGENTS renderer

Test pure rendering from input content.

## 8. LLM client

Test missing API key and JSON validation paths without real network.

Only add tests that can pass deterministically.

---

# Sixth step — Use fixture repos correctly

Use or create:

``tests/fixtures/nextjs-basic/``

A good fixture should include:

``package.json``
``pnpm-lock.yaml``
``tsconfig.json``
``README.md``
``components.json``
``next.config.ts`` or ``next.config.mjs``
``tailwind.config.ts`` if needed
``app/page.tsx``
``app/layout.tsx``
``components/ui/button.tsx``
``lib/utils.ts``
``src/`` if relevant
``docs/overview.md``
``.gitignore``

Also include files that should be ignored:

``node_modules/ignored.ts``
``.next/cache/file.js``
``.env.local``
``ignored-by-gitignore.ts``
``public/logo.png``

Keep fixture files small.

Do not add large files unless testing size limits; if needed, generate the large file inside a temporary directory during the test instead of committing huge fixture files.

---

# Seventh step — Mock LLM behavior cleanly

For generated document pipeline tests, do not call the real LLM.

Preferred strategies:

1. Mock ``generateText`` from ``src/core/llm/client.ts``.
2. Inject a fake generation function if the code already supports it.
3. If neither is easy, test prompt builders and validation separately, and report that generator pipeline mocking needs a small refactor.

Do not perform real network calls.

Do not require ``OPENAI_API_KEY`` in tests.

---

# Eighth step — Validate commands

Run:

``pnpm typecheck``

Run:

``pnpm test``

Run:

``pnpm dev --help``

Run if safe:

``pnpm dev inspect``

Do not run:

``pnpm dev init``

unless it is already implemented and does not require a real API key.

Do not run any command requiring a real LLM call.

---

# Expected final deliverable

At the end, provide a test audit report.

Use this format:

## Summary

Briefly state whether the test suite is ready for ``init`` implementation.

## Existing test coverage

List current test files and what they cover.

## Coverage by ticket

Use this format:

- Ticket 1 — CLI bootstrap: Covered / Partial / Missing
- Ticket 2 — Core Zod models: Covered / Partial / Missing
- Ticket 3 — Path/output utilities: Covered / Partial / Missing
- Ticket 4 — File discovery/indexing: Covered / Partial / Missing
- Ticket 5 — Stack detection: Covered / Partial / Missing
- Ticket 6 — Command detection: Covered / Partial / Missing
- Ticket 7 — Inspect command: Covered / Partial / Missing
- Ticket 8 — Important file reader: Covered / Partial / Missing
- Ticket 9 — LLM client: Covered / Partial / Missing
- Ticket 10 — Repo context builder: Covered / Partial / Missing
- Ticket 11 — Repo analysis / architecture doc generation: Covered / Partial / Missing
- Ticket 12 — Conventions doc generation: Covered / Partial / Missing
- Ticket 13 — Testing doc generation: Covered / Partial / Missing
- Ticket 14 — Agent rules / AGENTS renderer: Covered / Partial / Missing

## Tests added or updated

List files changed and what was added.

## Remaining gaps

List anything still not covered and why.

## Risk assessment before ``init``

State whether it is safe to move to ``init``.

Use one of:

- Safe to proceed
- Proceed with caution
- Not ready

Explain briefly.

## Validation results

Report:

- ``pnpm typecheck``
- ``pnpm test``
- ``pnpm dev --help``
- ``pnpm dev inspect`` if run

## Notes

Mention any test instability, mocking limitations, or areas where code should be refactored for better testability.

---

# Acceptance criteria

This task is complete when:

1. The current test suite has been inspected.
2. Coverage has been mapped to tickets 1–14.
3. Clear missing tests have been identified.
4. High-priority deterministic tests have been added where practical.
5. No tests call the real LLM.
6. No tests require ``OPENAI_API_KEY``.
7. Core deterministic modules are covered:
   - file index
   - stack detection
   - command detection
   - path/output utilities
   - repo context builder
   - important file reader
8. Prompt/doc-generation modules are at least partially covered:
   - doc specs
   - prompt builders
   - shared generator pipeline with mocked LLM if possible
   - AGENTS renderer
9. ``pnpm typecheck`` passes.
10. ``pnpm test`` passes or failures are clearly explained.
11. A final audit report is provided.
12. ``init`` remains unimplemented in this task.