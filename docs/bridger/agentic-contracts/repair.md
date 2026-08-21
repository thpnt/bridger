# Stage 9 — Repair

Responsibility

Stage 9 routes a target rejected by hard validation or target review back into the existing worker execution path.

Repair continues the same target task.

Stage 7 FAIL
or
Stage 8 NEEDS_WORK
        ↓
REPAIR
        ↓
Stage 2 — Scheduling
        ↓
Stage 3 — Context Hydration
        ↓
Stage 4 — Worker Cycle
        ↓
Stage 6 — Finalization
        ↓
Stage 7 — Hard Validation
        ↓
Stage 8 — Target Review

Stage 9 does not introduce a separate repair agent, repair worker loop, repair context contract, repair workspace, repair task, or repair persistence subsystem.

The existing Stage 2–4 machinery is the repair execution mechanism.

⸻

Incoming repair state

Stage 9 begins only from:

TargetTaskState.phase == REPAIR

The transition into REPAIR is produced durably by either:

TargetValidationReport.result == FAIL

or:

TargetReviewVerdict.result == NEEDS_WORK

At this boundary:

* the rejected candidate is identified by the TargetFinalizationRequest and its immutable TaskCheckpoint;
* the corresponding validation report or review verdict is immutable;
* generated findings are immutable;
* TargetTaskState.open_finding_refs contains the current unresolved repair findings;
* pending_finalization_request_ref has been cleared;
* no candidate is currently under evaluation;
* the target retains its existing workspace, completion state, evidence, questions, working summary, usage, and budget.

Repair does not create or replace:

target_task_id
TargetTaskSpec
SourceBinding
target workspace identity
ExecutionBudget
ExecutionUsage

Historical finalization requests, checkpoints, validation reports, review verdicts, and findings remain preserved.

⸻

REPAIR phase semantics

REPAIR is a durable waiting/admission phase.

It means:

The previous evaluation round failed, unresolved evaluator findings exist, and the same target task may be admitted to another worker execution through normal scheduling.

While a target remains in REPAIR:

* no worker is running;
* no concurrency slot is held;
* no model or tool usage is consumed;
* no artifact mutation occurs;
* no provider conversation state is required.

The target leaves REPAIR only through normal Stage 2 scheduling:

REPAIR
    ↓
SCHEDULED

Direct transitions such as:

REPAIR → WORKING

are not allowed.

⸻

Scheduling and concurrency

Stage 2 remains the sole scheduling authority.

A REPAIR target is eligible for the same scheduling path as other executable targets.

Before:

REPAIR → SCHEDULED

the scheduler reuses the existing admission rules, including:

* dependency eligibility;
* target execution budget;
* fleet execution budget;
* max_repair_cycles;
* target-concurrency availability.

SCHEDULED reserves the execution slot exactly as in ordinary execution.

Repair receives no special priority, separate queue, separate worker pool, or repair-specific concurrency mechanism in V0.

⸻

Repair context hydration

Stage 9 introduces no RepairContext.

Stage 3 compiles the normal WorkerContext with:

mode = REPAIR

The repair context contains the same target execution information used during normal worker execution, plus every currently open repair finding.

At minimum it includes:

shared worker instructions
target identity and TargetDefinition
target scope and ownership boundaries
SourceBinding
current TargetCompletionState
current artifact inventory
working_summary
open questions
remaining budget
current unresolved findings
allowed worker tools

Each repair finding exposed to the worker preserves:

finding identity
finding origin
actionable finding content
affected artifact / obligation / scope when available

The worker receives only current actionable evaluation feedback.

Normal repair hydration does not include:

full worker transcript
reviewer transcript or hidden reasoning
complete TaskEvent history
all historical validation reports
all historical review verdicts
resolved or superseded findings
old tool outputs
checkpoint history
provider conversation state
sibling worker histories

Historical state remains durable and inspectable by the runtime but is not automatically loaded into the worker context.

⸻

Worker execution during repair

Repair uses the existing Stage 4 worker.

The worker retains exactly the normal worker permissions:

read repository through RepositoryNavigator
inspect graph/file/symbol/source evidence
write inside its target workspace
create/edit/delete/reorganize target-local generated files
record evidence
update completion-state resolutions
update working summary and open questions
request finalization

