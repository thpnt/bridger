# Stage 5 — Persistence & Recovery

## 1. Responsibility

Stage 5 is the cross-cutting **durability and recovery** layer of the memory-agent harness.

It does not introduce a new semantic worker phase.

Its responsibility is to ensure that the authoritative mutations produced by Stages 0–4 remain crash-safe and that an admitted target can resume without its original process, `WorkerContext`, provider conversation, or recent tool-result working set.

Conceptually:

```text
durable authoritative state
        ↓
Stage 3
transient WorkerContext
        ↓
Stage 4
transient provider/model/tool trajectory
        ↓
durable mutations throughout execution
        ↓
Stage 5
atomic persistence
trace
checkpoints
recovery
```

Stage 5 owns:

* persistence of existing fleet/target authorities;
* append-only execution trace;
* recoverable checkpoints;
* atomic multi-authority mutations;
* process-crash reconciliation;
* source/state integrity validation before resume;
* provider retry/backoff;
* runtime/infrastructure retry classification;
* lost-conversation recovery;
* active-context-capacity reset;
* whole-fleet restart;
* runtime error persistence.

Stage 5 does **not** own:

* target activation or initialization semantics;
* scheduling policy;
* worker context compilation;
* worker tool semantics;
* semantic completion meaning;
* candidate knowledge semantics;
* finalization semantics;
* hard validation;
* semantic review;
* repair findings;
* target/fleet acceptance.

Runtime failures never become semantic `REPAIR`.

---

## 2. Authority model

The following authority model is locked.

```text
MemoryFleetSpec
TargetTaskSpec
    immutable execution definition

FleetRunState
TargetTaskState
TargetCompletionState
    current operational authority

candidate Markdown
    current candidate-product authority

EvidenceReference
OpenQuestion
    durable target-data authorities

TaskCheckpoint
    immutable known-good recovery snapshot
    subordinate to newer valid current state

TaskEvent
    append-only execution/audit history
    never state authority

RuntimeErrorRecord
    immutable runtime-error detail

transaction / in-flight records
    private crash-consistency machinery

WorkerContext
provider conversation
execution-state overlay
recent tool-result working set
    transient and disposable
```

`TaskEvent[]` is **not** an event-sourced runtime.

Normal loading never reconstructs `TargetTaskState` by replaying events.

If trace and current authoritative state disagree, the current state remains operational authority, while the disagreement is treated as an integrity/observability problem.

---

## 3. V0 persistence model

V0 uses ordinary local filesystem persistence.

No database is introduced.

No event-sourced reducer is introduced.

No generic persistence framework is introduced.

The persistence model is:

```text
atomic current-state snapshots
+
immutable records
+
append-only trace
+
immutable named checkpoints
+
short-lived redo-style transaction intents
```

`runtime_root` contains private runtime execution state.

`output_root` contains candidate product artifacts.

Candidate Markdown never becomes runtime state merely because Stage 5 snapshots it for recovery.

### Conceptual layout

```text
runtime_root/
├── fleet-spec.json
├── fleet-state.json
├── events.jsonl
├── run.lock
│
├── errors/
│   └── <error-id>.json
│
├── transactions/
│   └── <operation-id>/
│
├── inflight/
│   └── provider/
│
└── targets/
    └── <target-task-id>/
        ├── task-spec.json
        ├── state.json
        ├── completion.json
        │
        ├── evidence/
        │   └── <evidence-id>.json
        │
        ├── questions/
        │   └── <question-id>.json
        │
        └── checkpoints/
            └── <checkpoint-id>/
                ├── checkpoint.json
                └── artifacts/
```

Current candidate Markdown remains under:

```text
TargetTaskSpec.target_workspace
⊂
MemoryFleetSpec.output_root
```

Existing Stage 0–4 path helpers should be reused where already implemented. The locked requirement is the authority separation, not unnecessary path abstraction.

---

# 4. `TaskEvent`

## 4.1 Role

`TaskEvent` is one immutable record in the fleet's append-only execution trace.

It answers:

> **What observably happened during execution?**

It does not answer:

> **What is the current authoritative state?**

### Contract

```python
class TaskEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    event_id: str

    fleet_run_id: str
    target_task_id: str | None = None

    sequence: int

    event_type: str
    timestamp: str

    operation_id: str | None = None

    payload: dict[str, Any]
```

