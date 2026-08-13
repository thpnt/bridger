# Bridger — Memory Agent Fleet Harness: Locked High-Level Design

**Status:** Locked high-level design for V0  
**Date:** 12 August 2026  
**Scope:** Memory-agent fleet orchestration, per-target agent loop, runtime ownership, evaluation boundaries, durable state, context lifecycle, recovery, and fleet reconciliation.  
**Next design step:** Define the concrete contracts, schemas, interfaces, target catalog, completion criteria, reviewer rubrics, and persistence layout that implement this design.

---

## 1. Purpose

This document locks the high-level design of Bridger's memory-agent harness before implementation begins.

The memory-agent fleet is responsible for creating the evidence-backed knowledge portion of the Repository Brain. Each memory agent receives a bounded knowledge target, autonomously navigates the repository through Bridger's read-only repository-navigation interfaces, and creates or updates Markdown knowledge inside its assigned target folder.

The harness exists to make that work reliable over long-running executions.

The design is based on the long-running-agent principles captured in `agentic-loops.md`, especially:

- durable task state must live outside model context;
- the model proposes actions while the runtime controls execution;
- generation and evaluation should be separated;
- completion must be earned rather than self-declared;
- important policies should be enforced by mechanisms rather than prompts;
- handoffs between contexts should be structured;
- context should be reconstructed from durable state instead of replaying an ever-growing transcript;
- the runtime needs explicit termination, retry, recovery, and budget semantics;
- harness complexity should remain minimal until traces demonstrate a need for more machinery.

The generic examples in `implementation-oriented-long-running-agent-harness-course.md` are implementation inspiration only. They are not authoritative contracts for Bridger.

This document adapts the long-running-agent pattern to Bridger's more constrained problem:

```text
The repository revision is already known.
The memory targets are predefined.
Each target has a bounded semantic responsibility.
The worker owns repository discovery for that target.
The worker owns the internal Markdown segmentation of its target folder.
The runtime owns execution state, validation, continuation, and acceptance.
Reviewers judge generated knowledge artifacts, not the repository itself.
```

---

# 2. Core mental model

The harness is a control system around probabilistic workers.

```text
MODEL
    proposes actions and knowledge

HARNESS
    controls execution lifecycle and permissions

DURABLE STATE
    records current execution reality

REPOSITORY NAVIGATION
    exposes bounded read-only repository evidence

WORKER
    discovers, interprets, and writes target knowledge

HARD VALIDATOR
    verifies objective invariants

REVIEWER
    judges artifact-level semantic quality

RUNTIME
    decides whether to continue, repair, accept, stop, or recover
```

The primary rule is:

> **The worker may believe it is finished, but only the runtime can accept a target as finished.**

A worker signals readiness through an explicit finalization request. That request transfers control to the runtime; it does not change completion state.

---

# 3. Bridger-specific simplifications

The generic long-running-agent pattern often includes:

```text
Planner
    ↓
contract negotiation
    ↓
Generator
    ↓
Evaluator
```

Bridger does not require all of these stages.

## 3.1 No planner agent for V0 target execution

Memory targets are predefined.

Conceptually:

```text
architecture/
testing/
conventions/
business-logic/
...
```

The exact initial target catalog will be locked separately, but the harness assumes that targets exist before execution begins.

The fleet runtime therefore does not need an LLM planner to invent or negotiate the task decomposition.

Its job is to:

- load the predefined target catalog;
- instantiate the required target tasks;
- schedule them;
- track them;
- coordinate dependencies when explicitly defined;
- reconcile their outputs;
- decide when the requested fleet scope is accepted.

The worker remains autonomous inside the target. It decides how to investigate the repository and how to organize the resulting knowledge.

## 3.2 No runtime contract negotiation

Anthropic's contract-negotiation pattern is valuable when "done" is initially underspecified.

Bridger's memory tasks should instead use **predefined, versioned completion contracts**.

A target contract will eventually define:

- purpose;
- semantic scope;
- exclusions;
- coverage obligations;
- evidence policy;
- objective hard gates;
- reviewer rubric;
- uncertainty requirements;
- budgets or policy defaults.

The runtime loads that contract before execution.

Changing the contract changes the meaning of a successful target and therefore requires a version change.

## 3.3 No evaluator repository rediscovery

The reviewer does **not** independently navigate or rediscover the repository.

Repository discovery is the worker's responsibility and is intentionally paid for once.

The reviewer judges the generated knowledge artifacts against their explicit target contract and against other generated knowledge where applicable.

This is a deliberate cost and architecture decision:

```text
Worker
    owns semantic grounding against repository evidence

Hard validator
    owns mechanical evidence and artifact integrity

Reviewer
    owns quality, consistency, organization, deduplication,
    scope discipline, writing quality, and explicit contract coverage
```

Offline evaluation during Bridger development may independently compare worker outputs with expert-reviewed repository truth. That is an evaluation of the harness and worker quality, not part of every production run.

---

# 4. Global architecture

The harness has two control levels:

1. **Fleet runtime** — owns the whole memory-generation run.
2. **Target runtime** — owns one bounded memory target.

