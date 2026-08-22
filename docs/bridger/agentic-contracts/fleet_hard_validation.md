# Stage 11 — Fleet Hard Validation

## 1. Responsibility

Stage 11 is the deterministic **fleet-composition validation boundary** over the current set of locally accepted targets.

Its lifecycle boundary is:

```text
Stage 10
all activated TargetTaskState.phase = ACCEPTED
+
each last_accepted_result_ref
resolves to one AcceptedTargetResult
+
FleetRunState.phase = RUNNING
        ↓
Stage 11
RUNNING → VALIDATING
resolve exact accepted fleet candidate
verify fleet composition
persist FleetValidationReport
        │
        ├── PASS
        │     ↓
        │  VALIDATING → REVIEWING
        │     ↓
        │  Stage 12
        │
        └── FAIL
              ↓
           fleet validation findings
              ↓
           VALIDATING → REPAIRING
              ↓
           reopen affected targets
              ↓
           REPAIRING → RUNNING
              ↓
           normal target repair lifecycle
```

Stage 11 operates only after every activated target has earned local acceptance.

Stage 11 owns:

* validating fleet-validation admission;
* resolving the exact current `AcceptedTargetResult` for every activated target;
* establishing the exact fleet candidate being validated;
* verifying deterministic cross-target composition invariants;
* building the accepted-artifact fleet namespace;
* validating generated-memory relative Markdown links against the exact accepted artifact set;
* creating immutable fleet-validation findings;
* creating the immutable `FleetValidationReport`;
* performing `RUNNING → VALIDATING`;
* performing `VALIDATING → REVIEWING` on PASS;
* performing `VALIDATING → REPAIRING` on FAIL;
* routing fleet-validation findings to affected targets;
* reopening affected targets through `ACCEPTED → REPAIR`;
* performing `REPAIRING → RUNNING` after reopening is durably established;
* maintaining the current `FLEET_VALIDATION` finding projection;
* preserving validation idempotency and crash recovery.

Stage 11 does **not** own:

* repository exploration or rediscovery;
* artifact generation or mutation;
* completion-state mutation;
* evidence creation or semantic verification;
* rerunning target hard validation;
* rerunning target review;
* deciding whether generated knowledge is semantically correct;
* cross-target duplication review;
* contradiction review;
* terminology reconciliation;
* semantic ownership reconciliation;
* deciding whether additional cross-target links should exist;
* global writing quality or organization review;
* fleet acceptance;
* Repository Brain publication.

Stage 11 invokes no LLM.

Its purpose is:

> **Prove that the exact locally accepted target results selected for the fleet form one mechanically valid generated-memory corpus.**

---

## 2. Existing authorities consumed

Stage 11 consumes the already-locked authorities:

```text
MemoryFleetSpec
FleetRunState

TargetTaskSpec
TargetTaskState

AcceptedTargetResult
CandidateArtifactRef

local acceptance provenance
artifact-version persistence

FindingRef
FindingOrigin

TaskEvent
Stage 5 persistence / recovery machinery
```

Stage 11 does not replace or reinterpret these authorities.

In particular:

```text
MemoryFleetSpec.target_ids
```

remains the authoritative activated target scope.

```text
TargetTaskState.phase
```

remains the authoritative target lifecycle state.

```text
TargetTaskState.last_accepted_result_ref
```

remains the authoritative selector for the target's current locally accepted candidate.

```text
AcceptedTargetResult
```

remains the immutable provenance record for that exact accepted candidate.

Stage 11 introduces no second target-status, accepted-target, artifact, or fleet-candidate authority.

---

## 3. Stage 11 admission

Stage 11 may begin only when:

```text
FleetRunState.phase == RUNNING
```

and every activated target in:

```text
MemoryFleetSpec.target_ids
```

has exactly one corresponding target task whose:

```text
TargetTaskState.phase == ACCEPTED
```

and whose:

```text
last_accepted_result_ref
```

resolves.

The activated target set is not recalculated by Stage 11.

Stage 11 does not rerun:

```text
target activation rules
frontend/design detection
target dependency discovery
target initialization
```

Those responsibilities were already resolved when the immutable fleet was created.

### Incomplete local acceptance

If any activated target has not reached `ACCEPTED`, Stage 11 is not eligible to run.

This does **not** produce:

```text
FleetValidationReport.FAIL
```

because an incomplete local lifecycle is not a defective accepted fleet candidate.

It is a control-flow/admission condition.

---

## 4. Exact fleet candidate

The Stage 11 validation subject is derived exclusively from current locally accepted results.

Conceptually:

```text
MemoryFleetSpec.target_ids
        ↓
resolve TargetTaskSpec / TargetTaskState
        ↓
TargetTaskState.last_accepted_result_ref
        ↓
AcceptedTargetResult
        ↓
ordered AcceptedTargetResult[]
```

The accepted-result ordering follows the immutable target ordering in:

```text
MemoryFleetSpec.target_ids
```

This ordered accepted-result list is the exact fleet candidate.

Stage 11 must not select target content from:

```text
current filesystem contents
latest artifact revision generally
live TargetCompletionState
TargetTaskState.artifact_refs
historical accepted results
trace ordering
timestamps
conversation history
```

The rule is:

> **Fleet validation evaluates exactly the candidates identified by the current `last_accepted_result_ref` of each activated accepted target.**

A historical `AcceptedTargetResult` remains durable provenance but does not participate when a newer accepted result has replaced it as the target's current locally accepted result.

---

## 5. No persisted `FleetCandidate`

Stage 11 introduces no durable contract such as:

```text
FleetCandidate
FleetCandidateState
FleetCandidateManifest
AcceptedTargetMap
FleetArtifactManifest
```

The exact fleet candidate is already completely identified by:

```text
fleet_run_id
+
ordered AcceptedTargetResult IDs
```

A validator may build transient indexes while executing, but they are implementation details and are not additional persisted authorities.

This avoids duplicating accepted-target state that already exists in Stage 10.

---

## 6. Validation-subject integrity

Before fleet composition gates run, Stage 11 must establish that the accepted fleet candidate can be trusted as a runtime subject.

For every activated target, the runtime must verify that:

```text
TargetTaskSpec exists
TargetTaskState exists

TargetTaskState.phase == ACCEPTED
last_accepted_result_ref resolves

AcceptedTargetResult exists
AcceptedTargetResult belongs to the target task
AcceptedTargetResult belongs to the fleet
target identity matches TargetTaskSpec
target contract version matches TargetTaskSpec

AcceptedTargetResult.source
    == TargetTaskSpec.source
    == MemoryFleetSpec.source

referenced immutable accepted artifact versions resolve
referenced artifact digests remain valid

referenced local acceptance provenance resolves
```

Stage 11 may defensively verify these invariants even when earlier stages already proved them.

It does **not** rerun the earlier semantic or mechanical evaluation that produced local acceptance.

---

## 7. Runtime corruption versus fleet-validation failure

Stage 11 strictly separates two failure classes.

### Runtime / persistence integrity failure

If Stage 11 cannot reconstruct a trustworthy accepted fleet candidate because an already-guaranteed durable invariant is broken, the operation fails as runtime/persistence corruption.

Examples:

```text
ACCEPTED target with no last_accepted_result_ref

last_accepted_result_ref does not resolve

AcceptedTargetResult belongs to another fleet

AcceptedTargetResult source differs from TargetTaskSpec.source

AcceptedTargetResult references missing historical artifact bytes

stored accepted artifact digest no longer matches

accepted-result local evaluation provenance is missing or invalid
```

These conditions do **not** create:

```text
FleetValidationReport.FAIL
FleetValidationFinding
worker repair
```

The worker cannot repair corrupted runtime provenance.

### Fleet-validation failure

Once a valid accepted fleet candidate has been established, a deterministic defect in how those accepted artifacts compose is a Stage 11 validation failure.

Examples:

```text
generated-memory link points to no artifact
generated-memory link escapes the memory namespace
accepted artifact paths collide in the composed fleet
cross-target artifact reference is structurally invalid
```

These conditions produce:

```text
FleetValidationReport.FAIL
+
FleetValidationFinding[]
```

and may reopen the affected target tasks.

### Locked distinction

```text
cannot trust the fleet candidate
    → runtime/persistence failure

trusted fleet candidate
but composition invariant fails
    → fleet-validation FAIL
```

This preserves the same integrity-versus-repair boundary used by target hard validation and target acceptance.

---

## 8. Trust in local acceptance

Stage 11 does not rerun Stage 7 hard validation for every accepted target.

Stage 10 already establishes:

```text
exact candidate
    ↓
Stage 7 PASS
    ↓
Stage 8 PASS
    ↓
AcceptedTargetResult
```

The accepted result exists specifically so later fleet stages can consume the locally proven candidate without re-performing target-local evaluation.

Therefore Stage 11 does not repeat:

```text
completion obligation gates
covered-item evidence requirements
target workspace validation
individual evidence-range validation
individual graph evidence validation
local source compatibility evaluation
local artifact non-emptiness checks
target-local reviewer checks
```

Stage 11 verifies that accepted provenance remains resolvable, then evaluates only invariants that require seeing multiple accepted targets together.

The separation is:

```text
Stage 7
    proves one submitted target candidate mechanically

Stage 8
    reviews that target candidate semantically as an artifact

Stage 10
    freezes the locally successful candidate

Stage 11
    proves deterministic composition of those frozen candidates
```

---

## 9. Accepted artifact fleet namespace

Stage 11 constructs a transient accepted-artifact index from the exact `AcceptedTargetResult[]`.

For each accepted artifact:

```text
target_id
+
CandidateArtifactRef.relative_path
```

defines its fleet-relative generated-memory path.