## 4.2 Event ordering

V0 uses one fleet-global append-only trace:

```text
runtime_root/events.jsonl
```

`sequence` is monotonically increasing within one `fleet_run_id`.

```text
sequence
    = ordering authority

timestamp
    = informational/debug metadata
```

Target-local traces are derived by filtering on:

```text
target_task_id
```

A fleet-level event uses:

```text
target_task_id = null
```

No separate target event files or trace-state object are required.

## 4.3 Operation identity

`operation_id` groups records associated with one logical runtime operation and supports idempotent crash recovery.

Typical uses include:

* one artifact mutation;
* one usage transaction;
* one provider invocation and its retries;
* one checkpoint creation;
* one recovery operation.

No separate generic correlation-ID contract is required.

## 4.4 Payloads

The envelope remains generic.

Each `event_type` should nevertheless validate the payload shape expected by that event before append.

V0 does not require one large discriminated-union model containing every possible event payload.

Large source/artifact/provider payloads are referenced by identity/digest rather than embedded.

---

# 5. Trace coverage

Stages 0–4 should emit trace events for material execution boundaries, including as applicable:

```text
fleet_bound
fleet_initialized
target_initialized

phase_transition
context_hydrated
cycle_started

model_attempt_started
model_attempt_completed
model_attempt_failed

tool_dispatch_started
tool_dispatch_completed
tool_dispatch_rejected
tool_dispatch_failed

artifact_mutated
evidence_recorded
completion_updated
progress_updated
question_opened
question_resolved

usage_delta

finalization_control_received

checkpoint_created
retry_scheduled
execution_interrupted
runtime_error_recorded
recovery_reset
```

Stages 6+ may extend the controlled event vocabulary later.

Trace never contains private model reasoning or chain-of-thought.

By default Stage 5 also does not persist:

```text
complete provider conversation
complete WorkerContext
complete source reads
complete repository-navigation outputs
complete tool-result working set
complete rewritten artifact bodies
```

Events store compact metadata such as:

```text
tool/provider identity
normalized arguments where safe
result status
result digest/size
artifact/evidence reference
usage delta
error reference
```

Raw visible provider messages or full tool results may optionally be retained in an explicit debug mode as external blobs referenced by events.

Such debug data is always:

```text
optional
non-authoritative
non-required for recovery
```

---

# 6. Current-state persistence

Mutable JSON authorities use:

```text
serialize
→ write temporary sibling file
→ flush/fsync
→ atomic os.replace()
→ fsync parent directory
```

Immutable records use atomic create and are never rewritten in place.

Examples:

```text
EvidenceReference
OpenQuestion
RuntimeErrorRecord
TaskCheckpoint
```

A successful runtime mutation is not returned to Stage 4 until its authoritative durable commit boundary has been crossed.

---

# 7. Multi-authority transaction protocol

Atomic rename protects one file but cannot protect semantic operations spanning several authorities.

Examples include:

```text
TargetTaskState.usage
+
FleetRunState.usage
```

and:

```text
candidate Markdown
+
TargetTaskState.artifact_refs
```

Stage 5 therefore introduces one small private redo-style transaction helper.

It is crash machinery, not a domain contract.

## 7.1 Protocol

For one multi-authority operation:

```text
1. acquire required runtime lock(s)

2. validate preconditions
   - identities
   - expected artifact revision
   - permissions
   - budget capacity
   - operation-specific invariants

3. compute all after-images

4. durably stage required files

5. durably write:
   transactions/<operation-id>/intent.json

   ───────────────────────────────
   operation is now committed
   ───────────────────────────────

6. apply every after-image/deletion idempotently

7. fsync affected directories

8. append the required TaskEvent exactly once

9. remove the completed transaction directory
```

Recovery behavior:

```text
staging exists
but no durable intent
    → discard staging

durable intent exists
    → finish the operation forward
```

Committed operations are never rolled backward.

The transaction intent contains enough information to complete the operation and emit its trace event.

`operation_id` prevents duplicate event emission or duplicate side effects during recovery.

## 7.2 Required uses

The helper is required whenever one semantic operation spans multiple authorities, especially:

```text
target + fleet usage update

cycle start
    phase transition
    + target usage
    + fleet usage

candidate artifact write/delete
    + CandidateArtifactRef update

EvidenceReference creation
    + TargetTaskState.evidence_refs update

OpenQuestion creation
    + TargetTaskState.open_question_refs update

provider usage settlement
    + target usage
    + fleet usage
    + in-flight reservation removal

checkpoint publication
    + last_checkpoint_ref update
```

Single-authority mutations such as a completion-state update or `working_summary` replacement need only atomic replacement plus trace emission.

---

# 8. Concurrency and locking

V0 remains a single-process bounded-concurrency runtime.

No leases, heartbeats, distributed locks, worker ownership records, or distributed scheduler are introduced.

## 8.1 Process ownership

The process holds one OS-level advisory lock for the lifetime of the fleet run:

```text
runtime_root/run.lock
```

Its only purpose is to prevent two Bridger processes from concurrently owning the same fleet runtime.

Process death releases the lock through normal OS semantics.

## 8.2 Process-local synchronization

The running process uses:

```text
fleet_lock
    FleetRunState
    shared fleet budgets/reservations
    fleet recovery coordination

target_lock[target_task_id]
    target state/completion/artifacts/evidence/questions

trace_lock
    events.jsonl sequence assignment + append
```

When both state locks are required:

```text
fleet_lock
    ↓
target_lock
```

in that order.

The trace lock is independent and must not acquire state locks while held.

## 8.3 Shared usage

One runtime helper owns each Stage 4 usage delta:

```text
apply_usage_delta(target_task_id, delta)
```

and durably updates both:

```text
TargetTaskState.usage
FleetRunState.usage
```

as one logical transaction.

Workers never write either state file directly.

Concurrent targets therefore cannot drift or double-spend shared fleet capacity.

---

# 9. Candidate artifact, evidence and question durability

## 9.1 Candidate artifacts

The current candidate artifact authority is:

```text
artifact bytes under target_workspace
+
current CandidateArtifactRef
```

Every committed mutation preserves:

```text
artifact_id
relative_path
revision
digest
```

Candidate writes remain subject to Stage 4 optimistic revision checks.

A successful mutation must make the new bytes and new reference durable as one logical operation.

Temporary/staged bytes never become candidate authority.

Recovery verifies every current artifact reference against:

```text
workspace boundary
existence
revision
digest
```

## 9.2 Evidence

`EvidenceReference` remains immutable, target-bound and `SourceBinding`-bound.

Existing Stage 4 canonical source+kind+locator deduplication remains authoritative.

Persistence does not introduce another evidence identity or deduplication mechanism.

A committed evidence operation durably creates/reuses the record and updates target evidence references.

An unreferenced immutable record left by a pre-commit crash is not authoritative and may be ignored or cleaned up.

## 9.3 Open questions

`OpenQuestion` remains immutable.

Current openness continues to be represented exclusively by:

```text
TargetTaskState.open_question_refs
```

Resolving a question removes the current-state reference; it does not mutate the historical question object.

Historical open/resolve operations are visible through `TaskEvent`.

---

# 10. `TaskCheckpoint`

## 10.1 Role

`TaskCheckpoint` is an immutable **known-good target recovery point**.

It answers:

> **From what exact durable target state could execution be reconstructed without provider conversation history?**

It is not current operational authority when newer valid current state exists.

### Contract

Conceptually:

```python
class TaskCheckpoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    checkpoint_id: str
    checkpoint_sequence: int

    fleet_run_id: str
    target_task_id: str

    source: SourceBinding

    target_task_spec_digest: str

    trace_sequence: int
    created_at: str

    task_state: TargetTaskState
    completion_state: TargetCompletionState

    evidence_records: list[EvidenceReference]
    open_questions: list[OpenQuestion]

    checkpoint_digest: str
```

Candidate artifact bytes are stored beside the checkpoint and identified through the exact `CandidateArtifactRef`s contained in the checkpointed `TargetTaskState`.

Conceptually:

```text
checkpoints/<checkpoint-id>/
├── checkpoint.json
└── artifacts/
    └── exact snapshot bytes
```

`checkpoint_digest` covers the canonical checkpoint metadata and checkpoint-contained snapshot files, excluding the digest field itself.

## 10.2 Deliberately absent state

A checkpoint does **not** persist:

```text
WorkerContext
provider conversation/thread
provider messages
private model reasoning
execution-state overlay
recent tool-result working set
repository excerpts
repository graph contents
```

Repository evidence can be reacquired through existing Stage 4 tools after rehydration.

## 10.3 `last_checkpoint_ref`

`TargetTaskState.last_checkpoint_ref` identifies the latest successfully published checkpoint selected by the runtime.

Checkpoint creation may generate the checkpoint ID first so its state snapshot contains the same reference.

A complete checkpoint records the `TaskEvent.sequence` high-water mark observed before checkpoint publication.

The later:

```text
checkpoint_created
```

event references the checkpoint.

Event position is audit metadata; checkpoint consistency is established by identities, snapshots and digests rather than by event replay.

---

# 11. Checkpoint cadence

Ordinary durable state writes and named checkpoints are separate mechanisms.

Stage 5 does **not** checkpoint every mutation, model turn or tool call.

V0 creates named checkpoints at meaningful recovery boundaries:

```text
1. after target initialization
   baseline checkpoint

2. when a Stage 4 execution relinquishes control
   and future work will require fresh context, including:
   - active-context-capacity reset
   - provider/runtime interruption after local retry policy
   - orderly worker-cycle handoff
   - finalization handoff

3. after crash reconciliation,
   immediately before restarting an interrupted worker
```

Stages 6+ may reuse the same mechanism at their own future lifecycle boundaries.

---

# 12. Recovery validation

No target may resume until its durable authorities pass recovery validation.

## 12.1 Immutable identity validation

Validate:

```text
MemoryFleetSpec
TargetTaskSpec

fleet_run_id
target_task_id

SourceBinding:
    repository_id
    repository_revision
    graph_snapshot_id
    enrichment_overlay_id?

target contract version
runtime profile identity
worker profile identity
permission profile identity
```

`TargetTaskSpec.source` must still equal the owning fleet source binding.

The exact `TargetDefinition` version must still resolve.

## 12.2 Source validation

Recovery verifies that the available upstream authorities still correspond exactly to:

```text
repository revision
graph snapshot
optional enrichment overlay
```

Recovery must never:

```text
silently use another checkout revision
silently use a newer graph
silently substitute another enrichment overlay
```

A source mismatch is an integrity/runtime failure, not semantic repair.

## 12.3 Target state validation

Validate:

```text
state/spec identity
legal lifecycle phase
phase-specific invariants

TargetCompletionState obligation identity
exact TargetDefinition correspondence

nonnegative monotonic usage
no unresolved committed transaction
```

Every Stage 4 target usage delta must have been reflected exactly once at fleet scope.

## 12.4 Product/data validation

Validate:

```text
every current CandidateArtifactRef
every current EvidenceReference
every current OpenQuestion reference
last_checkpoint_ref when present
```

Artifact validation includes:

```text
inside target workspace
exists
correct revision
correct digest
```

Evidence must remain target/source compatible.

Known transaction/temp files are excluded from candidate inventory. Unexpected candidate files that conflict with the current authoritative artifact inventory are integrity failures.

---

# 13. Checkpoint fallback and rollback policy

Recovery first performs:

```text
finish committed transactions
        ↓
validate current authoritative state
```

If current state is valid, it remains authoritative even when an older checkpoint exists.

Historical checkpoint rollback is **not automatic in V0**.

A checkpoint may automatically restore missing/corrupt bytes only when the current authoritative state already identifies the exact same object revision/digest.

Example:

```text
current state:
    artifact revision = 4
    digest = X

latest checkpoint:
    exact revision 4
    exact digest X

artifact bytes missing
    → exact checkpoint bytes may be restored
```

But:

```text
current state = artifact revision 7
checkpoint = artifact revision 4
```

must never silently restore revision 4.

Recovery likewise never rolls back:

```text
ExecutionUsage
TargetCompletionState
lifecycle phase
committed evidence
```

to an older historical value.

If recovery would require losing committed work or consumed budget, the task becomes an integrity failure requiring explicit intervention rather than silently rewinding execution.

---

# 14. Safe-phase reconstruction

Stage 5 introduces no `RECOVERING` phase.

Existing lifecycle states remain the only lifecycle authority.

## 14.1 Recovered `SCHEDULED`

`SCHEDULED` already means:

> The target is admitted and owns a concurrency slot.

Recovery leaves it:

```text
SCHEDULED
```

and invokes Stage 3 directly.

Stage 2 is not called again.

No cycle is consumed merely by recovering `SCHEDULED`.

## 14.2 Recovered `HYDRATING`

`WorkerContext` is transient and may simply be discarded.

Because the cycle has not yet been charged:

```text
HYDRATING
    ↓ Stage 5 recovery transition
SCHEDULED
    ↓ Stage 3
HYDRATING
```

The existing admission/concurrency slot is preserved.

Stage 2 is not called.

No cycle is lost.

## 14.3 Recovered `WORKING`

A `WORKING` target has already consumed its cycle.

The interrupted cycle remains consumed.

Recovery performs:

```text
reconcile committed mutations
reconcile provider in-flight state
record interruption
create fresh checkpoint
        ↓
WORKING → SCHEDULED
        ↓
Stage 3 rehydration
        ↓
new Stage 4 worker execution
```

The replacement worker execution is a **new cycle**.

Therefore:

```text
interrupted cycle
    remains consumed

new HYDRATING → WORKING
    consumes another cycle

repair mode
    also consumes another repair_cycle
```

Stage 2 is never involved because the target remains the same admitted task.

## 14.4 Future active phases

For:

```text
FINALIZING
VALIDATING
REVIEWING
```

Stage 5 only provides durable loading, integrity checks and checkpoint machinery.

The owning future stage must define any phase-specific replay/re-entry semantics.

Stage 5 does not invent Stage 6–8 behavior in advance.

---

# 15. Lost provider conversation

Provider conversation state is never required for correctness.

After:

```text
process crash
provider conversation loss
tool working-set loss
```

recovery relies on:

```text
TargetTaskState
TargetCompletionState
working_summary
open questions
candidate artifacts
evidence
findings when applicable
TaskCheckpoint
```

and re-enters the existing Stage 3 hydration path.

No attempt is made to reconstruct:

```text
previous assistant messages
provider thread IDs
provider response handles
provider compacted context
historical tool turns
```

The next Stage 4 execution starts with fresh provider context.

---

# 16. Active-context-capacity recovery

Stage 4 already performs ordinary recent-tool eviction.

When the minimum valid next provider request still cannot fit:

```text
active trajectory interrupted
        ↓
durable current state preserved
        ↓
checkpoint
        ↓
WORKING → SCHEDULED
        ↓
discard transient trajectory
        ↓
Stage 3 rehydration
        ↓
new worker cycle
```

Discarded state includes:

```text
provider conversation
provider continuation reference
provider compacted context
execution-state overlay
recent tool-result working set
```

`working_summary` should be current when possible but is **not** a correctness prerequisite for reset.

Recovery remains valid using the other durable authorities when interruption occurs before the worker can update the summary.

Native within-cycle provider compaction, when available through `LLMClient`, is
also transient and never participates in recovery. No LLM summarizer,
compaction agent or generic context-reset service is introduced.

Evicted repository information can be reacquired through existing repository-navigation tools.

---

# 17. Provider retry/backoff

Provider failure classification belongs to the provider/runtime adapter.

Stage 5 must not implement:

```python
except Exception:
    retry()
```

## 17.1 V0 retry policy

One logical model request permits:

```text
initial attempt
+
maximum 2 retries
=
maximum 3 provider attempts
```

Backoff:

```text
provider Retry-After
    → honor when supplied

otherwise:
retry 1 → 1 second
retry 2 → 2 seconds
```

This is a small runtime policy and does not require a new persisted domain contract.

## 17.2 Retryable failures

Examples include:

```text
connection/reset failure
timeout
HTTP 408
HTTP 429
HTTP 5xx
provider-explicit retryable/transient failure
```

## 17.3 Non-retryable failures

Examples include:

```text
invalid request/schema
authentication/authorization
invalid model/profile configuration
nonrecoverable context/configuration error
permission-policy failure
valid provider refusal
```

Malformed model tool arguments remain Stage 4 worker-correctable errors and are not provider retries.

## 17.4 Usage interaction

Retries remain inside the same Stage 4 cycle while local retry policy remains active.

Every actual retry:

```text
reuses the same logical provider request
counts as another model invocation attempt
re-checks target/fleet hard budgets
```

