# Stage 3 — Context Hydration

## 1. Responsibility

Stage 3 is the deterministic **durable-state → bounded-worker-context** boundary.

Its lifecycle boundary is:

```text
Stage 2
TargetTaskState.phase = SCHEDULED
        ↓
Stage 3
SCHEDULED → HYDRATING
resolve authoritative inputs
project worker-relevant state
apply context-window policy
compile WorkerContext
        ↓
Stage 4
HYDRATING → WORKING
worker model/tool execution
```

`SCHEDULED` already means that the target has been admitted into execution and owns a target-concurrency slot.

Stage 3 owns:

* validating hydration preconditions;
* `SCHEDULED → HYDRATING`;
* resolving the exact worker instructions and target contract;
* projecting durable task and completion state into a model-facing view;
* hydrating the complete candidate-artifact inventory;
* validating referenced evidence state without eagerly hydrating evidence content;
* hydrating currently open repair findings;
* deriving remaining target budget;
* resolving the allowed worker tool identities;
* enforcing the hard initial provider-input cap;
* compiling one immutable `WorkerContext`;
* optional debug persistence of that compiled context.

Stage 3 does **not** own:

* scheduling or concurrency admission;
* `HYDRATING → WORKING`;
* model execution;
* provider-specific message/request construction;
* repository exploration;
* tool execution;
* candidate-artifact mutation;
* evidence mutation;
* completion-state mutation;
* transcript persistence;
* checkpoints or crash recovery;
* finalization;
* validation or review;
* repair routing;
* acceptance.

Stage 4 owns `HYDRATING → WORKING` immediately before worker execution actually begins.

This preserves the meaning:

```text
HYDRATING
    = execution admitted; worker context is being prepared

WORKING
    = worker execution has actually begun
```

A successfully compiled context therefore does not itself imply that a model call occurred.

---

## 2. Existing authorities consumed

Stage 3 consumes the already-locked authorities:

```text
MemoryFleetSpec
TargetTaskSpec
TargetTaskState
TargetCompletionState

MemoryTargetCatalog
TargetDefinition

candidate artifact state
evidence state
open-question state
finding state

worker profile
permission profile
worker instruction artifacts
```

The main immutable provenance chain remains:

```text
MemoryFleetSpec
    target_catalog_version
    source binding
        │
        ▼
TargetTaskSpec
    target_id
    target_contract_version
    worker_profile_id
    permission_profile_id
    source binding
        │
        ▼
TargetDefinition
```

`TargetCompletionState` must still correspond exactly to the completion obligations of the `TargetDefinition` identified by:

```text
TargetTaskSpec.target_contract_version
```

Stage 3 introduces no competing task, completion, artifact, evidence, or finding authority.

---

# 3. Hydration model

V0 hydration consists of:

```text
authoritative state
+
immutable instructions/contracts
+
current target-local product state
+
context-window policy
        ↓
deterministic projection
        ↓
WorkerContext
```

Stage 3 introduces:

```text
WorkerContext               transient contract
WorkerContextMode           transient vocabulary
ContextWindowManager        runtime service
```

It introduces:

```text
no context database
no context history
no persisted context authority
no conversation state
no provider thread dependency
no compaction database
no context lifecycle state
no separate repair context architecture
```

`WorkerContext` is reconstructed whenever required.

---

# 4. `WorkerContext`

## 4.1 Semantic definition

`WorkerContext` is the immutable, bounded, provider-neutral execution view supplied to one worker execution.

It answers:

> **What does this worker need to know now to continue this exact target correctly?**

It is not authoritative task state.

Conceptually:

```text
WorkerContext
├── runtime metadata
│   ├── target_task_id
│   ├── mode
│   ├── worker_profile_id
│   ├── permission_profile_id
│   └── allowed_tool_ids
│
├── immutable task context
│   ├── source binding
│   ├── shared worker instructions
│   ├── global ownership guidance
│   ├── target-specific worker instructions
│   └── target contract view
│
├── semantic progress
│   └── completion obligations + current state
│
├── continuation state
│   ├── working summary
│   ├── open questions
│   └── open repair findings
│
├── current product context
│   └── complete candidate-artifact inventory
│
└── execution headroom
    └── remaining target budget
```

The concrete implementation may use small frozen submodels for these projections. They do not become independent durable authorities.

## 4.2 Lifetime and mutability

`WorkerContext` is:

```text
transient
immutable after compilation
valid for one worker execution
reconstructable from authoritative state
non-authoritative
provider-neutral
```

Normal execution does not persist it.

The worker cannot mutate it.

Changes made during Stage 4 affect the real durable authorities and are reflected only in a later reconstruction.

---

# 5. Context mode

V0 uses exactly:

```text
INITIAL
REPAIR
```

The mode is derived, not persisted as another lifecycle authority.

Conceptually:

```text
first admitted execution
with no routed repair findings
    → INITIAL

execution readmitted after
hard-validation / target-review /
fleet-validation / fleet-review findings
    → REPAIR
```

`REPAIR` does not create:

* another `TargetTaskSpec`;
* another `target_task_id`;
* another workspace;
* another completion state;
* another evidence store;
* another budget;
* another worker architecture.

Repair is another execution of the same target task with additional structured feedback.

Crash/checkpoint recovery is not a third context mode. Recovery semantics remain Stage 5 responsibility.

---

# 6. Static instruction and target-contract resolution

Stage 3 always resolves three distinct sources.

## 6.1 Shared worker instructions

Shared worker instructions define fleet-wide worker behavior such as:

* role and objective;
* grounding requirements;
* target isolation;
* repository-navigation discipline;
* evidence discipline;
* artifact-writing boundaries;
* uncertainty requirements;
* completion/finalization behavior.

## 6.2 Target-specific worker instructions

Each target has a target-specific instruction pack containing useful investigation and execution guidance.

It must not unnecessarily duplicate the semantic contract already contained in `TargetDefinition`.

## 6.3 `TargetDefinition`

Stage 3 resolves the exact immutable definition identified by:

```text
TargetTaskSpec.target_id
TargetTaskSpec.target_contract_version
```

The worker-facing projection includes:

```text
canonical_question
purpose
expected_abstraction

always_relevant_scope
conditional_scope
exclusions

boundary_guidance
investigation_expectations
evidence_expectations

output_quality_expectations
```

Runtime-only fields such as:

```text
activation
depends_on
```

do not need to be exposed to the worker.

The global cross-target ownership guidance from `MemoryTargetCatalog` is also included so that workers preserve canonical semantic ownership.

Instruction/profile identities must resolve to immutable or versioned instruction content. Materially changing worker instructions without changing their identifying profile/version is invalid.

---

# 7. Completion-state projection

The worker receives **every completion obligation**, including already resolved obligations.

Stage 3 joins:

```text
TargetDefinition.completion_obligations
+
TargetCompletionState.items
```

into one model-facing view.

For every obligation the worker receives:

```text
obligation_id
description
applicability
condition_hint

status
resolution_note
evidence_refs
```

The completion vocabulary remains exactly:

```text
uninvestigated
covered
not-applicable
unknown
```

Resolved obligations are not removed merely to save tokens.

This prevents later repair work from losing awareness of previously satisfied semantic responsibilities.

The target's completion contract is deliberately finite and therefore belongs to the mandatory hydration core.

Stage 3 does not judge whether a current resolution is semantically correct.

---

# 8. `TargetTaskState` projection

`TargetTaskState` is **not** serialized wholesale.

Only model-useful continuation state is projected.

| State                              | Worker projection                                                       |
| ---------------------------------- | ----------------------------------------------------------------------- |
| `working_summary`                  | Always included when present                                            |
| `open_question_refs`               | Dereferenced and included                                               |
| `artifact_refs`                    | Complete inventory only; contents are retrieved on demand during Stage 4 |
| `evidence_refs`                    | Not eagerly projected as evidence handles; evidence is retrieved on demand during Stage 4 |
| `open_finding_refs`                | Every open finding included in repair mode                              |
| `usage`                            | Converted into remaining-budget view                                    |
| `phase`                            | Not blindly serialized; execution mode represents what the worker needs |
| `last_checkpoint_ref`              | Runtime-private                                                         |
| `last_progress_signature`          | Runtime-private                                                         |
| `stall_count`                      | Runtime-private                                                         |
| `pending_finalization_request_ref` | Runtime-private                                                         |
| `last_error_ref`                   | Runtime-private                                                         |
| `termination_reason`               | Runtime-private                                                         |
| `last_accepted_result_ref`         | Runtime-private                                                         |

The model receives what it needs to continue the work, not an internal runtime dump.

---

# 9. Working summary and open questions