```text
Repository revision R
Layers 1–5 deterministic/enrichment data
Layer 6 RepositoryNavigator
        │
        ▼
┌─────────────────────────────────────────────┐
│              MEMORY FLEET RUNTIME           │
│                                             │
│ load target catalog                         │
│ instantiate tasks                           │
│ schedule bounded concurrency                │
│ track global progress                       │
│ coordinate recovery                         │
│ run fleet reconciliation                    │
│ own fleet completion                        │
└──────────────────┬──────────────────────────┘
                   │
          bounded target execution
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
 architecture/   testing/   conventions/
       │           │           │
       ▼           ▼           ▼
┌────────────┐ ┌────────────┐ ┌────────────┐
│ Target     │ │ Target     │ │ Target     │
│ Runtime    │ │ Runtime    │ │ Runtime    │
└─────┬──────┘ └─────┬──────┘ └─────┬──────┘
      │              │              │
      ▼              ▼              ▼
   Worker         Worker         Worker
      │              │              │
      ▼              ▼              ▼
 target-local    target-local    target-local
 knowledge       knowledge       knowledge
```

Each target runs the same basic closed loop:

```text
INITIALIZE
    ↓
HYDRATE CONTEXT
    ↓
WORKER EXECUTION
    ↓
FINALIZATION REQUEST
    ↓
HARD VALIDATION
    │
    ├── FAIL ───────────────► REPAIR
    │                           │
    │                           └──► WORKER EXECUTION
    │
    └── PASS
         ↓
      REVIEWER
         │
         ├── NEEDS_WORK ─────► REPAIR
         │                       │
         │                       └──► WORKER EXECUTION
         │
         └── PASS
              ↓
          TARGET ACCEPTED
```

After all required targets are locally accepted:

```text
accepted target folders
        │
        ▼
FLEET HARD VALIDATION
        │
        ▼
FLEET REVIEW
        │
    ┌───┴──────────┐
    │              │
   PASS          ISSUES
    │              │
    ▼              ▼
FLEET ACCEPTED   reopen only
                 affected targets
                      │
                      └──► normal repair loop
```

---

# 5. Memory target boundary

The unit of work is a **memory target folder**, not a predetermined Markdown file.

For example:

```text
architecture/
```

The runtime owns the target directory and the semantic contract for that target.

The worker owns the internal segmentation.

A valid worker may choose:

```text
architecture/
├── overview.md
├── runtime.md
├── persistence.md
└── integrations.md
```

Another valid worker may choose:

```text
architecture/
├── system-architecture.md
├── execution-model.md
└── data-and-integrations.md
```

Both may be accepted if the target contract is satisfied.

## 5.1 Harness-owned properties

The harness owns:

- target identity;
- target folder boundary;
- purpose;
- allowed scope;
- out-of-scope areas;
- required semantic coverage;
- evidence policy;
- completion criteria;
- reviewer rubric;
- execution budgets;
- repository and graph/enrichment identities;
- target lifecycle and final status.

## 5.2 Worker-owned properties

The worker owns:

- repository exploration strategy;
- investigation order;
- which repository areas to inspect;
- which graph entities to follow;
- how deeply to follow a workflow;
- which evidence supports each substantive claim;
- Markdown file count;
- Markdown file names;
- internal topic grouping;
- document organization;
- reorganization or replacement of files inside the assigned target workspace.

There is therefore no V0 contract such as:

```text
architecture target MUST contain persistence.md
```

unless a future design decision explicitly introduces a globally mandatory file.

The completion contract is semantic rather than filename-driven.

---

# 6. Component model

The following list defines **responsibilities**, not a requirement to implement one class per row.

V0 should combine responsibilities where doing so keeps the implementation simpler and clearer.

| Component | High-level responsibility |
|---|---|
| **Memory Target Catalog** | Stores predefined target definitions and versioned completion contracts. |
| **Fleet Runtime / Scheduler** | Owns the whole fleet lifecycle, task instantiation, bounded concurrency, global status, and completion. |
| **Target Runtime / Loop Controller** | Owns lifecycle transitions for one target. |
| **Task State Store** | Persists authoritative current execution state outside model context. |
| **Trace / Event Store** | Records what happened for observability, debugging, and evaluation. |
| **Context Compiler** | Reconstructs bounded worker or reviewer context from durable state. |
| **Worker Runner** | Runs the worker model/tool loop for one target. |
| **Tool Runtime** | Executes allowed tools and enforces permissions and boundaries. |
| **Repository Navigator** | Existing shared read surface over repository, graph, enrichment, files, symbols, and source evidence. |
| **Artifact Workspace** | Provides controlled writes inside the assigned memory target. |
| **Evidence Recorder** | Persists typed references and associations needed by the generated knowledge. |
| **Finalization Control** | Exposes the worker's explicit request to transfer control to evaluation. |
| **Hard Validator** | Checks objective invariants in deterministic code. |
| **Reviewer Runner** | Runs fresh, read-only artifact-level semantic review. |
| **Budget / Retry Policy** | Enforces execution limits and separates transient model/provider failures from semantic repair. |
| **Checkpoint / Recovery Manager** | Makes target execution resumable from durable state. |
| **Fleet Reconciler** | Checks whole-fleet consistency, duplication, ownership boundaries, and cross-target quality. |
| **Result Collector** | Produces the accepted memory-fleet result consumed by the later publication layer. |