The Stage 4 accounting semantics remain unchanged:

```text
model_calls
    +1 immediately before invocation attempt

provider-reported tokens
    charged when reported
```

When transient retry policy is exhausted, the current worker trajectory ends and Stage 5 performs normal fresh-cycle recovery.

Provider retry exhaustion does not become semantic `REPAIR`.

A non-retryable provider/configuration failure that makes future execution impossible may become target `FAILED`.

---

# 18. In-flight provider reservation

Stage 4 requires concurrent model calls to respect shared fleet capacity.

Stage 5 makes that reservation crash-safe through a small private persisted record.

Conceptually:

```text
attempt_id
target_task_id

input_token_reservation
output_token_reservation

state:
    prepared
    invoked
```

This is runtime machinery, not an `ExecutionUsage` field and not a new public domain contract.

## 18.1 Before invocation

Atomically:

```text
model_calls += 1
at target + fleet scope

+
create prepared token reservation
```

Normal execution then crosses the provider invocation boundary:

```text
prepared → invoked
```

## 18.2 Settled response/failure

When the provider attempt returns definitively:

```text
charge reported token usage when present
remove token reservation
```

The reservation is budget capacity, not reported consumption.

## 18.3 Crash ambiguity

If recovery finds:

```text
prepared
```

the reservation may be released because the durable invocation boundary was not crossed.

The already-durable `model_calls` increment remains consumed; Stage 5 never decrements monotonic usage.

If recovery finds:

```text
invoked
without settled response/usage
```

the provider may have consumed work.

Stage 5 therefore:

```text
keeps model_calls consumed
does not fabricate token usage
keeps the unresolved token reservation as a conservative budget hold
```

The reservation may not be silently released merely because the original process disappeared.

If unresolved ambiguity prevents safe continuation, execution fails explicitly rather than granting potentially free capacity.

Provider idempotency keys may be used when supported, but correctness does not depend on them.

---

# 19. Tool/runtime retry

Stage 5 distinguishes infrastructure failure from Stage 4 worker-correctable errors.

## 19.1 Read-only operations

A read-only tool may receive at most one automatic identical retry when the runtime explicitly classifies the failure as transient infrastructure failure.

Each actual runtime dispatch continues to consume:

```text
tool_calls += 1
```

## 19.2 Mutation operations

A committed mutation is never semantically re-issued after a crash.

Recovery uses the original `operation_id`:

```text
no commit intent
    → mutation did not commit

commit intent exists
    → finish existing mutation forward
```

## 19.3 Never infrastructure-retry

The following remain normal Stage 4 controlled errors:

```text
malformed arguments
unknown object/path
permission rejection
workspace-boundary rejection
invalid completion update
stale artifact revision
optimistic revision conflict
```

Unexpected unclassified runtime exceptions cross the Stage 5 interruption boundary rather than being retried blindly.

---

# 20. `RuntimeErrorRecord`

`TargetTaskState.last_error_ref` and `FleetRunState.last_error_ref` point to immutable `RuntimeErrorRecord`s.

### Contract

```python
class RuntimeErrorRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    error_id: str

    fleet_run_id: str
    target_task_id: str | None = None

    phase: str | None = None

    category: str
    operation: str
    message: str

    retryable: bool

    operation_id: str | None = None
    cause_ref: str | None = None
    debug_ref: str | None = None

    timestamp: str
```

V0 keeps the category vocabulary small:

```text
provider
storage
runtime
integrity
context-capacity
configuration
```

A runtime error is different from a validation/review finding:

```text
RuntimeErrorRecord
    execution/state/infrastructure problem

validation/review finding
    semantic/product-quality problem
```

A transient provider attempt that later succeeds remains visible in trace but does not need to replace `last_error_ref`.

---

# 21. Persistence frequency

The following must be durable before dependent control continues:

```text
phase transition

cycle/model/tool usage delta
provider-reported token usage

candidate artifact mutation

evidence creation/reference update
completion-state update

working_summary update
question open/resolve

RuntimeErrorRecord + last_error_ref

checkpoint publication + last_checkpoint_ref
```

Optional debug persistence is best-effort:

```text
raw provider messages
raw tool-result blobs
debug WorkerContext snapshot
full stack-trace blob
```

Failure to persist optional debug information never invalidates authoritative state.