`working_summary` is first-class durable continuation state.

When present it is included in full.

Stage 3:

* does not rewrite it;
* does not summarize it again;
* does not silently truncate it;
* does not treat it as repository truth.

Its purpose is to preserve compact continuity without transcript replay.

If a `working_summary` has grown so large that the mandatory hydration core cannot fit, that is a state-maintenance/configuration failure rather than permission for Stage 3 to silently discard it.

Every currently open question is also dereferenced and hydrated.

Stage 3 does not include:

```text
resolved historical questions
question-generation history
reasoning traces that produced questions
```

---

# 10. Repair findings

In `REPAIR` mode, every currently open finding routed to this target is hydrated.

Supported origins remain:

```text
hard-validation
target-review
fleet-validation
fleet-review
```

The worker-facing projection must expose at least:

```text
finding identity
origin
actionable finding content
affected artifact/scope when present
```

Stage 3 does not expose hidden reviewer reasoning or review transcripts.

All repair sources converge on the same context architecture:

```text
normal WorkerContext
+
currently open actionable findings
```

No separate `RepairAgent` or repair-specific worker contract exists.

---

# 11. Candidate artifact hydration

Candidate artifacts use **complete inventory without eager content hydration**.

## 11.1 Complete inventory is mandatory

Every current `CandidateArtifactRef` appears in the context inventory.

At minimum the worker can determine:

artifact identity
relative path
current revision

The runtime retains the authoritative digest whether or not the digest itself is useful to the model.

Stage 3 does not hydrate candidate-artifact contents.

Artifact contents remain available during Stage 4 through the target-workspace read tools.

The rule is:

Stage 3 tells the worker which candidate artifacts exist. Stage 4 lets the worker retrieve their contents on demand.

## 11.2 Integrity

Before the artifact inventory is exposed, every current artifact reference must resolve against authoritative candidate-artifact state.

The following are integrity failures:

missing referenced artifact
artifact outside target workspace
artifact identity mismatch
artifact revision mismatch
artifact digest mismatch

Stage 3 never substitutes unverified filesystem state for an authoritative candidate-artifact reference.


This removes:

- opportunistic full-content hydration;
- artifact selection priority;
- repair-specific artifact-content prioritization;
- full-or-omit logic;
- artifact-content token fitting.

Stage 3 never silently hydrates unverified filesystem contents in place of the referenced candidate.

---

# 12. Evidence hydration

Stage 3 does **not** eagerly hydrate evidence contents or a separate collection of compact evidence handles.

Durable evidence remains authoritative external state.

Evidence references that are already part of mandatory worker-facing state, such as references attached to completion items or repair findings, remain visible through those projections.

Detailed evidence is retrieved on demand during Stage 4 through the appropriate evidence and repository-navigation tools.

Stage 3 does not eagerly replay:

source excerpts
search-result pages
graph tool responses
symbol-navigation results
historical tool outputs
repository exploration transcripts
compact evidence-handle collections

The intended relationship is:

working_summary
    → what the worker currently understands

completion/findings evidence refs
    → identities of relevant durable grounding when already referenced

Stage 4 tools
    → evidence and repository details retrieved on demand

Stage 3 may validate that evidence references present in authoritative state resolve correctly.

A missing durable evidence record referenced by authoritative state is an integrity failure.


This is an important distinction: **we are not removing evidence continuity from durable state. 

---

# 13. No transcript hydration in V0

Stage 3 includes no previous model conversation history.

Specifically, it does not hydrate:

```text
previous assistant messages
previous user/tool messages
last-N conversation turns
old reasoning
old tool outputs
provider conversation IDs
provider thread IDs
```

Within one bounded Stage 4 worker execution, immediate model/tool interaction may naturally accumulate in the active provider context.

Across worker executions, continuity is reconstructed from:

```text
working_summary
open questions
completion state
candidate artifacts
evidence
repair findings
```

Recovery must therefore never depend on provider conversation state.

---

# 14. Repository-context boundary

Stage 3 performs no repository discovery.

It does not use `RepositoryNavigator` to decide what repository files, symbols, graph entities, or source excerpts are relevant.

The only eagerly represented upstream repository information is identity/provenance such as:

```text
repository_id
repository_revision
graph_snapshot_id
enrichment_overlay_id?
```

Repository understanding remains progressively disclosed during Stage 4 through the existing Layer 6 `RepositoryNavigator`.

