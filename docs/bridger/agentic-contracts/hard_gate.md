# Stage 7 — Hard Validation

## 1. Responsibility

Stage 7 is the deterministic evaluation boundary between a worker-submitted candidate and Stage 8 semantic/artifact review.

```text
TargetFinalizationRequest
        ↓
candidate_checkpoint_ref
        ↓
exact submitted TaskCheckpoint
        ↓
deterministic hard validation
        │
        ├── PASS → REVIEWING
        │
        └── FAIL → REPAIR
```

Stage 7 determines only properties that runtime code can establish deterministically.

It owns:

```text
finalization/checkpoint integrity
completion-state mechanical gates
candidate-artifact integrity
evidence-reference integrity
source/revision compatibility
target-workspace boundaries
runtime-state invariants
validation findings
validation report persistence
VALIDATING lifecycle transitions
```

It does not judge:

```text
repository interpretation correctness
whether evidence semantically proves a claim
whether unknown/not-applicable is substantively justified
whether important repository knowledge was missed
writing quality
organization
duplication
scope quality
terminology
artifact usefulness
```

Those responsibilities remain with the worker, Stage 8 reviewer, or offline Bridger evaluation according to the existing ownership model.

Stage 7 invokes no model and performs no repository rediscovery.

---

## 2. Validation subject

Stage 7 validates the **exact candidate submitted by Stage 6**.

The authoritative chain is:

```text
TargetTaskState.pending_finalization_request_ref
        ↓
TargetFinalizationRequest
        ↓
candidate_checkpoint_ref
        ↓
TaskCheckpoint
```

The referenced `TaskCheckpoint` is the immutable evaluation cut.

Candidate facts are loaded from that checkpoint, including the checkpointed:

```text
TargetCompletionState
candidate artifact state
evidence state
open-question state
source identities
```

Current mutable workspace state must not replace the checkpoint as the validation authority.

`TargetTaskState` is consulted only for current control-plane state such as:

```text
phase
pending_finalization_request_ref
open_finding_refs
```

`TargetTaskSpec` remains authoritative for the immutable assignment, target workspace, target contract version, and source binding.

`TargetDefinition` remains authoritative for completion-obligation definitions and applicability.

No separate `ValidationSubject` persisted contract is introduced.

---

## 3. Validation-subject integrity

Before candidate hard gates run, Stage 7 must be able to reconstruct a coherent evaluation subject.

Required preconditions include:

```text
TargetFinalizationRequest exists
TaskCheckpoint exists
request belongs to the expected fleet and target
checkpoint belongs to the expected target
request.candidate_checkpoint_ref resolves exactly
TargetTaskState.pending_finalization_request_ref identifies the request
TargetTaskSpec resolves
TargetDefinition resolves from target_contract_version
checkpoint/source identities are compatible with TargetTaskSpec.source
required checkpointed state can be loaded and validated
```

Failure to establish these conditions is a runtime/persistence integrity failure.

It is **not**:

```text
TargetValidationReport.FAIL
```

and must not produce worker repair findings.

The existing Stage 5 recovery/failure path owns missing, corrupted, or internally inconsistent runtime persistence.

The distinction is:

```text
cannot establish a valid evaluation subject
    → runtime/recovery failure

valid evaluation subject
but candidate violates deterministic gates
    → hard-validation FAIL
```

---

## 4. Completion-state gates

The checkpointed `TargetCompletionState` must mechanically match the exact `TargetDefinition` identified by:

```text
TargetTaskSpec.target_contract_version
```

Stage 7 validates:

```text
TargetCompletionState.target_task_id matches TargetTaskSpec.target_task_id

one CompletionItemState exists for every completion obligation

no missing obligation IDs
no unknown obligation IDs
no duplicate obligation IDs

completion vocabulary is valid

no obligation remains uninvestigated

covered / not-applicable / unknown
    require a non-empty resolution_note

not-applicable
    may only resolve a CONDITIONAL obligation

every completion-item evidence reference resolves
    to valid evidence for the same target/source binding
```

Every obligation, including conditional obligations, must leave:

