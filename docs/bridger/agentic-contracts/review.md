# Stage 8 — Target Review

## 1. Responsibility

Stage 8 is the fresh, read-only **semantic and artifact-quality review boundary** for one mechanically valid target candidate.

Its lifecycle boundary is:

```text
Stage 7
TargetTaskState.phase = REVIEWING
+
TargetValidationReport = PASS
+
exact validated candidate checkpoint
        ↓
Stage 8
compile fresh review context
invoke target reviewer
persist review verdict
        ↓
        ├── PASS       → remain REVIEWING → Stage 10
        └── NEEDS_WORK → REPAIR          → Stage 9
````

Stage 8 evaluates only properties visible from the target contract and the exact candidate that Stage 7 passed.

Stage 8 owns:

* compilation of the transient `TargetReviewContext`;
* fresh reviewer-model execution;
* artifact-level semantic-quality judgment;
* creation of `TargetReviewFinding` records;
* persistence of the immutable `TargetReviewVerdict`;
* current `TARGET_REVIEW` finding projection updates;
* `REVIEWING → REPAIR` on `NEEDS_WORK`;
* reviewer-model usage accounting.

Stage 8 does **not** own:

* repository rediscovery;
* repository-navigation or source-reading tools;
* independent verification that repository evidence semantically supports the prose;
* deterministic mechanical validation already owned by Stage 7;
* worker execution or artifact mutation;
* repair strategy;
* target acceptance;
* fleet-level reconciliation;
* offline Bridger evaluation.

Stage 10 alone owns:

```text
REVIEWING → ACCEPTED
```

A reviewer `PASS` is necessary for acceptance but is not itself acceptance.

---

## 2. Incoming authoritative state

Stage 8 may run only when:

```text
TargetTaskState.phase == REVIEWING

TargetTaskState.pending_finalization_request_ref
    → TargetFinalizationRequest F

F.candidate_checkpoint_ref
    → TaskCheckpoint C

TargetValidationReport V
    → PASS
    → bound to F and C
```

The review subject is exactly:

```text
TaskCheckpoint C
```

The reviewer must never silently review:

* the ambient mutable target workspace;
* later artifact revisions;
* reconstructed state from trace history;
* provider conversation state.

The authority chain is:

```text
TargetFinalizationRequest F
        ↓
candidate checkpoint C
        ↓
TargetValidationReport V — PASS
        ↓
TargetReviewVerdict R
```

`R` must remain explicitly bound to the same `F`, `C`, and `V`.

---

## 3. Reviewer responsibility boundary

The reviewer judges semantic and artifact quality visible from its legitimate inputs.

V0 review concerns include:

```text
visible completion-contract coverage
internal consistency
scope discipline
organization and navigability
appropriate level of detail
internal duplication
terminology consistency
writing clarity
quality of explicit unknowns and contradictions
visible unsupported certainty
Markdown / metadata / completion-state semantic consistency
quality of worker-owned file segmentation
```

The reviewer may fail visible coverage.

Example:

```text
completion obligation = covered

candidate artifacts contain no meaningful treatment
of that obligation
```

The reviewer may also fail visible contradiction or overstatement.

Example:

```text
completion state = unknown

artifact states the same matter as certain
```

The reviewer may **not** independently decide:

```text
whether an undisclosed repository subsystem was missed
whether a source workflow was interpreted correctly
whether another source file would have been better evidence
whether an EvidenceReference semantically proves a claim
whether not-applicable is actually true in repository reality
whether unknown could have been resolved through more discovery
```

Those require repository rediscovery or source-grounding verification and remain worker/offline-evaluation responsibilities.

---

## 4. `TargetDefinition` and reviewer rubric authority

`TargetDefinition` remains the sole semantic contract for the target.

It owns:

```text
target purpose
semantic scope
exclusions
cross-target ownership
completion obligations
output-quality expectations
```

The reviewer rubric is an evaluation/calibration artifact for applying that contract.

It may define:

```text
quality interpretation
target-specific examples
criterion identifiers
expected depth
scope-leakage examples
organization / segmentation expectations
```

It must not introduce:

```text
new completion obligations
new required repository topics
new semantic ownership
new grounding requirements
new target exclusions
```

Therefore:

```text
TargetDefinition
    = what successful target knowledge means