The first implementation should not introduce a generic agent framework or elaborate supervisor hierarchy unless it is needed to express these responsibilities cleanly.

---

# 7. Agent roles and permissions

## 7.1 Worker agent

The worker is the only production-time LLM role responsible for discovering repository semantics for its target.

It receives:

- target purpose and contract;
- repository identity and revision;
- durable progress relevant to the current cycle;
- previous validation/reviewer findings when repairing;
- access to the repository-navigation tool surface;
- access to target-local artifact operations;
- access to evidence-recording operations;
- finalization control.

It may:

```text
search repository
inspect graph entities
traverse graph
inspect communities
list files and symbols
read bounded source evidence
record evidence
create Markdown files in its target
edit Markdown files in its target
delete/reorganize target-local generated files when allowed
create/update target-local metadata and claims
request finalization
```

It may not:

```text
modify source repository
modify FileIndex or SymbolIndex
modify deterministic graph snapshots
modify enrichment overlays
modify another target's workspace
mark hard criteria PASS
mark reviewer criteria PASS
set task status ACCEPTED
publish a Repository Brain snapshot
```

## 7.2 Reviewer agent

The reviewer runs in a fresh reasoning context after hard validation passes.

It is read-only.

The reviewer receives the target contract and generated artifacts needed to judge the result, but **does not receive repository-navigation tools**.

A target reviewer may receive:

- target purpose, scope, and exclusions;
- completion/review rubric;
- current Markdown files;
- target-local metadata and claim information;
- coverage/unknown/contradiction state where relevant;
- the hard-validation report;
- optionally previous reviewer findings for comparison.

It judges properties such as:

- coverage of explicit target obligations;
- internal consistency;
- duplication and unnecessary repetition;
- contradictions inside the target;
- scope leakage;
- terminology consistency;
- organization and navigability;
- quality of file segmentation;
- appropriate level of detail;
- writing clarity and style;
- unsupported certainty visible from the artifacts themselves;
- quality of explicit unknowns and contradictions;
- semantic consistency between Markdown and its metadata/claims.

It does **not** judge by rediscovering the repository:

- whether an unmentioned repository subsystem should have been discovered;
- whether a source workflow was interpreted correctly by independently tracing the code;
- whether another source file would have been better evidence;
- whether the worker missed a repository fact that is not implied by the explicit target contract or generated artifacts.

That semantic grounding responsibility belongs to the worker.

## 7.3 Fleet reviewer

The fleet reviewer follows the same principle at whole-memory scope.

It sees accepted generated target folders and their relevant metadata, but it does not rediscover the repository.

It judges:

- cross-target duplication;
- cross-target contradictions;
- terminology inconsistencies;
- scope/ownership leakage;
- poor division of responsibility between targets;
- repeated explanations that should have one clear owner;
- missing explicit target-level obligations when visible from the target catalog;
- global organization and knowledge usability.

It emits findings. It never edits target artifacts directly.

---

# 8. Step-by-step lifecycle

## Step 0 — Bind the source state

Before a memory fleet can run, the runtime binds the generation run to exact upstream identities.

At minimum, the run must be associated with:

```text
repository identity
repository revision
repository scope
deterministic graph snapshot
compatible structural state
optional compatible enrichment overlay
target-contract versions
runtime/profile versions as later defined
```

The memory run is never an unversioned conversation against a mutable repository.

Upstream artifacts remain immutable and read-only.

---

## Step 1 — Load the target catalog

The runtime loads the predefined memory targets required for the requested Brain scope.

Conceptually:

```text
MemoryTargetCatalog
    ├── architecture
    ├── testing
    ├── conventions
    └── ...
```

For each target, the catalog provides a versioned semantic contract.

No LLM planning stage is required to invent these targets.

The exact target names and contracts are a follow-up design task.

---

## Step 2 — Initialize the fleet run

The fleet runtime:

1. creates the fleet-run identity;
2. binds upstream revision/snapshot identities;
3. materializes the required target tasks;
4. initializes each target in a non-passing state;
5. initializes budgets and runtime counters;
6. records dependencies if the target catalog explicitly defines any;
7. persists initial task/fleet state;
8. makes eligible targets runnable.

All completion criteria begin unresolved or failing.

A worker never receives an implicitly successful target.

---

## Step 3 — Schedule target execution

The fleet runtime schedules runnable targets under bounded concurrency.

The default design favors independent target execution when targets do not depend on one another.

Concurrency is owned by the runtime rather than by the workers.

Rules:

- one target failure must not automatically cancel unrelated sibling targets;
- successful targets are not regenerated because another target failed;
- target-local state remains isolated;
- global concurrency and provider limits are enforced centrally;
- dependencies, if any, are explicit rather than inferred through hidden worker communication.

V0 does not require peer-to-peer communication between target workers.

---

## Step 4 — Hydrate the worker context

Before a worker cycle, the Context Compiler reconstructs the bounded model context from durable state.

The worker should receive the smallest complete view required for the current target and phase.

Conceptually:

```text
static worker instructions
+
target purpose / scope / exclusions
+
completion contract
+
source identities
+
current target state
+
current artifact inventory
+
working summary / structured progress
+
unresolved hard-validation findings
+
latest reviewer findings
+
relevant evidence references / handles
+
remaining budgets
+
tool definitions
```