```text
uninvestigated
```

before hard validation can pass.

For a conditional obligation, the worker must resolve it to one of:

```text
covered
not-applicable
unknown
```

rather than leaving applicability unexplored.

### Covered evidence requirement

A completion item resolved as:

```text
covered
```

must reference at least one valid durable `EvidenceReference`.

This is a grounding prerequisite, not a semantic-sufficiency judgment.

Stage 7 establishes:

> valid evidence exists and is attached.

It does not establish:

> the evidence is sufficient to prove the worker's interpretation.

No minimum evidence count is imposed for:

```text
unknown
not-applicable
```

Their substantive justification remains outside deterministic validation.

---

## 5. Candidate-artifact gates

Stage 7 validates the exact candidate artifacts captured by the finalization checkpoint.

The candidate must contain:

```text
at least one candidate artifact
at least one non-empty Markdown artifact
```

For every candidate artifact, Stage 7 validates:

```text
artifact_id is valid and unique
relative_path is valid and unique
revision is valid
digest is valid
checkpointed artifact content/version resolves
persisted content matches the recorded digest
path is normalized
path is relative
path remains inside TargetTaskSpec.target_workspace
no path traversal
no sibling-target access
no source-repository path
no runtime-state path
artifact type is allowed candidate Markdown
content is valid decodable text
```

Stage 7 does not impose:

```text
required Markdown filenames
required document count
required headings
fixed section structure
minimum word counts
file-segmentation rules
writing-quality metrics
```

The worker continues to own target-local file names, file count, segmentation, and organization.

---

## 6. Evidence-reference gates

Every evidence reference belonging to the submitted candidate must resolve against the immutable upstream authorities bound by `TargetTaskSpec.source`.

For every referenced `EvidenceReference`, Stage 7 validates:

```text
evidence_id resolves
target_task_id matches
SourceBinding matches TargetTaskSpec.source
evidence kind is supported
locator is structurally valid
```

V0 evidence families remain:

```text
FILE
SOURCE_RANGE
SYMBOL
GRAPH_ENTITY
```

Kind-specific validation is:

```text
FILE
    → path exists in authoritative FileIndex
    → source/read policy permits the reference

SOURCE_RANGE
    → path exists
    → range resolves inside the bound file
    → content_digest matches the bound revision content

SYMBOL
    → symbol exists in authoritative SymbolIndex

GRAPH_ENTITY
    → graph entity exists in the bound graph snapshot
```

Evidence validation is intentionally repeated at the final candidate boundary even though evidence was validated when recorded.

Stage 7 does not introduce evidence for:

```text
conversation messages
tool-result blobs
search-result blobs
model reasoning
```

and does not infer durable evidence from source paths or symbol names merely written in Markdown.

Stage 7 does not parse arbitrary Markdown to invent claim/evidence associations. A final claim-sidecar/citation contract has not been introduced by the worker stage and is therefore not created here.

---

## 7. Source and provenance compatibility

Stage 7 revalidates the immutable provenance chain.

Conceptually:

```text
MemoryFleetSpec.source
        ==
TargetTaskSpec.source
        ==
checkpoint source binding
        ==
EvidenceReference.source
```

The bound upstream authorities must resolve compatibly:

```text
repository_id
repository_revision
graph_snapshot_id
enrichment_overlay_id when present
```

Stage 7 reuses existing upstream identity and compatibility validation.

It does not rebuild or reinterpret the deterministic substrate, graph, or enrichment overlay.

Upstream authorities remain immutable and read-only.

---

## 8. Open questions

Open questions are allowed at successful hard validation.

```text
open_question_refs != []
```

does not itself cause failure.

Stage 7 validates only their mechanical integrity:

```text
every referenced question exists
question belongs to the same target task
checkpointed open-question state is structurally valid
```

Stage 7 does not decide:

```text
whether a question should have been resolved
whether remaining uncertainty is acceptable
whether an open question should correspond to an unknown completion item
whether the generated knowledge communicates the uncertainty well
```

Unknowns and unresolved questions remain legitimate first-class knowledge outcomes.