## 21.1 Trace write failure

Authoritative state is never rolled back solely because the corresponding trace append failed.

For committed multi-authority operations, the transaction intent retains the required event until it is durably appended exactly once.

For other mutations, an unrecoverable trace-write failure stops further execution rather than continuing indefinitely without observability.

Current authoritative state remains valid.

---

# 22. `last_progress_signature` and `stall_count`

Stage 5 persists the already-existing fields:

```text
last_progress_signature
stall_count
```

but V0 does not activate heuristic stall detection.

Normal V0 behavior remains:

```text
last_progress_signature = None
stall_count = 0
```

unless a future explicitly designed mechanism owns them.

Stage 5 does not currently decide whether progress means:

```text
artifact changed
evidence added
completion changed
summary changed
question changed
```

Execution budgets already provide deterministic termination bounds.

No heuristic no-progress policy is introduced until traces demonstrate that it is needed.

---

# 23. Failure and lifecycle semantics

Stage 5 may produce existing runtime terminal states where appropriate.

## `REPAIR`

Never used for persistence, provider, source, corruption or recovery failures.

`REPAIR` remains semantic candidate repair only.

## `FAILED`

May be used for unrecoverable conditions such as:

```text
source/revision mismatch
graph/enrichment identity mismatch
unrecoverable runtime-state corruption
unrecoverable artifact/evidence integrity failure
non-retryable provider/profile configuration failure
unrecoverable persistence transaction failure
recovery ambiguity that cannot be made safe
```

## `EXHAUSTED`

Used only when the applicable execution budget is the reason no further target execution can occur.

Target budget exhaustion may produce target `EXHAUSTED`.

Fleet-budget exhaustion alone does not relabel the target as target-level `EXHAUSTED`; the fleet runtime owns the fleet-level terminal decision.

## `STOPPED`

Persisted crash-safely by Stage 5, but initiated by the operator/higher runtime coordinator rather than by persistence policy.

---

# 24. Fleet restart

Whole-process recovery follows this deterministic sequence:

```text
1. acquire runtime_root/run.lock

2. load MemoryFleetSpec

3. finish every committed unfinished transaction

4. discard abandoned pre-intent staging

5. validate/truncate any torn events.jsonl tail

6. load FleetRunState

7. load every:
       TargetTaskSpec
       TargetTaskState
       TargetCompletionState

8. validate exact upstream SourceBinding

9. validate:
       target contracts/profiles
       current artifacts
       evidence
       questions
       checkpoints
       usage/in-flight records

10. reconcile provider reservations

11. derive current active target occupancy from phases

12. verify occupancy <= max_concurrent_targets

13. recover already-active targets directly

14. only then allow Stage 2 to consider genuinely unscheduled:
       INITIALIZED
       REPAIR
```

Active occupancy is derived from:

```text
SCHEDULED
HYDRATING
WORKING
FINALIZING
VALIDATING
REVIEWING
```

No lease/heartbeat/worker-owner record is required.

Recovered active targets must never be admitted a second time.

---

# 25. Crash-point rules

The following V0 outcomes are locked.

| Crash point                                                        | Recovery rule                                                           |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| `HYDRATING` before cycle charge                                    | Return to `SCHEDULED`; rehydrate; no cycle consumed                     |
| cycle/usage committed before first model call                      | Cycle remains consumed; fresh cycle required                            |
| `model_calls` committed before provider invocation                 | Model call remains consumed; prepared token reservation may be released |
| provider invocation entered, result unknown                        | Model call remains consumed; unresolved token reservation retained      |
| provider usage committed but response trajectory lost              | Usage remains consumed; response context is disposable                  |
| read-only tool charged but result lost                             | Tool call remains consumed; result may be reacquired                    |
| mutation staged before commit intent                               | Discard staging                                                         |
| commit intent written before final file replacement                | Finish operation forward                                                |
| candidate artifact replaced before state-ref update                | Finish state-ref update forward                                         |
| evidence/question record written before committed reference update | Uncommitted orphan is non-authoritative                                 |
| target usage applied before fleet usage                            | Transaction completes fleet update                                      |
| trace tail partially written                                       | Truncate invalid tail; current state remains authority                  |
| minimum active context no longer fits                              | Checkpoint → fresh Stage 3/4 cycle                                      |
| process crashes while `SCHEDULED`                                  | Resume Stage 3 directly; never Stage 2                                  |