It should not receive by default:

```text
the full prior transcript
all old raw tool outputs
all sibling worker traces
reviewer hidden reasoning
the whole repository
the entire graph
```

The prompt is a **compiled execution view**, not the canonical task state.

---

## Step 5 — Worker exploration and generation

The worker runs a bounded model/tool loop.

Typical behavior:

```text
orient from target state
    ↓
search / inspect enriched graph
    ↓
follow relevant graph entities
    ↓
locate files and symbols
    ↓
read bounded source evidence
    ↓
follow required workflows / boundaries / tests / config
    ↓
record evidence and durable findings
    ↓
create or refine target Markdown
    ↓
update target-local metadata / claims
    ↓
continue until target appears ready
```

The worker is not forced into a predetermined repository reading plan.

The task is bounded; the input file set is not.

The worker may investigate any repository area needed for its assigned target, subject to repository policy and runtime budgets.

---

## Step 6 — Persist progress continuously

Important progress must survive model-context loss.

The runtime persists durable state during execution rather than waiting for successful completion.

At meaningful boundaries it should record enough information to recover:

- current phase;
- artifact inventory and versions/digests as appropriate;
- structured progress/coverage state;
- evidence references;
- unresolved questions or contradictions;
- validation/reviewer findings;
- budget counters;
- checkpoint metadata;
- trace events.

The conversation itself is never authoritative.

---

## Step 7 — Worker requests finalization

When the worker believes the target satisfies its contract, it invokes a dedicated control action conceptually equivalent to:

```text
request_finalization()
```

Semantics:

```text
"I believe the current target artifacts are ready for evaluation."
```

Not:

```text
"Set the task to complete."
```

The runtime intercepts the request, persists the current state, ends the current worker execution cycle, and transitions the target to hard validation.

A normal natural-language statement such as "done" is not sufficient to accept the target.

---

## Step 8 — Run hard validation

Hard validation is deterministic code.

It checks properties the runtime can establish reliably without asking an LLM.

The exact gates will be defined in the contract-design phase, but the categories include:

### Source identity and compatibility

- target still points to the correct repository revision;
- graph snapshot identity is unchanged and compatible;
- enrichment overlay, if used, targets the correct graph snapshot.

### Write boundaries

- generated writes remain inside the assigned memory target/runtime state;
- upstream deterministic/enrichment artifacts are unchanged;
- sibling targets were not modified.

### Artifact integrity

- generated artifact paths are valid;
- required generated sidecars or metadata resolve;
- document/claim identities are valid and unique within their defined boundary;
- internal references are structurally resolvable;
- no invalid/orphaned runtime artifacts are accepted.

### Evidence integrity

- referenced file/symbol/graph evidence exists;
- evidence resolves against the correct revision/snapshot;
- ranges and identifiers are structurally valid;
- required evidence-bearing records are present when the contract demands them.

### Runtime invariants

- task state is internally consistent;
- budgets/counters are valid;
- required completion declarations or coverage records exist;
- no publication-blocking runtime error is unresolved.

Hard validation does **not** attempt to decide:

```text
"Does this prose correctly explain the code?"
"Did the worker discover every important repository concept?"
"Is this architectural interpretation true?"
```

Those questions would require repository rediscovery and belong to worker trust plus offline evaluation.

### Hard-validation outcome

```text
PASS
    → reviewer

FAIL
    → structured findings
    → target transitions to REPAIR
```

Findings must be granular and actionable.

---

## Step 9 — Run target review

Review only runs after hard validation succeeds.

The reviewer receives a fresh context so it does not inherit the worker's rationalizations or long execution history.

The reviewer evaluates the whole target folder against a structured rubric.

Its output is a structured verdict such as:

```text
PASS
```

or:

```text
NEEDS_WORK
    findings[]
```

A finding should identify:

- criterion/rubric dimension;
- severity or repair priority;
- affected file(s) or target scope;
- concrete issue;
- required outcome of repair.

The reviewer does not edit the artifacts.

### Reviewer PASS

The runtime may mark the target locally accepted if no other target-level gate remains.

### Reviewer NEEDS_WORK

The runtime persists the findings and transitions the target to repair.

---

## Step 10 — Repair

Repair is continuation from durable state, not a complete restart.

The Context Compiler creates a new worker context containing:

```text
target contract
+
current generated artifacts
+
relevant prior evidence/progress
+
specific failed hard gates
+
specific reviewer findings
+
remaining budget
```

The worker may:

```text
patch
rewrite
reorganize
merge files
split files
delete poor generated files
replace a weak approach
perform additional repository investigation
```

The harness should not force endless local patching.

If the worker determines that the current knowledge organization or investigation approach is fundamentally weak, it may substantially restructure the target while preserving the target boundary and valid evidence.

After repair, the worker again requests finalization.

---

## Step 11 — Target acceptance

A target becomes `ACCEPTED` only after:

```text
finalization requested
+
hard validation PASS
+
target reviewer PASS
```

The runtime records the accepted state and the exact accepted artifact set.

A worker cannot directly write `ACCEPTED`.

Accepted targets remain available for later fleet reconciliation.

---

## Step 12 — Fleet hard validation

When every required target is locally accepted, the fleet runtime runs whole-memory objective checks.