---

## 9. `ValidationFinding`

A deterministic candidate-gate failure is represented by an immutable validation finding.

Conceptually:

```python
class ValidationFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    finding_id: str
    validation_report_id: str
    target_task_id: str

    rule_id: str

    subject_kind: str
    subject_ref: str | None = None

    message: str
```

`rule_id` is a stable machine-readable identifier for the failed invariant.

Examples:

```text
completion.uninvestigated
completion.covered_without_evidence
completion.invalid_not_applicable

artifact.missing
artifact.digest_mismatch
artifact.outside_workspace

evidence.unresolvable
evidence.source_mismatch

source.binding_mismatch
```

`subject_kind` identifies the affected category, for example:

```text
target
completion-obligation
artifact
evidence
source
```

`subject_ref` identifies the concrete affected object when applicable.

Validation findings are blocking by definition. V0 introduces no separate:

```text
severity
confidence
repair strategy
```

field.

Finding IDs should be deterministically derived from the validation round, rule, and affected subject so deterministic re-execution produces stable identities.

Existing `FindingRef` with:

```text
origin = HARD_VALIDATION
```

remains the reference type used by `TargetTaskState.open_finding_refs`.

---

## 10. `TargetValidationReport`

Stage 7 persists one immutable report for each finalization request.

```python
class ValidationVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class TargetValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    validation_report_id: str

    fleet_run_id: str
    target_task_id: str

    finalization_request_id: str
    candidate_checkpoint_ref: str

    verdict: ValidationVerdict
    finding_refs: list[FindingRef]

    created_at: datetime
```

The exact Python timestamp representation is an implementation detail.

The report directly records both:

```text
finalization_request_id
candidate_checkpoint_ref
```

so historical evaluation always identifies both the submitted evaluation round and its exact candidate.

### Cardinality

V0 locks:

```text
one TargetFinalizationRequest
    → at most one TargetValidationReport
```

`validation_report_id` should therefore be deterministically derived from:

```text
finalization_request_id
```

No separate:

```text
validation_attempt_id
validation retry counter
report supersession chain
```

is introduced.

### Verdict invariants

```text
PASS
    → finding_refs is empty

FAIL
    → at least one HARD_VALIDATION finding exists
```

Reports and findings are immutable historical evaluation records.

---

## 11. Findings projection in `TargetTaskState`

`TargetTaskState.open_finding_refs` remains the current unresolved projection and does not duplicate finding contents.

When a Stage 7 report is committed:

```text
remove currently open HARD_VALIDATION finding refs

then

PASS
    → add none

FAIL
    → add the new report's HARD_VALIDATION finding refs
```

Findings from other origins are preserved:

```text
TARGET_REVIEW
FLEET_VALIDATION
FLEET_REVIEW
```

Historical validation findings are never deleted or mutated merely because they are no longer open.

This supports repeated evaluation rounds without turning `TargetTaskState` into an evaluation-history store.

---

## 12. Lifecycle ownership

Stage 7 owns:

```text
FINALIZING → VALIDATING
```

and both hard-validation outcome transitions:

```text
VALIDATING → REVIEWING
    on PASS

VALIDATING → REPAIR
    on FAIL
```

### `FINALIZING → VALIDATING`

Before this transition:

```text
pending_finalization_request_ref
```

must identify the valid Stage 6 finalization request whose candidate checkpoint will be evaluated.

`VALIDATING` means:

> The exact finalization request and candidate checkpoint are durably known and deterministic hard validation is in progress or awaiting completion.

### PASS

A committed PASS performs:

```text
VALIDATING → REVIEWING
```

`pending_finalization_request_ref` remains unchanged.

This preserves the identity of the evaluation round for Stage 8.

`REVIEWING` therefore means:

> The current submitted candidate has a durable hard-validation PASS and is ready for semantic/artifact review.

### FAIL

A committed FAIL performs:

```text
VALIDATING → REPAIR
```

and clears:

```text
pending_finalization_request_ref
```

The immutable request, checkpoint, report, and findings remain historical.