The boundary is:

```text
Stage 3
    hydrates task continuity

Stage 4 + RepositoryNavigator
    hydrates repository evidence on demand
```

The whole repository, whole graph, and sibling target outputs are never automatically injected.

---

# 15. Worker-tool boundary

Stage 3 resolves:

```text
permission_profile_id
allowed_tool_ids
```

and verifies that the referenced permission/profile configuration is available and internally valid.

`WorkerContext` contains allowed tool identities, not provider-specific function/tool schemas.

Stage 4 owns:

* concrete tool registry resolution;
* provider-ready tool definitions;
* tool invocation;
* permission enforcement;
* tool-result handling.

This keeps `WorkerContext` provider-neutral while making the permitted execution surface explicit.

---

# 16. Remaining-budget projection

The worker receives derived target-level execution headroom rather than raw budget and usage objects.

Conceptually:

```text
RemainingExecutionBudget
├── cycles
├── model_calls
├── tool_calls
├── repair_cycles?
├── input_tokens?
└── output_tokens?
```

For every bounded dimension:

```text
remaining = configured limit - current usage
```

An unconfigured optional token dimension remains unbounded in the view.

The worker does **not** receive fleet-wide remaining budget.

Fleet budget:

* is shared across concurrent targets;
* changes independently of one worker;
* remains runtime-owned.

Stage 2 remains the authority that decides whether another execution may be admitted. Showing target headroom to the worker does not transfer budget authority to the model.

---

# 17. Context-window management

Stage 3 introduces a small cross-cutting runtime service:

```text
ContextWindowManager
```

It exists because two different limits must be managed:

```text
1. initial hydrated model input
2. total active model context as a Stage 4 tool loop accumulates
```

These are distinct from `ExecutionBudget`.

## 17.1 Responsibility

`ContextWindowManager` provides model-aware visibility over:

```text
model context-window capacity
configured/reserved output capacity
current input-token count
remaining request context capacity
hard initial provider-input cap
```

It is used by Stage 3 to bound initial hydration.

Stage 4 must later reuse the same service before model calls as messages, tool calls, and tool results accumulate.

It does **not**:

```text
store conversation history
become runtime authority
perform compaction
reset contexts
summarize tool history
decide checkpoint recovery
```

Those policies remain Stage 4/5 concerns.

## 17.2 V0 model policy

Current GPT-5.6 Luna and GPT-5.6 Terra both expose approximately:

```text
context window       1,050,000 tokens
maximum output         128,000 tokens
```

For Bridger V0 the hard maximum **complete initial provider request input** is:

```text
32,000 tokens
```

This is a hard Stage 3 limit, not a preferred fill target.

Bridger should minimize initial model context rather than attempt to utilize the available model context window.

The initial request contains only the authoritative task context required to begin or continue the target correctly. Repository evidence, candidate-artifact contents, and other working detail are retrieved on demand during Stage 4 through explicit tools.

Therefore:

actual initial request size
    = only the mandatory compiled context required for this execution

hard maximum
    = 32,000 tokens

Unused capacity remains unused.

Stage 3 never adds optional context merely because token capacity remains available.

32,000 is a V0 runtime-profile hard limit, not a semantic target-contract constant.

A future profile/model may select another hard limit.

## 17.3 Complete request budget

The 32K hard limit applies to the **complete first provider input**, not merely the serialized `WorkerContext`.

Therefore the maximum `WorkerContext` payload allowance is derived after accounting for provider/request overhead such as:

```text
tool definitions
structured-output schema when applicable
provider framing/message overhead
other fixed request content
```

Conceptually:

initial_request_input_hard_cap = 32K

minus non-WorkerContext request input
        ↓
maximum WorkerContext token allowance

Stage 3 does not attempt to fill that allowance.

If the complete mandatory initial provider input exceeds 32K:

hydration fails

---

## 17.4 Global context-window visibility

During Stage 4 the same manager must be able to derive, before each model request:

```text
model_context_window_tokens
current_request_input_tokens
reserved_response_tokens
remaining_context_tokens
within_context_limit
```

The effective hard relationship is:

```text
current input
+
maximum/reserved response + reasoning capacity
<=
model context window
```

Stage 3 does not decide what Stage 4 does when an accumulated context approaches that boundary; it only establishes the shared mechanism needed to observe it.

---

# 18. Token counting

