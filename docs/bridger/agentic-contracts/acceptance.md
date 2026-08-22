# Stage 10 — Target Acceptance

## 1. Responsibility

Stage 10 is the deterministic **local acceptance commit boundary** for one target.

Its lifecycle boundary is:

```text
Stage 8
TargetTaskState.phase = REVIEWING
+
TargetValidationReport = PASS
+
TargetReviewVerdict = PASS
        ↓
Stage 10
verify acceptance provenance
freeze exact accepted candidate
persist AcceptedTargetResult
REVIEWING → ACCEPTED
        ↓
Stage 11
fleet-level validation may consume the
locally accepted target result
```

A target reaches Stage 10 only after both local evaluation gates have succeeded.

Stage 10 owns:

* validating local-acceptance preconditions;
* proving that finalization, hard-validation, review and current candidate state refer to the same exact candidate;
* creating the immutable `AcceptedTargetResult`;
* persisting that result through the existing Stage 5 persistence boundary;
* performing `REVIEWING → ACCEPTED`;
* updating `TargetTaskState.last_accepted_result_ref`;
* clearing `pending_finalization_request_ref`;
* making the accepted target available to later fleet stages;
* preserving idempotency across duplicate execution and crash recovery.

Stage 10 does **not** own:

* repository exploration;
* artifact generation or mutation;
* completion-state mutation;
* evidence creation or mutation;
* hard validation;
* target review;
* semantic evaluation;
* finding generation;
* finding resolution;
* repair;
* scheduling;
* fleet validation;
* fleet reconciliation;
* fleet acceptance;
* Repository Brain publication.

Stage 10 performs no new judgment.

It records that the exact candidate already proven by Stages 7 and 8 is now the target's authoritative **locally accepted result**. This preserves the existing separation between mutable target execution and immutable accepted outputs. 

---

## 2. Existing authorities consumed

Stage 10 consumes the already-locked authorities:

```text
MemoryFleetSpec
TargetTaskSpec
TargetTaskState
TargetCompletionState

candidate artifact state
EvidenceReference state

TargetFinalizationRequest
TargetValidationReport
TargetReviewVerdict

finding state
Stage 5 persistence / recovery machinery
```

Stage 10 does not replace or reinterpret these authorities.

The target lifecycle remains owned exclusively by:

```text
TargetTaskState.phase
```

`FleetRunState` remains shallow and references target tasks rather than storing a copied per-target lifecycle map. 

---

## 3. Acceptance meaning

Local acceptance means:

> The exact candidate identified by the accepted result has passed the target's deterministic hard-validation gate and artifact-level target review under the target's immutable assignment and source binding.

It does **not** mean:

```text
the complete fleet is valid
cross-target links are valid
cross-target ownership is correct
cross-target duplication is absent
cross-target contradictions are absent
global terminology is coherent
fleet reconciliation has passed
the memory fleet is accepted
the Repository Brain is publishable
```

Those are later fleet-level responsibilities.

The distinction is:

```text
TARGET ACCEPTANCE
    exact candidate passed its local gates

FLEET ACCEPTANCE
    complete set of locally accepted targets
    passed fleet validation and reconciliation
```

---

## 4. `AcceptedTargetResult`

Stage 10 introduces one new durable contract:

```text
AcceptedTargetResult
```

No separate acceptance report, acceptance state, acceptance attempt, acceptance checkpoint or acceptance manifest is introduced.

### Semantic definition

`AcceptedTargetResult` is the immutable identity of **one exact target candidate that successfully passed both local evaluation gates**.

It answers:

> Which exact version of this target was locally accepted, against which source and contract, and through which evaluation results?

It is historical accepted provenance, not mutable execution state.

### Contract

Conceptually:

```python
class AcceptedTargetResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    accepted_target_result_id: str

    target_task_id: str
    fleet_run_id: str
    target_id: str
    target_contract_version: str

    source: SourceBinding

    artifact_refs: list[CandidateArtifactRef]
    completion_items: list[CompletionItemState]
    evidence_refs: list[str]

    finalization_request_ref: str
    validation_report_ref: str
    review_verdict_ref: str
```

The exact ID encoding is implementation-private.

