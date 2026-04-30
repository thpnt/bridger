# bridger POC — Implementation Tickets

## Project goal

Build a local TypeScript CLI that scans a Next.js/TypeScript repository, generates AI-readiness documentation, and enriches rough product/dev requests into implementation-ready, bridger tickets.

The POC must prove this flow:

```txt
cd target-repo
bridger inspect
bridger init
bridger new-skill "Skills to add a new page to the website"
bridger enrich-ticket "Improve onboarding error handling"
```

Expected outputs:

```txt
.bridger/
  repo-context.json
  file-index.json
  generated/
    architecture.md
    conventions.md
    testing.md
    agent-rules.md
    ticket-template.md
  tickets/
    <ticket-slug>.md
    <ticket-slug>.json

.agents/
  skills/
    generated-skill-1/
    generated-skill-2/
    generated-skill-3/

AGENTS.md
```

---

# Technical guidelines

## Stack

Use:

```txt
TypeScript
Node.js 20+
pnpm
commander
zod
fast-glob
ignore
dotenv
fs-extra
slugify
openai or @ai-sdk/openai
vitest
tsx
```

Prefer simple, explicit code over premature abstractions.

## Project structure

Start with a single package:

```txt
bridger/
  package.json
  tsconfig.json
  .env.example
  README.md

  src/
    cli/
      index.ts
      commands/
        init.ts
        inspect.ts
        enrich-ticket.ts

    core/
      repo-scanner/
        scan-repo.ts
        detect-stack.ts
        detect-commands.ts
        build-file-index.ts
        read-important-files.ts
        gitignore.ts

      context-builder/
        build-repo-context.ts
        generate-architecture-doc.ts
        generate-conventions-doc.ts
        generate-testing-doc.ts
        generate-agent-rules-doc.ts
        generate-ticket-template.ts
        render-agents-md.ts

      ticket-compiler/
        enrich-ticket.ts
        select-relevant-files.ts
        score-agent-suitability.ts
        render-ticket-markdown.ts

      llm/
        client.ts
        prompts/
          repo-analysis-prompt.ts
          conventions-prompt.ts
          testing-prompt.ts
          agent-rules-prompt.ts
          ticket-enrichment-prompt.ts

      models/
        repo-context.ts
        file-index.ts
        ticket.ts
        config.ts

      output/
        ensure-output-dirs.ts
        write-json.ts
        write-markdown.ts

      utils/
        logger.ts
        paths.ts
        read-json.ts
        slug.ts

  tests/
    fixtures/
      nextjs-basic/
    repo-scanner.test.ts
    ticket-compiler.test.ts
```

## Implementation rules

1. Build the local CLI first. Do not build SaaS, MCP, GitHub app, auth, billing, or dashboard.
2. Target Next.js/TypeScript repositories first.
3. Do not add embeddings in the POC.
4. Do not execute generated code.
5. Do not modify user source files.
6. Only write to `.bridger/` and root-level `AGENTS.md`.
7. Always validate LLM structured outputs with Zod.
8. Prefer explicit unknowns over hallucinated certainty.
9. Generated outputs must be reviewable Markdown and JSON.
10. Optimize for useful ticket output, not architectural completeness.

---

# Ticket 1 — Bootstrap the CLI package

## Objective

Create the initial TypeScript CLI project with build, dev, and test scripts.

## Scope

Create:

```txt
package.json
tsconfig.json
.env.example
README.md
src/cli/index.ts
src/cli/commands/inspect.ts
src/cli/commands/init.ts
src/cli/commands/enrich-ticket.ts
```

## Requirements

The CLI should expose:

```txt
bridger inspect
bridger init
bridger enrich-ticket
```

For now, each command can print a placeholder message.

## Suggested dependencies

```txt
commander
zod
fast-glob
ignore
dotenv
fs-extra
slugify
tsx
typescript
vitest
```

## Suggested package scripts

```json
{
  "scripts": {
    "dev": "tsx src/cli/index.ts",
    "build": "tsc",
    "typecheck": "tsc --noEmit",
    "test": "vitest"
  }
}
```

## Acceptance criteria

