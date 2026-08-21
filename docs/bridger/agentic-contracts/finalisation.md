# Stage 6 — Finalization Request

**Status:** Locked for V0

## Responsibility

Stage 6 is the explicit runtime handoff between worker execution and deterministic evaluation.

It receives a valid Stage 4 `request_finalization()` control signal, freezes the exact candidate being submitted, persists an immutable finalization request, and transitions the target from:

```text
WORKING → FINALIZING
```

Stage 6 does not evaluate whether the candidate is complete or correct.

Its only successful outcome means:

> The worker's current candidate has been durably submitted for evaluation.

The execution boundary is:

```text
Stage 4 — Worker Cycle
        │
        │ valid request_finalization()
        ▼
Stage 6 — Finalization Request
        │
        │ durable TargetFinalizationRequest
        │ exact candidate checkpoint
        │ WORKING → FINALIZING
        ▼
Stage 7 — Hard Validation
```

`FINALIZING → VALIDATING` belongs to Stage 7.

---

## Existing Stage 4 contract

Stage 4 already owns the worker-facing control:

```text
request_finalization()
```

Its semantics are:

> I believe the current target candidate is ready for runtime evaluation.

The control call:

* takes no semantic arguments;
* is not an operational worker tool;
* does not consume `tool_calls`;
* must be the sole model tool/control call in its response;
* ends the active Stage 4 worker trajectory when valid.

Stage 4 does not:

* create `TargetFinalizationRequest`;
* set `pending_finalization_request_ref`;
* perform `WORKING → FINALIZING`;
* evaluate completion obligations;
* run hard validation.

Those responsibilities begin at Stage 6 or later.

---

# 1. `TargetFinalizationRequest`

Stage 6 introduces one new persisted contract:

```python
class TargetFinalizationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    finalization_request_id: str
    fleet_run_id: str
    target_task_id: str

    candidate_checkpoint_ref: str

    created_at: datetime
```

`TargetFinalizationRequest` is an immutable lifecycle/control record.

It identifies:

```text
which target submitted
+
which exact candidate was submitted
+
when the submission was created
```

It does not duplicate the candidate itself.

No worker-authored semantic payload is included.

Fields such as the following are excluded from V0:

```text
reason
summary
confidence
completion claim
evidence-quality claim
artifact list
evidence list
completion-state copy
SourceBinding copy
```

The exact submitted candidate is represented by `candidate_checkpoint_ref`.

---

# 2. Exact submitted candidate

Every successful Stage 6 operation creates a **fresh Stage 5 `TaskCheckpoint`**.

An arbitrary existing `TargetTaskState.last_checkpoint_ref` must not be reused because it may predate the final Stage 4 mutations.

The finalization boundary is therefore:

```text
current durable WORKING candidate
        ↓
fresh TaskCheckpoint
        ↓
TargetFinalizationRequest.candidate_checkpoint_ref
```

The checkpoint is the immutable identity of the candidate submitted for this evaluation round.

Stage 7 and later evaluation stages must evaluate the candidate identified by:

```text
TargetFinalizationRequest.candidate_checkpoint_ref
```

rather than inferring the submitted candidate from the current live workspace.

This allows later repair cycles to modify the workspace without changing the historical candidate that was previously evaluated.

No additional contracts such as:

```text
FinalizationSnapshot
CandidateSubmission
EvaluationBundle
```

are introduced.

`TaskCheckpoint` already provides the required candidate snapshot boundary.

---

# 3. Finalization checkpoint semantics

The finalization checkpoint captures the final committed candidate while the target is still logically in:

```text
WORKING
```

It represents the exact worker-produced state submitted for evaluation.

The current authoritative `TargetTaskState` is then transitioned to:

```text
phase = FINALIZING
```

This preserves the distinction:

```text
TaskCheckpoint
    → what candidate was submitted

TargetTaskState
    → where runtime control currently is
```

At successful Stage 6 completion:

```text
TargetTaskState.last_checkpoint_ref
    ==
TargetFinalizationRequest.candidate_checkpoint_ref
```