Conceptually:

```text
repository/overview.md
business-logic/domain.md
architecture/runtime.md
data-and-state/persistence.md
testing/strategy.md
...
```

The index contains only artifact versions frozen by the current accepted results.

Stage 11 must not discover the candidate fleet by scanning the mutable output directories.

This automatically excludes:

```text
failed candidates
rejected artifact versions
historical accepted versions that are no longer current
partially repaired candidates
unaccepted artifacts
ambient files
```

from the Stage 11 subject.

---

## 10. Fleet artifact namespace gates

The composed accepted artifact set must satisfy:

```text
every accepted artifact resolves

every fleet-relative generated-memory path is normalized

every artifact remains associated with its owning target

no accepted artifact path escapes the generated-memory namespace

no two accepted artifacts resolve to the same fleet-relative path
```

Stage 11 reuses the accepted target's existing artifact identity and version contract.

It does not introduce a new global bare:

```text
artifact_id
```

uniqueness rule.

Where artifact identity must be qualified across targets, the safe conceptual identity is:

```text
(target_task_id, artifact_id)
```

The fleet-relative path remains the generated-memory navigation identity.

This avoids creating a new global artifact-ID contract solely for Stage 11.

---

## 11. Cross-target Markdown link validation

Cross-target links become mechanically verifiable only after the exact accepted artifact set for the full fleet exists.

Stage 11 therefore validates generated-memory Markdown document links against the exact accepted fleet namespace.

Example:

```markdown
See [persistence](../data-and-state/persistence.md).
```

For each eligible relative generated-memory Markdown link, Stage 11:

```text
takes the accepted source artifact path
        ↓
resolves the relative link path
        ↓
normalizes the destination path
        ↓
verifies the destination remains in the memory namespace
        ↓
verifies the destination exists in the exact accepted artifact index
```

A link must resolve against the **current accepted fleet**, not against:

```text
ambient filesystem contents
historical accepted targets
rejected candidates
currently edited repair candidates
```

### Example failure

```text
architecture/runtime.md
    → ../data-and-state/old-storage.md

current accepted data-and-state result
    contains persistence.md
    but no old-storage.md
```

Stage 11 produces a fleet-validation finding against the target that owns the broken link.

---

## 12. Markdown-link V0 scope

Stage 11 validates only generated-memory relative Markdown document references for which deterministic fleet-path resolution is meaningful.

V0 does not perform network validation for:

```text
https://...
http://...
mailto:...
other external URI schemes
```

Fragment-only links such as:

```text
#runtime-flow
```

do not require fleet path resolution.

For a link such as:

```text
../architecture/runtime.md#startup
```

Stage 11 validates:

```text
../architecture/runtime.md
```

but does not validate the renderer-specific heading fragment:

```text
#startup
```

V0 does not introduce a canonical Markdown heading-anchor contract.

Stage 11 also does not parse ordinary prose or code-formatted repository paths as cross-target references.

---

## 13. Link existence versus link quality

Stage 11 checks only mechanical link validity.

It can establish:

```text
the link is structurally safe
the destination belongs to the exact accepted fleet
the destination artifact exists
```

It does not judge:

```text
whether the link should have been added
whether a different target is a better destination
whether the relationship is semantically correct
whether additional links are missing
whether duplicated prose should become a link
```

Therefore:

```text
zero cross-target links
```

does not itself cause Stage 11 failure.

Cross-target organization, ownership, duplication, terminology and semantic linking quality belong to Stage 12 fleet reconciliation.

---

## 14. No new claim/document graph

Stage 11 does not introduce new global contracts such as:

```text
DocumentRecord
GlobalDocumentId
ClaimGraph
QualifiedClaimReference
FleetKnowledgeGraph
```

solely to satisfy early exploratory ideas about fleet validation.

Only relations represented by already-authoritative V0 contracts or mechanically observable generated-memory document links are validated.

If a later knowledge-bundle contract introduces additional stable cross-target reference types, they may be added to fleet hard validation in a future version.

V0 does not invent those contracts here.

---

## 15. `FleetValidationFinding`

A worker-correctable deterministic fleet-composition failure is represented by an immutable:

```text
FleetValidationFinding
```

Conceptually:

```python
class FleetValidationFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    finding_id: str
    fleet_validation_report_id: str
    fleet_run_id: str

    rule_id: str

    affected_target_task_ids: list[str]

    subject_kind: str
    subject_ref: str | None = None

    message: str
```

The exact Pydantic location and ID encoding are implementation details.

### `rule_id`

`rule_id` is a stable machine-readable identifier for the failed deterministic fleet invariant.

Examples:

```text
artifact.path_collision
artifact.invalid_fleet_path

link.outside_fleet
link.missing_destination
link.invalid_path
```

Runtime-provenance corruption does not receive a `rule_id` because it does not produce a `FleetValidationFinding`.

### Affected targets

```text
affected_target_task_ids
```