The exact gates will be defined later, but likely categories include:

- every required target is accepted;
- all target outputs belong to the same repository revision;
- compatible upstream snapshot identities are used;
- global document identities are valid;
- qualified cross-file references resolve;
- target directory boundaries are respected;
- no stale, failed, or unaccepted artifact is included in the candidate fleet;
- fleet state is internally consistent.

Failure reopens only the affected target(s) where possible.

---

## Step 13 — Fleet semantic reconciliation

A fresh, read-only fleet reviewer examines the accepted generated memory corpus.

It does not navigate the repository.

It evaluates cross-target artifact quality, including:

- duplicate explanations;
- contradictory generated claims;
- inconsistent vocabulary;
- unclear target ownership;
- scope leakage;
- inappropriate cross-target coupling;
- global organization and readability.

Example:

```text
architecture/runtime.md
and
business-logic/request-flow.md

both contain nearly identical detailed descriptions
of the same request execution lifecycle.
```

The fleet reviewer can produce a finding such as:

```text
architecture owns the structural overview;
business-logic owns domain-specific behavior;
remove duplicated implementation detail from one side.
```

The runtime routes that finding back to the affected target tasks.

---

## Step 14 — Targeted fleet repair

Only targets implicated by fleet findings are reopened.

They return through the normal loop:

```text
REPAIR
    ↓
WORKER
    ↓
FINALIZATION
    ↓
HARD VALIDATION
    ↓
TARGET REVIEW
    ↓
ACCEPTED
```

After the affected targets are accepted again, fleet validation and reconciliation run again.

There is no separate privileged fleet-repair mechanism that bypasses target contracts.

---

## Step 15 — Fleet acceptance

The fleet becomes accepted only when:

```text
all required targets accepted
+
fleet hard validation PASS
+
fleet semantic review PASS
```

The fleet runtime then emits the accepted memory-fleet result for the next Repository Brain publication layer.

The memory-agent harness itself does not publish the Repository Brain.

Publication remains a later authority boundary.

---

# 9. Durable state versus transient context

A central long-running-agent principle is:

```text
model context ≠ task memory
```

Bridger therefore maintains two distinct systems.

## 9.1 Durable authoritative state

Durable state should conceptually cover six categories.

### 1. Task definition

```text
target identity
target contract/version
repository/snapshot identities
execution policy/profile
```

### 2. Execution state

```text
current lifecycle phase
cycle / attempt counters
budget usage
coverage/progress
open questions
unresolved validation findings
unresolved reviewer findings
working summary or structured continuation state
```

### 3. Artifact state

```text
generated Markdown inventory
target-local metadata/claims
digests or versions where needed
accepted candidate set
```

### 4. Evidence state

```text
typed evidence references
source identities
claim/evidence associations
relevant evidence metadata
```

### 5. Evaluation state

```text
hard-validation reports
reviewer verdicts
fleet reconciliation findings
acceptance status
```

### 6. Trace / observability state

```text
model-call events
tool-call events
artifact mutations
evidence-recording events
finalization requests
state transitions
usage and budgets
errors
retries
checkpoints
```

The exact physical schemas and storage files are not locked by this document.

## 9.2 Transient model context

Transient context includes:

- current prompt;
- recent reasoning trajectory;
- immediate tool observations;
- bounded excerpts loaded for the current investigation;
- current reviewer prompt.

It may be discarded and rebuilt.

The system must be able to continue from durable state without relying on the full prior conversation.

---

# 10. State and trace are separate concepts

## 10.1 State answers

```text
Where is the task now?
```

Example:

```text
phase = REPAIR
target = architecture
hard gates = PASS
review findings = [R-12, R-15]
budget remaining = ...
```

State is optimized for execution and recovery.

## 10.2 Trace answers

```text
How did the task reach this state?
```

Example:

```text
worker cycle started
search_repository(...)
get_graph_community(...)
read_symbol_excerpt(...)
evidence recorded
artifact written
request_finalization
hard validation passed
review failed
repair started
```

Trace is optimized for:

- debugging;
- harness evaluation;
- cost analysis;
- failure analysis;
- understanding model/tool behavior;
- future ablation of harness components.

A compact state snapshot must not replace the detailed trace.

---

# 11. Context lifecycle

The default context strategy is **reconstruction**, not transcript replay.

For every worker or reviewer execution:

```text
durable state
    +
target contract
    +
relevant artifact/evidence state
    +
current findings
    +
tool definitions
        ↓
Context Compiler
        ↓
bounded model context
```

## 11.1 Priority order for worker context

A useful default priority is:

```text
1. system/runtime rules
2. current target objective and scope
3. source/revision identity
4. completion contract
5. current structured task state
6. unresolved validation/reviewer findings
7. relevant artifact/evidence context
8. bounded recent interaction only when useful
```

## 11.2 Compaction and fresh contexts

Neither aggressive compaction nor forced fresh-context resets are permanently locked as universal mechanisms.

The architecture only requires that:

- durable state survives either strategy;
- context can be rebuilt independently;
- role boundaries use separate contexts;
- the runtime may start a fresh worker cycle after finalization/repair when useful;
- context policy can evolve based on traces and model behavior.

This follows the general rule:

> Harness complexity should be earned by observed failures.

---