reviewer rubric
    = how that existing contract is evaluated
```

No second target contract is introduced.

---

## 5. `TargetReviewContext`

`TargetReviewContext` is a transient, immutable, provider-neutral reviewer input.

It is compiled fresh for one validated candidate and is never authoritative durable task state.

Conceptually:

```text
TargetReviewContext

review identity
├── target_task_id
├── target_id
├── target_contract_version
├── finalization_request_ref
├── candidate_checkpoint_ref
├── validation_report_ref
└── source binding

target contract
├── purpose / canonical question
├── scope
├── exclusions
├── boundary guidance
├── completion obligations
└── output-quality expectations

candidate
├── checkpointed TargetCompletionState
├── exact checkpointed candidate artifacts
├── candidate-local metadata / claims when applicable
└── artifact identities / paths / revisions / digests

evaluation
├── Stage 7 PASS report
├── shared reviewer instructions
├── target-specific reviewer rubric
└── structured review-output contract
```

The candidate material must resolve from the checkpointed artifact versions referenced by the validated submission.

### Context exclusions

The reviewer does not normally receive:

```text
worker transcript
worker reasoning
working_summary
worker tool history
TaskEvent history
old checkpoints
provider conversation state
RepositoryNavigator
raw repository source
graph-navigation capability
sibling target artifacts
previous reviewer reasoning
previous reviewer findings
```

Previous review findings are intentionally excluded by default.

Each newly submitted candidate receives a fresh independent assessment rather than a review biased toward checking only earlier criticisms.

---

## 6. Reviewer permissions and execution model

The Stage 8 reviewer is:

```text
fresh-context
read-only
artifact-focused
tool-less
```

V0 exposes no tools to the reviewer.

In particular:

```text
no RepositoryNavigator
no TargetWorkspace
no EvidenceRecorder
no source reader
no shell
no artifact mutation tools
```

The complete reviewable candidate is compiled directly into `TargetReviewContext`.

This is deliberate V0 simplicity. Candidate-reading tools or multi-pass review should be introduced only if real target sizes demonstrate that one bounded review context is insufficient.

---

## 7. Review verdict

The V0 verdict vocabulary is exactly:

```text
PASS
NEEDS_WORK
```

No additional status such as:

```text
UNCERTAIN
PARTIAL_PASS
PASS_WITH_WARNINGS
```

is introduced.

### `PASS`

Means:

> No material issue within Stage 8's legitimate artifact-review authority should block local target acceptance.

It does not mean that repository interpretation has been independently proven correct.

Invariant:

```text
PASS
→ zero review findings
```

### `NEEDS_WORK`

Means:

> At least one material artifact-level issue within Stage 8's authority must be repaired before local acceptance.

Invariant:

```text
NEEDS_WORK
→ one or more review findings
```

Reviewer/provider execution uncertainty is not a semantic verdict.

Malformed output, provider failure, context failure, or runtime interruption remain runtime failures rather than `NEEDS_WORK`.

---

## 8. `TargetReviewFinding`

One persisted review finding represents one concrete blocking artifact-quality issue.

Conceptually:

```text
TargetReviewFinding
├── finding_id
├── review_id
├── target_task_id
├── criterion_id
├── message
├── affected_artifact_refs[]
├── affected_obligation_ids[]
└── required_outcome
```

The reviewer draft uses `affected_artifact_paths[]`, containing exact relative
paths from the immutable candidate checkpoint. The runtime validates those paths
and deterministically resolves them to the authoritative
`TargetReviewFinding.affected_artifact_refs[]` before persistence. Unknown paths
or obligation IDs are malformed reviewer output, acquire no durable authority,
and use the existing bounded retry and recovery behavior.

Affected artifact and obligation references are optional when the issue applies to the complete target.

`required_outcome` describes what must become true without prescribing the worker's implementation strategy.

Example:

```text
criterion:
    internal-duplication

message:
    overview.md and runtime.md contain materially duplicated
    descriptions of the same startup flow