Later stages may create newer checkpoints. The permanent identity of the submitted candidate therefore remains the checkpoint referenced by the `TargetFinalizationRequest`, not the current value of `last_checkpoint_ref`.

---

# 4. Stage 6 runtime interface

The Stage 6 runtime should expose one small operation, conceptually:

```text
handle_finalization_request(target_task_id)
    → TargetFinalizationRequest
```

The exact function name may follow the existing runtime module structure.

The caller is the Stage 4 runtime after a valid standalone `request_finalization()` response has already been recognized.

Stage 6 derives all candidate and source state from existing authoritative persisted objects.

No semantic arguments are supplied by the worker.

---

# 5. Preconditions

A new finalization submission may be created only when:

```text
TargetTaskState.phase == WORKING
```

and Stage 4 execution is quiescent.

Before Stage 6 commits:

* the worker model call that emitted `request_finalization()` has ended;
* all preceding Stage 4 mutations are durably committed;
* no worker mutation remains in flight;
* usage from the Stage 4 model invocation has already been accounted for;
* any shared model-call reservations have been settled.

Stage 6 does not inspect semantic candidate readiness.

---

# 6. Persistence transaction

The complete finalization handoff is one Stage 5 logical persistence transaction.

Conceptually:

```text
BEGIN finalization transaction

1. create fresh finalization TaskCheckpoint

2. create immutable TargetFinalizationRequest
       candidate_checkpoint_ref = checkpoint

3. update TargetTaskState
       last_checkpoint_ref = checkpoint
       pending_finalization_request_ref = request
       phase = FINALIZING

4. append finalization-related TaskEvent records

COMMIT
```

Stage 6 reuses the persistence, checkpoint, atomic-write, transaction, and recovery mechanisms already defined by Stage 5.

No separate finalization transaction framework is introduced.

The committed state must never expose:

```text
phase = FINALIZING
```

without a valid:

```text
pending_finalization_request_ref
        ↓
TargetFinalizationRequest
        ↓
candidate TaskCheckpoint
```

Likewise, a successfully committed current finalization request must not coexist with an authoritative target state that continues normal Stage 4 execution.

---

# 7. `pending_finalization_request_ref`

`TargetTaskState.pending_finalization_request_ref` identifies:

> The immutable finalization request currently being evaluated for this target.

It is populated atomically with:

```text
WORKING → FINALIZING
```

During the same evaluation round it remains stable through downstream evaluation phases such as:

```text
FINALIZING
VALIDATING
REVIEWING
```

Stage 6 does not clear it.

Later lifecycle stages own clearing the current pending request when that evaluation round ends, for example when routing into repair or when local acceptance is completed.

A target must not begin another `WORKING` cycle while an old finalization request remains pending.

Historical `TargetFinalizationRequest` objects remain immutable and are not reused.

---

# 8. Multiple finalization rounds

One `target_task_id` may produce multiple historical finalization requests over its lifetime.

For example:

```text
WORKING
→ request A
→ FINALIZING
→ VALIDATING
→ REPAIR
→ SCHEDULED
→ HYDRATING
→ WORKING
→ request B
→ FINALIZING
```

Both requests remain historical immutable records:

```text
request A → checkpoint A
request B → checkpoint B
```

Repair does not create:

* a new `TargetTaskSpec`;
* a new `target_task_id`;
* a new source binding;
* a fresh execution budget.

Usage and budgets continue on the same target task.

---

# 9. Finalization protocol validity

Stage 6 validates only that a coherent runtime submission can be created.

Examples of Stage 6-level invalidity include:

```text
unknown target
wrong target/run binding
phase != WORKING
worker mutation still in flight
corrupt authoritative state
candidate checkpoint cannot be persisted coherently
```

Stage 6 does not determine whether the candidate is semantically ready.

The following are therefore valid states to submit for evaluation:

```text
uninvestigated completion obligations
unknown obligations
not-applicable obligations
open questions
missing evidence
empty evidence set
missing or empty candidate artifacts
```