# 12. Evidence and trust boundary

The Repository Brain is evidence-backed, but production-time evaluation deliberately avoids doing the worker's repository investigation twice.

The trust split is:

| Question | Owner |
|---|---|
| Does the referenced source artifact exist at the correct revision? | Hard validator |
| Does the evidence identifier/range resolve structurally? | Hard validator |
| Does the generated claim correctly interpret the repository? | Worker |
| Is the generated knowledge internally coherent and well organized? | Reviewer |
| Is there unnecessary duplication across generated memory? | Target/fleet reviewer |
| Are workers generally trustworthy at repository interpretation? | Offline Bridger evaluation framework |

This is an intentional V0 tradeoff.

The worker's semantic accuracy must therefore be benchmarked separately during harness development.

Production runs do not pay for a second full repository discovery by the reviewer.

---

# 13. Completion and termination semantics

The runtime owns all terminal decisions.

## 13.1 Successful target termination

```text
hard validation PASS
+
review PASS
→ ACCEPTED
```

## 13.2 Successful fleet termination

```text
all required targets ACCEPTED
+
fleet validation PASS
+
fleet review PASS
→ FLEET ACCEPTED
```

## 13.3 Non-success terminal states

The design allows explicit terminal states such as:

```text
BLOCKED
EXHAUSTED
FAILED
STOPPED
```

The exact enum is follow-up contract work.

Typical reasons include:

### BLOCKED

The target cannot progress because a required upstream artifact or allowed source evidence is unavailable.

### EXHAUSTED

A configured execution budget or maximum repair policy has been reached without acceptance.

### FAILED

A non-recoverable runtime/state/integrity failure prevents safe continuation.

### STOPPED

An operator or higher-level runtime deliberately stops the task.

Workers do not choose terminal states directly.

---

# 14. Retry versus repair

Provider/runtime retry and semantic repair are different operations.

## 14.1 Retry

Retry handles transient execution failure:

```text
timeout
rate limit
temporary provider error
transient tool/runtime failure
```

It should not automatically increment semantic repair state.

## 14.2 Repair

Repair handles valid execution that produced an unacceptable target:

```text
hard validation failed
reviewer found duplication
reviewer found poor organization
reviewer found missing explicit contract coverage
fleet reconciliation found contradiction
```

Repair is a new bounded worker cycle informed by structured findings.

The concrete retry limits and backoff policy are not locked here.

---

# 15. Checkpointing and recovery

The runtime must support recovery at meaningful task boundaries.

Minimum architectural requirement:

> A bounded memory task must be resumable from durable task-level state or a checkpoint without depending on the original model transcript.

Useful checkpoint boundaries include:

- task initialization;
- after meaningful artifact/evidence updates;
- before/after finalization;
- after hard validation;
- after reviewer verdict;
- before entering repair;
- target acceptance.

Exact checkpoint frequency is implementation policy, not a high-level contract.

Recovery should:

1. load immutable task specification;
2. load latest valid durable state/checkpoint;
3. verify source/snapshot compatibility;
4. verify generated workspace integrity;
5. restore counters/findings;
6. reconstruct model context;
7. continue from the correct lifecycle phase.

The runtime must not silently resume against a different repository revision.

---

# 16. Fleet concurrency and isolation

The fleet is naturally parallelizable because target scopes are predefined.

V0 should support bounded concurrency without introducing a complex agent society.

Rules:

1. Fleet runtime owns concurrency.
2. Each worker has isolated task state and context.
3. Each worker writes only inside its assigned target/runtime workspace.
4. Workers do not communicate through hidden shared conversation state.
5. Sibling target failure does not automatically cancel successful siblings.
6. Accepted targets are not regenerated unless a later fleet finding explicitly reopens them.
7. Provider concurrency limits are enforced centrally.
8. Cross-target coordination happens through runtime state and reconciliation findings, not ad hoc worker messaging.

If later evidence shows that some targets require ordered dependencies, those dependencies should be explicit in the target catalog.

---

# 17. Data-flow view by component

The exact schemas are deferred, but the transformations are already lockable.

| Component | Primary input | Transformation | Primary output |
|---|---|---|---|
| **Target Catalog** | Static/versioned target definitions | Resolve requested target scope and contracts | Target specs/contracts |
| **Fleet Runtime** | Upstream identities + target specs + fleet state | Instantiate, schedule, coordinate, reconcile | Fleet state + target executions |
| **Target Runtime** | Target spec + target state | Apply lifecycle/state-machine rules | Updated target state / next phase |
| **Context Compiler** | Target state + contract + artifacts + findings | Select and format bounded execution context | Worker/reviewer model input |
| **Worker Runner** | Compiled context + allowed tools | Model reasoning/tool loop | Tool calls, artifact/evidence mutations, finalization request |
| **Tool Runtime** | Structured tool call + permissions | Authorize and execute | Structured tool result / runtime event |
| **Repository Navigator** | Search/traversal/read requests | Read immutable Layers 1–6 data | Bounded graph/file/symbol/source context |
| **Artifact Workspace** | Worker artifact mutation request | Enforce target-local write boundary | Updated target artifacts |
| **Evidence Recorder** | Worker evidence selection | Normalize and persist evidence references | Durable evidence records/associations |
| **Hard Validator** | Contract + task state + artifacts + evidence + source identities | Deterministic invariant checks | Validation report |
| **Reviewer Runner** | Contract + generated artifacts + validation result | Artifact-level semantic review | PASS / structured findings |
| **Repair routing** | Failed validation/review | Persist findings and reopen task | Repair-ready task state |
| **Fleet Reconciler** | Accepted target artifacts/states | Global hard checks + artifact-level cross-target review | Fleet PASS or routed findings |
| **Checkpoint/Recovery** | Durable state + artifacts + source identity | Verify and reconstruct executable state | Resumable target/fleet runtime |
| **Trace Store** | Runtime/model/tool events | Append/normalize/redact as policy requires | Replayable/debuggable execution trace |
| **Result Collector** | Fully accepted fleet | Freeze accepted memory result references | Publication-layer handoff |