contains the target task or tasks whose generated candidate must be repaired to resolve the finding.

Every referenced target must belong to the fleet being validated.

Most broken-link findings normally affect the target containing the invalid link.

A fleet-wide structural defect may identify more than one affected target when necessary.

### Subject

`subject_kind` identifies the primary affected object category, for example:

```text
artifact
link
fleet-path
```

`subject_ref` identifies the concrete object when useful.

The message must be sufficiently actionable for the normal repair worker to understand what mechanical outcome is required.

V0 introduces no separate:

```text
severity
confidence
repair strategy
```

field.

Fleet-validation findings are blocking by definition.

### Finding identity

Finding IDs should be deterministic for the validation report, failed rule and affected subject so deterministic replay of the same Stage 11 evaluation produces stable identities.

Existing:

```text
FindingRef(
    origin = FLEET_VALIDATION
)
```

remains the reference type stored in runtime state.

---

## 16. `FleetValidationReport`

Stage 11 introduces the immutable:

```text
FleetValidationReport
```

It answers:

> **Did this exact set of current locally accepted targets form a mechanically valid fleet, and if not, which deterministic fleet-composition invariants failed?**

Conceptually:

```python
class FleetValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    fleet_validation_report_id: str
    fleet_run_id: str

    accepted_target_result_refs: list[str]

    verdict: ValidationVerdict
    finding_refs: list[FindingRef]
```

Stage 11 reuses the existing deterministic:

```text
ValidationVerdict.PASS
ValidationVerdict.FAIL
```

vocabulary.

No separate `FleetValidationVerdict` enum is required.

### Accepted-result binding

```text
accepted_target_result_refs
```

contains the exact ordered Stage 10 accepted-result IDs that formed the validation subject.

Ordering follows:

```text
MemoryFleetSpec.target_ids
```

This is the fleet equivalent of exact-candidate provenance at the target level.

### PASS

A PASS report requires:

```text
verdict == PASS
finding_refs == []
```

### FAIL

A FAIL report requires:

```text
verdict == FAIL
finding_refs != []
```

Every report finding ref must have:

```text
origin == FLEET_VALIDATION
```

and resolve to an immutable `FleetValidationFinding` produced by that report.

---

## 17. Exact-fleet invariant

The central Stage 11 provenance rule is:

> **A `FleetValidationReport` applies only to the exact ordered set of `AcceptedTargetResult` objects recorded in that report.**

For example:

```text
repository      → R1
architecture    → A1
testing         → T1
```

is a different fleet candidate from:

```text
repository      → R1
architecture    → A2
testing         → T1
```

even when `A1` and `A2` belong to the same target task.

Therefore:

```text
FleetValidationReport PASS for [R1, A1, T1]
```

does not authorize:

```text
[R1, A2, T1]
```

to proceed to Stage 12.

Any changed locally accepted target result produces a new fleet candidate and requires Stage 11 again.

Stage 11 must not infer fleet equivalence from similar paths, unchanged target IDs, timestamps, or ambient contents.

---

## 18. Stage 11 runtime interface

The primary Stage 11 operation is conceptually:

```text
validate_fleet(fleet_run_id)
    → FleetValidationReport
```

The runtime resolves authoritative inputs internally.

The caller does not provide arbitrary:

```text
accepted target refs
artifact refs
source bindings
target list
fleet paths
finding claims
```

as validation inputs.

The normal operation is:

```text
load MemoryFleetSpec
        ↓
load FleetRunState
        ↓
verify Stage 11 admission
        ↓
RUNNING → VALIDATING
        ↓
resolve exact current AcceptedTargetResult[]
        ↓
verify validation-subject integrity
        ↓
build transient accepted-artifact index
        ↓
run deterministic fleet composition gates
        ↓
persist FleetValidationReport
        ↓
PASS or FAIL lifecycle handling
        ↓
return FleetValidationReport
```

No model or repository-navigation tool is invoked.

---

## 19. Successful Stage 11 path

On PASS:

```text
FleetValidationReport.verdict = PASS
```

and:

```text
FleetRunState.phase
    VALIDATING → REVIEWING
```

Stage 11 also replaces the current `FLEET_VALIDATION` finding projection with the empty set.

Historical fleet-validation reports and findings remain immutable and durable.

The successful Stage 11 boundary is therefore:

```text
FleetRunState.phase = REVIEWING
+
FleetValidationReport = PASS
+
report.accepted_target_result_refs
    = exact current accepted fleet
+
no current FLEET_VALIDATION findings
```

Stage 12 must review that same exact accepted fleet.

Stage 11 does not create the Stage 12 reviewer context.

---

## 20. Failed Stage 11 path

A deterministic fleet-composition failure produces:

```text
FleetValidationReport.FAIL
+
FleetValidationFinding[]
```

The failure path is:

```text
VALIDATING
    ↓
persist report/findings
    ↓
REPAIRING
    ↓
route findings
    ↓
affected target(s)
ACCEPTED → REPAIR
    ↓
RUNNING
```

Only targets identified by the current fleet-validation findings are reopened.

Unaffected accepted targets remain:

```text
ACCEPTED
```

and retain their current:

```text
last_accepted_result_ref
```

This preserves the locked rule that sibling failure does not automatically invalidate independent successful targets.

---

## 21. Meaning of `REPAIRING`

`FleetPhase.REPAIRING` is a real durable fleet-level reopening boundary.

It means:

> Fleet evaluation has produced actionable findings, but all affected target states and finding projections have not yet been durably returned to normal target repair execution.

It is not a worker execution phase.

While the fleet is:

```text
REPAIRING
```

Stage 2 must not admit normal work.

After affected targets have been durably moved to:

```text
TargetPhase.REPAIR
```

and their fleet-validation finding refs are installed, Stage 11 completes:

```text
FleetRunState.phase
    REPAIRING → RUNNING
```

Normal Stage 2 scheduling may then resume.

This gives crash recovery an explicit boundary between:

```text
fleet evaluation result committed
```

and:

```text
target repair routing committed
```

without introducing a new state object.

---

## 22. Reopening affected targets

A fleet-validation finding does not create a privileged fleet repair path.

For every affected accepted target:

```text
ACCEPTED
    ↓ Stage 11
REPAIR
    ↓ Stage 2
SCHEDULED
    ↓ Stage 3
HYDRATING
    ↓ Stage 4
WORKING
    ↓ Stage 6
FINALIZING
    ↓ Stage 7
VALIDATING
    ↓ Stage 8
REVIEWING
    ↓ Stage 10
ACCEPTED
```

Stage 11 does not permit:

```text
ACCEPTED → direct artifact edit → ACCEPTED
```

or:

```text
fleet validation
    → repair
    → Stage 8 directly
```

Any worker mutation after fleet rejection creates a new candidate.

That candidate must pass the normal local hard-validation and target-review path before becoming locally accepted again.

---

## 23. Historical accepted results

Fleet-level rejection does not invalidate or mutate a historical `AcceptedTargetResult`.

Example:

```text
AcceptedTargetResult A
        ↓
Stage 11 finding
        ↓
target reopened
        ↓
worker repairs candidate
        ↓
Stages 7 / 8 PASS
        ↓
AcceptedTargetResult B
```

Both:

```text
A
B
```

remain immutable historical records.

After the new local acceptance:

```text
TargetTaskState.last_accepted_result_ref = B
```

Stage 11 subsequently validates `B`.

`A` remains a true historical statement that its exact candidate earned local acceptance.

It simply no longer represents the target selected for the current fleet.

Stage 11 never rewrites previous accepted-target provenance.

---

## 24. Fleet-validation finding projection

Fleet-validation reports and findings are immutable history.

Mutable runtime state contains only the **current unresolved projection**.

The current fleet-level projection is held through:

```text
FleetRunState.open_finding_refs
```

and the affected target projection through:

```text
TargetTaskState.open_finding_refs
```

using:

```text
FindingOrigin.FLEET_VALIDATION
```

### New Stage 11 result

Every completed Stage 11 validation replaces only the current:

```text
FLEET_VALIDATION
```

projection.

It must not remove current findings originating from:

```text
HARD_VALIDATION
TARGET_REVIEW
FLEET_REVIEW
```

unless their owning stage separately does so.

### PASS

On PASS:

```text
current FLEET_VALIDATION projection → []
```

in fleet state and affected target states.

Historical findings remain persisted.

### FAIL

On FAIL:

```text
previous current FLEET_VALIDATION refs
    → removed from current projection

new report findings
    → installed as current FLEET_VALIDATION projection
```

Targets no longer affected by the new report lose their old current fleet-validation finding refs.

Targets affected by the new report receive the new refs.

---

## 25. Fleet findings across local re-acceptance

A target reopened by Stage 11 may later earn local acceptance again before the fleet-level finding has been proven resolved globally.

The existing fleet-validation finding therefore remains historical/current fleet-level feedback until Stage 11 runs again.

It does not retroactively invalidate the new Stage 10 local acceptance.

The distinction is:

```text
Stage 10
    proves the repaired target candidate passes local gates

Stage 11
    proves the repaired candidate composes correctly with siblings
```

Therefore a renewed:

```text
TargetTaskState.phase = ACCEPTED
```

does not itself clear the relevant `FLEET_VALIDATION` projection.

The next completed Stage 11 run replaces that projection.

This avoids falsely declaring a cross-target defect resolved merely because one target passed its local gates.

---

## 26. Re-entry after fleet repair

After Stage 11 FAIL:

```text
affected targets → REPAIR
unaffected targets → remain ACCEPTED
FleetRunState → RUNNING
```

The affected targets then execute normally.

When every activated target is again:

```text
ACCEPTED
```

