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

# Ticket 8 — Implement prioritized important file reader

## Objective

Read a curated, budgeted set of important files to provide grounded context to the LLM.

The goal is not to duplicate stack detection. `detectStack` and `detectCommands` already infer framework, tooling, and commands.

This reader should focus primarily on files that reveal:

```txt
codebase architecture
application entry points
domain/business logic
models, schemas, and types
data access patterns
UI/component conventions
testing patterns
existing agent/developer instructions
```

## Files

Create:

```txt
src/core/repo-scanner/read-important-files.ts
```

## Requirements

Implement:

```ts
export type ImportantFile = {
  path: string;
  reason: string;
  content: string;
};

export async function readImportantFiles(
  repoRoot: string,
): Promise<ImportantFile[]>;
```

The reader should discover, prioritize, and read a small set of useful files from the repo.

## Priority 1 — Existing agent/developer instructions

Read if present:

```txt
AGENTS.md
CLAUDE.md
```

Reason examples:

```txt
Existing agent instruction file
Existing Claude instruction file
```

## Priority 2 — Product/project documentation

Read if present, but keep capped:

```txt
README.md
docs/**/*.md
```

Reason examples:

```txt
Project README
Project documentation
```

Documentation is useful for product intent, but may be stale or verbose. It should not consume most of the content budget.

## Priority 3 — Application entry points

Prioritize files that reveal routing, layouts, pages, and API boundaries:

```txt
app/layout.*
app/page.*
app/**/page.*
app/**/layout.*
app/**/route.*
src/app/layout.*
src/app/page.*
src/app/**/page.*
src/app/**/layout.*
src/app/**/route.*
pages/_app.*
pages/index.*
pages/api/**
src/pages/**
```

Reason examples:

```txt
Application layout entry point
Application page/route entry point
API route entry point
```

## Priority 4 — Domain, model, schema, and data-access files

Prioritize files that reveal business logic, data models, validation schemas, and persistence boundaries:

```txt
src/core/**
src/domain/**
src/domains/**
src/models/**
src/entities/**
src/schemas/**
src/types/**
src/lib/**
lib/**
db/**
src/db/**
prisma/schema.prisma
drizzle/**
supabase/**
```

Reason examples:

```txt
Domain/business logic file
Model/schema/type definition file
Data access or persistence file
Infrastructure/helper file
```

## Priority 5 — Representative UI/component files

Read a representative sample from:

```txt
components/**
src/components/**
```

Prefer:

```txt
components/ui/**
src/components/ui/**
components/layout/**
src/components/layout/**
components/navigation/**
src/components/navigation/**
```

Reason examples:

```txt
Representative UI component file
Representative layout/navigation component file
```

## Priority 6 — Representative tests

Read a small sample from:

```txt
tests/**
__tests__/**
*.test.*
*.spec.*
```

Reason examples:

```txt
Representative test file
```

## Priority 7 — Small supporting config files only

Config files should be treated as supporting evidence, not core context.

Consider only small files such as:

```txt
components.json
tsconfig.json
next.config.*
tailwind.config.*
package.json
```

Reason examples:

```txt
Design system or component alias configuration
TypeScript path alias configuration
Framework configuration with possible repo-specific behavior
Tailwind theme/configuration
Package scripts and dependency manifest
```

Do not include lockfiles.

Do not allow config files to dominate the context budget.

## Budget rules

Use hard limits:

```ts
const MAX_SINGLE_FILE_BYTES = 20 * 1024;
const MAX_TOTAL_CONTENT_BYTES = 120 * 1024;
const MAX_CONFIG_TOTAL_BYTES = 20 * 1024;
```

Behavior:

```txt
Skip files larger than MAX_SINGLE_FILE_BYTES.
Stop reading once MAX_TOTAL_CONTENT_BYTES would be exceeded.
Stop reading config files once MAX_CONFIG_TOTAL_BYTES would be exceeded.
Do not silently read huge files.
```

## Binary and noisy file rules

Only read likely text/source files.

Allowed extensions should include:

```txt
.ts
.tsx
.js
.jsx
.mjs
.cjs
.json
.md
.mdx
.css
.scss
.sql
.prisma
.yaml
.yml
.toml
```

Skip binary/noisy files such as:

```txt
.png
.jpg
.jpeg
.gif
.webp
.svg
.ico
.mp4
.mov
.woff
.woff2
.ttf
.pdf
.zip
.tar
.gz
.sqlite
.db
```

Also skip generated/noisy folders:

```txt
node_modules
.next
dist
build
coverage
.git
.bridger
.agents
```

## Behavior

The implementation should:

```txt
1. Discover candidate files using deterministic filesystem heuristics.
2. Assign each candidate a priority and reason.
3. Deduplicate candidates by path.
4. Sort by priority, then by path.
5. Read files as UTF-8 only if they are within size limits and allowed extensions.
6. Track total content bytes.
7. Track config content bytes separately.
8. Return selected files with repo-relative paths.
9. Handle missing files gracefully.
10. Never call the LLM.
```

## Suggested internal candidate type

```ts
type ImportantFileCandidate = {
  path: string;
  reason: string;
  priority: number;
  category:
    | "agent"
    | "docs"
    | "entrypoint"
    | "domain"
    | "component"
    | "test"
    | "config";
};
```

## Acceptance criteria

- Does not read huge files.
- Does not read binary files.
- Prioritizes code architecture, domain/model/schema files, app entry points, representative components, and tests over config files.
- Includes existing agent/developer instructions when present.
- Includes README/docs when present, but capped.
- Includes only small supporting config files.
- Caps total config content separately from total content.
- Does not include lockfiles.
- Does not include `.bridger` or `.agents` generated files.
- Returns paths relative to repo root.
- Handles missing files gracefully.
- Does not call the LLM.
- Add at least one Vitest test using a fixture repo.

## Test expectations

Create or update a fixture repo with files such as:

```txt
tests/fixtures/important-files-basic/
  README.md
  AGENTS.md
  package.json
  tsconfig.json
  next.config.ts
  pnpm-lock.yaml
  src/
    app/
      layout.tsx
      page.tsx
      api/
        health/
          route.ts
    domains/
      billing/
        schema.ts
        service.ts
    lib/
      supabase.ts
    components/
      ui/
        button.tsx
      navigation/
        sidebar.tsx
    __tests__/
      billing.test.ts
  public/
    logo.png
  .bridger/
    generated/
      architecture.md
  .agents/
    skills/
      generated-skill/
        SKILL.md
```

Tests should verify:

- Important files include `AGENTS.md`, `README.md`, app entry points, domain/schema/service files, lib files, representative components, and tests.
- Important files do not include lockfiles.
- Important files do not include binary files such as `public/logo.png`.
- Important files do not include `.bridger` or `.agents` files.
- Large files above `MAX_SINGLE_FILE_BYTES` are skipped.
- Returned paths are relative to the repo root.
- Config files are included only if small.
- Config content does not exceed `MAX_CONFIG_TOTAL_BYTES`.
- Total returned content does not exceed `MAX_TOTAL_CONTENT_BYTES`.

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

# Ticket 12 — Add repo knowledge generation workflows

## Objective

Generate practical, repo-grounded Markdown documentation from repo structure, file index, important files, and selected source evidence.

This ticket introduces three single-pass documentation workflows:

``txt
architecture workflow -> architecture.md
coding conventions workflow -> conventions.md
business logic workflow -> business-logic.md
``

The goal is not to build the dynamic knowledge base yet. That will be implemented in Milestone 2.

For now, these workflows should use the same generation pattern:

``txt
RepoContext
FileIndex
FileIndexSummary
ImportantFiles
Prompt instructions
LLM generateText
Markdown section validation
``

Each workflow should have its own prompt and output file.

## Files

Create or update:

``txt
src/core/llm/prompts/repo-analysis-prompt.ts
src/core/llm/prompts/conventions-prompt.ts
src/core/llm/prompts/business-logic-prompt.ts

src/core/context-builder/generate-architecture-doc.ts
src/core/context-builder/generate-conventions-doc.ts
src/core/context-builder/generate-business-logic-doc.ts
``

If not already created by Ticket 11, also create:

``txt
src/core/context-builder/file-index-summary.ts
``

## Generated outputs

Later, the `init` command should write:

```txt
.bridger/generated/architecture.md
.bridger/generated/conventions.md
.bridger/generated/business-logic.md
```

## Shared input shape

Each generator should accept the same kind of input:

```ts
type GenerateRepoKnowledgeDocInput = {
  repoContext: RepoContext;
  fileIndex: FileIndex;
  importantFiles: ImportantFile[];
};
```

The exact type can be duplicated per generator or shared if useful.

## Shared rules

All workflows must follow these rules:

```txt
Use only provided context.
Do not invent architecture, conventions, domains, workflows, APIs, or business rules.
Reference real files and folders from the repo.
Distinguish observed facts from assumptions.
Mark missing or weak evidence as Unknown.
Prefer concise, practical guidance.
Avoid generic filler.
Do not generate tickets or implementation plans.
Output Markdown.
```