- `pnpm install` works.
- `pnpm dev --help` shows the CLI help.
- `pnpm dev inspect` runs without crashing.
- `pnpm dev init` runs without crashing.
- `pnpm dev enrich-ticket "test"` runs without crashing.
- `pnpm typecheck` passes.

---

# Ticket 2 — Define core Zod models

## Objective

Define shared schemas and TypeScript types for repo context, file index, and enriched tickets.

## Files

Inside:

```txt
src/core/models/repo-context.ts
src/core/models/file-index.ts
src/core/models/ticket.ts
src/core/models/config.ts
```

## RepoContext model

Include:

```ts
repoRoot: string
generatedAt: string
stack: {
  framework: string
  language: string
  packageManager: string
  styling: string[]
  validation: string[]
  database: string[]
  testFramework: string[]
}
commands: {
  install?: string
  dev?: string
  build?: string
  lint?: string
  typecheck?: string
  test?: string
  format?: string
}
importantFiles: Array<{
  path: string
  reason: string
}>
generatedDocs: {
  architecturePath: string
  conventionsPath: string
  testingPath: string
  agentRulesPath: string
  ticketTemplatePath: string
}
```

## FileIndex model

Include:

```ts
generatedAt: string
files: Array<{
  path: string
  extension?: string
  sizeBytes: number
  reason?: string
  tags: string[]
}>
```

## EnrichedTicket model

Include:

```ts
title: string
goal: string
userImpact?: string
currentBehavior?: string
desiredBehavior: string
repoContext: string[]
acceptanceCriteria: string[]
constraints: string[]
suggestedFiles: Array<{
  path: string
  reason: string
}>
testExpectations: string[]
missingQuestions: string[]
assumptions: string[]
riskLevel: "low" | "medium" | "high"
agentSuitability: {
  score: number
  label: "poor" | "medium" | "good" | "excellent"
  reason: string
}
handoffPrompt: string
```

## Acceptance criteria

- Schemas are exported with inferred TypeScript types.
- Invalid ticket risk levels fail validation.
- Invalid agent suitability scores fail validation.
- `pnpm typecheck` passes.

---

# Ticket 3 — Implement repo path and output utilities

## Objective

Create reusable utilities for path resolution, output folder creation, JSON writing, Markdown writing, and slug generation.

## Files

Create:

```txt
src/core/utils/paths.ts
src/core/utils/slug.ts
src/core/utils/read-json.ts
src/core/output/ensure-output-dirs.ts
src/core/output/write-json.ts
src/core/output/write-markdown.ts
src/core/utils/logger.ts
```

## Requirements

Implement helpers for:

```ts
resolveRepoRoot(input?: string): string
getAgentReadyDir(repoRoot: string): string
getGeneratedDir(repoRoot: string): string
getTicketsDir(repoRoot: string): string
toSlug(input: string): string
readJsonFile<T>(path: string): Promise<T>
writeJson(path: string, data: unknown): Promise<void>
writeMarkdown(path: string, content: string): Promise<void>
ensureOutputDirs(repoRoot: string): Promise<void>
```

## Acceptance criteria

- Helpers create `.bridger/generated` and `.bridger/tickets`.
- JSON is written with stable pretty formatting.
- Markdown writer creates parent directories if needed.
- Slug output is filesystem-safe.

---

# Ticket 4 — Implement gitignore-aware file discovery

## Objective

Implement file discovery that respects `.gitignore` and excludes noisy folders/files.

## Files

Create:

```txt
src/core/repo-scanner/gitignore.ts
src/core/repo-scanner/build-file-index.ts
```

## Exclusions

Always exclude:

```txt
node_modules
.next
dist
build
coverage
.git
.env
.env.*
*.png
*.jpg
*.jpeg
*.gif
*.webp
*.svg
*.ico
*.mp4
*.mov
*.woff
*.woff2
*.ttf
```

Respect `.gitignore` when present.

## Prioritized paths

Tag files from:

```txt
README.md
docs/**
AGENTS.md
CLAUDE.md
package.json
tsconfig.json
next.config.*
tailwind.config.*
components.json
app/**
pages/**
src/**
components/**
lib/**
server/**
db/**
supabase/**
prisma/**
drizzle/**
```