the scheduler again hands control to Stage 11.

Stage 11 validates the **entire current accepted fleet again**.

V0 does not implement incremental or affected-edge-only fleet validation.

For the small fixed V0 target fleet, full deterministic revalidation is simpler and avoids invalid assumptions about which global relations may have changed.

---

## 27. Stage 12 exact-fleet handoff

Stage 12 may begin only after:

```text
FleetRunState.phase == REVIEWING
```

and there exists a valid:

```text
FleetValidationReport.PASS
```

whose:

```text
accepted_target_result_refs
```

exactly equal the fleet's current accepted-result refs.

Stage 12 must not independently choose another fleet candidate from:

```text
current filesystem state
latest artifact revisions
historical accepted results
mutable target workspace contents
```

The invariant is:

```text
fleet hard-validated
    =
fleet sent to fleet review
```

If any target is reopened or newly accepted after the PASS report, the previous Stage 11 PASS no longer authorizes Stage 12 review of that changed fleet.

Stage 11 must run again first.

---

## 28. Persistence

Stage 11 reuses Stage 5 persistence and transaction semantics.

No fleet-validation-specific storage protocol is introduced.

### Validation start

The transition:

```text
RUNNING → VALIDATING
```

is persisted through existing crash-safe state mutation.

### PASS commit

The logical PASS commit includes:

```text
FleetValidationReport PASS

replacement of current FLEET_VALIDATION projection with []

FleetRunState:
    VALIDATING → REVIEWING

corresponding trace/event records
```

The runtime must never expose:

```text
FleetRunState.phase = REVIEWING
```

without a resolvable PASS report applying to the exact current accepted fleet.

### FAIL result commit

The first logical FAIL boundary includes:

```text
FleetValidationReport FAIL
FleetValidationFinding[]
current fleet-level FLEET_VALIDATION projection
FleetRunState:
    VALIDATING → REPAIRING
trace/events
```

### Reopening commit

The fleet reopening boundary includes:

```text
affected TargetTaskState:
    ACCEPTED → REPAIR

affected target FLEET_VALIDATION finding projections

removal of obsolete target FLEET_VALIDATION projections

FleetRunState:
    REPAIRING → RUNNING

trace/events
```

Stage 11 uses the existing Stage 5 multi-authority transaction/recovery machinery.

It does not introduce:

```text
FleetValidationTransaction
FleetValidationCheckpoint
FleetRepairTransaction
```

contracts.

---

## 29. Idempotency

Fleet hard validation is idempotent for the same exact fleet candidate.

Conceptually:

```text
same fleet_run_id
+
same ordered AcceptedTargetResult refs
        ↓
same semantic fleet validation round
```

Repeated execution caused by:

```text
caller retry
process retry
recovery
duplicate invocation
```

must not create semantically duplicate reports or findings for the same accepted fleet candidate.

The report identity should be deterministically derived from the fleet and exact accepted-result set.

The precise ID encoding is implementation-private.

If a complete valid `FleetValidationReport` already exists for the exact current fleet candidate, recovery or duplicate execution may reuse it rather than creating another semantic validation round.

A changed accepted-result ref creates a new fleet candidate and therefore requires a new report.

---

## 30. Crash recovery

### Crash before `RUNNING → VALIDATING`

The fleet remains:

```text
RUNNING
```

with all targets accepted.

Stage 11 may begin normally.

### Crash while `VALIDATING` before report persistence

Recovery reloads:

```text
FleetRunState.phase = VALIDATING
```

and re-derives the exact current accepted-result set.

Targets cannot execute while the fleet is `VALIDATING`, so the validation subject cannot legitimately change during this phase.

Deterministic fleet validation may be executed again.

### Crash after PASS report persistence but before `REVIEWING`

Recovery detects the valid PASS report for the exact accepted fleet and completes:

```text
VALIDATING → REVIEWING
```

without creating another semantic validation round.

### Crash after FAIL report persistence

Recovery reuses the committed FAIL report and findings.

It must not rerun validation merely to recreate equivalent findings.

### Crash while `REPAIRING`

`REPAIRING` is a safe recovery boundary.

Stage 5 recovery completes or restores the interrupted reopening transaction so the runtime reaches a coherent state in which:

```text
all affected targets are REPAIR
+
required finding projections are installed
+
FleetRunState.phase = RUNNING
```

or remains durably:

```text
REPAIRING
```

until that transaction can be completed.

The runtime must not expose a partially routed repair fleet as normal `RUNNING` work.

### Corrupt recovery state

Impossible combinations such as:

```text
REVIEWING without applicable FleetValidationReport.PASS

VALIDATING with changed target acceptance state

REPAIRING with missing committed FAIL report

current fleet-validation finding refs that do not resolve
```

are runtime/persistence integrity failures.

They are not converted into new worker findings.

---

## 31. Concurrency

Stage 11 begins only after all activated targets are:

```text
ACCEPTED
```