Repair does not grant additional permissions.

The worker decides how to address the findings.

A repair may require:

* a small Markdown correction;
* fixing artifact structure;
* correcting evidence references;
* changing completion-state resolution;
* additional repository investigation;
* rewriting weak explanations;
* resolving contradictions;
* reducing duplication;
* reorganizing target-local files.

Validation or review findings describe why the candidate was rejected. They do not become authoritative implementation instructions.

⸻

Finding ownership and resolution

Evaluation findings remain owned by their evaluator.

The worker cannot:

delete evaluator findings
mark evaluator findings resolved
mutate open_finding_refs directly
declare validation or review feedback verified

TargetTaskState.open_finding_refs is a projection of currently unresolved findings. The underlying finding records remain immutable.

Hard-validation findings

A later Stage 7 result owns the current HARD_VALIDATION projection.

new Stage 7 FAIL
    → replace current HARD_VALIDATION finding refs
      with findings from the new validation report
new Stage 7 PASS
    → clear current HARD_VALIDATION finding refs

Previous hard-validation findings remain immutable historical records.

Target-review findings

A later Stage 8 verdict owns the current TARGET_REVIEW projection.

new Stage 8 NEEDS_WORK
    → replace current TARGET_REVIEW finding refs
      with findings from the new review verdict
new Stage 8 PASS
    → clear current TARGET_REVIEW finding refs

Previous review findings remain immutable historical records.

Findings across evaluation stages

Finding origins are resolved independently.

Example:

Candidate A
    ↓
Stage 7 PASS
    ↓
Stage 8 NEEDS_WORK
    ↓
review findings R1, R2
    ↓
repair
    ↓
Candidate B
    ↓
Stage 7 FAIL
    ↓
hard finding H1

The current repair projection is:

R1
R2
H1

The old review findings remain open because Stage 8 has not yet verified that the new candidate resolved them.

After a later Stage 7 PASS, hard-validation findings clear, while review findings remain open until the new candidate is independently reviewed by Stage 8.

This prevents worker edits from implicitly declaring evaluator findings solved.

⸻

Rejected checkpoint and mutable workspace

Every submitted candidate is frozen by Stage 6 in an immutable TaskCheckpoint.

That checkpoint is historical provenance for the candidate that produced the corresponding validation or review result.

It is never mutated during repair.

At the transition into REPAIR, the authoritative current candidate workspace must still correspond to the rejected checkpoint because worker mutation is forbidden while the candidate is in:

FINALIZING
VALIDATING
REVIEWING

Normal repair therefore begins conceptually from:

rejected TaskCheckpoint C
        │
        │ same candidate at repair boundary
        ▼
current target workspace
        ↓
worker repair mutations
        ↓
new candidate

Once Stage 4 begins, the workspace may diverge freely from the rejected checkpoint.

The rejected checkpoint remains unchanged.

Workspace/checkpoint mismatch

If the runtime finds that the current authoritative candidate no longer corresponds to the rejected checkpoint before repair execution begins, Stage 9 must not silently restore or substitute files.

Such a mismatch is a Stage 5 persistence/recovery integrity failure.

Repair begins only from a valid durable candidate state.

Unverified ambient filesystem contents are never treated as authoritative repair state.

⸻

Completion-state behavior

TargetCompletionState remains mutable through the existing controlled Stage 4 completion-state operation.

Stage 9 introduces no new completion-state API.

Repair may change an obligation between already-allowed terminal resolutions when additional investigation or evaluator feedback changes the correct conclusion.

Examples:

covered → unknown
unknown → covered
not-applicable → covered
covered → not-applicable

Resolution notes and evidence references may also be updated.

The existing prohibition remains:

terminal resolution → uninvestigated

Repair does not erase previous investigation.

Evaluator findings represent that the current candidate requires more work; they do not require resetting semantic progress to an uninvestigated state.

⸻

Repair-cycle accounting

ExecutionUsage.repair_cycles follows the existing Stage 4 accounting rule.

A repair cycle is charged once when a repair-mode worker execution actually begins:

HYDRATING → WORKING