### Ownership / mutability

| Property    | Rule                                       |
| ----------- | ------------------------------------------ |
| Created by  | Target runtime during Stage 10             |
| Mutable by  | Nobody                                     |
| Persisted   | Yes                                        |
| Lifetime    | Retained provenance for the fleet run      |
| Parent      | `TargetTaskSpec` / owning fleet            |
| Consumed by | Stages 11–13 and later publication handoff |

---

## 5. Identity and source provenance

The accepted result carries:

```text
target_task_id
fleet_run_id
target_id
target_contract_version
SourceBinding
```

These values are frozen from the immutable target assignment.

They must satisfy:

```text
accepted_result.target_task_id
    == TargetTaskSpec.target_task_id

accepted_result.fleet_run_id
    == TargetTaskSpec.fleet_run_id

accepted_result.target_id
    == TargetTaskSpec.target_id

accepted_result.target_contract_version
    == TargetTaskSpec.target_contract_version

accepted_result.source
    == TargetTaskSpec.source
    == MemoryFleetSpec.source
```

`SourceBinding` is copied intentionally into the immutable accepted result.

The accepted result must remain independently sufficient to establish the repository revision, graph snapshot and optional enrichment overlay against which the target was accepted.

No source identity is inferred from the current workspace at acceptance time.

---

## 6. Accepted artifact set

`artifact_refs` freezes the exact current candidate artifact set using the already-locked `CandidateArtifactRef` contract:

```text
artifact_id
relative_path
revision
digest
```

Stage 10 does not copy artifact contents into `AcceptedTargetResult`.

The accepted result therefore identifies:

```text
which artifacts
which artifact revisions
which content digests
```

constituted the locally accepted target.

### Artifact-version preservation

Every artifact version referenced by an `AcceptedTargetResult` must remain resolvable after acceptance.

A later repair may:

```text
edit an artifact
replace an artifact
delete an artifact from the current candidate
reorganize the target workspace
```

but it must not destroy the historical artifact version required by an earlier accepted result.

Stage 10 reuses Stage 5 artifact-version persistence for this purpose.

No parallel `accepted-artifacts/` authority is introduced.

---

## 7. Accepted completion state

The accepted result contains a frozen snapshot of:

```text
CompletionItemState[]
```

from the exact `TargetCompletionState` evaluated by the successful local gates.

This snapshot includes the existing fields:

```text
obligation_id
status
resolution_note
evidence_refs
```

The static obligation definitions remain owned by the referenced `TargetDefinition`.

Stage 10 does not duplicate:

```text
obligation description
applicability metadata
investigation guidance
target semantics
```

### Why completion state is copied

`TargetCompletionState` is mutable runtime state.

A target may later be reopened and its completion resolutions may change.

Therefore an accepted result must preserve:

> what the semantic completion state was when this candidate was locally accepted.

Referencing only the live `TargetCompletionState` would allow historical accepted provenance to change retroactively.

No separate `AcceptedCompletionState` contract is introduced.

---

## 8. Evidence references

`AcceptedTargetResult.evidence_refs` freezes the exact evidence-reference set associated with the accepted candidate.

Only evidence IDs are copied.

The full immutable `EvidenceReference` objects remain in their existing evidence authority.

Every referenced evidence object must:

```text
exist
belong to the accepted target task
match the accepted SourceBinding
remain resolvable after acceptance
```

Stage 10 does not create new evidence and does not reinterpret existing evidence.

---

## 9. Evaluation provenance

The accepted result references exactly one successful local evaluation chain:

```text
finalization_request_ref
validation_report_ref
review_verdict_ref
```

The referenced objects remain independent immutable historical records.

Stage 10 does not embed or rewrite them.

The accepted evaluation chain must establish:

```text
TargetFinalizationRequest
        ↓
TargetValidationReport = PASS
        ↓
TargetReviewVerdict = PASS
```

for the exact candidate being accepted.

Previous validation reports, review verdicts and repair rounds remain durable history and are not removed or superseded in place.

---

## 10. Exact-candidate invariant

The central Stage 10 rule is:

> **The candidate accepted by Stage 10 must be exactly the candidate that passed both local gates.**