Accepted targets hold no target execution slot.

While the fleet is:

```text
VALIDATING
REPAIRING
REVIEWING
```

ordinary Stage 2 target scheduling is not permitted by the existing fleet-phase rules.

No additional Stage 11 concurrency mechanism is needed.

Stage 11 introduces no:

```text
validation semaphore
validation worker slot
fleet validation lease
lock service
queue
```

The existing durable fleet phase is sufficient.

---

## 32. Usage and budgets

Stage 11 performs deterministic runtime work only.

It consumes:

```text
0 worker cycles
0 repair cycles
0 model calls
0 tool calls
0 input tokens
0 output tokens
```

Stage 11 therefore does not mutate:

```text
ExecutionUsage
```

and introduces no:

```text
fleet-validation budget
validation token budget
validation tool budget
```

A fleet whose model execution budget is fully consumed may still complete Stage 11 if all targets have already earned local acceptance.

If Stage 11 fails and an affected target lacks budget for another repair cycle, existing Stage 2 budget/exhaustion semantics determine what happens when repair execution is considered.

Stage 11 does not predict whether repair will be affordable before producing correct deterministic findings.

---

## 33. Semantic responsibilities deferred to Stage 12

Stage 11 intentionally does not decide questions such as:

```text
Do two targets explain the same concept redundantly?

Do accepted targets contradict one another semantically?

Is terminology consistent across the memory corpus?

Does a detailed explanation belong to the correct canonical target?

Should one target link to another instead of repeating content?

Is the fleet globally well organized?

Is the corpus easy for humans or models to navigate?

Does a cross-target link make semantic sense?
```

Those require artifact-level semantic judgment.

They belong to:

```text
Stage 12 — Fleet Reconciliation
```

The separation is deliberate:

```text
Stage 11
    deterministic mechanical composition

Stage 12
    semantic cross-target reconciliation
```

Stage 11 must not expand into an LLM-backed fleet reviewer.

---

## 34. Responsibilities deferred to Stage 13

Stage 11 does not create:

```text
AcceptedMemoryFleetResult
```

and does not set:

```text
FleetRunState.phase = ACCEPTED
```

A successful Stage 11 PASS establishes only:

```text
fleet hard validation passed
```

The fleet must still pass Stage 12 reconciliation.

Final fleet acceptance remains Stage 13 responsibility.

Stage 11 also has no Repository Brain publication authority.

---

## 35. Locked invariants