Their effect on validation belongs to Stage 7 or later stages.

The worker is allowed to request evaluation while mistaken.

---

# 10. Candidate immutability during evaluation

No additional frozen-workspace state is introduced.

Worker mutation permissions are enforced by lifecycle.

Worker-owned mutation interfaces such as:

```text
TargetWorkspace
CompletionStateUpdater
EvidenceRecorder
progress/state mutation operations
```

must allow worker-originated mutation only while:

```text
TargetTaskState.phase == WORKING
```

Once Stage 6 commits:

```text
WORKING → FINALIZING
```

the submitted candidate is no longer mutable by Stage 4.

The same restriction naturally applies while the target remains in downstream evaluation phases.

The immutable checkpoint referenced by the finalization request remains the authoritative submitted candidate even if a later repair round modifies the live workspace.

---

# 11. Open questions and uncertainty

Open questions are allowed at finalization.

They may represent legitimate states such as:

```text
unknown behavior
contradictory repository evidence
insufficient evidence
ambiguous intent
```

Stage 6 preserves the current open-question state through the finalization checkpoint.

It does not require open questions to be empty.

Whether a particular unresolved question prevents later validation or acceptance belongs to downstream stages.

---

# 12. Idempotency

Stage 6 does not introduce a separate:

```text
FinalizationAttempt
attempt counter
generic idempotency contract
```

Idempotency is derived from the persisted target lifecycle and Stage 5 transaction recovery.

Normal first invocation:

```text
phase = WORKING
pending_finalization_request_ref = null
```

creates one new checkpoint and one new request.

After successful commit:

```text
phase = FINALIZING
pending_finalization_request_ref = request A
```

a repeated handling of the same logical finalization must resolve and return the existing request rather than create a second request.

If the process crashes during persistence, Stage 5 recovery completes or restores the same logical transaction.

If the transaction never became durable, authoritative state remains at the previous `WORKING` checkpoint and no finalization submission exists.

No public `operation_id` is required in `TargetFinalizationRequest`.

Stage 5 may continue using its internal transaction operation identifiers for persistence and trace purposes.

---

# 13. Recovery from `FINALIZING`

A valid recovered target in:

```text
phase = FINALIZING
```

must have:

```text
pending_finalization_request_ref
        ↓
existing TargetFinalizationRequest
        ↓
existing valid candidate TaskCheckpoint
```

The request and checkpoint must resolve to the same:

```text
fleet_run_id
target_task_id
source/spec identity
```

Once this state exists durably, Stage 6 is complete.

Recovery from `FINALIZING` therefore performs no worker execution.

It must not:

```text
return through Stage 2
rehydrate Stage 3 worker context
restart Stage 4
restore provider conversation
create another finalization request
create another submission checkpoint
```

The recovered request is handed directly to Stage 7.

Provider/model conversation state is not required for recovery.

If the persisted `FINALIZING` state is structurally corrupt and Stage 5 recovery cannot restore its request/checkpoint transaction, normal runtime integrity-failure handling applies. Stage 6 must not reconstruct or guess a submitted candidate from current workspace files.

---

# 14. Concurrency

Stage 6 does not modify scheduling admission or concurrency ownership.

The target already owns its target-concurrency slot while in:

```text
WORKING
```

and continues to own it through:

```text
FINALIZING
VALIDATING
REVIEWING
```

Therefore:

```text
WORKING → FINALIZING
```

does not release or reacquire a scheduling slot.

Stage 2 is not involved.

---

# 15. Usage accounting

Stage 6 introduces no new execution usage.

It does not increment:

```text
cycles
repair_cycles
model_calls
tool_calls
input_tokens
output_tokens
```

The Stage 4 model invocation that produced `request_finalization()` has already been accounted for normally.

`request_finalization()` itself remains excluded from `tool_calls`.

Runtime persistence work such as:

```text
checkpoint creation
request persistence
TaskEvent creation
transaction journaling
state-file replacement
```