Stage 7 does not schedule the repair worker.

`REPAIR → SCHEDULED` remains owned by Stage 2 and must reacquire normal scheduler admission.

---

## 13. Persistence and transaction boundaries

Stage 7 reuses Stage 5 persistence and transaction machinery.

No new checkpoint type or validation-attempt persistence mechanism is introduced.

### Validation start transaction

The validation start boundary atomically persists:

```text
FINALIZING → VALIDATING
+
corresponding TaskEvent trace
```

No candidate state is changed.

No new `TaskCheckpoint` is created.

### Deterministic validation execution

The validator loads the exact Stage 6 checkpoint and runs all gates without mutating candidate state.

Intermediate individual gate results do not require durable persistence.

### Validation completion transaction

The outcome is committed as one logical durable operation containing:

```text
ValidationFinding records when applicable
TargetValidationReport
TargetTaskState.open_finding_refs projection
outcome lifecycle transition
pending_finalization_request_ref update when applicable
TaskEvent trace
```

PASS commits:

```text
TargetValidationReport.PASS
open HARD_VALIDATION findings = none
VALIDATING → REVIEWING
pending_finalization_request_ref preserved
```

FAIL commits:

```text
TargetValidationReport.FAIL
new HARD_VALIDATION findings projected as open
VALIDATING → REPAIR
pending_finalization_request_ref cleared
```

The report must not be persisted as an outcome separate from the corresponding authoritative lifecycle/state update.

---

## 14. Recovery and idempotency

Stage 7 is deterministic and re-executable.

No Stage 7-specific checkpoint is required.

Recovery behavior is:

```text
crash before validation start
    → target remains FINALIZING
    → Stage 7 may start normally

crash after FINALIZING → VALIDATING
but before completion commit
    → rerun validation from the same candidate checkpoint

validation completed only in memory
    → rerun validation

crash during completion transaction
    → Stage 5 transaction recovery determines committed/non-committed state

completion transaction committed
but caller crashes
    → persisted report/state are authoritative
    → do not create a second report
```

The idempotency key is:

```text
finalization_request_id
```

Invocation behavior is conceptually:

```text
if a report already exists for finalization_request_id:
    return/use the existing report

else:
    require the request to be the current valid evaluation request
    and phase to be FINALIZING or VALIDATING
    then execute/re-execute validation
```

A target recovered in `VALIDATING` does not require:

```text
Stage 2 scheduling
Stage 3 hydration
worker context
provider conversation
```

It simply resumes deterministic validation of the same checkpoint.

---

## 15. Multiple validation rounds

Repair does not create a new target task.

Example:

```text
target_task_id = T

finalization request A
    ↓
candidate checkpoint A
    ↓
validation report A — FAIL
    ↓
REPAIR
    ↓
worker modifies candidate
    ↓
new finalization request B
    ↓
candidate checkpoint B
    ↓
validation report B — PASS
```

The following remain unchanged across rounds:

```text
target_task_id
TargetTaskSpec
target workspace identity
target budget
accumulated target usage
fleet usage
source binding
```

Every finalization request, checkpoint, validation report, and finding remains immutable and historically traceable.

The current `open_finding_refs` projection contains only unresolved findings relevant to the current execution state.

---

## 16. Usage semantics

Hard validation does not consume any existing `ExecutionUsage` counter.

Stage 7 does not increment:

```text
cycles
repair_cycles
model_calls
tool_calls
input_tokens
output_tokens
```

Hard validation is internal deterministic runtime work.

A validation FAIL does not increment `repair_cycles`.

That counter remains tied to actual repair worker execution according to the already-locked worker-cycle lifecycle.

No validation-specific budget or usage dimension is introduced in V0.

---

## 17. Concurrency semantics

Stage 7 does not introduce a separate concurrency model.

The existing scheduler contract already treats:

```text
FINALIZING
VALIDATING
REVIEWING
```

as slot-occupying phases.

Therefore:

```text
FINALIZING → VALIDATING
    → existing target slot retained

VALIDATING → REVIEWING
    → existing target slot retained

VALIDATING → REPAIR
    → target slot released
```

