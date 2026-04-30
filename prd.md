# Compact PRD — Agent-Ready Ticket Compiler POC

## 1. Product summary

**Agent-Ready** is a local CLI that scans a software repository, generates AI-readiness documentation, and enriches rough product/dev requests into implementation-ready tickets for humans and AI coding agents.

The POC focuses on one core question:

> Can repo-grounded context make ticket enrichment significantly better than generic ChatGPT/Claude prompting?

The product should help teams prepare better work units before delegating to developers, Claude Code, Codex, Cursor, Copilot, or other coding agents.

---

## 2. Target user

Primary POC user:

> AI-forward developers, founders, tech leads, or small teams using TypeScript/Next.js and experimenting with coding agents.

Secondary user:

> PM/founder/non-technical stakeholder who writes rough product requests that need to become actionable engineering tickets.

---

## 3. Core pain

Modern AI coding agents are useful, but they fail or require too much steering when:

* tickets are vague;
* acceptance criteria are missing;
* product context is scattered;
* repo conventions are undocumented;
* agents do not know which files or domains matter;
* teams cannot decide whether a task is agent-suitable;
* devs spend time clarifying low-quality requests.

---

## 4. POC scope

### In scope

The POC ships as a local TypeScript CLI.

Core commands:

```txt
agent-ready init
agent-ready inspect
agent-ready enrich-ticket "Improve onboarding error handling"
agent-ready enrich-ticket --file rough-ticket.md
```

The POC should:

* detect the repo stack;
* scan important files;
* infer commands from `package.json`;
* generate repo AI-readiness docs;
* generate `AGENTS.md`;
* enrich rough tickets using repo context;
* output enriched tickets as Markdown;
* output structured JSON for future reuse.

### Out of scope

Do not build in the POC:

* SaaS dashboard;
* auth;
* billing;
* GitHub app;
* Jira/GitLab/Linear integrations;
* MCP server;
* vector database;
* background coding agents;
* branch creation;
* PR automation;
* multi-tenant architecture;
* hosted repo sync.

---

## 5. Supported stack for POC

Start narrow.

Supported target repos:

```txt
Next.js
TypeScript
pnpm/npm/yarn/bun
Tailwind optional
shadcn/ui optional
Zod optional
Supabase/Prisma/Drizzle optional
Vitest/Jest/Playwright/Cypress optional
```

The CLI can run on any repo, but output quality is optimized for Next.js/TypeScript.

---

## 6. User stories

### Story 1 — Generate repo AI-readiness docs

As a developer, I run:

```txt
agent-ready init
```

The CLI scans my repo and generates:

```txt
.agent-ready/
  repo-context.json
  file-index.json
  generated/
    architecture.md
    conventions.md
    testing.md
    agent-rules.md
    ticket-template.md

AGENTS.md
```

### Story 2 — Inspect repo detection

As a developer, I run:

```txt
agent-ready inspect
```

The CLI prints:

```txt
Framework: Next.js
Language: TypeScript
Package manager: pnpm
Styling: Tailwind, shadcn/ui
Validation: Zod
Database: Supabase
Test framework: Vitest
Commands:
- dev: pnpm dev
- lint: pnpm lint
- typecheck: pnpm typecheck
- test: pnpm test
```

### Story 3 — Enrich rough ticket

As a developer or PM, I run:

```txt
agent-ready enrich-ticket "Improve onboarding error handling"
```

The CLI outputs:

```txt
.agent-ready/tickets/improve-onboarding-error-handling.md
.agent-ready/tickets/improve-onboarding-error-handling.json
```

The ticket includes:

* title;
* goal;
* current behavior;
* desired behavior;
* repo-specific context;
* suggested files;
* acceptance criteria;
* constraints;
* test expectations;
* missing questions;
* assumptions;
* risk level;
* agent suitability score;
* agent handoff prompt.

---

## 7. Success criteria

The POC is successful if, on 5 real tickets across 2–3 repos:

1. It identifies relevant files correctly at least ~70% of the time.
2. The enriched ticket is clearly better than the rough input.
3. The generated acceptance criteria are usable with minimal edits.
4. The output includes repo-specific conventions, not generic advice.
5. The handoff prompt is good enough to paste into Claude Code/Codex/Cursor.
6. The tool surfaces useful missing questions.
7. The generated `AGENTS.md` is something a developer would commit or adapt.

The POC fails if:

* output is mostly generic;
* it hallucinates repo structure;
* suggested files are consistently wrong;
* the enriched ticket is not better than a generic LLM prompt;
* developers would not use the result.

---

# Start Guide — Weekend Build Plan

## 1. Recommended stack