V0 implements one token-counting backend only:

```text
OpenAI-compatible token counting
```

There is no generic multi-provider tokenizer abstraction required beyond the minimal interface needed by `ContextWindowManager`.

V0 does not use:

```text
characters / 4
word-count approximations
provider-independent guesses
```

for context-window enforcement.

The counter operates on the exact serialized context/request representation being budgeted as closely as the OpenAI tokenizer/request format permits.

Additional provider-specific counters are deferred until Bridger supports another provider requiring them.

Context-token accounting is separate from the cumulative:

```text
ExecutionUsage.input_tokens
ExecutionUsage.output_tokens
```

contracts.

The former answers:

> **Will this individual model request fit?**

The latter answers:

> **How much execution budget has this target consumed over its lifetime?**

---

# 19. Mandatory hydration

## 19.1 Mandatory core

The following must never be silently removed to make the context fit:

```text
shared worker instructions
global ownership guidance
target-specific worker instructions
target semantic contract

source binding

all completion obligations + current states

working_summary when present
all open questions

all open repair findings in REPAIR mode

complete candidate-artifact inventory

remaining target budget
allowed tool identities
```

If the mandatory core plus required provider/request overhead cannot fit inside the configured initial-input budget:

```text
hydration fails
```

Stage 3 does not silently truncate a completion contract, repair finding, or continuation summary.

---

# 20. Omission visibility

Optional omission must be explicit.

The worker must be able to distinguish:

```text
artifact/evidence does not exist
```

from:

```text
artifact/evidence exists but was not eagerly hydrated
```

The context therefore exposes appropriate counts/availability information, conceptually:

```text
candidate artifacts:
    total: 6
    contents included: 3
    contents available on demand: 3

evidence:
    total: 120
    handles included: 40
    additional evidence available on demand: 80
```

No omitted authoritative record is deleted or mutated.

---

# 21. Canonical serialization and prompt caching

The serialized model-facing context must be deterministic and ordered **stable-first**.

This is required both for reproducibility and to maximize provider input-prefix caching.

The ordering principle is:

```text
most reusable / least cycle-dependent
        ↓
most dynamic / cycle-dependent
```

Canonical order:

```text
1. shared worker instructions

2. fleet/source-stable context
   - source binding
   - global cross-target ownership guidance

3. target-stable context
   - target-specific worker instructions
   - immutable target contract

4. execution mode

5. completion obligations + current states

6. repair findings                  # REPAIR only

7. working summary
8. open questions

9. remaining target budget

10. complete candidate-artifact inventory
```

Stable sections must not contain unnecessary cycle-specific data such as:

```text
timestamps
debug sequence numbers
changing counters
ephemeral request IDs
```

before reusable content.

Runtime/debug metadata such as `target_task_id` may exist in the structured `WorkerContext` without being placed before stable model-facing content.

Collection serialization must also be deterministic:

```text
completion obligations
    → TargetDefinition order

artifact inventory
    → normalized relative-path order
```

Stage 4 should preserve the same stable-prefix principle when adding provider-specific request structure and stable tool definitions.

---

# 22. Context compiler

Stage 3 exposes one primary compilation interface:

```text
compile_worker_context(...)
    → WorkerContext
```

Conceptually it consumes:

```text
MemoryFleetSpec

TargetTaskSpec
TargetTaskState
TargetCompletionState

MemoryTargetCatalog
TargetDefinition

resolved worker profile
resolved permission profile
shared worker instructions
target-specific worker instructions

candidate artifact resolver        # reference/integrity validation only
evidence resolver                  # referenced-state integrity validation only
finding resolver
open-question resolver

ContextWindowManager
```

It does not require:

```text
sibling TargetTaskState objects
full FleetRunState contents
RepositoryNavigator
trace history
checkpoint history
reviewer transcript
provider conversation state
```

## Compilation sequence

```text
1. validate task/spec/source identity
2. verify TargetTaskState.phase == SCHEDULED
3. transition SCHEDULED → HYDRATING
4. resolve exact catalog/TargetDefinition/profile/instructions
5. validate TargetCompletionState against TargetDefinition
6. resolve and integrity-check current artifact references
7. resolve open questions
8. resolve open findings
9. validate referenced evidence state
10. derive context mode
11. derive remaining target budget
12. derive the maximum WorkerContext allowance under the 32K complete-request hard cap
13. construct the mandatory WorkerContext
14. serialize/count the complete initial provider input as accurately as the V0 token-counting policy permits
15. fail if the complete initial provider input exceeds 32K
16. produce immutable WorkerContext
17. optionally write debug snapshot
18. return WorkerContext
```

