# Bridger v0 Core Engine Workplan

## Purpose

This document defines the ordered workstreams required to turn Bridger into a credible v0 for both existing repositories and fresh hackathon repositories.

The goal is not to list every implementation ticket yet. The goal is to define the major feature blocks and core engines that must be implemented, what each block is responsible for, how it fits into the product, and what “done” means for each block.

Bridger v0 should prove one thing:

> Coding agents perform better when they receive Bridger-generated project context, instructions, and task-specific prompts.

## Product direction

Bridger supports two repository lifecycle modes.

### Existing repo mode

For mature or partially mature repositories, Bridger acts as a codebase context compiler.

```txt
existing codebase
→ deterministic codebase intelligence
→ specialized memory agents
→ .bridger memory layer
→ AGENTS.md / other exports
→ task-specific prompts
```

### Fresh repo mode

For new hackathon-style repositories, Bridger acts as a project-start context harness.

```txt
fresh repo
→ project brief + selected skills + agent rules
→ initial .bridger context layer
→ AGENTS.md
→ task-specific prompts
→ update as codebase grows
```

Fresh mode should not pretend to infer deep architecture from an empty repository. It should seed explicit intent, rules, selected skills, and prompting discipline first. As the repository grows, `bridger update` should progressively convert observed code into compiled memory.

---

# Guiding principles

## 1. Deterministic first

Bridger should extract and structure as much context as possible without LLM calls before asking any memory agent to interpret the repository.

The deterministic layer owns:

- file discovery;
- skip rules;
- file role tagging;
- import graph construction;
- entrypoint detection;
- framework and schema signals;
- CodebaseMap generation;
- ReadingPlan generation;
- affected traversal;
- artifact validation.

## 2. LLM agents are bounded transformations

Specialized memory agents should not freely explore the repository. They should receive curated context produced by the deterministic compiler.

Each memory agent has:

- a clear purpose;
- a target memory file;
- a reading plan;
- grounding rules;
- required output sections;
- an unknowns policy.

## 3. `.bridger/memory` is canonical

Root-level files such as `AGENTS.md`, `CLAUDE.md`, Cursor rules, or Copilot instructions should be treated as exports.

The canonical internal state is:

```txt
.bridger/memory/*
.bridger/config.json
.bridger/artifacts/*
.bridger/skills/*
```

## 4. Fresh mode stores declared intent separately from observed facts

Fresh repositories contain little or no codebase evidence. Therefore Bridger must clearly separate:

- user-declared project intent;
- selected generic skills;
- observed codebase facts;
- inferred conventions;
- unknowns.

## 5. Reviewability matters

Bridger should avoid silently overwriting trusted project context. For v0, it can regenerate files, but it should show clear summaries of what changed or what was produced. Later versions should move toward reviewable diffs.

---

# Target v0 command surface

The v0 command surface should be small and coherent.

```bash
bridger init
bridger init --fresh
bridger update
bridger prompt "Add feature X"
bridger inspect
bridger inspect --graph
```

Optional later commands:

```bash
bridger skills list
bridger skills add <skill>
bridger exports generate
bridger doctor
```

For v0, these optional actions can be handled inside `init`, `init --fresh`, and `update` instead of becoming separate commands immediately.

---

# Workstream 0 — Project state, configuration, and file layout

## Goal

Create the stable internal structure that all other Bridger commands rely on.

This block ensures that `init`, `init --fresh`, `prompt`, `update`, skills, memory agents, and exports all share a consistent project state.

## Responsibilities

Define and manage the `.bridger` directory structure.

Recommended structure:

```txt
.bridger/
  config.json
  index.md
  log.md

  memory/
    repo-analysis.md
    architecture.md
    business-logic.md
    conventions.md
    testing.md
    agent-rules.md

  skills/
    selected-skills.json
    *.md

  artifacts/
    scan-result.json
    repo-graph.json
    graph-summary.json
    codebase-map.json
    reading-plans.json
    memory-run-plan.json
    prompt-generation-plan.json

  exports/
    AGENTS.generated.md
    CLAUDE.generated.md
```