required_outcome:
    retain one canonical detailed explanation and reduce
    the other to bounded orientation context
```

V0 introduces no:

```text
severity
confidence
priority
repair-plan hierarchy
root-cause model
nested critique structure
```

All persisted Stage 8 findings are acceptance-blocking.

### Finding identity

The reviewer model does not create authoritative finding IDs.

The runtime assigns finding identity after validating the structured reviewer output.

A simple V0 identity is derived from:

```text
review_id + finding ordinal
```

Historical findings are immutable.

---

## 9. `TargetReviewVerdict`

`TargetReviewVerdict` is the immutable persisted semantic result of Stage 8.

Conceptually:

```text
TargetReviewVerdict
├── review_id
├── target_task_id
├── finalization_request_ref
├── candidate_checkpoint_ref
├── validation_report_ref
├── verdict
├── finding_refs[]
└── reviewer_profile_id
```

The verdict must bind explicitly to:

```text
the exact finalization request
the exact candidate checkpoint
the exact PASS validation report
```

This allows Stage 10 to prove directly that one exact candidate passed both local evaluation gates.

### Review identity

One finalization request has at most one committed review verdict.

Conceptually:

```text
one TargetFinalizationRequest
    → one logical review_id
    → at most one committed TargetReviewVerdict
```

Provider retries do not create new semantic review identities.

No separate:

```text
ReviewAttempt
ReviewSession
ReviewerConversation
ReviewState
```

contract is introduced.

---

## 10. Lifecycle behavior

### `REVIEWING`

`REVIEWING` means:

> The submitted candidate has passed Stage 7 and is within semantic review or the subsequent local-acceptance handoff.

A target may therefore remain `REVIEWING` when:

```text
review has not yet been committed

or

TargetReviewVerdict = PASS
and Stage 10 acceptance has not yet occurred
```

No intermediate `REVIEWED` or `AWAITING_ACCEPTANCE` phase is introduced.

### `NEEDS_WORK`

A committed `NEEDS_WORK` verdict owns:

```text
REVIEWING → REPAIR
```

The transition occurs only together with durable review findings and state-projection updates.

### `PASS`

A committed `PASS` verdict leaves:

```text
TargetTaskState.phase = REVIEWING
```

Stage 10 later consumes the durable PASS verdict and exclusively owns:

```text
REVIEWING → ACCEPTED
```

This makes review PASS crash-safe without allowing Stage 8 to perform acceptance indirectly.

---

## 11. `open_finding_refs`

`TargetTaskState.open_finding_refs` remains a projection of **currently unresolved** findings, not evaluation history.

A newly committed Stage 8 verdict supersedes the current projection whose origin is:

```text
TARGET_REVIEW
```

### New `NEEDS_WORK`

```text
remove previous TARGET_REVIEW refs
add findings from the new review
```

### New `PASS`

```text
remove previous TARGET_REVIEW refs
add none
```

Historical review verdicts and historical finding records remain immutable.

Stage 8 must not clear findings owned by another authority:

```text
HARD_VALIDATION
FLEET_VALIDATION
FLEET_REVIEW
```

If an earlier semantic problem still exists in a newly submitted candidate, the fresh reviewer should emit it again as a finding for the new review round.

---

## 12. Persistence boundary

Reviewer model invocation occurs outside the durable mutation transaction.

Conceptually:

```text
1. validate REVIEWING boundary
2. resolve F, C and PASS V
3. return existing verdict if already committed
4. compile TargetReviewContext
5. perform budget/context preflight
6. invoke reviewer
7. parse and validate structured output
8. assign runtime-owned finding identities
9. atomically persist semantic review outcome
```

### PASS commit

One logical durable operation establishes:

```text
TargetReviewVerdict = PASS
+
clear current TARGET_REVIEW finding refs
+
review TaskEvent / usage state
```

The target remains:

```text
REVIEWING
```

### NEEDS_WORK commit

One logical durable operation establishes:

```text
TargetReviewFinding records
+
TargetReviewVerdict = NEEDS_WORK
+
replace current TARGET_REVIEW finding refs
+
REVIEWING → REPAIR
+
review / transition TaskEvent state
```

Stage 8 reuses the Stage 5 persistence transaction and recovery mechanisms.

No Stage-8-specific workflow engine, transaction system, or checkpoint type is introduced.

No new candidate checkpoint is required: Stage 6's submitted `TaskCheckpoint` remains the reviewed candidate authority.

---

## 13. Recovery and idempotency

Stage 8 uses:

```text
at-least-once reviewer execution
+
at-most-one committed verdict
```

### REVIEWING with no committed verdict

Recovery reconstructs `TargetReviewContext` from durable state and may invoke the reviewer again.

No provider conversation needs to be restored.

### Provider response existed only in memory

If the process crashes after the reviewer returns but before persistence, that response has no durable authority.

Recovery may invoke the reviewer again.

A different probabilistic response is acceptable because no earlier verdict was committed.

### Verdict already committed

Recovery reuses the existing verdict.

The reviewer must not run again for the same finalization request.

### Partial persistence

If a verdict/finding record is durable but related state projection or lifecycle mutation was interrupted, Stage 5 redo/recovery semantics complete the intended operation.

Provider conversation state is never authoritative recovery state.

---

## 14. Multiple review rounds

Repair preserves the existing target execution identity.

Example:

```text
same target_task_id