Compilation requires no LLM call.

Given identical authorities, static artifacts, token-counting policy, and profile configuration, compilation must produce semantically identical `WorkerContext` content.

---

# 23. Lifecycle mutations and side effects

The Stage 3 lifecycle mutation is:

```text
SCHEDULED → HYDRATING
```

Stage 3 does not increment execution consumption merely because hydration occurred:

```text
cycles
model_calls
tool_calls
repair_cycles
input_tokens
output_tokens
```

Those counters represent actual execution consumption.

Normal context compilation does not mutate:

```text
working_summary
open questions
artifact refs
evidence refs
completion state
findings
budgets
checkpoints
accepted results
```

The pure context-building portion should remain separable from lifecycle mutation and debug-output code.

---

# 24. Debug context persistence

`WorkerContext` is not persisted during normal execution.

When explicit context-debug mode is enabled, Stage 3 writes an inspectable snapshot of the exact compiled context.

Conceptual layout:

```text
.bridger/
└── debug/
    └── <fleet_run_id>/
        └── worker-contexts/
            └── <target_task_id>/
                ├── hydration-0001.json
                ├── hydration-0002.json
                └── ...
```

The debug snapshot should preserve:

```text
structured WorkerContext
canonical serialized model-facing context
token-count/context-window diagnostics
```

This storage exists exclusively for:

```text
developer inspection
prompt debugging
context-selection debugging
token-budget debugging
evaluation of context quality
```

It is explicitly **not**:

```text
recovery state
checkpoint state
task authority
conversation memory
publication input
Repository Brain content
```

The runtime must behave identically when debug persistence is disabled.

Failure to write a debug snapshot must not make an otherwise valid hydration fail. It should only produce diagnostic/logging information.

If exact provider-wire requests are later required for debugging, Stage 4 may add provider-request snapshots beside these files; that does not change Stage 3 authority.

---

# 25. Successful hydration

Hydration succeeds when:

```text
task/spec/source identities are valid
TargetDefinition resolves exactly
completion state is structurally valid
required referenced state resolves
candidate artifact integrity checks pass
worker/profile/instruction configuration resolves
mandatory WorkerContext is complete
complete initial provider input does not exceed the 32K hard cap
WorkerContext is produced
```

At successful Stage 3 exit:

```text
TargetTaskState.phase == HYDRATING
```

Stage 4 then owns:

```text
HYDRATING → WORKING
```

immediately before beginning worker execution.

---

# 26. Failure semantics

Stage 3 distinguishes two classes.

## 26.1 Illegal invocation

Examples:

```text
target phase is not SCHEDULED
task/state identities do not match
target belongs to another fleet
duplicate invalid hydration invocation
```

The operation is rejected.

If the illegal condition is detected before transition, Stage 3 does not mutate the phase.

These are runtime/programming errors, not worker repair.

## 26.2 Hydration integrity/configuration failure

Examples:

```text
missing TargetDefinition
catalog/version mismatch
target contract mismatch
source/spec mismatch

invalid TargetCompletionState
missing completion obligation
unexpected completion obligation

missing referenced candidate artifact
artifact digest/revision mismatch

missing referenced evidence
missing open-question record
missing open finding

missing worker profile
missing permission profile
missing worker instructions

invalid context-window configuration
complete initial provider input exceeds the 32K hard cap

malformed persisted runtime state
```

These failures cannot be repaired by the worker.

They therefore do not create semantic `REPAIR` findings.

For an unrecoverable handled V0 hydration failure:

```text
HYDRATING → FAILED
```

with the relevant runtime error recorded through the existing error mechanism.

Transient process/storage recovery policy remains Stage 5 responsibility.

---

# 27. First execution

A normal first execution begins approximately as:

```text
phase = SCHEDULED

working_summary = null
open_question_refs = []
artifact_refs = []
evidence_refs = []
open_finding_refs = []

all completion items = uninvestigated
```

Hydration produces:

```text
INITIAL mode

shared + target instructions
source identity
complete target semantic contract

all completion obligations:
    uninvestigated

no prior candidate artifacts
no prior evidence
no findings

remaining target budget
allowed tools
```