## Requirements

Implement:

```ts
buildFileIndex(repoRoot: string): Promise<FileIndex>
```

Each file entry should include:

- relative path;
- extension;
- size in bytes;
- tags;
- optional reason.

## Acceptance criteria

- `node_modules`, `.next`, `.git`, and `.env*` are excluded.
- `.gitignore` is respected.
- `package.json`, README, app/src/lib/components folders are indexed when present.
- File index validates against `FileIndexSchema`.
- Add at least one Vitest test using a fixture repo.

---

# Ticket 5 — Implement stack detection

## Objective

Detect framework, language, package manager, styling tools, validation libraries, database tools, and test framework.

## Files

Create:

```txt
src/core/repo-scanner/detect-stack.ts
```

## Detection heuristics

Package manager:

```txt
pnpm-lock.yaml -> pnpm
yarn.lock -> yarn
package-lock.json -> npm
bun.lockb or bun.lock -> bun
```

Framework:

```txt
next dependency -> Next.js
app/ or pages/ + next.config.* -> Next.js
```

Language:

```txt
tsconfig.json or typescript dependency -> TypeScript
otherwise JavaScript or unknown
```

Styling:

```txt
tailwindcss dependency or tailwind.config.* -> Tailwind
components.json -> shadcn/ui
```

Validation:

```txt
zod dependency -> Zod
```

Database:

```txt
@supabase/supabase-js or supabase/ -> Supabase
prisma dependency or prisma/schema.prisma -> Prisma
drizzle-orm or drizzle.config.* -> Drizzle
```

Testing:

```txt
vitest -> Vitest
jest -> Jest
playwright -> Playwright
cypress -> Cypress
```

## Acceptance criteria

- Stack detection works without calling the LLM.
- Handles missing `package.json` gracefully.
- Returns `unknown` instead of crashing when ambiguous.
- Add tests for a Next.js fixture.

---

# Ticket 6 — Implement command detection

## Objective

Infer useful project commands from `package.json`.

## Files

Create:

```txt
src/core/repo-scanner/detect-commands.ts
```

## Requirements

Detect:

```ts
install
dev
build
lint
typecheck
test
format
```

Use package manager prefix:

```txt
pnpm dev
npm run dev
yarn dev
bun run dev
```

For install:

```txt
pnpm install
npm install
yarn install
bun install
```

Map package scripts intelligently:

```txt
dev -> dev
build -> build
lint -> lint
typecheck/check-types/tsc -> typecheck
test/test:unit -> test
format/prettier -> format
```

## Acceptance criteria

- Detects commands from package scripts.
- Falls back gracefully when a script does not exist.
- Uses the detected package manager.
- Add tests.

---

# Ticket 7 — Implement the `inspect` command

## Objective

Create a useful terminal command that prints detected repo information without using the LLM.

## Files

Modify:

```txt
src/cli/commands/inspect.ts
```

Use:

```txt
detect-stack.ts
detect-commands.ts
build-file-index.ts
```

## Output example

```txt
bridger Inspect

Repo: /path/to/repo
Framework: Next.js
Language: TypeScript
Package manager: pnpm
Styling: Tailwind, shadcn/ui
Validation: Zod
Database: Supabase
Testing: Vitest, Playwright

Commands:
- install: pnpm install
- dev: pnpm dev
- build: pnpm build
- lint: pnpm lint
- typecheck: pnpm typecheck
- test: pnpm test

Indexed files: 183
```

## Acceptance criteria

- `pnpm dev inspect` works on the current repo.
- No LLM/API key is required.
- Output is readable.
- Command exits with non-zero status only on real errors.

---

# Ticket 8 — Implement important file reader

## Objective

Read a curated set of important files to provide grounded context to the LLM.

## Files

Create:

```txt
src/core/repo-scanner/read-important-files.ts
```

## Requirements

Read files like:

```txt
README.md
docs/**/*.md
AGENTS.md
CLAUDE.md
package.json
tsconfig.json
next.config.*
tailwind.config.*
components.json
```

Also read small representative files from:

```txt
app/**
src/**
components/**
lib/**
```

Limit file size per file.

Suggested limits:

```txt
Max single file: 20 KB
Max total selected content: 120 KB
```

Return:

```ts
type ImportantFile = {
  path: string
  reason: string
  content: string
}
```

## Acceptance criteria

- Does not read huge files.
- Does not read binary files.
- Prioritizes README/package/config/docs.
- Returns paths relative to repo root.
- Handles missing files gracefully.

---

# Ticket 9 — Implement LLM client

## Objective

Add a minimal LLM client for text generation and structured JSON generation.

## Files

Create:

```txt
src/core/llm/client.ts
```

## Requirements

Use one provider only for POC.

Recommended:

```txt
OpenAI SDK
OPENAI_API_KEY
```

`.env.example`:

```txt
OPENAI_API_KEY=
AGENT_READY_MODEL=gpt-5.5-thinking
```

If model selection is uncertain, allow override through env.

Expose:

```ts
generateText(input: {
  system: string
  prompt: string
}): Promise<string>

generateJson<T>(input: {
  system: string
  prompt: string
  schemaName: string
  schema: z.ZodSchema<T>
}): Promise<T>
```

Implementation can either use native structured outputs if available or generate JSON text and validate with Zod.

## Acceptance criteria

- Missing API key produces a clear error.
- LLM errors produce actionable error messages.
- Structured outputs are validated with Zod.
- Invalid JSON fails with a useful error.

---

# Ticket 10 — Implement repo context builder

## Objective

Build the complete `RepoContext` object from scanner outputs and planned generated doc paths.

## Files

Create:

```txt
src/core/context-builder/build-repo-context.ts
```

## Requirements

Implement:

```ts
buildRepoContext(repoRoot: string): Promise<RepoContext>
```

It should:

- detect stack;
- detect commands;
- build file index;
- identify important files and reasons;
- set generated doc paths;
- add `generatedAt`.

## Acceptance criteria

- Output validates against `RepoContextSchema`.
- Does not call the LLM.
- Can be used by `init`.
- Writes stable relative generated doc paths.

---

# Ticket 11 — Add repo analysis prompt

## Objective

Create a prompt that generates grounded architecture documentation.

## Files

Create:

```txt
src/core/llm/prompts/repo-analysis-prompt.ts
src/core/context-builder/generate-architecture-doc.ts
```

## Prompt guidelines

The generated document must include:

```txt
Project overview
Detected stack
App structure
Core domains
Important folders
Data flow assumptions
Commands
Risky areas
Unknowns
```

Rules:

```txt
Use only provided context.
Do not invent architecture.
Mark missing information as unknown.
Distinguish observed facts from assumptions.
Prefer concise, practical guidance.
```

## Acceptance criteria

- Produces Markdown.
- References real files/folders from the repo.
- Includes an `Unknowns` section.
- Avoids confident claims without evidence.

---

# Ticket 12 — Add conventions prompt

## Objective

Generate practical coding conventions from repo structure and selected files.

## Files

Create:

```txt
src/core/llm/prompts/conventions-prompt.ts
src/core/context-builder/generate-conventions-doc.ts
```

## Required sections

```txt
TypeScript conventions
Component conventions
Server/client boundary conventions
Validation conventions
Styling conventions
Data access conventions
Testing conventions
Naming conventions
Observed conventions
Recommended conventions
Things agents should avoid
```

## Acceptance criteria

- Separates observed conventions from recommendations.
- Mentions uncertainty when patterns are weak.
- Avoids generic filler.
- Outputs Markdown.

---

# Ticket 13 — Add testing profile prompt

## Objective

Generate a testing and verification profile for agents.

## Files

Create:

```txt
src/core/llm/prompts/testing-prompt.ts
src/core/context-builder/generate-testing-doc.ts
```

## Required sections

```txt
Available commands
Detected test frameworks
When to add tests
Suggested verification flow
Manual QA checklist
Unknowns
```

## Acceptance criteria

- Uses detected package commands.
- Does not invent commands.
- If no tests are detected, says so.
- Provides practical verification steps for agents.

---