with:

WorkerContext.mode == REPAIR

At that transition:

usage.cycles += 1
usage.repair_cycles += 1

Repair cycles are not incremented when:

entering REPAIR
being scheduled
entering HYDRATING
processing a finding
making a model call
making a tool call
submitting finalization

A semantic repair episode normally contains one repair worker cycle.

If an already-started repair worker execution is lost and Stage 5 recovery intentionally begins a fresh worker execution, the original execution remains consumed and the fresh repair execution consumes another repair cycle.

No separate repair-round identity is introduced in V0.

Both hard-validation and target-review failures consume the same max_repair_cycles budget.

⸻

Model, tool, and token usage

Stage 9 itself consumes no model, tool, cycle, or token usage.

Usage continues through the normal Stage 4 mechanisms.

Repair worker execution contributes to the same cumulative counters:

cycles
repair_cycles
model_calls
tool_calls
input_tokens
output_tokens

Target and fleet usage remain monotonic.

Repair never resets usage or provides a fresh target/fleet budget.

⸻

Persistence

Stage 9 reuses Stage 5 persistence and transaction semantics.

No new repair-specific transaction format is introduced.

The evaluation stage that sends a target into REPAIR durably commits the relevant:

validation report or review verdict
immutable findings
open_finding_refs projection
pending-finalization cleanup
phase = REPAIR
trace/events

Subsequent durable transitions remain owned by their existing stages:

Stage 2:
REPAIR → SCHEDULED
Stage 3:
SCHEDULED → HYDRATING
Stage 4 / Stage 5:
HYDRATING → WORKING
usage/cycle accounting
worker mutations
Stage 6:
new finalization request
new candidate checkpoint

Stage 9 introduces no:

RepairRecord
RepairState
RepairCheckpoint
RepairAttempt
repair-specific event log

⸻

Recovery and idempotency

REPAIR is a safe durable recovery point.

Crash while in REPAIR

The runtime reloads the durable target state.

If:

phase == REPAIR
current findings resolve
candidate state is valid

the target may later be scheduled normally.

Crash before repair admission

The target remains in REPAIR.

No repair-cycle usage has been consumed.

Crash during REPAIR → SCHEDULED

Stage 5 transaction recovery determines whether the authoritative result is:

REPAIR

or:

SCHEDULED

The same repair execution must never receive two concurrency reservations.

Duplicate scheduling

Only a target currently in REPAIR may undergo:

REPAIR → SCHEDULED

A target already in:

SCHEDULED
HYDRATING
WORKING

has already been admitted and is not scheduled again.

Crash after repair-cycle accounting

The HYDRATING → WORKING phase transition and its usage delta remain one crash-safe durable mutation.

Replaying recovery must not accidentally charge the same transition twice.

If Stage 5 determines that the interrupted WORKING execution is consumed and starts a new worker execution, that fresh repair execution receives its own repair-cycle charge.

Worker failure during repair

A worker/provider/runtime failure while WORKING is handled by the existing Stage 5 recovery policy.

It does not create a new semantic REPAIR transition and does not generate validation or review findings.

Already committed artifact, evidence, completion, summary, and question mutations remain authoritative according to existing persistence semantics.

Provider conversation state is never recovery authority.

⸻

Multiple repair rounds

A target may undergo multiple repair/evaluation rounds without changing its identity.

Example:

Candidate A
    ↓
Stage 7 FAIL
    ↓
Repair 1
    ↓
Candidate B
    ↓
Stage 7 PASS
    ↓
Stage 8 NEEDS_WORK
    ↓
Repair 2
    ↓
Candidate C
    ↓
Stage 7 PASS
    ↓
Stage 8 PASS

Across all rounds, the following remain unchanged:

target_task_id
TargetTaskSpec
SourceBinding
target workspace identity
configured budgets

Usage continues cumulatively.

Each round produces new immutable evaluation lineage:

TargetFinalizationRequest
TaskCheckpoint
TargetValidationReport
ValidationFinding[]
TargetReviewVerdict?
TargetReviewFinding[]?

Previous rounds are never rewritten or discarded.

⸻

No-progress and repeated failures

Stage 9 introduces no repair-specific loop detector.