The exact file names can evolve, but the separation of responsibilities should remain stable.

## Configuration requirements

`.bridger/config.json` should store at least:

- project mode: `fresh`, `existing`, or `unknown`;
- project name;
- detected or selected stack;
- package manager;
- selected skills;
- enabled exports;
- memory schema version;
- artifact schema version;
- last init timestamp;
- last update timestamp;
- target coding agents, if selected;
- fresh-repo answers, if applicable;
- model/provider configuration references, without storing secrets.

## Definition of done

This block is done when:

- `.bridger` has a stable structure;
- config creation, reading, validation, and updating are implemented;
- commands can detect whether Bridger is already initialized;
- commands can detect project mode;
- missing or invalid config produces a clear error;
- config changes are deterministic and test-covered;
- no downstream command needs to guess where memory, skills, artifacts, or exports live.

---

# Workstream 1 — CLI UX and command orchestration foundation

## Goal

Make the CLI reliable, predictable, and demo-ready before deeper engines are added.

This workstream does not implement all feature logic. It ensures every command has the right shape, clear output, and clean failure behavior.

## Responsibilities

Implement or refine:

- `bridger init`;
- `bridger init --fresh`;
- `bridger update`;
- `bridger prompt "task"`;
- `bridger inspect`;
- `bridger inspect --graph`.

The CLI should provide:

- concise command summaries;
- clear next steps;
- useful errors;
- no noisy logs by default;
- optional verbose/debug mode;
- consistent exit codes;
- copy-pasteable prompt output;
- stable behavior in CI or non-interactive environments.

## Expected behavior

`bridger init` should:

- scan the repo;
- decide whether it looks fresh or existing;
- initialize `.bridger`;
- run the appropriate mode flow;
- produce a summary.

`bridger init --fresh` should:

- force fresh repo mode;
- ask the basic project questions;
- select or confirm skills;
- generate initial project context;
- export AGENTS.md.

`bridger update` should:

- require an initialized project;
- rescan the repo;
- rebuild deterministic artifacts;
- update memory and exports according to v0 rules;
- print a useful change summary.

`bridger prompt` should:

- require initialized Bridger state;
- accept a task;
- select relevant context;
- generate a coding-agent-ready prompt.

`bridger inspect` should:

- show high-level project state;
- show selected skills;
- show memory files and exports;
- show whether artifacts exist and validate.

`bridger inspect --graph` should:

- show scanning and graph intelligence;
- show entrypoints;
- show clusters;
- show reading plans;
- show warnings and diagnostics.

## Definition of done

This block is done when:

- the CLI command surface exists;
- commands have consistent formatting and error behavior;
- commands can run without performing LLM calls unless required;
- commands fail clearly when `.bridger` is missing, invalid, or incomplete;
- interactive and non-interactive modes are considered;
- command-level tests cover success and failure paths;
- the CLI is good enough to use in a live demo without manual explanation.

---

# Workstream 2 — Deterministic scanning and codebase intelligence engine

## Goal

Build the reliable deterministic foundation that extracts structural facts from a repository before any LLM memory agent runs.

This is the most important technical foundation for existing repositories and also the basis for tracking fresh repositories as they evolve.

## Responsibilities

The deterministic codebase intelligence engine should handle:

- repository scanning;
- ignore and skip rules;
- file inclusion diagnostics;
- sensitive file exclusion;
- binary and large-file exclusion;
- file role tagging;
- language detection;
- stack and framework detection;
- import extraction;
- local import resolution;
- external import signals;
- repo graph generation;
- fan-in and fan-out computation;
- entrypoint detection;
- schema/model/contract detection;
- path-first cluster detection;
- CodebaseMap generation;
- ReadingPlan generation;
- affected traversal support;
- artifact validation;
- artifact writing.

## Expected artifacts

This workstream should produce validated deterministic artifacts under `.bridger/artifacts`.

Minimum artifacts:

```txt
scan-result.json
repo-graph.json
graph-summary.json
codebase-map.json
reading-plans.json
```

## Required intelligence outputs

### Scan result

Should include:

- included files;
- skipped files;
- skip reasons;
- warnings;
- repository stats;
- package manager and stack signals where available.