Repository understanding begins through `RepositoryNavigator` during Stage 4.

---

# 28. Repair execution

A repair execution receives the same immutable task and durable progress plus the current actionable findings.

Conceptually:

```text
REPAIR mode

same source binding
same target contract
same original target budget

all completion obligations + current resolutions

all open repair findings

working summary
open questions

complete candidate-artifact inventory

remaining target budget
```
Candidate-artifact contents and detailed evidence remain available on demand through Stage 4 tools and are not eagerly hydrated.

The worker may then:

```text
inspect more repository evidence
edit artifacts
rewrite artifacts
split/merge documents
reorganize target-local output
update completion state
request finalization again
```

Fleet-reconciliation reopening uses this same mechanism.

No sibling worker history is automatically hydrated.

---

# 29. Determinism and authority

The following remain authoritative:

```text
MemoryFleetSpec
TargetTaskSpec
TargetTaskState
TargetCompletionState

TargetDefinition / MemoryTargetCatalog

candidate artifact state
evidence state
question state
finding state
```

The following are derived:

```text
WorkerContext
WorkerContextMode
remaining-budget view
maximum WorkerContext token allowance
serialized model-facing context
context-window diagnostics
```

`WorkerContext` can never be used as durable task truth.

Normal recovery reconstructs it from the authoritative state.

Debug snapshots do not alter this rule.

---

# 30. Stage 3 invariants

# 30. Stage 3 invariants

1. Only a target in `SCHEDULED` may enter normal Stage 3 hydration.
2. Stage 3 owns `SCHEDULED → HYDRATING`.
3. Stage 4 owns `HYDRATING → WORKING`.
4. `WorkerContext` is transient, immutable and provider-neutral.
5. Normal execution does not persist `WorkerContext`.
6. Debug persistence is optional, non-authoritative and non-blocking.
7. No previous conversation transcript is required for hydration.
8. Repository source content is not eagerly discovered by the compiler.
9. Every completion obligation is represented in every worker context.
10. `working_summary`, open questions and open repair findings are mandatory when present.
11. Candidate-artifact inventory is complete.
12. Candidate-artifact contents are never eagerly hydrated in Stage 3.
13. Detailed evidence and separate evidence-handle collections are never eagerly hydrated in Stage 3.
14. Candidate-artifact contents and detailed evidence are retrieved on demand during Stage 4.
15. Fleet budget is not exposed as worker-owned headroom.
16. Remaining target budget is derived, not authoritative.
17. Execution budgets and model context-window capacity are separate mechanisms.
18. The V0 complete initial provider-input hard cap is 32K tokens.
19. The 32K cap is a maximum, not a target or fill level.
20. Unused initial context capacity remains unused.
21. `ContextWindowManager` observes both initial hydration and later accumulated Stage 4 context.
22. V0 implements OpenAI-compatible token counting only.
23. Mandatory context must fit within the complete-request hard cap; it is never silently discarded.
24. No optional-context selection, ranking, filling, or omission accounting exists in Stage 3.
25. Stable context is serialized before dynamic context to maximize reusable prompt-prefix caching.
26. Compilation requires no LLM.
27. Hydration never creates semantic repair findings for runtime corruption.
28. Missing or mismatched authoritative references fail explicitly.
29. No provider conversation/thread ID is required for correctness or recovery.
30. No new persisted context authority is introduced.
31. Target workers remain isolated from sibling execution histories.

---

# 31. Stage 4+ deferments

Stage 3 intentionally does not lock:

### Stage 4

```text
exact provider request/message format
model/tool loop
concrete worker tool schemas
tool execution behavior
tool-result accumulation policy
context-reset/compaction behavior
completion-update operations
evidence-recording operations
workspace-write operations
finalization tool
```

Stage 4 must reuse `ContextWindowManager` to monitor effective active context before each model request.

### Stage 5

```text
checkpoint contract
recovery from HYDRATING/WORKING
crash reconstruction
retry/backoff policy
context reset after recovery
```

### Stages 6–9

```text
finalization-request contract
validation finding contract
review finding contract
reviewer context
repair-routing implementation
```

Stage 3 only requires that future findings can be projected into actionable worker-facing content.

### Stage 10+

```text
accepted-result freezing
fleet-level sibling-artifact access
fleet reconciliation context
Repository Brain publication
```

Stage 3 remains specifically the bounded worker-context hydration boundary.