is not model/tool execution usage.

No budget is reset, refunded, or recreated at finalization.

---

# 16. Trace

Stage 6 reuses the Stage 5 `TaskEvent` trace.

Relevant events should record lifecycle facts such as:

```text
finalization_requested
checkpoint_created
phase_transition
```

Events should reference durable objects rather than copy them.

For example:

```text
finalization_requested
    finalization_request_id
    candidate_checkpoint_ref
```

and:

```text
phase_transition
    WORKING → FINALIZING
```

The trace does not duplicate:

* the full finalization request;
* candidate artifact contents;
* completion state;
* evidence state;
* checkpoint contents.

Authority remains:

```text
TargetFinalizationRequest
    → finalization submission identity

TaskCheckpoint
    → exact submitted candidate

TaskEvent
    → historical explanation of what occurred
```

---

# 17. Source identity and provenance

`TargetFinalizationRequest` does not duplicate `SourceBinding` or target-contract metadata.

Candidate provenance is resolved through:

```text
TargetFinalizationRequest
        ↓
candidate_checkpoint_ref
        ↓
TaskCheckpoint
        ↓
TargetTaskSpec / SourceBinding
```

The checkpoint must remain bound to the exact immutable task/source identity already established by Stages 0–1.

This is sufficient to establish the repository revision, graph/enrichment identity, target contract, and exact candidate state without duplicating those fields into the finalization request.

---

# 18. Stage 7 handoff

Stage 7 receives a stable durable input consisting conceptually of:

```text
TargetFinalizationRequest
+
its referenced TaskCheckpoint
+
immutable TargetTaskSpec
```

`TargetTaskState` remains the current lifecycle authority.

Stage 7 owns the transition:

```text
FINALIZING → VALIDATING
```

and all hard-validation semantics.

Stage 6 does not define:

```text
TargetValidationReport
hard completion gates
evidence sufficiency
artifact completeness rules
unknown/not-applicable validity
validation PASS/FAIL routing
review semantics
repair routing
acceptance
```

Those remain Stage 7+ concerns.

---

# 19. Locked invariants

```text
Finalization is a request for evaluation, not completion.

Only the runtime performs WORKING → FINALIZING.

FINALIZING → VALIDATING belongs to Stage 7.

Every successful finalization creates a fresh TaskCheckpoint.

TargetFinalizationRequest.candidate_checkpoint_ref identifies
the exact immutable candidate submitted for that evaluation round.

phase == FINALIZING
    → pending_finalization_request_ref exists.

pending_finalization_request_ref
    → resolves to one immutable TargetFinalizationRequest.

TargetFinalizationRequest
    → resolves to one valid candidate TaskCheckpoint.

Worker-originated candidate mutation is legal only in WORKING.

Successful Stage 6 finalization does not imply:
    validation PASS,
    review PASS,
    completion,
    or acceptance.

Stage 6 performs no semantic completion validation.

Stage 6 adds no model/tool usage.

A target may have multiple immutable historical
TargetFinalizationRequest objects across repair rounds.

Only one request may be current/pending at a time.

Recovered FINALIZING targets resume directly into Stage 7.

Recovered FINALIZING targets never return through
Stage 2, Stage 3, or Stage 4.

Provider conversation state is not required after finalization.

No additional finalization state, attempt, snapshot,
submission, or evaluation-bundle contract is introduced.
```

---

# 20. V0 implementation surface

Stage 6 should remain deliberately small.

The required implementation consists of:

```text
1. TargetFinalizationRequest
       immutable persisted contract

2. one Stage 6 runtime operation
       handle finalization submission

3. fresh TaskCheckpoint creation
       through existing Stage 5 mechanisms

4. one Stage 5 logical transaction
       checkpoint
       request
       TargetTaskState update
       trace

5. WORKING → FINALIZING

6. pending_finalization_request_ref semantics

7. idempotent replay/recovery behavior

8. direct durable handoff to Stage 7
```

No additional orchestration framework or finalization-specific state machine is required.