1. Stage 11 is deterministic runtime validation and invokes no model.
2. Stage 11 begins only from `FleetRunState.phase == RUNNING`.
3. Stage 11 begins only when every activated target is locally `ACCEPTED`.
4. The activated target set comes from immutable `MemoryFleetSpec.target_ids`.
5. Stage 11 does not recalculate target activation.
6. Incomplete target acceptance is an admission condition, not `FleetValidationReport.FAIL`.
7. Stage 11 owns `RUNNING → VALIDATING`.
8. The fleet-validation subject is derived exclusively through each `TargetTaskState.last_accepted_result_ref`.
9. Historical accepted results not currently selected do not participate.
10. Ambient workspace contents never define the fleet-validation subject.
11. The ordered `AcceptedTargetResult` set is the exact fleet candidate.
12. Accepted-result ordering follows `MemoryFleetSpec.target_ids`.
13. No persisted `FleetCandidate` or fleet candidate manifest is introduced.
14. Broken accepted-result/source/persistence provenance is a runtime integrity failure.
15. Runtime integrity failure does not create fleet-validation findings.
16. Stage 11 does not rerun Stage 7 hard validation.
17. Stage 11 trusts valid immutable local-acceptance provenance.
18. Stage 11 validates only invariants that genuinely require composing accepted targets.
19. The accepted fleet artifact index is derived from current `AcceptedTargetResult.artifact_refs`.
20. Stage 11 does not discover candidate artifacts by scanning mutable output directories.
21. Failed, stale, historical and unaccepted candidate versions are excluded by construction.
22. Fleet-relative generated-memory artifact paths must be valid and non-colliding.
23. No new globally unique bare `artifact_id` requirement is introduced.
24. Generated-memory relative Markdown document links must resolve against the exact accepted fleet.
25. Generated-memory relative links may not escape the memory namespace.
26. External URLs are not network-validated by Stage 11.
27. Heading fragments are not mechanically validated in V0.
28. Link existence is deterministic Stage 11 scope; link semantic quality is not.
29. A fleet may PASS Stage 11 with zero cross-target links.
30. No global claim graph, document-ID system or new cross-target metadata authority is introduced solely for Stage 11.
31. `FleetValidationFinding` represents only worker-correctable deterministic fleet-composition defects.
32. Fleet-validation findings are immutable.
33. `FindingRef.origin = FLEET_VALIDATION` is used for runtime projections.
34. `FleetValidationReport` is immutable.
35. Stage 11 reuses the existing `ValidationVerdict` PASS/FAIL vocabulary.
36. PASS contains no fleet-validation findings.
37. FAIL contains at least one actionable fleet-validation finding.
38. `FleetValidationReport.accepted_target_result_refs` identifies the exact evaluated fleet.
39. A PASS report applies only to its exact accepted-result set.
40. Any changed accepted-result ref requires Stage 11 again.
41. PASS owns `VALIDATING → REVIEWING`.
42. FAIL owns `VALIDATING → REPAIRING`.
43. `REPAIRING` is a real durable fleet-level reopening boundary.
44. Fleet-validation failure reopens only affected targets where possible.
45. Affected targets transition `ACCEPTED → REPAIR`.
46. Unaffected targets remain `ACCEPTED`.
47. Stage 11 completes `REPAIRING → RUNNING` only after reopening state is durably established.
48. Reopened targets use the normal Stage 2–10 lifecycle.
49. Fleet repair never bypasses Stage 7 or Stage 8.
50. Historical `AcceptedTargetResult` objects are never rewritten or deleted by Stage 11.
51. A repaired target that earns local acceptance again produces a new immutable accepted result when its candidate changed.
52. Renewed local acceptance does not itself prove the previous fleet finding globally resolved.
53. The next Stage 11 run replaces the current `FLEET_VALIDATION` finding projection.
54. Historical fleet-validation reports/findings remain immutable.
55. Stage 11 clears or replaces only `FLEET_VALIDATION` projections, not findings owned by other evaluation stages.
56. After fleet repair, Stage 11 reruns over the entire current accepted fleet.
57. V0 does not implement incremental fleet validation.
58. Stage 12 must review exactly the accepted-result set passed by Stage 11.
59. Stage 11 does not perform semantic fleet reconciliation.
60. Stage 11 does not accept the fleet.
61. Stage 11 reuses Stage 5 persistence and recovery machinery.
62. No Stage 11-specific checkpoint or persistence protocol is introduced.
63. Validation is idempotent for the same fleet and exact accepted-result set.
64. Recovery may deterministically rerun incomplete validation against an unchanged accepted fleet.
65. A committed report is reused during recovery rather than semantically duplicated.
66. No ordinary target scheduling occurs while the fleet is `VALIDATING`, `REPAIRING`, or `REVIEWING`.
67. Stage 11 consumes no worker/model/tool/token/repair usage.
68. Stage 11 introduces no dedicated execution budget.
69. Runtime corruption is never disguised as worker repair.
70. Stage 11 remains the smallest deterministic composition gate between local target acceptance and fleet semantic reconciliation.

---

## 36. New Stage 11 surface

Stage 11 adds only:

### Durable contracts

```text
FleetValidationReport
FleetValidationFinding
```

### Runtime interface

```text
validate_fleet(fleet_run_id)
    → FleetValidationReport
```

### Lifecycle behavior

```text
RUNNING → VALIDATING

PASS:
VALIDATING → REVIEWING

FAIL:
VALIDATING → REPAIRING
affected targets:
    ACCEPTED → REPAIR
REPAIRING → RUNNING
```

Existing contracts are reused directly:

```text
MemoryFleetSpec
FleetRunState
TargetTaskSpec
TargetTaskState
AcceptedTargetResult
CandidateArtifactRef
ValidationVerdict
FindingRef
FindingOrigin
TaskEvent
Stage 5 persistence/recovery machinery
```

Stage 11 does **not** introduce:

```text
FleetCandidate
FleetCandidateState
FleetCandidateManifest
FleetArtifactManifest
FleetArtifactIndex persisted contract
FleetLinkIndex persisted contract
FleetValidationState
FleetValidationAttempt
FleetValidationCheckpoint
FleetValidationContext
FleetValidationBudget
FleetValidationUsage
accepted-target map
copied target-status map
global claim graph
global document registry
new scheduler state
new persistence protocol
fleet repair agent
incremental fleet validator
```

---

## 37. Stage 12+ deferments

Stage 11 intentionally leaves the following behavior downstream.

### Stage 12 — Fleet Reconciliation

```text
FleetReviewContext

fleet reviewer execution

FleetReviewVerdict

FleetReviewFinding

cross-target duplication
cross-target contradictions
terminology consistency
semantic target ownership
scope leakage
global organization
semantic link quality

fleet-review-driven targeted reopening
```

Stage 12 operates over the exact locally accepted fleet that received Stage 11 PASS.

It remains read-only and performs no repository rediscovery.

### Stage 13 — Fleet Acceptance

```text
final PASS provenance

AcceptedMemoryFleetResult

FleetRunState:
    REVIEWING → ACCEPTED

accepted-result binding for the whole memory fleet

handoff to Repository Brain publication
```

Stage 11 remains specifically the deterministic boundary that proves the exact set of immutable locally accepted target results forms a structurally compatible fleet before semantic fleet reconciliation begins.