# Ticket 14 — Add agent rules prompt and `AGENTS.md` renderer

## Objective

Generate agent-facing rules and write root-level `AGENTS.md`.

## Files

Create:

```txt
src/core/llm/prompts/agent-rules-prompt.ts
src/core/context-builder/generate-agent-rules-doc.ts
src/core/context-builder/render-agents-md.ts
```

## `AGENTS.md` should include

```txt
Project overview
Commands
Rules for agents
Coding conventions
Testing expectations
Risky areas
Task scoping rules
Files/folders to avoid unless explicitly requested
Unknowns
```

## Important behavior

If `AGENTS.md` already exists:

- For POC, do not try to merge intelligently.
- Write `.bridger/generated/agent-rules.md`.
- Ask/require a flag before overwriting root `AGENTS.md`, or create `AGENTS.generated.md`.

Recommended POC behavior:

```txt
Default: write AGENTS.generated.md
Optional: --write-agents-md writes/overwrites AGENTS.md
```

## Acceptance criteria

- Does not silently overwrite existing `AGENTS.md`.
- Generated rules are practical and repo-specific.
- Includes commands.
- Includes risky areas and scoping guidance.

---

# Ticket 15 — Implement `init` command

## Objective

Wire scanner, repo context builder, LLM doc generation, and file output into the `init` command.

## Files

Modify:

```txt
src/cli/commands/init.ts
```

Use:

```txt
build-repo-context.ts
generate-architecture-doc.ts
generate-conventions-doc.ts
generate-testing-doc.ts
generate-agent-rules-doc.ts
generate-ticket-template.ts
render-agents-md.ts
write-json.ts
write-markdown.ts
```

## Requirements

Command:

```txt
bridger init
bridger init --write-agents-md
```

Outputs:

```txt
.bridger/repo-context.json
.bridger/file-index.json
.bridger/generated/architecture.md
.bridger/generated/conventions.md
.bridger/generated/testing.md
.bridger/generated/agent-rules.md
.bridger/generated/ticket-template.md
AGENTS.generated.md
```

If `--write-agents-md` is passed:

```txt
AGENTS.md
```

## Acceptance criteria

- `pnpm dev init` generates all expected files.
- Does not require manual folder creation.
- Does not overwrite existing `AGENTS.md` unless flag is passed.
- Prints a useful summary of generated files.
- `repo-context.json` and `file-index.json` validate.

---

# Ticket 16 — Implement ticket template generation

## Objective

Generate a standard bridger ticket template.

## Files

Create:

```txt
src/core/context-builder/generate-ticket-template.ts
```

## Template sections

```txt
Title
Goal
User impact
Current behavior
Desired behavior
Relevant repo context
Acceptance criteria
Constraints
Suggested files
Test expectations
Missing questions
Assumptions
Risk level
Agent suitability
Agent handoff prompt
```

## Acceptance criteria

- Writes `.bridger/generated/ticket-template.md`.
- Template is usable by humans and LLM prompts.
- Template is concise enough to copy into issue trackers.

---

# Ticket 17 — Implement relevant file selector

## Objective

Select relevant files for a rough ticket using simple path and keyword heuristics.

## Files

Create:

```txt
src/core/ticket-compiler/select-relevant-files.ts
```

## Algorithm

1. Lowercase rough ticket.
2. Extract keywords.
3. Apply domain synonyms.
4. Match keywords against file paths from `file-index.json`.
5. Prefer files in relevant directories.
6. Always include docs/config context separately.
7. Return top N files with reasons.

## Suggested synonym map

```ts
const DOMAIN_SYNONYMS: Record<string, string[]> = {
  onboarding: ["onboarding", "signup", "setup", "getting-started"],
  auth: ["auth", "login", "session", "oauth"],
  github: ["github", "git", "installation", "repository"],
  error: ["error", "exception", "failure", "toast", "alert"],
  billing: ["billing", "stripe", "subscription", "plan"],
  dashboard: ["dashboard", "analytics", "metrics"],
  settings: ["settings", "preferences", "profile"],
  form: ["form", "input", "validation", "schema"],
  email: ["email", "resend", "notification", "message"]
};
```