### RepoGraph

Should include:

- file nodes;
- directory nodes if useful;
- contains edges;
- local import edges;
- unresolved import diagnostics;
- fan-in and fan-out;
- stable sorting.

### CodebaseMap

Should include:

- entrypoint candidates;
- clusters;
- file roles;
- framework signals;
- external library signals;
- schema/model/contract hints;
- test and fixture classification;
- central files;
- source/test/config counts.

### ReadingPlans

Should include at least:

- architecture reading plan;
- testing reading plan;
- doc-specific reading plans for memory agents.

Reading plans should use batches, not only flat file lists.

### Affected traversal

Should support the future prompt generator by answering:

- what files are related to a seed file;
- what files depend on it;
- what files it depends on;
- what tests are structurally connected;
- what cluster it belongs to;
- what entrypoints may reach it.

For v0, file-level affected traversal is enough.

## Definition of done`

This block is done when:

- scanning excludes common noise and dangerous files;
- source files, tests, fixtures, configs, docs, generated files, and lockfiles are classified correctly;
- common entrypoints are detected for TypeScript/Node CLI, Next.js, React/Vite, Python scripts, FastAPI-style apps, and Django-style apps;
- local imports produce graph edges;
- external imports produce signals but not graph edges;
- common schema/model conventions are detected where possible;
- clusters are stable, path-first, and useful;
- architecture and testing reading plans are meaningfully different;
- artifacts validate before being written;
- `inspect --graph` can explain the results;
- deterministic tests prove stable output across repeated runs;
- no LLM call is needed for this whole layer.

---

# Workstream 3 — Fresh repository bootstrap flow

## Goal

Make Bridger useful on new or almost-empty repositories, especially for hackathon use cases.

Fresh mode should create a project context harness instead of pretending to compile mature codebase knowledge.

## Responsibilities

Implement fresh repo detection and/or explicit fresh initialization.

Fresh repo mode should collect basic project intent through a small set of questions.

Suggested questions:

- What are you building?
- Who is the target user?
- What is the intended stack?
- Is this frontend, backend, full-stack, CLI, library, AI app, or something else?
- Which coding agent will you use most?
- What matters most for this project: speed, quality, tests, UI, security, maintainability?
- Should Bridger install recommended skills for this stack?
- What are the non-goals or constraints?

The flow should create initial project context files such as:

```txt
.bridger/project-brief.md
.bridger/architecture-decisions.md
.bridger/development-rules.md
.bridger/testing-strategy.md
.bridger/agent-workflow.md
```

Or equivalent sections inside `.bridger/memory` if a flatter structure is preferred.

## Expected behavior

Fresh mode should produce:

- `.bridger/config.json` with mode set to `fresh`;
- a project brief;
- selected skills;
- starter memory files with clear Unknowns sections;
- an initial `AGENTS.md` export;
- a useful summary of next steps;
- enough context for `bridger prompt` to work immediately.

Fresh memory files should clearly distinguish:

- declared intent;
- selected skills;
- observed facts;
- inferred conventions;
- unknowns.

## Definition of done

This block is done when:

- Bridger can detect a fresh repo or accept `--fresh`;
- the fresh flow runs without requiring existing code structure;
- the user can answer a small number of questions and receive useful project context;
- selected skills are written to `.bridger` state;
- `AGENTS.md` is generated from the fresh context;
- `bridger prompt` works immediately after fresh init;
- `bridger update` can later convert observed code into compiled memory;
- fresh mode does not overclaim architecture, business logic, or conventions.

---

# Workstream 4 — Skill pack system

## Goal

Provide reusable, stack-aware, coding-agent-friendly playbooks that make Bridger useful even before a repository has mature code.

Skills should improve agent behavior by giving concise, practical implementation constraints.

## Responsibilities

Create a skill system that supports:

- a curated set of built-in skills;
- skill selection during fresh init;
- skill selection during existing repo init when stack is detected;
- storing selected skills in `.bridger/config.json` or `.bridger/skills/selected-skills.json`;
- rendering relevant skills into AGENTS.md and prompts;
- updating selected skills later.