```txt
Language: TypeScript
Runtime: Node.js 20+
Package manager: pnpm
CLI framework: commander or cac
Validation: zod
File scanning: fast-glob
Gitignore support: ignore
Markdown output: plain string templates
LLM: OpenAI SDK or Anthropic SDK
Env: dotenv
Formatting/linting: eslint + prettier or biome
Testing: vitest
```

Recommended libraries:

```txt
commander
zod
fast-glob
ignore
dotenv
fs-extra
execa
slugify
@ai-sdk/openai or openai
```

Use one LLM provider only for the POC. Provider abstraction can come later.

---

## 2. Package structure

Start with a single package. Avoid monorepo overhead for the POC.

```txt
agent-ready/
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
          ticket-enrichment-prompt.ts

      models/
        repo-context.ts
        file-index.ts
        ticket.ts
        config.ts

      output/
        write-json.ts
        write-markdown.ts
        ensure-output-dirs.ts

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

---

## 3. CLI commands

### `agent-ready inspect`

Purpose:

> Fast local repo diagnosis without calling the LLM.

Responsibilities:

* detect framework;
* detect language;
* detect package manager;
* detect styling tools;
* detect validation libraries;
* detect DB tools;
* detect test frameworks;
* detect useful scripts.

Output to terminal only.

Example:

```txt
agent-ready inspect
```

Expected output:

```txt
Agent-Ready Inspect

Repo: /Users/me/project
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
```

---

### `agent-ready init`

Purpose:

> Generate the local repo AI-readiness context.

Responsibilities:

* run repo scanner;
* build file index;
* read important files;
* call LLM for repo docs;
* write `.agent-ready/` files;
* write or update `AGENTS.md`.

Output files:

```txt
.agent-ready/repo-context.json
.agent-ready/file-index.json
.agent-ready/generated/architecture.md
.agent-ready/generated/conventions.md
.agent-ready/generated/testing.md
.agent-ready/generated/agent-rules.md
.agent-ready/generated/ticket-template.md
AGENTS.md
```

---

### `agent-ready enrich-ticket`

Purpose:

> Convert rough request into agent-ready ticket.

Supported inputs:

```txt
agent-ready enrich-ticket "Improve onboarding error handling"
agent-ready enrich-ticket --file rough-ticket.md
```

Responsibilities:

* load `.agent-ready/repo-context.json`;
* load generated docs;
* select relevant files based on ticket keywords;
* call LLM with repo context + rough ticket;
* validate structured output with Zod;
* write Markdown and JSON outputs.

Output files:

```txt
.agent-ready/tickets/<slug>.md
.agent-ready/tickets/<slug>.json
```

---

# 4. Core data models

## `RepoContext`

```ts
import { z } from "zod";

export const RepoContextSchema = z.object({
  repoRoot: z.string(),
  generatedAt: z.string(),

  stack: z.object({
    framework: z.string(),
    language: z.string(),
    packageManager: z.string(),
    styling: z.array(z.string()),
    validation: z.array(z.string()),
    database: z.array(z.string()),
    testFramework: z.array(z.string()),
  }),

  commands: z.object({
    install: z.string().optional(),
    dev: z.string().optional(),
    build: z.string().optional(),
    lint: z.string().optional(),
    typecheck: z.string().optional(),
    test: z.string().optional(),
    format: z.string().optional(),
  }),

  importantFiles: z.array(
    z.object({
      path: z.string(),
      reason: z.string(),
    })
  ),

  generatedDocs: z.object({
    architecturePath: z.string(),
    conventionsPath: z.string(),
    testingPath: z.string(),
    agentRulesPath: z.string(),
    ticketTemplatePath: z.string(),
  }),
});

export type RepoContext = z.infer<typeof RepoContextSchema>;
```

---

## `FileIndex`

```ts
export const FileIndexEntrySchema = z.object({
  path: z.string(),
  extension: z.string().optional(),
  sizeBytes: z.number(),
  reason: z.string().optional(),
  tags: z.array(z.string()).default([]),
});

export const FileIndexSchema = z.object({
  generatedAt: z.string(),
  files: z.array(FileIndexEntrySchema),
});

export type FileIndex = z.infer<typeof FileIndexSchema>;
```

---

## `EnrichedTicket`

```ts
export const EnrichedTicketSchema = z.object({
  title: z.string(),
  goal: z.string(),

  userImpact: z.string().optional(),
  currentBehavior: z.string().optional(),
  desiredBehavior: z.string(),

  repoContext: z.array(z.string()),

  acceptanceCriteria: z.array(z.string()),
  constraints: z.array(z.string()),

  suggestedFiles: z.array(
    z.object({
      path: z.string(),
      reason: z.string(),
    })
  ),

  testExpectations: z.array(z.string()),
  missingQuestions: z.array(z.string()),
  assumptions: z.array(z.string()),

  riskLevel: z.enum(["low", "medium", "high"]),

  agentSuitability: z.object({
    score: z.number().min(0).max(100),
    label: z.enum(["poor", "medium", "good", "excellent"]),
    reason: z.string(),
  }),

  handoffPrompt: z.string(),
});