A repaired target must later regain admission through normal:

```text
REPAIR → SCHEDULED
```

scheduling.

No validator semaphore, validation queue, lease, heartbeat, or validation-specific scheduling state is introduced for V0.

---

## 18. Stage 8 handoff

After successful Stage 7 completion, the following durable invariant holds:

```text
TargetTaskState.phase == REVIEWING

pending_finalization_request_ref
    → TargetFinalizationRequest F

F.candidate_checkpoint_ref
    → TaskCheckpoint C

TargetValidationReport
    → finalization_request_id == F
    → candidate_checkpoint_ref == C
    → verdict == PASS

no open HARD_VALIDATION findings
for the current evaluation round
```

Stage 8 must review the same checkpointed candidate `C`.

It must not substitute an ambient later workspace state.

Stage 7 therefore hands Stage 8 a mechanically valid, exact, immutable candidate identity together with its PASS report.

Stage 8 remains responsible for semantic/artifact review only.

---

## 19. Failure handoff

After hard-validation failure, Stage 7 leaves:

```text
TargetTaskState.phase = REPAIR

pending_finalization_request_ref = None

immutable failed TargetValidationReport

immutable ValidationFinding records

TargetTaskState.open_finding_refs
    containing the current HARD_VALIDATION findings
```

This is the complete Stage 7 repair handoff.

Stage 7 does not define:

```text
repair-context rendering
repair execution strategy
finding prioritization
worker rewrite/patch behavior
new repository exploration policy
Stage 9 control flow
```

Those remain later-stage responsibilities.

---

## 20. Core invariants

Stage 7 locks the following V0 rules:

1. Hard validation always evaluates the exact checkpoint submitted by Stage 6.
2. Current mutable workspace state cannot replace the submitted checkpoint as validation authority.
3. One finalization request identifies one exact candidate checkpoint.
4. One finalization request produces at most one immutable validation report.
5. Validation reports remain permanently bound to both their finalization request and candidate checkpoint.
6. Hard validation is deterministic runtime code and invokes no model.
7. Hard validation does not perform repository rediscovery.
8. Failure to reconstruct a valid evaluation subject is a runtime/persistence failure, not a worker validation failure.
9. Every completion obligation must leave `uninvestigated` before PASS.
10. `covered` completion items require at least one valid durable evidence reference.
11. `unknown` and `not-applicable` do not require an arbitrary minimum evidence count.
12. `not-applicable` remains valid only for conditional obligations.
13. Evidence validity is mechanical; semantic sufficiency is not a Stage 7 judgment.
14. Candidate artifacts must be non-empty, digest-valid, and confined to the exact target workspace.
15. Stage 7 does not impose filenames, document structure, word counts, or writing-quality metrics.
16. Open questions are allowed and do not automatically block PASS.
17. Historical reports and findings are immutable.
18. `TargetTaskState.open_finding_refs` contains only the current unresolved projection.
19. PASS produces no hard-validation findings.
20. FAIL produces at least one actionable hard-validation finding.
21. Stage 7 owns `FINALIZING → VALIDATING`.
22. PASS atomically produces `VALIDATING → REVIEWING`.
23. FAIL atomically produces `VALIDATING → REPAIR`.
24. `pending_finalization_request_ref` is preserved through PASS into `REVIEWING`.
25. `pending_finalization_request_ref` is cleared on hard-validation FAIL.
26. No Stage 7 checkpoint or validation-attempt object is introduced.
27. Recovery from `VALIDATING` re-executes deterministic validation against the same Stage 6 checkpoint.
28. `finalization_request_id` is the validation idempotency key.
29. Multiple validation rounds reuse the same target task and original remaining budget.
30. Stage 7 does not increment worker/model/tool/token/repair usage counters.
31. Existing target concurrency semantics remain unchanged.
32. Stage 8 must review exactly the candidate checkpoint that Stage 7 passed.
33. Stage 7 never accepts the target; local acceptance remains downstream of both hard validation and Stage 8 review.