---

# 18. Lifecycle state machine

The exact persisted enum is follow-up contract work, but the high-level state machine is locked.

```text
INITIALIZED
     │
     ▼
  RUNNING
     │
     │ request_finalization
     ▼
HARD_VALIDATING
     │
  ┌──┴─────────┐
  │            │
 FAIL         PASS
  │            │
  ▼            ▼
REPAIR      REVIEWING
  ▲            │
  │       ┌────┴──────┐
  │       │           │
  │   NEEDS_WORK     PASS
  │       │           │
  └───────┘           ▼
                  ACCEPTED
```

Side exits are runtime-owned:

```text
BLOCKED
EXHAUSTED
FAILED
STOPPED
```

The key invariant is:

```text
RUNNING → ACCEPTED
```

is impossible.

Acceptance requires passing through runtime evaluation.

---

# 19. Hard rules

The following high-level rules are locked for V0.

## 19.1 Execution control

1. The runtime, not the worker, owns lifecycle transitions.
2. A worker cannot mark its own target accepted.
3. Finalization is an explicit runtime control operation.
4. Hard gates run before LLM review.
5. Failed evaluation returns structured findings and routes to repair.
6. Acceptance requires both objective and reviewer gates.

## 19.2 Planning and contracts

7. No planner agent is required for predefined V0 memory targets.
8. No per-run generator/evaluator contract negotiation is required.
9. Target contracts are predefined and versioned.
10. The worker owns near-term exploration strategy inside its bounded target.

## 19.3 Target artifacts

11. A memory target is a predefined folder-level semantic scope.
12. The worker owns the number, names, and segmentation of Markdown files inside that folder.
13. The harness evaluates semantic target coverage, not a fixed filename checklist unless a future contract explicitly requires one.
14. Workers may reorganize target-local generated artifacts during repair.

## 19.4 Repository access and grounding

15. Workers use the existing Bridger repository-navigation interface rather than direct unrestricted repository access.
16. Workers may autonomously explore any allowed repository area needed for their bounded task.
17. The enriched graph is a navigation map, not sufficient behavioral evidence by itself where source verification is required.
18. Workers must not mutate deterministic substrate or enrichment artifacts.
19. Important generated knowledge must remain evidence-backed according to the later evidence contract.

## 19.5 Reviewer boundaries

20. Reviewer agents are fresh-context and read-only.
21. Reviewers cannot edit generated knowledge.
22. Production reviewers do not receive repository-navigation tools.
23. Production reviewers do not rediscover the repository.
24. Reviewers judge artifact-level semantic quality, consistency, deduplication, organization, writing quality, scope discipline, and explicit contract coverage.
25. Semantic correctness against source implementation is trusted to the worker and measured through offline harness evaluation.

## 19.6 State and context

26. Conversation history is not authoritative task state.
27. Durable structured state must survive context reset or process restart.
28. Context is reconstructed from durable state rather than built by indefinite transcript accumulation.
29. State and trace are separate concerns.
30. Complete enough traces must exist to debug model/tool divergence and evaluate the harness.

## 19.7 Fleet behavior

31. Fleet runtime owns scheduling and bounded concurrency.
32. Target state is isolated.
33. Sibling failure does not automatically invalidate successful independent targets.
34. Whole-fleet reconciliation occurs only after required targets are locally accepted.
35. Fleet reviewers also operate over generated knowledge rather than rediscovering the repository.
36. Fleet findings reopen only affected targets when possible.
37. Reopened targets must pass their normal hard-validation and review loop again.

## 19.8 Simplicity

38. The V0 harness should prefer ordinary explicit Python control flow over an unnecessary generic agent framework.
39. Responsibilities do not imply one class per component.
40. No complex supervisor graph, peer-to-peer agent society, planner hierarchy, multiple semantic memory databases, or arbitrary reflection stages are introduced without evidence that they solve a real failure mode.
41. Model allocation remains replaceable and should be benchmarked per role rather than hardcoded as architecture.
42. Context-reset/compaction policy remains adjustable based on actual traces.
43. Harness components should be revisited as model capability improves.

---

# 20. What this document deliberately does not lock

The following are separate design tasks.

## 20.1 Exact target catalog

Not locked here:

```text
exact target names
exact number of targets
dependencies between targets
target-specific scopes and exclusions
```

The folder-based target model is locked; the catalog content is not.

## 20.2 Concrete data schemas

Not locked here:

```text
MemoryTargetSpec
CompletionContract
AgentTaskState
EvidenceReference
CoverageState
FinalizationRequest
ValidationFinding
ValidationReport
ReviewFinding
ReviewVerdict
FleetRunState
Checkpoint
TraceEvent
```

This document defines their roles and relationships only.

## 20.3 Exact persistence layout

A filesystem-backed runtime is a natural V0 fit, but the exact paths, filenames, JSON/JSONL layout, atomic-write strategy, and snapshot structure are not locked here.

## 20.4 Detailed evidence-backed knowledge-bundle schema

Markdown, metadata, claims, evidence references, and file-bounded ownership belong to the next knowledge-contract design work.

## 20.5 Target-specific hard gates

The categories are locked, but exact rules and thresholds must be defined per target/contract.

## 20.6 Reviewer rubrics

Reviewer responsibility is locked, but rubric dimensions, severities, scoring, examples, and acceptance thresholds require explicit design.

## 20.7 Budgets and retry numbers

Budget ownership is locked.

Exact values are not.

## 20.8 Model/provider allocation

Worker and reviewer are distinct roles.

The provider/model used for each remains configuration and should be benchmark-driven.

## 20.9 Incremental-update specialization

The same control principles should apply to future maintenance/update agents, but the exact incremental workflow is not defined by this document.

---

# 21. V0 implementation guidance

The design should be implemented with the smallest architecture that preserves the locked boundaries.

A suitable implementation philosophy is:

```text
typed contracts at Bridger-owned boundaries
+
explicit Python runtime/state machine
+
existing LLMClient
+
existing RepositoryNavigator tool execution
+
filesystem-backed durable state initially
+
structured validation reports
+
fresh reviewer calls
+
clear trace events
```

Avoid implementing abstractions merely because they appear in a generic long-running-agent framework.

A practical module structure may later separate:

```text
memory/
    targets/
    runtime/
    workers/
    review/
    validation/
    state/
```

but file layout is not locked here.

The implementation should optimize for:

- inspectability;
- deterministic lifecycle behavior;
- simple recovery;
- typed boundaries;
- minimal hidden state;
- easy trace reading;
- easy unit testing of state transitions and hard gates;
- provider independence through the existing LLMClient;
- reuse of Layer 6 repository-navigation functions rather than duplicating repository tools.

---

# 22. Harness evaluation principle

The production reviewer deliberately does not re-check repository semantics.

Therefore worker trust must be earned through harness-level evaluation.

During development, Bridger should evaluate representative targets by comparing generated knowledge against expert-reviewed repository expectations.

Evaluation should measure at least the concerns already established for the memory-agent layer:

```text
valid evidence-reference rate
correctness of central behavioral claims
assigned-scope coverage
unsupported-certainty rate
Markdown / metadata / claim consistency
completion time
tool usage
model cost
stability of core conclusions across repeated runs
```

Trace inspection remains critical.

The harness-development loop is:

```text
run target
    ↓
inspect trace and artifacts
    ↓
identify where worker/context/tool/runtime behavior diverged
    ↓
change prompt/tool/contract/harness
    ↓
rerun
```

The goal is not to compensate for every observed weakness with another permanent agent.

The preferred sequence is:

```text
understand failure
→ improve interface / contract / context / hard mechanism
→ add complexity only if required
```

---

# 23. Final locked design summary

Bridger's V0 memory-agent harness is a **deterministic two-level control runtime around bounded repository-understanding workers**.

```text
PREDEFINED TARGET CATALOG
        │
        ▼
FLEET RUNTIME
        │
        ├── instantiate bounded target tasks
        ├── schedule under bounded concurrency
        ├── persist fleet/task state
        ├── isolate failures
        └── own fleet completion
        │
        ▼
TARGET RUNTIME
        │
        ▼
CONTEXT COMPILER
        │
        ▼
WORKER
        │
        ├── graph-guided repository exploration
        ├── source verification
        ├── evidence recording
        ├── target-folder Markdown generation
        └── finalization request
        │
        ▼
HARD VALIDATOR
        │
        ├── identity
        ├── permissions
        ├── artifact integrity
        ├── evidence integrity
        └── runtime invariants
        │
        ▼
ARTIFACT REVIEWER
        │
        ├── explicit target coverage
        ├── consistency
        ├── deduplication
        ├── organization
        ├── writing quality
        ├── scope discipline
        └── uncertainty quality
        │
        ▼
PASS / REPAIR LOOP
        │
        ▼
TARGET ACCEPTED
        │
        ▼
FLEET VALIDATION + ARTIFACT-ONLY CROSS-TARGET REVIEW
        │
        ▼
TARGETED REPAIR IF NEEDED
        │
        ▼
MEMORY FLEET ACCEPTED
        │
        ▼
HANDOFF TO REPOSITORY BRAIN PUBLICATION
```

The design can be reduced to five invariants:

> **1. Workers discover and generate.**

> **2. Runtime state, not conversation history, records execution reality.**

> **3. Hard gates enforce what code can establish reliably.**

> **4. Reviewers judge the generated knowledge artifacts without repeating repository discovery.**

> **5. Only the runtime decides whether a target or fleet is complete.**

These invariants are the foundation for the next task: defining the exact contracts and interfaces that make the harness implementable.