Finalization F1
    ↓
Checkpoint C1
    ↓
Validation V1 PASS
    ↓
Review R1 NEEDS_WORK

repair

Finalization F2
    ↓
Checkpoint C2
    ↓
Validation V2 PASS
    ↓
Review R2 PASS
```

Historical:

```text
F1 / C1 / V1 / R1 / findings
F2 / C2 / V2 / R2
```

remain immutable.

Repair does not reset or replace:

```text
target_task_id
TargetTaskSpec
source binding
target workspace identity
execution budget
accumulated usage
```

A later review round only replaces the current `TARGET_REVIEW` finding projection.

---

## 15. Usage and budgets

Stage 8 uses the existing `ExecutionUsage` and `ExecutionBudget` contracts.

Every actual reviewer provider invocation attempt increments:

```text
model_calls += 1
```

at both target and fleet scope.

Provider-reported usage increments:

```text
input_tokens
output_tokens
```

at both scopes.

Reviewer retries consume additional model calls and tokens.

Stage 8 does not increment:

```text
cycles
repair_cycles
tool_calls
```

because:

* no worker cycle begins;
* repair-cycle accounting belongs to repair worker admission/execution;
* the reviewer has no tools.

Before every reviewer invocation, existing target and fleet hard budgets are checked.

If the target's own remaining hard budget cannot permit the required reviewer call:

```text
REVIEWING → EXHAUSTED
```

If only the fleet-wide budget prevents further execution, Stage 8 does not incorrectly mark the target as target-level `EXHAUSTED`; fleet-level exhaustion remains owned by the existing fleet budget/runtime semantics.

---

## 16. Concurrency

Stage 8 introduces no new scheduling contract.

`REVIEWING` already occupies the target's existing Stage 2 execution slot.

Therefore:

```text
Stage 7 PASS
    → REVIEWING
    → same slot remains held

NEEDS_WORK
    → REPAIR
    → slot released

PASS
    → remain REVIEWING
    → slot remains held until Stage 10
```

No reviewer-specific target queue, admission system, or scheduling phase is introduced.

Generic provider-level concurrency/rate limiting may be reused where already available but does not change target scheduling semantics.

---

## 17. Stage 9 repair handoff

A committed `NEEDS_WORK` produces the durable Stage 9 boundary:

```text
TargetTaskState.phase = REPAIR

same TargetTaskSpec
same target_task_id
same source binding
same accumulated usage

TargetFinalizationRequest F
candidate checkpoint C
TargetValidationReport V = PASS

TargetReviewVerdict R = NEEDS_WORK
    bound to F / C / V

current TARGET_REVIEW findings
    referenced by open_finding_refs
```

Stage 8 does not prescribe the repair strategy.

The worker may later:

```text
patch
rewrite
reorganize
merge/split files
replace weak structure
perform additional repository investigation
```

under normal Stage 9/worker rules.

---

## 18. Stage 10 acceptance handoff

A successful Stage 8 boundary is:

```text
TargetTaskState.phase = REVIEWING