Existing:

last_progress_signature
stall_count

remain governed by the previously locked runtime policy.

Stage 9 does not reset or reinterpret them.

An unchanged candidate may be resubmitted.

It still produces:

new TargetFinalizationRequest
new TaskCheckpoint
new Stage 7 evaluation

If the same defect remains, the new evaluator may produce equivalent findings again.

Recurring findings remain distinct immutable evaluation records tied to distinct candidate rounds.

Repair termination is enforced through existing execution budgets, including max_repair_cycles, rather than a new finding-repetition counter.

⸻

New finalization after repair

Repair returns the target to ordinary worker execution.

When the worker believes the repaired candidate is ready, it uses the existing Stage 6 finalization interface.

Stage 6 creates:

new TargetFinalizationRequest
new immutable TaskCheckpoint

The previous rejected checkpoint is never reused or mutated.

The new checkpoint identifies the exact repaired candidate submitted for evaluation.

⸻

Mandatory Stage 7 re-entry

Every repaired candidate must pass hard validation again.

The required path is always:

REPAIR
    ↓
normal worker execution
    ↓
new finalization request
    ↓
new TaskCheckpoint
    ↓
VALIDATING

A target rejected by Stage 8 must not return directly to Stage 8 after repair.

Even if the previous candidate passed hard validation, any worker mutation creates a new candidate whose mechanical validity must be established again.

Therefore:

new candidate
    → Stage 7
    → Stage 8 only after Stage 7 PASS

is invariant.

⸻

Stage 10 boundary

Stage 9 never accepts a target.

The only path toward target acceptance after repair is:

repair
    ↓
new finalization
    ↓
Stage 7 PASS
    ↓
Stage 8 PASS
    ↓
Stage 10 — Target Acceptance

Stage 9 does not:

set ACCEPTED
create an accepted target result
define acceptance provenance
bypass validation or review

Target acceptance remains exclusively downstream.

⸻

Locked invariants

1. Repair continues the same target task.
2. REPAIR is a durable non-executing phase awaiting normal scheduling.
3. Stage 2 exclusively owns REPAIR → SCHEDULED.
4. Stage 3 hydrates repair through the existing WorkerContext with mode = REPAIR.
5. Stage 4 uses the same worker, permissions, tools, and workspace mechanisms for normal and repair execution.
6. No separate repair agent, repair context, repair task, repair workspace, or repair loop exists in V0.
7. Target identity, source binding, workspace identity, configured budget, and accumulated usage never reset during repair.
8. Historical candidates, checkpoints, reports, verdicts, and findings are immutable.
9. open_finding_refs contains the current unresolved finding projection, not duplicated evaluation history.
10. The worker cannot mutate or declare evaluator findings resolved.
11. Each evaluation origin supersedes or clears only its own current finding projection.
12. Review findings remain unresolved until a later Stage 8 verdict evaluates a repaired candidate.
13. Hard-validation and target-review findings may therefore coexist temporarily.
14. Repair normally begins from the exact candidate that produced the current findings.
15. A pre-repair checkpoint/workspace mismatch is a persistence/recovery integrity failure, not a semantic repair action.
16. The rejected checkpoint remains immutable while the current workspace becomes mutable again during worker execution.
17. Completion-state changes during repair use the existing completion-state operation.
18. Terminal completion states may change to another permitted terminal state; they do not revert to uninvestigated.
19. Stage 9 itself consumes no execution usage.
20. repair_cycles increments once for each actual repair-mode worker execution at HYDRATING → WORKING.
21. A fresh recovery worker execution may consume an additional repair cycle if the previous execution was already consumed.
22. Hard-validation and target-review repair share the same repair-cycle budget.
23. Repair receives no special scheduling or concurrency policy.
24. Provider/runtime failures are handled through Stage 5 recovery and do not become semantic repair findings.
25. Stage 9 introduces no new V0 no-progress or repeated-failure mechanism.
26. Every repaired submission creates a new finalization request and immutable candidate checkpoint.
27. Every repaired candidate must pass Stage 7 again.
28. Stage 8 independently reviews the new candidate after Stage 7 PASS.
29. Stage 9 never produces an accepted target.