export type EnrichedTicket = z.infer<typeof EnrichedTicketSchema>;
```

---

# 5. Repo scanning logic

## Files to include

Prioritize:

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

## Files to exclude

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
*.lock noise except package manager detection
large binary files
images
videos
fonts
```

Respect `.gitignore`.

---

## Stack detection heuristics

From `package.json` dependencies:

```txt
next -> Next.js
typescript -> TypeScript
tailwindcss -> Tailwind
zod -> Zod
@supabase/supabase-js -> Supabase
prisma -> Prisma
drizzle-orm -> Drizzle
vitest -> Vitest
jest -> Jest
playwright -> Playwright
cypress -> Cypress
```

From files:

```txt
app/ -> Next.js App Router
pages/ -> Next.js Pages Router
components.json -> shadcn/ui
supabase/ -> Supabase
prisma/schema.prisma -> Prisma
drizzle.config.* -> Drizzle
```

Package manager:

```txt
pnpm-lock.yaml -> pnpm
yarn.lock -> yarn
package-lock.json -> npm
bun.lockb or bun.lock -> bun
```

---

# 6. LLM prompts

## Repo analysis prompt

Goal:

> Generate grounded repo docs. Do not invent architecture. Use only provided file tree, selected files, package metadata, and existing docs.

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

Important rule:

```txt
If information is not present in the provided context, mark it as unknown instead of guessing.
```

---

## Conventions prompt

Goal:

> Infer practical coding conventions from the repo.

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
Things agents should avoid
```

Important rule:

```txt
Separate observed conventions from recommended conventions.
```

---

## Ticket enrichment prompt

Input:

* rough ticket;
* repo context;
* generated docs;
* selected relevant files;
* commands;
* team rules if available.

Output:

* strict JSON matching `EnrichedTicketSchema`.

Important rules:

```txt
Do not invent exact file behavior if not provided.
Prefer "appears to" or "likely" when uncertain.
Mark assumptions explicitly.
Surface missing questions.
Keep the task scoped.
Prefer concrete acceptance criteria.
Suggest files only when there is evidence from file paths or provided snippets.
```

---

# 7. Relevant file selection

For POC, use heuristic search. No embeddings.

Algorithm:

1. Lowercase rough ticket.
2. Extract meaningful keywords.
3. Match keywords against file paths.
4. Add domain synonyms manually for common words.
5. Include top N path matches.
6. Include package/config/docs.
7. Limit total selected content to token budget.

Example synonym map:

```ts
const DOMAIN_SYNONYMS: Record<string, string[]> = {
  onboarding: ["onboarding", "signup", "setup", "getting-started"],
  auth: ["auth", "login", "session", "oauth"],
  github: ["github", "git", "installation", "repository"],
  error: ["error", "exception", "failure", "toast", "alert"],
  billing: ["billing", "stripe", "subscription", "plan"],
  dashboard: ["dashboard", "analytics", "metrics"],
};
```

For the POC, “good enough” file retrieval is acceptable.

---

# 8. Weekend implementation plan

## Phase 1 — CLI skeleton

Deliverables:

* package setup;
* `bin` entry;
* `agent-ready --help`;
* commands registered;
* `.env.example`.

Suggested `package.json` fields:

```json
{
  "name": "agent-ready",
  "version": "0.0.1",
  "type": "module",
  "bin": {
    "agent-ready": "./dist/cli/index.js"
  },
  "scripts": {
    "dev": "tsx src/cli/index.ts",
    "build": "tsc",
    "typecheck": "tsc --noEmit",
    "test": "vitest"
  }
}
```

---

## Phase 2 — Repo scanner

Deliverables:

* `scanRepo(repoRoot)`
* `detectStack(repoRoot)`
* `detectCommands(packageJson)`
* `buildFileIndex(repoRoot)`
* `.gitignore` support
* `inspect` command working

Success:

```txt
pnpm dev inspect
```

prints useful repo facts without LLM.

---

## Phase 3 — Context generator

Deliverables:

* `buildRepoContext`
* LLM client
* architecture doc generation
* conventions doc generation
* testing doc generation
* agent rules generation
* `AGENTS.md` generation

Success:

```txt
pnpm dev init
```

generates `.agent-ready/` and `AGENTS.md`.

---

## Phase 4 — Ticket compiler

Deliverables:

* rough ticket input support;
* file-based ticket input support;
* relevant file selection;
* structured LLM ticket output;
* Zod validation;
* Markdown rendering;
* ticket JSON output.

Success:

```txt
pnpm dev enrich-ticket "Improve onboarding error handling"
```

generates a useful enriched ticket.

---

## Phase 5 — Manual evaluation

Test on:

* one personal Next.js project;
* one repo with auth/onboarding;
* one repo with a dashboard or API domain.

For each, test 2 rough tickets:

```txt
Improve onboarding error handling
Add loading states to dashboard cards
Refactor GitHub sync errors
Add empty state to repo list
Improve settings form validation
```

Compare:

* generic ChatGPT output;
* Agent-Ready output;
* what you would actually give Claude Code/Codex.

---

# 9. Example output format

Generated ticket Markdown should look like this:

```md
# Improve onboarding error handling for GitHub connection failures