## Skill structure

Each skill should have a consistent structure.

Recommended fields:

- skill id;
- title;
- purpose;
- when to apply;
- compatible stacks;
- coding-agent rules;
- implementation guidelines;
- testing expectations;
- common mistakes;
- security or reliability notes;
- freshness/version note if relevant.

Skills should be concise. They should guide agent behavior, not become generic tutorials.

## Suggested v0 skill set

A reasonable v0 target is around 20 skills.

Suggested initial skills:

1. TypeScript
2. JavaScript / Node.js
3. React
4. Next.js
5. Vite frontend apps
6. Tailwind CSS
7. shadcn/ui
8. Node API design
9. FastAPI
10. Python application structure
11. Database access
12. Prisma
13. Supabase
14. Authentication
15. Stripe / billing
16. Unit testing
17. Integration testing
18. End-to-end testing
19. API contract design
20. Security baseline
21. AI SDK / LLM app patterns
22. CLI application design

The exact list can be adjusted, but v0 should avoid having too many low-quality skills.

## Definition of done

This block is done when:

- skills have a stable internal model;
- at least 15 to 20 high-quality built-in skills exist;
- users can select skills during fresh init;
- Bridger can auto-suggest skills from detected stack;
- selected skills are stored in project state;
- AGENTS.md can include selected skill guidance;
- `bridger prompt` can include relevant skills for a task;
- skills are concise, practical, and not generic filler;
- tests verify skill loading, selection, persistence, and rendering.

---

# Workstream 5 — Memory agents and memory orchestration

## Goal

Build the specialized LLM-based system that compiles curated repository evidence into `.bridger/memory` files.

This is the core of Bridger’s compiled memory layer.

## Responsibilities

Implement:

- MemoryAgentRegistry;
- MemoryOrchestrator;
- memory run plan builder;
- agent context assembly;
- memory agent execution;
- output validation;
- memory file writing;
- basic diagnostics;
- support for init mode;
- basic support for update mode.

## Initial memory agents

V0 should include these agents:

### RepoAnalysisAgent

Target file:

```txt
.bridger/memory/repo-analysis.md
```

Purpose:

Explain what kind of project this is, what the main areas are, what is known, what is unknown, and how a coding agent should orient itself.

### ArchitectureAgent

Target file:

```txt
.bridger/memory/architecture.md
```

Purpose:

Explain entrypoints, subsystems, dependency flow, major architectural boundaries, and where future work should fit.

### BusinessLogicAgent

Target file:

```txt
.bridger/memory/business-logic.md
```

Purpose:

Extract project-specific domain concepts, workflows, product behavior, and business rules where evidence exists.

### ConventionsAgent

Target file:

```txt
.bridger/memory/conventions.md
```

Purpose:

Describe coding conventions, file organization patterns, naming patterns, implementation style, error handling, and recurring design choices.

### TestingAgent

Target file:

```txt
.bridger/memory/testing.md
```

Purpose:

Explain the testing setup, what should be tested, where tests live, what test patterns exist, and how coding agents should verify changes.

### AgentRulesAgent

Target file:

```txt
.bridger/memory/agent-rules.md
```

Purpose:

Synthesize operational rules for coding agents based on the other memory files, selected skills, and deterministic artifacts.

## Agent input requirements

Each agent should receive:

- target memory file path;
- role-specific instructions;
- current memory content if updating;
- relevant CodebaseMap summary;
- doc-specific ReadingPlan;
- reading batch contents;
- selected skills when relevant;
- grounding rules;
- output rules;
- unknowns policy.

## Agent output requirements

Each agent should produce:

- markdown only;
- required sections;
- an explicit Unknowns section;
- practical guidance for coding agents;
- no unsupported claims;
- no generic filler.

## Definition of done

This block is done when:

- all v0 memory agents are registered;
- each agent has a clear purpose and target file;
- each agent receives doc-specific context instead of the same flat repo context;
- memory generation works for existing repos;
- memory generation works in constrained form for fresh repos;
- outputs are validated before writing;
- `.bridger/memory` is created consistently;
- AgentRulesAgent runs after the other memory agents;
- generated memory is useful enough to feed AGENTS.md and `bridger prompt`;
- failure modes are clear when LLM configuration is missing or invalid.