Conceptually:

```text
candidate finalized
    =
candidate hard-validated
    =
candidate reviewed
    =
candidate frozen into AcceptedTargetResult
```

Acceptance-relevant identity includes at least:

```text
target/source identity
artifact IDs
artifact revisions
artifact digests
completion-state snapshot
evidence binding
```

Stage 10 must use the candidate-provenance mechanisms already established by Stages 6–8 rather than reconstructing provenance from conversation history.

If the candidate changed after the relevant evaluation was produced, the previous PASS result does not authorize acceptance of the changed candidate.

Examples of invalid drift include:

```text
artifact revision changed
artifact digest changed
artifact added or removed
completion resolution changed
evidence binding changed
target/source identity mismatch
```

Stage 10 must fail explicitly rather than:

```text
accept stale evaluation
guess intended provenance
silently rerun evaluation
create semantic repair findings
```

Candidate-provenance corruption is a runtime integrity failure, not worker feedback.

---

## 11. Acceptance preconditions

`accept_target()` may succeed only when all of the following hold.

### Lifecycle

```text
TargetTaskState.phase == REVIEWING
```

### Assignment

The target task resolves to one immutable `TargetTaskSpec`, and all target/fleet/source identities remain compatible.

### Validation

The applicable `TargetValidationReport`:

```text
exists
belongs to this target task
has verdict PASS
applies to the exact candidate being accepted
```

### Review

The applicable `TargetReviewVerdict`:

```text
exists
belongs to this target task
has verdict PASS
was produced from the successful local validation path
applies to the exact candidate being accepted
```

### Candidate integrity

Every accepted artifact and evidence reference resolves exactly.

The current completion state matches the completion state evaluated by the successful local path.

### Findings

No unresolved local finding may currently block acceptance.

Stage 10 verifies this invariant but does not resolve findings itself.

---

## 12. Acceptance operation

The Stage 10 runtime interface is conceptually:

```text
accept_target(target_task_id)
    → AcceptedTargetResult
```

The runtime resolves all authoritative inputs internally.

The caller does not provide arbitrary:

```text
artifact refs
completion state
evidence refs
validation result
review result
source binding
```

as acceptance claims.

Those values are loaded from durable authoritative state.

The normal operation is:

```text
load authoritative target state
        ↓
verify REVIEWING
        ↓
resolve successful validation/review chain
        ↓
verify exact candidate identity
        ↓
construct immutable AcceptedTargetResult
        ↓
persist accepted result
        ↓
update TargetTaskState
        ↓
append trace transition
        ↓
return AcceptedTargetResult
```

No LLM is invoked.

---

## 13. Lifecycle mutation

On successful first acceptance:

```text
TargetTaskState.phase
    REVIEWING → ACCEPTED
```

Stage 10 owns this transition.

The runtime also sets:

```text
last_accepted_result_ref
    = accepted_target_result_id

pending_finalization_request_ref
    = null
```

The runtime does not clear unrelated durable target state merely because acceptance succeeded.

In particular, Stage 10 does not automatically erase:

```text
working_summary
open_question_refs
artifact_refs
evidence_refs
usage
checkpoint history
trace history
```

These remain available for provenance, debugging and possible later reopening.

---

## 14. `FleetRunState`

Stage 10 does not introduce or maintain a copied per-target acceptance map inside `FleetRunState`.

The locked global state remains:

```text
FleetRunState
    └── target_task_ids[]
```

and current target lifecycle is obtained from each authoritative:

```text
TargetTaskState.phase
```

Therefore Stage 10 does not add:

```text
accepted_target_ids
target_statuses
target_result_map
```

to `FleetRunState`.

When all required target tasks have:

```text
phase == ACCEPTED
```

the condition is derived from target states and the scheduler stops admitting ordinary target work.

Control may then proceed to Stage 11. The existing scheduler already defines all-required-targets-accepted as the handoff condition to the fleet gates. 

Stage 10 itself does not transition the fleet into a fleet-validation phase.

---

## 15. Persistence commit

Stage 10 reuses the persistence and recovery semantics locked in Stage 5.

The logical acceptance commit is:

```text
1. persist complete immutable AcceptedTargetResult

2. persist TargetTaskState update:
       phase = ACCEPTED
       last_accepted_result_ref = result ID
       pending_finalization_request_ref = null

3. append the corresponding acceptance / lifecycle trace event
```

The implementation must preserve the invariant:

```text
TargetTaskState.phase == ACCEPTED
    ⇒
last_accepted_result_ref resolves to
a complete valid AcceptedTargetResult
```

The runtime must never expose durable state equivalent to:

```text
phase = ACCEPTED
last_accepted_result_ref = null
```

Stage 10 does not define a second persistence protocol.

Atomic replacement, crash-safe state writes, artifact version durability and recovery continue to use Stage 5 mechanisms.

---

## 16. Idempotency

Acceptance is idempotent for the same exact successful candidate and evaluation chain.

Repeated execution must not create semantically duplicate accepted results simply because:

```text
the process retried
the caller retried
recovery reran acceptance
the same operation was invoked twice
```

Conceptually, accepted-result identity is derived deterministically from the accepted provenance, including:

```text
target task
exact candidate identity
successful validation identity
successful review identity
```

The precise hashing or textual ID format is implementation-private.

The required semantic behavior is:

```text
same target
+
same exact candidate
+
same successful local evaluation chain
        ↓
same accepted result
```

If the target has already reached:

```text
phase = ACCEPTED
last_accepted_result_ref = X
```

and `X` is valid for the same acceptance, another `accept_target()` call returns `X` or its equivalent loaded result without producing another acceptance.

---

## 17. Crash recovery

### Crash before accepted-result persistence

Durable state remains effectively:

```text
phase = REVIEWING
review PASS already exists
```

Recovery may rerun acceptance from durable state.

Hard validation and review do not need to rerun solely because acceptance itself was interrupted.

### Crash after result persistence but before target-state update

Recovery detects the already-persisted valid accepted result for the same candidate and completes:

```text
REVIEWING → ACCEPTED
```

without creating a new semantic acceptance.

### Crash after target-state update

Recovery sees:

```text
phase = ACCEPTED
last_accepted_result_ref = X
```

and validates that `X` resolves correctly.

No target work or evaluation is rerun.

### Invalid partial state

If recovery encounters an impossible combination such as:

```text
ACCEPTED with missing accepted result
accepted result with incompatible source/task identity
accepted result referencing missing artifact versions
```

the condition is treated as persistence/runtime corruption according to Stage 5 failure semantics.

It is not converted into worker repair.

---

## 18. Usage and budgets

Stage 10 consumes no worker/model execution budget.

It performs:

```text
0 worker cycles
0 repair cycles
0 model calls
0 tool calls
0 input tokens
0 output tokens
```

Acceptance therefore does not mutate `ExecutionUsage`.

A target that has already earned validation PASS and review PASS may still be accepted when its remaining worker execution budget is zero.

Budget exhaustion governs whether additional execution may begin.

It does not prevent the runtime from recording an already-earned successful acceptance.

Ordinary trace/persistence activity is not counted as worker execution usage.

---

## 19. Concurrency consequence

`REVIEWING` is an active target phase.

`ACCEPTED` is not runnable and does not occupy a target execution slot.

Therefore:

```text
REVIEWING → ACCEPTED
```

naturally releases the target's concurrency occupancy through the existing derived scheduler rules.

Stage 10 introduces no:

```text
release-slot command
lease record
semaphore artifact
scheduler callback contract
```

The lifecycle transition is sufficient.

---

## 20. Historical local evaluation

Acceptance does not rewrite prior evaluation history.

Example:

```text
candidate A
    validation FAIL

candidate B
    validation PASS
    review NEEDS_WORK

candidate C
    validation PASS
    review PASS
    accepted
```

`AcceptedTargetResult` for the successful local acceptance references only the final successful chain for candidate C.

The previous:

```text
finalization requests
validation reports
review verdicts
findings
repair events
checkpoints
```

remain immutable historical records.

They are not deleted or mutated merely because a later candidate succeeds.

---

## 21. Reopening an accepted target

`ACCEPTED` is locally successful but reopenable.