The preferred failure semantics are:

```text
no duplicate side effects
no budget reset
no unlimited free retries
forward recovery of committed operations
explicit failure rather than unsafe guessing
```

Perfect distributed exactly-once execution is not a V0 requirement.

---

# 26. Runtime interfaces

Stage 5 may be implemented through a small set of explicit services/helpers rather than one class per responsibility.

Conceptually:

```text
load_fleet_runtime(...)
persist_state(...)

append_task_event(...)

commit_operation(...)

create_checkpoint(...)
validate_checkpoint(...)

record_runtime_error(...)

recover_target(...)
recover_fleet(...)

run_provider_with_retry(...)
```

The transaction writer, run lock, in-flight provider reservation and atomic-file helpers remain private implementation mechanisms.

---

# 27. Minimal new durable contracts

Stage 5 introduces exactly three new durable domain contracts:

```text
TaskEvent
TaskCheckpoint
RuntimeErrorRecord
```

Stage 5 does **not** introduce:

```text
RecoveryState
RecoveryPhase
WorkerAttempt
WorkerRun
PersistenceManagerState
UsageLedger
event-sourced reducer
provider conversation state
provider continuation reference
provider compacted context
persistent scheduler queue
lease/heartbeat state
distributed transaction system
generic retry-state object
```

Private persistence records such as:

```text
transaction intent
provider in-flight reservation
temporary staged file
run lock
```

exist only to implement crash safety.

---

# 28. Stage 5 invariants

1. Stage 5 introduces no `RECOVERING` lifecycle phase.
2. Existing fleet/target state files remain operational authority.
3. `TaskEvent` is append-only history, not replay authority.
4. `TaskCheckpoint` is a recoverable snapshot subordinate to newer valid current state.
5. Candidate artifacts, evidence and runtime state remain separate authorities.
6. Provider conversation state is never required for recovery.
7. `WorkerContext`, execution-state overlays and tool working sets remain transient.
8. Every authoritative mutable file is written atomically.
9. Every committed multi-authority mutation is recoverable forward through one durable operation intent.
10. Committed operations are never rolled backward during ordinary crash recovery.
11. Usage counters are monotonic and never decremented by recovery.
12. Every Stage 4 usage delta is applied consistently at target and fleet scope.
13. An interrupted cycle remains consumed.
14. A replacement worker execution after `WORKING` interruption is a new cycle.
15. `HYDRATING` recovery does not consume a cycle that never started.
16. Recovered active targets remain admitted and bypass Stage 2.
17. Recovery never silently changes repository revision, graph snapshot or enrichment overlay.
18. Historical checkpoints never silently rewind committed work or usage.
19. Candidate artifact recovery is revision/digest exact.
20. Evidence deduplication continues to use the Stage 4 canonical identity.
21. Runtime/provider/persistence failures never become semantic `REPAIR`.
22. Every actual provider retry remains under the original target/fleet budgets.
23. Every provider invocation attempt consumes `model_calls`; reported tokens are charged when reported.
24. Ambiguous invoked provider work is not treated as free.
25. Operational tool retries remain bounded and consume normal `tool_calls`.
26. Mutation recovery finishes the original operation rather than issuing the semantic side effect again.
27. The fleet process owns one local run lock; no distributed ownership machinery exists.
28. `last_progress_signature` / `stall_count` are persisted but inactive in V0.
29. Optional debug data is never required for correctness.
30. No database, event-sourced runtime, generic persistence framework, distributed locking, lease system, heartbeat system or provider-thread dependency is introduced in V0.

---

# 29. Stage 6+ deferments

Stage 5 provides reusable durability machinery but does not define:

```text
TargetFinalizationRequest
WORKING → FINALIZING policy

hard-validation contracts
validation findings

reviewer context
review verdicts

semantic repair routing

target acceptance

fleet validation
fleet reconciliation
fleet acceptance

Repository Brain publication
```

Future stages may use:

```text
TaskEvent
TaskCheckpoint
RuntimeErrorRecord
atomic persistence
recovery validation
```

without creating a second persistence or lifecycle authority.

Stage 5 remains exclusively the cross-cutting persistence, trace and recovery layer.