## Goal

Improve the onboarding flow so users receive specific, actionable feedback when GitHub connection fails.

## Current behavior

The current repo context suggests onboarding logic exists under `/app/onboarding` and GitHub-related logic under `/lib/github`. The exact current error behavior needs confirmation.

## Desired behavior

Users should understand what failed and how to retry without restarting onboarding.

## Relevant repo context

- The app uses Next.js with TypeScript.
- UI components should reuse existing shadcn/ui components where possible.
- External inputs and API payloads should be validated with Zod.
- GitHub-related logic appears to live under `/lib/github`.

## Acceptance criteria

- Display specific messages for expired OAuth state, missing installation, and GitHub API failure.
- Preserve the current onboarding step after a recoverable failure.
- Add or update tests for error mapping logic if a test pattern exists.
- Do not modify billing, organization setup, or unrelated auth logic.

## Suggested files

- `/app/onboarding/...` — likely onboarding UI and flow logic.
- `/lib/github/...` — likely GitHub integration logic.
- `/components/onboarding/...` — likely reusable onboarding UI components.

## Test expectations

- Run `pnpm typecheck`.
- Run `pnpm lint`.
- Add or update tests around error mapping if an existing test framework is present.

## Missing questions

- Should error messages be localized?
- Should failures be logged for debugging?
- Should the user be able to retry from the same screen?

## Assumptions

- GitHub connection is part of onboarding.
- Error handling is currently too generic.
- The task should stay scoped to user-facing error behavior.

## Risk level

Medium-low.

## Agent suitability

Score: 82/100  
Label: good

Reason: The task is scoped, likely localized to onboarding/GitHub integration files, and has clear acceptance criteria. It should avoid touching auth, billing, or organization setup logic.

## Agent handoff prompt

You are working in this repository. Follow `AGENTS.md` and the generated repo conventions.

Task:
Improve onboarding error handling for GitHub connection failures.

Scope:
...
```

---

# 10. Implementation principles

Keep these constraints strict:

1. **No SaaS architecture in the POC.**
2. **No provider abstraction until needed.**
3. **No embeddings until keyword retrieval fails.**
4. **No GitHub app until local CLI value is proven.**
5. **No generated code execution.**
6. **No automatic file modifications except `.agent-ready/` and `AGENTS.md`.**
7. **Everything generated should be reviewable and editable.**
8. **Prefer explicit unknowns over hallucinated confidence.**
9. **Optimize for useful outputs, not architectural elegance.**
10. **The output must be better than generic ChatGPT.**

---

# 11. Suggested development order

Build in this exact order:

```txt
1. inspect command
2. repo scanner
3. file index
4. init command without LLM
5. LLM-generated docs
6. AGENTS.md generation
7. enrich-ticket command with rough string input
8. relevant file selector
9. structured ticket output
10. markdown renderer
11. manual evaluation
```

Avoid building the final product shell before the core output is useful.

---

# 12. Future paths after POC

Only after validating the local CLI:

## Path A — Hosted ticket compiler

Upload or sync `.agent-ready/` context and use a web UI to create enriched tickets.

## Path B — MCP server

Expose repo context and ticket enrichment to Claude/ChatGPT.

Resources:

```txt
repo://architecture
repo://conventions
repo://testing
repo://agent-rules
```

Tools:

```txt
search_repo_context
enrich_ticket
score_agent_suitability
generate_handoff_prompt
```

## Path C — GitHub/GitLab app

Comment on issues with:

* readiness score;
* missing context;
* suggested acceptance criteria;
* agent handoff prompt.

## Path D — Jira/Notion integration

Export enriched tickets into existing PM workflows.

---

# 13. Final POC definition

The weekend POC is successful if this works:

```txt
cd my-nextjs-repo
agent-ready init
agent-ready enrich-ticket "Improve onboarding error handling"
```

And the resulting ticket is specific enough that you would confidently paste the handoff prompt into Claude Code or Codex.