pending_finalization_request_ref → F
F.candidate_checkpoint_ref       → C

TargetValidationReport V
    verdict = PASS
    bound to F and C

TargetReviewVerdict R
    verdict = PASS
    bound to F, C and V
```

This is the durable proof that:

> The exact candidate `C` passed both deterministic hard validation and independent target review.

Stage 10 must not infer this from:

```text
trace ordering
reviewer conversation
worker conversation
ambient workspace contents
timestamps
```

Stage 10 uses these explicit durable bindings to perform local target acceptance.

---

## 19. Locked rules

1. Stage 8 runs only from `REVIEWING` after a Stage 7 PASS.
2. The review subject is exactly the candidate checkpoint referenced by the pending finalization request and passed by Stage 7.
3. Ambient mutable workspace state never replaces the checkpointed candidate.
4. The reviewer always runs from a fresh compiled context.
5. The reviewer is read-only.
6. The reviewer receives no repository-navigation capability.
7. The reviewer receives no tools in V0.
8. `TargetDefinition` remains the sole semantic target contract.
9. Reviewer rubrics calibrate evaluation but cannot create new semantic obligations.
10. Stage 8 judges only properties visible from its legitimate inputs.
11. Repository truth and source-grounding verification are outside Stage 8.
12. The verdict vocabulary is exactly `PASS` and `NEEDS_WORK`.
13. `PASS` contains zero review findings.
14. `NEEDS_WORK` contains at least one actionable review finding.
15. Reviewer findings are immutable historical records.
16. Reviewer-model output does not control authoritative finding identity.
17. `TargetTaskState` stores current finding references rather than duplicated finding contents/history.
18. A new review replaces only the current `TARGET_REVIEW` finding projection.
19. Historical review verdicts and findings are never mutated.
20. One finalization request has at most one committed `TargetReviewVerdict`.
21. Provider retries do not create separate semantic review rounds.
22. Provider conversation state is never authoritative.
23. Stage 8 owns `REVIEWING → REPAIR` on `NEEDS_WORK`.
24. A reviewer `PASS` leaves the target in `REVIEWING`.
25. Stage 10 exclusively owns `REVIEWING → ACCEPTED`.
26. Stage 8 reuses Stage 5 persistence and recovery semantics.
27. A crash before verdict persistence may cause reviewer re-execution.
28. A crash after verdict persistence must reuse the committed verdict.
29. Review model calls consume existing target/fleet model-call and token budgets.
30. Review does not increment worker-cycle, repair-cycle, or tool-call counters.
31. Target-budget inability to run the required review may produce `REVIEWING → EXHAUSTED`.
32. Fleet-only budget exhaustion does not falsely mark the target as target-level `EXHAUSTED`.
33. `REVIEWING` continues to occupy the already-reserved target concurrency slot.
34. Repair after review failure uses the same target task, workspace, source binding, budget, and accumulated usage.
35. Stage 8 does not accept targets, perform repair, or perform fleet reconciliation.
36. Simplicity remains preferred over additional review workflow machinery.

---

## 20. Stage 9+ deferments

Stage 8 intentionally does not define:

### Stage 9 — Repair

```text
repair-context compilation
repair finding prioritization
worker repair strategy
exact repair execution flow
```

Stage 8 only guarantees a durable `REPAIR` state and actionable current review findings.

### Stage 10 — Target acceptance

```text
AcceptedTargetResult schema
candidate freezing for acceptance
accepted-result persistence
REVIEWING → ACCEPTED transaction
last_accepted_result_ref semantics
```

Stage 8 only guarantees the durable proof that one exact candidate passed both local gates.

### Stages 11–13

```text
fleet hard validation
fleet reconciliation
fleet-level reopening
fleet acceptance
```

Cross-target duplication, contradiction, terminology, ownership, and whole-fleet organization remain later fleet-level responsibilities.

Stage 8 remains specifically the fresh, read-only semantic/artifact review boundary between Stage 7 hard validation and later repair or target acceptance.

```
```