Later fleet validation or reconciliation may identify an issue that requires this target to change.

The later fleet stages may therefore perform:

```text
ACCEPTED
    ↓ fleet finding
REPAIR
```

When this happens:

```text
last_accepted_result_ref
```

continues to reference the previous immutable accepted result.

The old accepted result still means:

> This exact historical candidate passed its local gates.

It does **not** mean:

> This candidate remains the current fleet-valid version.

The mutable target task may then pass again through:

```text
REPAIR
→ SCHEDULED
→ HYDRATING
→ WORKING
→ FINALIZING
→ VALIDATING
→ REVIEWING
→ ACCEPTED
```

The core state already explicitly preserves `last_accepted_result_ref` across such reopening. 

---

## 22. Repeated local acceptance

When a reopened target produces a changed successful candidate:

```text
previous candidate A
    → AcceptedTargetResult A

fleet finding
    ↓
repair

new candidate B
    ↓
validation PASS
    ↓
review PASS
    ↓
Stage 10
    → AcceptedTargetResult B
```

Result A remains immutable historical provenance.

Result B becomes the current locally accepted result:

```text
TargetTaskState.last_accepted_result_ref = B
```

Stage 10 does not mutate A into B.

No separate acceptance-generation counter is required.

The immutable results plus trace already preserve acceptance history.

---

## 23. Findings

Stage 10 does not own finding lifecycle.

Before local acceptance, all findings that block the current local evaluation path must already be resolved according to Stages 7–9.

Stage 10 only verifies that no unresolved blocking local finding contradicts acceptance.

It never:

```text
creates repair findings
resolves review findings
resolves validation findings
resolves fleet findings
rewrites finding history
```

If open finding state is inconsistent with the purported PASS chain, acceptance fails explicitly.

---

## 24. Downstream fleet contract

Stage 10 is the boundary between mutable local target execution and later fleet-level evaluation.

Stages 11–13 consume exact locally accepted results rather than arbitrary current workspace state.

Conceptually:

```text
TargetTaskState.last_accepted_result_ref
        ↓
AcceptedTargetResult
        ↓
exact accepted artifact versions
exact accepted completion snapshot
exact accepted evidence set
exact source and contract identity
exact local evaluation provenance
```

Later fleet validation must not decide which target candidate is accepted by inspecting:

```text
current filesystem contents
latest artifact revisions
current mutable TargetCompletionState
conversation history
```

`AcceptedTargetResult` is the authoritative selector of the locally accepted candidate.

This is the concrete purpose of introducing the contract.

---

## 25. Local acceptance versus publication

`AcceptedTargetResult` is not a published Repository Brain artifact.

The progression remains:

```text
AcceptedTargetResult[]
        ↓
Stage 11 — Fleet Hard Validation
        ↓
Stage 12 — Fleet Reconciliation
        ↓
Stage 13 — Fleet Acceptance
        ↓
AcceptedMemoryFleetResult
        ↓
Repository Brain publication layer
```

Stage 10 therefore freezes a local target result only.

It grants no publication authority.

---

## 26. Stage 10 invariants