---

# Workstream 6 — Agent export layer and AGENTS.md generation

## Goal

Generate high-quality coding-agent instruction files from Bridger’s canonical memory, selected skills, and project state.

For v0, `AGENTS.md` should be excellent. Other exports can be optional.

## Responsibilities

Implement an export layer that reads:

- `.bridger/memory/*`;
- `.bridger/config.json`;
- selected skills;
- project brief for fresh repos;
- relevant deterministic summaries;
- export target settings.

And produces:

- root-level `AGENTS.md`;
- optionally `.bridger/exports/AGENTS.generated.md`;
- optionally `CLAUDE.md`;
- optionally Cursor or Copilot instruction files.

## AGENTS.md expected content

A strong v0 `AGENTS.md` should include:

- project summary;
- current stack;
- how to orient in the repository;
- architecture overview;
- key directories and responsibilities;
- coding conventions;
- testing expectations;
- selected skill guidance;
- implementation rules;
- verification rules;
- unknowns and caution areas;
- instructions for using Bridger prompt/update.

It should be concise enough for coding agents to consume, but specific enough to improve behavior.

## Export principles

The export should:

- be generated from canonical Bridger memory;
- not duplicate every detail from memory files;
- prioritize operational instructions;
- be stable and deterministic;
- clearly mark generated sections;
- avoid overwriting user-authored content without a clear strategy.

## Definition of done

This block is done when:

- `AGENTS.md` can be generated for existing repos;
- `AGENTS.md` can be generated for fresh repos;
- selected skills are included when relevant;
- generated instructions are concise, practical, and project-specific;
- exports are downstream of `.bridger/memory`, not the canonical source;
- repeated generation is deterministic;
- users can understand what was generated and why;
- the generated file is good enough to use directly with Codex, Claude Code, Cursor, or similar tools.

---

# Workstream 7 — `bridger prompt` command

## Goal

Generate task-specific, project-aware implementation prompts for coding agents.

This is one of Bridger’s most important user-facing value loops.

## Responsibilities

The prompt command should take a rough task and generate a coding-agent-ready brief using:

- the user task;
- `.bridger/config.json`;
- `.bridger/memory/*`;
- selected skills;
- CodebaseMap;
- ReadingPlans;
- affected traversal;
- current repository state;
- fresh project brief if applicable.

## Prompt generation flow

Recommended v0 flow:

1. Read the user task.
2. Classify the task type.
3. Select relevant memory files.
4. Select relevant skills.
5. Select likely relevant clusters or files from CodebaseMap.
6. Use affected traversal if seed files are found.
7. Identify likely files to inspect or modify.
8. Identify relevant tests or verification commands.
9. Render a final implementation prompt.

The LLM can help classify or select context, but only from a bounded menu generated by deterministic artifacts.

## Expected prompt output

The generated prompt should include:

- task summary;
- project context;
- relevant memory files;
- relevant files and clusters to inspect;
- likely implementation areas;
- architecture constraints;
- coding conventions;
- selected skills relevant to the task;
- testing expectations;
- acceptance criteria;
- risks and unknowns;
- explicit instruction to avoid unsupported assumptions.

## Fresh repo behavior

In fresh repo mode, the prompt command should use:

- project brief;
- selected skills;
- declared architecture preferences;
- current file tree;
- sparse memory;
- observed code if any exists.

It should be useful even when there is little code.

## Existing repo behavior

In existing repo mode, the prompt command should use:

- compiled memory;
- codebase map;
- affected traversal;
- reading plans;
- relevant tests;
- selected skills only when useful.

## Definition of done

This block is done when:

- `bridger prompt "task"` works after both existing init and fresh init;
- output is directly usable in a coding agent;
- generated prompts are more specific than the raw user task;
- prompt generation uses memory and deterministic artifacts, not generic advice only;
- relevant files or clusters are suggested when possible;
- testing expectations are included;
- unknowns and risks are included;
- the output is copy-pasteable;
- tests cover prompt planning, context selection, rendering, and missing-state errors.