## Return type

```ts
type RelevantFile = {
  path: string
  reason: string
  score: number
}
```

## Acceptance criteria

- Ticket mentioning onboarding returns onboarding-related files when they exist.
- Ticket mentioning billing returns billing/stripe-related files when they exist.
- Does not return excluded files.
- Add tests using fixture file paths.

---

# Ticket 18 — Implement ticket enrichment prompt

## Objective

Create a structured LLM prompt that turns rough input into a validated `EnrichedTicket`.

## Files

Create:

```txt
src/core/llm/prompts/ticket-enrichment-prompt.ts
src/core/ticket-compiler/enrich-ticket.ts
```

## Prompt input

Include:

```txt
Rough ticket
Repo context
Architecture doc
Conventions doc
Testing doc
Agent rules doc
Relevant files list
Selected file snippets if available
Commands
```

## Prompt rules

```txt
Return strict JSON only.
Do not invent exact behavior.
Use "appears to" or "likely" when uncertain.
Mark assumptions explicitly.
Surface missing questions.
Keep task scoped.
Prefer concrete acceptance criteria.
Suggest files only when supported by file paths or snippets.
```

## Acceptance criteria

- Output validates against `EnrichedTicketSchema`.
- Missing questions are included when rough input is vague.
- Suggested files include reasons.
- Agent suitability score is justified.
- Handoff prompt is included.

---

# Ticket 19 — Implement ticket Markdown renderer

## Objective

Convert an `EnrichedTicket` into readable Markdown.

## Files

Create:

```txt
src/core/ticket-compiler/render-ticket-markdown.ts
```

## Required sections

```txt
# <title>

## Goal
## User impact
## Current behavior
## Desired behavior
## Relevant repo context
## Acceptance criteria
## Constraints
## Suggested files
## Test expectations
## Missing questions
## Assumptions
## Risk level
## Agent suitability
## Agent handoff prompt
```

## Acceptance criteria

- Markdown is readable in GitHub.
- Arrays render as bullet lists.
- Suggested files include path and reason.
- Handoff prompt is fenced or clearly separated.
- Empty optional sections are omitted or marked as unknown.

---

# Ticket 20 — Implement `enrich-ticket` command

## Objective

Wire ticket enrichment into the CLI.

## Files

Modify:

```txt
src/cli/commands/enrich-ticket.ts
```

## Supported usage

```txt
bridger enrich-ticket "Improve onboarding error handling"
bridger enrich-ticket --file rough-ticket.md
```

## Requirements

The command should:

1. Load `.bridger/repo-context.json`.
2. Load `.bridger/file-index.json`.
3. Load generated docs.
4. Select relevant files.
5. Read small snippets from relevant files.
6. Call ticket enrichment LLM.
7. Validate output.
8. Write:

```txt
.bridger/tickets/<slug>.md
.bridger/tickets/<slug>.json
```

## Behavior if `init` has not been run

Print:

```txt
No .bridger/repo-context.json found.
Run `bridger init` first.
```

Exit with non-zero status.

## Acceptance criteria

- Works with inline string input.
- Works with `--file`.
- Fails clearly if `init` was not run.
- Writes Markdown and JSON.
- Prints output file paths.
- Output ticket is validated.

---

# Ticket 21 — Add basic tests

## Objective

Add tests for deterministic, non-LLM logic.

## Files

Create/update:

```txt
tests/repo-scanner.test.ts
tests/ticket-compiler.test.ts
tests/fixtures/nextjs-basic/
```

## Test areas

Test:

- package manager detection;
- stack detection;
- command detection;
- file indexing exclusions;
- relevant file selection;
- slug generation;
- model validation.

Do not test actual LLM calls in unit tests.

## Acceptance criteria

- `pnpm test` passes.
- Tests do not require API keys.
- Fixture repo is small.
- Core deterministic logic has coverage.

---

# Ticket 22 — Add README with POC usage

## Objective

Document how to install, configure, and run the POC.

## Files

Update:

```txt
README.md
.env.example
```

## README sections

```txt
What is bridger?
POC scope
Installation
Environment variables
Commands
Example workflow
Generated files
Known limitations
Evaluation checklist
```