1. Stage 10 begins only from a target whose authoritative phase is `REVIEWING`.
2. Stage 10 owns `REVIEWING → ACCEPTED`.
3. Only the runtime may accept a target.
4. Workers and reviewers cannot directly create acceptance state.
5. Acceptance requires both hard-validation PASS and target-review PASS.
6. Stage 10 performs no new semantic or mechanical evaluation beyond acceptance-integrity checks.
7. The finalization request, validation report, review verdict and accepted candidate must all belong to the same target task.
8. The successful validation and review must apply to the exact candidate being accepted.
9. Candidate artifact identities, revisions and digests may not drift between successful evaluation and acceptance.
10. Accepted source identity must equal the immutable `TargetTaskSpec.source`.
11. Accepted target identity and contract version must equal the immutable `TargetTaskSpec`.
12. `AcceptedTargetResult` is immutable.
13. `AcceptedTargetResult` contains exact `CandidateArtifactRef` values, not artifact contents.
14. Historical artifact versions referenced by accepted results must remain resolvable.
15. No second accepted-artifact storage authority is introduced.
16. `AcceptedTargetResult` freezes a copy of the existing completion-item state.
17. The accepted result does not duplicate static obligation definitions.
18. `AcceptedTargetResult` freezes evidence IDs but does not duplicate full `EvidenceReference` records.
19. Evaluation reports/verdicts remain separate immutable authorities and are referenced rather than embedded.
20. Previous evaluation failures and repair history are preserved.
21. Stage 10 does not generate or resolve findings.
22. Acceptance-integrity corruption fails explicitly and is not converted into semantic repair.
23. Successful acceptance sets `TargetTaskState.phase = ACCEPTED`.
24. Successful acceptance sets `last_accepted_result_ref`.
25. Successful acceptance clears `pending_finalization_request_ref`.
26. Stage 10 does not destructively clear unrelated target continuation/history state.
27. `FleetRunState` does not copy target acceptance status.
28. The authoritative target phase remains `TargetTaskState.phase`.
29. All-required-targets-accepted is a derived handoff condition to Stage 11.
30. Stage 10 does not perform fleet lifecycle transitions.
31. `phase == ACCEPTED` requires a resolvable valid `last_accepted_result_ref`.
32. Acceptance uses the existing Stage 5 persistence and recovery mechanisms.
33. Acceptance is idempotent for the same exact candidate and successful evaluation chain.
34. Duplicate acceptance execution must not create semantically duplicate accepted results.
35. Recovery may complete interrupted acceptance without rerunning successful validation/review when their durable provenance remains valid.
36. Stage 10 consumes no worker/model/tool/token budget.
37. `REVIEWING → ACCEPTED` releases target concurrency through existing derived scheduling semantics.
38. A previous `AcceptedTargetResult` remains immutable when fleet-level findings reopen the target.
39. Reopened targets pass through their normal worker/finalization/validation/review path before becoming accepted again.
40. A changed candidate that later passes local gates creates a new immutable `AcceptedTargetResult`.
41. `last_accepted_result_ref` always identifies the latest locally accepted result for the mutable target execution.
42. Stage 11 and later fleet stages use accepted-result references to select exact target candidates.
43. Local target acceptance does not imply fleet acceptance.
44. Local target acceptance does not grant Repository Brain publication authority.

---

## 27. New Stage 10 surface

Stage 10 adds only:

### Durable contract

```text
AcceptedTargetResult
```

### Runtime interface

```text
accept_target(target_task_id)
    → AcceptedTargetResult
```

Existing contracts are reused directly:

```text
SourceBinding
CandidateArtifactRef
CompletionItemState
TargetTaskSpec
TargetTaskState
TargetCompletionState
TargetFinalizationRequest
TargetValidationReport
TargetReviewVerdict
EvidenceReference
TaskEvent
Stage 5 persistence/recovery machinery
```

Stage 10 does **not** introduce:

```text
AcceptedTargetState
TargetAcceptanceReport
TargetAcceptanceVerdict
TargetAcceptanceAttempt
TargetAcceptanceCheckpoint
TargetAcceptanceManifest
acceptance-specific budget
acceptance-specific finding
accepted-artifact duplicate store
fleet target-status projection
new scheduler state
new persistence protocol
```

---

## 28. Stage 11+ deferments

Stage 10 intentionally leaves the following fleet-level behavior to later stages.

### Stage 11 — Fleet hard validation

```text
FleetValidationReport
fleet structural/integrity gates
required-target accepted-result checks
cross-target source compatibility
cross-target artifact/link integrity
fleet validation findings
target reopening decisions from fleet validation
```

### Stage 12 — Fleet reconciliation

```text
FleetReviewContext
fleet reviewer execution
FleetReviewVerdict
cross-target duplication
cross-target contradiction
terminology consistency
semantic ownership reconciliation
fleet review findings
target reopening decisions from fleet review
```

### Stage 13 — Fleet acceptance

```text
AcceptedMemoryFleetResult
final fleet ACCEPTED transition
accepted fleet provenance
handoff to Repository Brain publication
```

Stage 10 remains specifically the deterministic boundary that freezes one exact locally successful target candidate and makes that immutable result available to the fleet-level stages.