## Workflow 1 — Architecture documentation

Generate:

```txt
.bridger/generated/architecture.md
```

Prompt file:

```txt
src/core/llm/prompts/repo-analysis-prompt.ts
```

Generator file:

```txt
src/core/context-builder/generate-architecture-doc.ts
```

Required sections:

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

Purpose:

```txt
Give agents and developers a compact, evidence-based understanding of the repo structure.
```

The document should focus on:

```txt
repo purpose
detected stack
routing/application structure
important folders
visible domain boundaries
data flow assumptions
commands
risky or ambiguous areas
unknowns
```

Acceptance criteria:

- Produces Markdown.
- References real files/folders from the repo.
- Includes an `Unknowns` section.
- Avoids confident claims without evidence.
- Does not call the LLM directly outside the shared LLM client.
- Does not write files directly.

## Workflow 2 — Coding conventions documentation

Generate:

```txt
.bridger/generated/conventions.md
```

Prompt file:

```txt
src/core/llm/prompts/conventions-prompt.ts
```

Generator file:

```txt
src/core/context-builder/generate-conventions-doc.ts
```

Required sections:

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
Unknowns
```

Purpose:

```txt
Extract practical coding conventions from the actual codebase so future agents follow existing patterns instead of introducing inconsistent ones.
```

The document should focus on:

```txt
how TypeScript is used
component structure and composition
server/client boundaries
validation/schema patterns
styling patterns
data access patterns
test patterns
naming conventions
repo-specific do/don't rules
```

The document must separate:

```txt
Observed conventions
Recommended conventions
Unknowns
```

Acceptance criteria:

- Produces Markdown.
- Separates observed conventions from recommendations.
- Mentions uncertainty when patterns are weak.
- References real source files when describing conventions.
- Avoids generic filler.
- Includes `Things agents should avoid`.
- Includes `Unknowns`.
- Does not call the LLM directly outside the shared LLM client.
- Does not write files directly.

## Workflow 3 — Business logic documentation

Generate:

```txt
.bridger/generated/business-logic.md
```

Prompt file:

```txt
src/core/llm/prompts/business-logic-prompt.ts
```

Generator file:

```txt
src/core/context-builder/generate-business-logic-doc.ts
```

Required sections:

```txt
Product/domain overview
Observed domain concepts
Observed entities and models
Observed business rules
Observed workflows
Data ownership and persistence
External integrations
Assumptions
Unknowns
Evidence map
```

Purpose:

```txt
Extract the real-world concepts and business meaning represented in the codebase.
```

The document should focus on:

```txt
business/domain concepts
entities and models
schemas and validation rules
real-world objects represented in code
business rules and invariants
workflow states and lifecycle concepts
data persistence and ownership
external integrations
unknown or ambiguous business logic
```

The document must distinguish:

```txt
Observed facts
Assumptions
Unknowns
```

The document must not invent business logic.

Examples of valid claims:

```txt
Observed: `src/domains/billing/schema.ts` defines a `Subscription` schema.
Assumption: This likely represents a customer's billing plan relationship.
Unknown: The subscription lifecycle is not clear from the selected files.
```

Examples of invalid claims:

```txt
The app charges customers monthly through Stripe.
Users receive invoices after every payment.
The onboarding workflow has three steps.
```

unless these claims are supported by provided source files.

Acceptance criteria:

- Produces Markdown.
- Identifies business/domain concepts only when supported by source evidence.
- References real files/folders from the repo.
- Separates observed facts, assumptions, and unknowns.
- Includes an `Evidence map`.
- Avoids invented product behavior.
- Avoids generic filler.
- Does not call the LLM directly outside the shared LLM client.
- Does not write files directly.

## Shared implementation requirements

Each generator should:

```txt
1. Build its prompt from RepoContext, FileIndexSummary, and ImportantFiles.
2. Call generateText from the LLM client.
3. Validate that required Markdown sections are present.
4. Return the Markdown string.
```

Each generator should not:

```txt
write files
create folders
call OpenAI SDK directly
read the filesystem
modify RepoContext
perform dynamic knowledge-base discovery
```

## Prompt requirements

Each prompt should:

```txt
include repo context JSON
include compact file index summary
include important file excerpts
state required output sections
state evidence and uncertainty rules
forbid hallucinated claims
require real file references
```

## Section validation

Each generated document should have a lightweight assertion helper.

Examples:

```ts
assertArchitectureDoc(markdown: string): void
assertConventionsDoc(markdown: string): void
assertBusinessLogicDoc(markdown: string): void
```

Each assertion should verify that the required sections are present.

If required sections are missing, throw a useful error listing missing sections.

## RepoContext generated docs update

Update the generated docs schema to include:

```txt
businessLogicPath
```

Expected generated doc paths:

```txt
architecturePath: ".bridger/generated/architecture.md"
conventionsPath: ".bridger/generated/conventions.md"
businessLogicPath: ".bridger/generated/business-logic.md"
testingPath: ".bridger/generated/testing.md"
agentRulesPath: ".bridger/generated/agent-rules.md"
ticketTemplatePath: ".bridger/generated/ticket-template.md"
```

Update any builder/helper that returns generated doc paths.

## Acceptance criteria

- `generateArchitectureDoc` exists and returns Markdown.
- `generateConventionsDoc` exists and returns Markdown.
- `generateBusinessLogicDoc` exists and returns Markdown.
- Each generator uses `generateText` from the shared LLM client.
- No generator writes files directly.
- No generator calls the OpenAI SDK directly.
- Each prompt includes repo context, file index summary, and important file excerpts.
- Each generated document has required section validation.
- `RepoContextGeneratedDocsSchema` includes `businessLogicPath`.
- Stable generated doc paths are repo-relative.
- No dynamic knowledge-base workflow is implemented in this ticket.

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



# Milestone 2 — Dynamic repo knowledge base compiler

## Goal

Build the first version of Bridger’s persistent repo knowledge base.

The v0 POC generates one-shot repo artifacts:

``txt
.bridger/generated/architecture.md
.bridger/generated/conventions.md
.bridger/generated/business-logic.md
.bridger/generated/testing.md
.bridger/generated/agent-rules.md
``

Milestone 2 introduces a more durable knowledge layer:

``txt
.bridger/knowledge/
  manifest.json
  conventions/
    overview.md
    typescript.md
    components.md
    validation.md
    data-access.md
    testing.md
  domain/
    overview.md
    concepts/
      <concept>.md
    workflows/
      <workflow>.md
  evidence/
    claims.json
    source-map.json
``

This knowledge base should be compiled from repo files and maintained as Markdown so it remains readable by humans, Codex, Claude Code, and future agent workflows.

The first milestone should only build the initial knowledge base. It should not implement automatic update-on-change yet.

---

# Ticket KB-1 — Define knowledge base architecture and schemas

## Objective

Define the structure, manifest, page types, and evidence model for Bridger’s repo knowledge base.

## Scope

Create schemas/models for:

``txt
Knowledge base manifest
Knowledge source files
Knowledge pages
Knowledge page kinds
Evidence claims
Source references
Confidence levels
Workflow run metadata
``

## Expected outputs

The system should be able to represent:

``txt
- convention pages
- business/domain concept pages
- workflow pages
- overview pages
- evidence references back to source files
- unresolved unknowns
- confidence levels
``

## Notes

This ticket should keep the model simple enough for the POC extension.

The knowledge base should be file-based and Markdown-first.

Do not introduce vector databases, graph databases, SaaS storage, or background synchronization yet.

---

# Ticket KB-2 — Define knowledge base folder structure and page templates

## Objective

Create the static folder layout and Markdown templates used by the knowledge compiler.

## Scope

Define templates for:

``txt
conventions/overview.md
conventions/typescript.md
conventions/components.md
conventions/validation.md
conventions/data-access.md
conventions/testing.md

domain/overview.md
domain/concepts/<concept>.md
domain/workflows/<workflow>.md

evidence/claims.json
evidence/source-map.json
manifest.json
``

## Page requirements

Each knowledge page should include:

``txt
Title
Purpose
Observed facts
Assumptions
Unknowns
Source files
Related pages
Last generated metadata
``

Domain concept pages should additionally include:

``txt
Definition
Real-world meaning
Code representation
Fields / attributes
Lifecycle / states
Business rules
Related concepts
Evidence
Open questions
``

Convention pages should additionally include:

``txt
Observed patterns
Examples from source files
Recommended agent behavior
Things agents should avoid
Confidence level
``

## Notes

The templates should be explicit enough that an LLM agent can update them consistently later.

---

# Ticket KB-3 — Implement knowledge source selection

## Objective

Select the source files that should be used to compile the knowledge base.

## Scope

Reuse existing POC artifacts:

``txt
FileIndex
RepoContext
ImportantFile reader
File index summary
``

The source selector should prioritize:

``txt
domain/business logic files
models, schemas, and types
data access files
app entry points
API routes
representative components
representative tests
existing docs and agent instructions
``

## Expected behavior

The selector should produce a bounded set of source files for knowledge compilation.

It should preserve evidence metadata:

``txt
path
reason
category
size
tags
selected_for
``

## Notes

This ticket should reuse the FileIndex. It should not rediscover files from scratch.

---

# Ticket KB-4 — Implement file relationship discovery graph

## Objective

Build a lightweight file relationship graph to support guided source expansion.

## Scope

Create a deterministic graph of relationships between source files.

Relationship types may include:

``txt
imports
exports
same folder
same domain folder
schema-to-service proximity
test-to-source proximity
route-to-component proximity
config-to-convention relevance
``

## Expected output

For a selected source file, Bridger should be able to find likely related files.

Example:

``txt
src/domains/billing/service.ts
  imports -> src/domains/billing/schema.ts
  related_test -> src/domains/billing/service.test.ts
  same_domain -> src/domains/billing/repository.ts
``

## Notes

This does not need a full AST engine in v1.

Start with simple import parsing and path heuristics.

The purpose is to guide the LLM toward relevant neighboring files instead of relying only on a flat file list.

---

# Ticket KB-5 — Design the knowledge compiler agent loop

## Objective

Define the reusable agentic workflow used to compile knowledge pages from source files.

## Scope

Design a bounded, tool-driven loop that can:

``txt
read selected source files
request related files from the graph
inspect existing knowledge pages
propose knowledge page changes
record evidence
write or update Markdown pages
record unresolved unknowns
``

## Required constraints

The loop must be bounded by:

``txt
max iterations
max files read
max total content read
max pages written
max LLM calls
``

## Notes

This ticket is design/scaffolding first.

Do not implement automatic continuous updates yet.

Do not let the agent write arbitrary repo files.

The agent should only write under:

``txt
.bridger/knowledge/
``

---

# Ticket KB-6 — Define LLM tool interface for knowledge compilation

## Objective

Define the internal tools available to the knowledge compiler agent.

## Candidate tools

``txt
list_source_files
read_source_file
find_related_files
read_knowledge_page
write_knowledge_page
append_evidence_claim
list_unknowns
finalize_compilation
``

## Tool rules

Tools should be deterministic and permissioned.

The agent should not directly access the filesystem.

All source reads should go through tool wrappers that enforce:

``txt
repo-relative paths
allowed file index entries
size limits
read budgets
``

All writes should be restricted to:

``txt
.bridger/knowledge/
``

## Notes

This ticket should define the tool contracts and safety model.

Implementation can come later.

---

# Ticket KB-7 — Implement convention knowledge workflow

## Objective

Implement the first knowledge compiler workflow for coding conventions.

## Input

``txt
RepoContext
FileIndex
ImportantFiles
File relationship graph
Existing knowledge pages if present
``

## Output

``txt
.bridger/knowledge/conventions/overview.md
.bridger/knowledge/conventions/typescript.md
.bridger/knowledge/conventions/components.md
.bridger/knowledge/conventions/validation.md
.bridger/knowledge/conventions/data-access.md
.bridger/knowledge/conventions/testing.md
``

## The workflow should extract

``txt
TypeScript conventions
component conventions
server/client boundaries
validation patterns
styling conventions
data access conventions
testing patterns
naming conventions
agent-safe implementation rules
things agents should avoid
``

## Notes

This should go deeper than the v0 `conventions.md`.

The generated one-shot `conventions.md` can later be rendered from this knowledge base.

---

# Ticket KB-8 — Implement business logic knowledge workflow

## Objective

Implement the knowledge compiler workflow for business/domain understanding.

## Input

``txt
RepoContext
FileIndex
ImportantFiles
File relationship graph
Existing knowledge pages if present
``

## Output

``txt
.bridger/knowledge/domain/overview.md
.bridger/knowledge/domain/concepts/<concept>.md
.bridger/knowledge/domain/workflows/<workflow>.md
``

## The workflow should extract

``txt
real-world concepts represented in code
domain entities
business objects
schemas and data models
lifecycle states
business rules
domain workflows
permissions and access rules
external integrations
data transformations
unknown or ambiguous business logic
``

## Notes

A concept page should only be created when there is concrete file evidence.

The workflow must distinguish:

``txt
Observed facts
Assumptions
Unknowns
``

The goal is to make future ticket enrichment more grounded in business meaning, not only code structure.

---

# Ticket KB-9 — Implement evidence and provenance tracking

## Objective

Track which source files support which knowledge claims.

## Scope

Create a lightweight evidence layer under:

``txt
.bridger/knowledge/evidence/
  claims.json
  source-map.json
``

## Each evidence claim should capture

``txt
claim
claim type
source files
source excerpts or line references if available
confidence
knowledge page path
created_at
``

## Notes

This is critical for trust.

Bridger should avoid writing knowledge that cannot be traced back to source files.

Line references are optional in the first version.

---

# Ticket KB-10 — Implement knowledge base writer

## Objective

Write the generated knowledge pages and manifest to disk.

## Scope

The writer should create:

``txt
.bridger/knowledge/
.bridger/knowledge/manifest.json
.bridger/knowledge/conventions/*
.bridger/knowledge/domain/*
.bridger/knowledge/evidence/*
``

## Requirements

The writer should:

``txt
create parent directories
write Markdown with stable formatting
write JSON with stable pretty formatting
avoid writing outside .bridger/knowledge
preserve deterministic paths
``

## Notes

The writer should reuse existing output utilities where possible.

---

# Ticket KB-11 — Implement knowledge base initialization command flow

## Objective

Add a command or init option to compile the knowledge base.

## Candidate command

``txt
bridger init --knowledge
``

or:

``txt
bridger build-knowledge
``

## Expected behavior

The command should:

``txt
build repo context
build file index
select knowledge source files
build file relationship graph
run convention knowledge workflow
run business logic knowledge workflow
write knowledge pages
write manifest and evidence files
print summary
``

## Notes

For the first version, prefer an explicit command or flag.

Do not make knowledge compilation automatic until the basic POC flow is stable.

---

# Ticket KB-12 — Render generated docs from knowledge base

## Objective

Use the knowledge base to improve one-shot generated docs.

## Scope

Generate or regenerate:

``txt
.bridger/generated/conventions.md
.bridger/generated/business-logic.md
.bridger/generated/agent-rules.md
``

from the compiled knowledge base.

## Notes

This creates a clean separation:

``txt
.bridger/knowledge/* = durable compiled repo memory
.bridger/generated/* = compact artifacts for agents and humans
``

The generated docs should become summaries of the knowledge base, not the knowledge base itself.

---

# Ticket KB-13 — Add manual evaluation checklist for knowledge base quality

## Objective

Create a manual evaluation checklist for the compiled knowledge base.

## File

``txt
docs/knowledge-evaluation.md
``

## Evaluation questions

``txt
Did the compiler identify real domain concepts?
Did it avoid invented business logic?
Are claims linked to source files?
Are coding conventions specific to the repo?
Are unknowns useful?
Would this help a coding agent implement a ticket?
Would this help a new developer understand the repo?
Did it overfit to config/docs instead of code?
Did it miss important folders?
``

## Scoring

Use:

``txt
1 = poor
2 = weak
3 = acceptable
4 = good
5 = excellent
``

Score:

``txt
Domain concept quality
Convention specificity
Evidence quality
Unknowns quality
Agent usefulness
Hallucination control
Overall value
``

---

# Ticket KB-14 — Smoke test knowledge compiler on one real repo

## Objective

Run the knowledge compiler on one real Next.js/TypeScript repo and evaluate output quality.

## Steps

Run:

``txt
bridger inspect
bridger init
bridger build-knowledge
``

Inspect:

``txt
.bridger/knowledge/manifest.json
.bridger/knowledge/conventions/*
.bridger/knowledge/domain/*
.bridger/knowledge/evidence/*
.bridger/generated/conventions.md
.bridger/generated/business-logic.md
``

## Acceptance criteria

``txt
Knowledge pages are generated.
Pages reference real source files.
Domain concepts are not hallucinated.
Coding conventions are repo-specific.
Unknowns are explicit.
At least 3 improvement ideas are documented.
``

---

# Milestone 2 cut line

The minimum useful knowledge-base milestone is:

``txt
bridger build-knowledge
``

with outputs:

``txt
.bridger/knowledge/manifest.json
.bridger/knowledge/conventions/overview.md
.bridger/knowledge/domain/overview.md
.bridger/knowledge/evidence/claims.json
``

If time is short, stop after:

``txt
KB-1
KB-2
KB-3
KB-4
KB-7
KB-8
KB-10
KB-13
``

Do not implement automatic updates until the first knowledge compilation workflow is useful.