## Example workflow

```txt
pnpm install
cp .env.example .env
pnpm dev inspect
pnpm dev init
pnpm dev enrich-ticket "Improve onboarding error handling"
```

## Known limitations

Mention:

```txt
Next.js/TypeScript optimized
No embeddings yet
No SaaS
No GitHub app
No MCP server
No agent execution
Heuristic file retrieval
Generated docs should be reviewed
```

## Acceptance criteria

- A developer can run the project from README alone.
- Limitations are explicit.
- Examples are copy-pasteable.

---

# Ticket 23 — Manual evaluation script

## Objective

Create a simple evaluation checklist for testing the POC on real repos.

## Files

Create:

```txt
docs/evaluation.md
```

## Evaluation flow

For each repo:

```txt
bridger inspect
bridger init
bridger enrich-ticket "<rough ticket>"
```

Evaluate:

```txt
Did stack detection work?
Are generated docs repo-specific?
Is AGENTS.generated.md useful?
Did relevant file selection make sense?
Is the enriched ticket better than the rough input?
Would a developer implement from this?
Would you paste the handoff prompt into Claude Code/Codex?
What hallucinations occurred?
What missing questions were useful?
```

## Scoring table

Use:

```txt
1 = poor
2 = weak
3 = acceptable
4 = good
5 = excellent
```

Score:

```txt
Repo-specificity
File relevance
Acceptance criteria quality
Missing questions quality
Agent handoff usefulness
Hallucination control
Overall usefulness
```

## Acceptance criteria

- `docs/evaluation.md` exists.
- It can be used manually without extra tooling.
- It focuses on product value, not code quality.

---

# Ticket 24 — Smoke test on one real repo

## Objective

Run the full POC on one real Next.js/TypeScript repo and collect observations.

## Steps

Run:

```txt
pnpm build
pnpm test
pnpm dev inspect
pnpm dev init
pnpm dev enrich-ticket "Improve onboarding error handling"
```

Then inspect:

```txt
.bridger/generated/architecture.md
.bridger/generated/conventions.md
.bridger/generated/testing.md
.bridger/generated/agent-rules.md
AGENTS.generated.md
.bridger/tickets/*.md
```

## Acceptance criteria

- Full flow completes.
- Generated docs are not empty.
- Enriched ticket is usable.
- Any hallucinations or weak outputs are documented.
- At least 3 improvement ideas are written down for the next iteration.

---

# Recommended weekend order

Implement in this order:

```txt
1. Ticket 1 — Bootstrap CLI package
2. Ticket 2 — Define core Zod models
3. Ticket 3 — Path/output utilities
4. Ticket 4 — Gitignore-aware file discovery
5. Ticket 5 — Stack detection
6. Ticket 6 — Command detection
7. Ticket 7 — Inspect command
8. Ticket 8 — Important file reader
9. Ticket 9 — LLM client
10. Ticket 10 — Repo context builder
11. Ticket 11 — Architecture doc generation
12. Ticket 12 — Conventions doc generation
13. Ticket 13 — Testing doc generation
14. Ticket 14 — Agent rules + AGENTS.generated.md
15. Ticket 16 — Ticket template generation
16. Ticket 15 — Init command
17. Ticket 17 — Relevant file selector
18. Ticket 18 — Ticket enrichment prompt
19. Ticket 19 — Ticket Markdown renderer
20. Ticket 20 — Enrich-ticket command
21. Ticket 21 — Basic tests
22. Ticket 22 — README
23. Ticket 23 — Evaluation doc
24. Ticket 24 — Smoke test
```

If time is short, stop after Ticket 20. That is the smallest useful POC.

---

# Cut line for the weekend

The minimum successful build is:

```txt
bridger inspect
bridger init
bridger enrich-ticket "Improve onboarding error handling"
```

With outputs:

```txt
.bridger/repo-context.json
.bridger/file-index.json
.bridger/generated/*.md
AGENTS.generated.md
.bridger/tickets/<slug>.md
.bridger/tickets/<slug>.json
```

Do not continue to integrations until this local flow is genuinely useful.