---

# Workstream 8 — `bridger update` command

## Goal

Allow Bridger to refresh project context as the repository evolves.

For fresh repos, this is the mechanism that gradually turns a project-start harness into compiled codebase memory.

For existing repos, this keeps memory and exports aligned with code changes.

## Responsibilities

V0 update should:

- require initialized Bridger state;
- rescan the repository;
- rebuild deterministic artifacts;
- detect new, changed, and deleted files when possible;
- identify changed clusters or areas;
- rerun relevant memory generation or regenerate memory in a simple way;
- update `.bridger/memory`;
- regenerate exports;
- print a clear summary.

## V0 scope

V0 does not need perfect incremental updates.

Acceptable v0 behavior:

- rebuild deterministic artifacts fully;
- regenerate memory files fully or rerun a bounded set of agents;
- regenerate AGENTS.md;
- show what changed at a high level.

Out of scope for v0:

- claim-level provenance;
- perfect minimal patches;
- automatic post-merge hooks;
- GitHub PR checks;
- background daemon;
- complex stale-claim detection.

## Fresh repo update behavior

In fresh mode, `bridger update` should:

- preserve declared project intent;
- preserve selected skills;
- scan newly created code;
- update observed facts;
- replace weak unknowns with observed information when possible;
- improve memory files over time;
- regenerate AGENTS.md from stronger evidence.

## Existing repo update behavior

In existing mode, `bridger update` should:

- rebuild repo intelligence;
- refresh memory from current code state;
- keep selected skills and config;
- regenerate exports;
- surface warnings if memory may be stale.

## Definition of done

This block is done when:

- `bridger update` works after fresh init;
- `bridger update` works after existing repo init;
- deterministic artifacts are refreshed;
- memory and exports are refreshed;
- selected skills and project config are preserved;
- command output explains what was updated;
- obvious deleted or newly added files are reflected in the updated state;
- update does not silently destroy user-declared project intent;
- tests cover update behavior in fresh and existing modes.

---

# Workstream 9 — Artifact validation, tests, and diagnostics

## Goal

Make Bridger reliable enough to trust as a developer tool.

This workstream cuts across all other workstreams.

## Responsibilities

Implement validation and tests for:

- config;
- scan result;
- repo graph;
- graph summary;
- codebase map;
- reading plans;
- memory run plan;
- selected skills;
- prompt generation plan;
- export output metadata if applicable.

Add diagnostics for:

- missing config;
- invalid artifacts;
- missing LLM configuration;
- no source files detected;
- too many skipped files;
- no entrypoints detected;
- no tests detected;
- selected skills incompatible with detected stack;
- stale or missing memory files;
- failed export generation.

## Test categories

V0 should include tests for:

- fresh repo initialization;
- existing repo initialization;
- scanning hygiene;
- file role tagging;
- entrypoint detection;
- import graph generation;
- CodebaseMap validation;
- ReadingPlan validation;
- skill selection and rendering;
- memory agent registry;
- AGENTS.md export rendering;
- prompt rendering;
- update behavior;
- CLI errors.

## Definition of done

This block is done when:

- every artifact has a validation step;
- invalid artifacts fail before LLM calls;
- deterministic output is stable across repeated runs;
- core flows have automated tests;
- diagnostics are visible through CLI output or inspect commands;
- failures are actionable;
- the demo can be run repeatedly without fragile manual cleanup.

---

# Workstream 10 — Packaging, installation, and demo readiness

## Goal

Make Bridger easy to run in a hackathon environment.

This workstream ensures that the product can actually be used by participants and demonstrated clearly.

## Responsibilities

Prepare:

- package configuration;
- CLI binary setup;
- `npx bridger` usage;
- environment variable documentation;
- minimal README;
- command examples;
- demo script;
- sample fresh repo scenario;
- sample existing repo scenario;
- clear troubleshooting guidance.

## Hackathon demo flow

Recommended fresh-repo demo:

```txt
1. Start with an empty or near-empty repo.
2. Run bridger init --fresh.
3. Answer basic project questions.
4. Select skills.
5. Generate AGENTS.md.
6. Run bridger prompt "Build the first feature".
7. Paste prompt into a coding agent.
8. Let the coding agent implement.
9. Run bridger update.
10. Run bridger prompt "Add the next feature".
11. Show that the second prompt uses both declared intent and observed code.
```

Recommended existing-repo demo:

```txt
1. Start with a small but non-trivial repo.
2. Run bridger init.
3. Show generated memory.
4. Show AGENTS.md.
5. Run bridger prompt for a concrete task.
6. Compare with a generic prompt.
```

## Definition of done

This block is done when:

- Bridger can be installed or run with a simple command;
- the main commands work from a clean repo;
- README explains the core workflow;
- missing API key or model configuration errors are clear;
- a hackathon participant can understand the workflow quickly;
- a demo can show fresh-repo value and existing-repo value;
- the generated prompt can be pasted directly into a coding agent;
- the product story is clear: Bridger improves coding-agent output through shared context.

---

# Recommended implementation order

The recommended order is:

```txt
0. Project state, configuration, and file layout
1. CLI UX and command orchestration foundation
2. Deterministic scanning and codebase intelligence engine
3. Fresh repository bootstrap flow
4. Skill pack system
5. Memory agents and memory orchestration
6. Agent export layer and AGENTS.md generation
7. bridger prompt command
8. bridger update command
9. Artifact validation, tests, and diagnostics
10. Packaging, installation, and demo readiness
```

However, some workstreams should be developed iteratively.

A practical build sequence would be:

```txt
Phase 1 — Foundation
  - config and .bridger layout
  - CLI command skeletons
  - deterministic artifacts
  - inspect command

Phase 2 — Fresh repo value
  - init --fresh
  - project brief
  - skills
  - AGENTS.md export
  - basic bridger prompt

Phase 3 — Existing repo value
  - improved scanner
  - CodebaseMap
  - ReadingPlans
  - memory agents
  - existing repo init

Phase 4 — Product loop
  - prompt generator improvements
  - update command
  - export regeneration
  - diagnostics

Phase 5 — Demo hardening
  - tests
  - packaging
  - README
  - demo scripts
```

This sequence is preferable because it creates visible product value early for fresh repositories while the deeper codebase intelligence and memory-agent system matures.

---

# V0 success criteria

Bridger v0 is successful when it can demonstrate both of the following.

## Fresh repo success

A user can start a new project, run Bridger, and immediately get:

- a project context harness;
- selected skills;
- a useful AGENTS.md;
- a task-specific coding-agent prompt;
- an update path as the repo grows.

## Existing repo success

A user can run Bridger on an existing repository and get:

- deterministic codebase intelligence;
- compiled memory files;
- useful agent instructions;
- task-aware prompts grounded in the actual repository.

## Product success

The user should be able to see that:

```txt
raw task prompt
  <
Bridger-generated task prompt
```

The Bridger-generated prompt should be more specific, better grounded, more aware of project constraints, and more likely to produce aligned coding-agent output.

---

# Explicit non-goals for v0

The following should not be required for v0:

- SaaS dashboard;
- hosted backend;
- billing;
- marketplace for skills;
- GitHub app;
- autonomous PR bot;
- background daemon;
- automatic post-merge hooks;
- claim-level provenance;
- advanced AST or Tree-sitter analysis;
- vector database;
- MCP server;
- IDE extension;
- enterprise governance;
- perfect incremental memory patches.

These can be future directions if the CLI proves valuable.

---

# Final v0 system shape

The intended v0 architecture is:

```txt
bridger init / init --fresh
  ↓
project state + deterministic scanning
  ↓
CodebaseMap + ReadingPlans
  ↓
fresh project brief and/or memory agents
  ↓
.bridger/memory
  ↓
selected skills
  ↓
AGENTS.md export
  ↓
bridger prompt
  ↓
better coding-agent execution
  ↓
bridger update
  ↓
refreshed memory and exports
```

This keeps Bridger aligned with its core thesis:

> One codebase. One shared context layer. Many AI coding agents.
