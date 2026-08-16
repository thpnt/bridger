# Stage 2 — Scheduling

## 1. Responsibility

Stage 2 is the deterministic runtime admission-control stage for target execution.

Its boundary is:

```text
Stage 1
initialized fleet/task state
        ↓
Stage 2
derive execution eligibility
apply dependencies, budgets and concurrency
schedule target executions
        ↓
Stage 3
hydrate scheduled targets
```

Stage 1 has already materialized the complete fleet and target state: immutable `TargetTaskSpec` objects with resolved dependency task IDs, mutable `TargetTaskState` objects in `INITIALIZED`, zeroed usage, and corresponding `TargetCompletionState` objects. Stage 2 consumes this initialized state without rerunning activation, dependency resolution, or target instantiation.

Stage 2 owns:

* target scheduling eligibility;
* explicit dependency evaluation;
* target and fleet budget eligibility for another execution cycle;
* bounded target concurrency;
* deterministic target selection when capacity is limited;
* admission of first-start and repair executions;
* the `INITIALIZED → SCHEDULED` and `REPAIR → SCHEDULED` target transitions;
* dependency-caused `BLOCKED` transitions for otherwise schedulable targets;
* target budget-caused `EXHAUSTED` transitions for otherwise schedulable targets;
* `FleetRunState.phase: INITIALIZED → RUNNING` when execution is first admitted;
* recognition of a terminal fleet no-progress state when no execution can continue.

Stage 2 does **not** own:

* target activation or initialization;
* `WorkerContext`;
* context hydration or prompt construction;
* worker/model execution;
* repository navigation;
* candidate artifact or evidence mutation;
* completion-state mutation;
* trace/event design;
* checkpoint restoration or recovery;
* finalization;
* hard validation;
* target review;
* repair finding generation;
* target acceptance;
* fleet hard validation;
* fleet reconciliation;
* fleet acceptance.

Stage 3 owns `SCHEDULED → HYDRATING`. The wider stage map and authority boundaries remain unchanged.

---

## 2. Existing contracts consumed

Stage 2 uses only already-locked core contracts and lifecycle types:

```text
MemoryFleetSpec
FleetRunState

TargetTaskSpec × N
TargetTaskState × N

ExecutionBudget
ExecutionUsage

TargetPhase
FleetPhase
```

`MemoryFleetSpec` provides:

* the immutable fleet identity;
* immutable source binding;
* activated target ordering;
* `fleet_budget`;
* `max_concurrent_targets`.

`FleetRunState` provides:

* authoritative fleet phase;
* fleet-level `ExecutionUsage`;
* references to the instantiated target tasks.

`TargetTaskSpec` provides:

* target identity;
* target budget;
* resolved `depends_on_target_task_ids`.

`TargetTaskState` provides:

* authoritative target phase;
* target-level `ExecutionUsage`.

The locked phase vocabulary and budget/usage contracts are reused without modification.

`TargetCompletionState` is **not consulted by Stage 2**. Semantic completion is not a scheduling predicate and Stage 2 never mutates completion state.

**No locked core contract changes are introduced by Stage 2.**

---

## 3. Scheduling model

V0 scheduling consists of:

```text
existing immutable specifications
+
existing mutable fleet/target states
+
deterministic scheduling policy
+
one scheduling interface
```

Stage 2 introduces:

```text
no SchedulerState
no persisted runnable flag
no scheduler queue
no lease state
no scheduling-attempt object
no scheduling decision artifact
no scheduler-owned semantic state
```

The following are derived views and are never persisted as independent authorities:

* runnable;
* newly startable;
* repair-ready;
* waiting on dependencies;
* dependency-blocked;
* available concurrency;
* active-target count;
* remaining budget;
* scheduling order.

`TargetTaskState.phase` remains the sole target lifecycle authority. `FleetRunState.phase` remains the sole fleet lifecycle authority.

`SCHEDULED` itself is the durable admission marker. No parallel scheduling record is required.

---

## 4. Runnable-target selection

### 4.1 Schedulable source phases

Stage 2 may admit target execution only from:

```text
INITIALIZED
REPAIR
```

They have distinct meanings:

```text
INITIALIZED
    → first worker execution

REPAIR
    → another worker execution of the same target task
      after structured repair findings already exist
```

No new target task or attempt identity is created for repair.

### 4.2 Active phases

Targets in:

```text
SCHEDULED
HYDRATING
WORKING
FINALIZING
VALIDATING
REVIEWING
```

are already in flight.

They are never selected again by Stage 2.

### 4.3 Non-runnable phases

Targets in:

```text
ACCEPTED
BLOCKED
EXHAUSTED
FAILED
STOPPED
```

are not schedulable.

`ACCEPTED` is successful non-runnability. The other values are unsuccessful terminal side exits for the current target lifecycle.

Stage 2 never moves any of these targets back into execution.

### 4.4 Eligibility in principle

A target is **execution-eligible in principle** when all of the following hold:

1. its phase is `INITIALIZED` or `REPAIR`;
2. the fleet phase permits target scheduling;
3. every explicit dependency is satisfied;
4. its target budget permits another execution cycle;
5. the fleet budget permits another execution cycle.

For ordinary target scheduling, the fleet phase must be:

```text
INITIALIZED
or
RUNNING
```

Stage 2 does not schedule while the fleet is:

```text
VALIDATING
REVIEWING
REPAIRING
ACCEPTED
BLOCKED
EXHAUSTED
FAILED
STOPPED
```

A fleet-level repair/reopening mechanism must return the fleet to `RUNNING` before normal Stage 2 scheduling resumes.

### 4.5 Runnable now

An execution-eligible target is **runnable now** when a target concurrency slot is also available.

Therefore:

```text
execution eligibility
+
available concurrency
=
runnable now
```

Lack of capacity does not change the target lifecycle phase.

### 4.6 Derived categories

The following classifications are useful derived concepts only:

```text
newly startable
    phase = INITIALIZED
    and otherwise execution-eligible

repair-ready
    phase = REPAIR
    and otherwise execution-eligible

temporarily waiting
    dependency is still progressing
    or no concurrency slot is available

terminally non-runnable
    ACCEPTED / BLOCKED / EXHAUSTED / FAILED / STOPPED
```

Runnable eligibility is always derived from authoritative specifications and state. It is never persisted.

---

## 5. Dependency handling

### 5.1 Dependency authority

The only scheduling dependencies are:

```text
TargetTaskSpec.depends_on_target_task_ids
```

Stage 1 has already resolved semantic target dependencies into concrete target-task IDs.

Stage 2 must not:

* infer dependencies from target semantics;
* infer dependencies from artifact links;
* infer dependencies from worker behavior;
* infer dependencies from repository structure;
* create implicit ordering between otherwise independent targets.

Targets remain independent by default.

### 5.2 Satisfied dependency

A dependency is satisfied **only** when the referenced target is:

```text
ACCEPTED
```

A dependency is not satisfied merely because it:

* completed worker execution;
* requested finalization;
* passed hard validation;
* entered review;
* reached some other terminal state.

`ACCEPTED` is the only successful dependency-satisfaction phase.

### 5.3 Dependency still progressing

If any dependency is in:

```text
INITIALIZED
SCHEDULED
HYDRATING
WORKING
FINALIZING
VALIDATING
REVIEWING
REPAIR
```

the dependent target is temporarily waiting.

Its own phase remains unchanged:

```text
INITIALIZED
or
REPAIR
```

Temporary dependency waiting is **not** represented as `BLOCKED`.

### 5.4 Dependency terminal failure

If a required dependency is in:

```text
BLOCKED
EXHAUSTED
FAILED
STOPPED
```

the dependency cannot satisfy the prerequisite through ordinary continuation.

An otherwise schedulable dependent target transitions:

```text
INITIALIZED → BLOCKED
REPAIR      → BLOCKED
```

Dependency blocking may propagate through dependency chains.

Example:

```text
A FAILED
↓
B depends on A → BLOCKED
↓
C depends on B → BLOCKED
```

### 5.5 `BLOCKED` semantics

Dependency-caused `BLOCKED` means:

> The target cannot execute because an explicitly declared prerequisite target cannot reach the required `ACCEPTED` state through the current lifecycle.

`BLOCKED` is terminal for Stage 2. Stage 2 never performs:

```text
BLOCKED → SCHEDULED
```

If a later lifecycle mechanism ever explicitly reopens a blocked target, that mechanism must first move the target into a schedulable phase such as `REPAIR`; such reopening is outside Stage 2.

---

## 6. Concurrency semantics

### 6.1 Meaning of `max_concurrent_targets`

`MemoryFleetSpec.max_concurrent_targets` is the maximum number of target executions admitted into their local target pipeline at the same time.

A slot represents an **in-flight target execution**, not merely a currently executing model call.

### 6.2 Slot-occupying phases

A target consumes one concurrency slot while in:

```text
SCHEDULED
HYDRATING
WORKING
FINALIZING
VALIDATING
REVIEWING
```

This includes local hard validation and local target review. They are part of the same admitted target execution.

### 6.3 Non-slot phases

These phases do not consume a concurrency slot:

```text
INITIALIZED
REPAIR
ACCEPTED
BLOCKED
EXHAUSTED
FAILED
STOPPED
```

In particular:

* `REPAIR` waits for readmission;
* accepted targets consume no slot;
* terminal unsuccessful targets consume no slot.

### 6.4 Available capacity

Available target capacity is derived as:

```text
active_target_count =
    number of targets whose phase is one of:
    SCHEDULED
    HYDRATING
    WORKING
    FINALIZING
    VALIDATING
    REVIEWING

available_slots =
    max_concurrent_targets - active_target_count
```

Available capacity cannot be negative in valid runtime state.

### 6.5 Admission count

One scheduler pass may schedule at most:

```text
min(
    number of runnable candidates,
    available_slots,
    applicable remaining hard budget capacity
)
```

Only newly selected targets are transitioned to `SCHEDULED`.

Already active targets are counted for capacity but are not returned as newly scheduled work.

### 6.6 Deterministic ordering

When more runnable targets exist than available capacity, Stage 2 selects targets using the immutable target ordering in:

```text
MemoryFleetSpec.target_ids
```

A target task's position is the position of its `TargetTaskSpec.target_id` in that frozen list.

The same ordering applies to first-start and repair candidates.

V0 introduces no:

* priority score;
* repair priority;
* aging;
* fairness cursor;
* round-robin history;
* work stealing;
* scheduler history state.

Given identical authoritative input state, scheduling selection must be deterministic.

### 6.7 Provider-specific concurrency

Provider/model-specific semaphores, adaptive rate limiting, dynamic throttling, and provider retry/backoff are not part of the Stage 2 V0 scheduling contract.

`max_concurrent_targets` is the only fleet scheduling-concurrency contract defined here.

---

## 7. Target start and resume rules

### 7.1 First start

A target starts for the first time through:

```text
INITIALIZED
    ↓ Stage 2
SCHEDULED
```

It must satisfy all dependency, budget, fleet-phase, and concurrency requirements before this transition.

### 7.2 Repair re-entry

A target that has entered semantic repair re-enters worker execution through:

```text
REPAIR
    ↓ Stage 2
SCHEDULED
```

This is the same target task.

Repair does not create:

* a new `TargetTaskSpec`;
* a new `target_task_id`;
* a fresh budget;
* a separate scheduling identity.

### 7.3 Meaning of `SCHEDULED`

`SCHEDULED` means:

> The runtime has admitted this target into active execution and reserved one target-concurrency slot, but Stage 3 has not yet hydrated its worker context.

The concurrency slot is reserved at the moment the transition to `SCHEDULED` occurs.

This prevents duplicate admission or oversubscription between scheduler passes.

### 7.4 Hydration boundary

Stage 2 owns:

```text
INITIALIZED → SCHEDULED
REPAIR      → SCHEDULED
```

Stage 3 owns:

```text
SCHEDULED → HYDRATING
```

Stage 2 does not compile or inspect `WorkerContext`.

### 7.5 Recovery is not scheduling

Crash/process/checkpoint recovery is distinct from repair re-entry.

A recovered target already in:

```text
SCHEDULED
HYDRATING
WORKING
FINALIZING
VALIDATING
REVIEWING
```

is already in flight and must not be scheduled again.

Recovery and checkpoint validation belong to Stage 5.

If recovery returns a target to `REPAIR`, normal Stage 2 admission applies from that point.

Stage 2 never guesses a recovery phase from incomplete state.

---

## 8. Budget eligibility and exhaustion

Stage 2 uses the existing:

```text
ExecutionBudget
ExecutionUsage
```

contracts at both target and fleet scope. The existing budget design uses the same monotonic counters for fleet and target execution and explicitly does not reset target budget during repair.

### 8.1 Budget scopes

Target-level eligibility compares:

```text
TargetTaskSpec.budget
against
TargetTaskState.usage
```

Fleet-level eligibility compares:

```text
MemoryFleetSpec.fleet_budget
against
FleetRunState.usage
```

Both scopes must permit another worker execution.

### 8.2 Remaining budget

For a bounded budget dimension:

```text
remaining = limit - current_usage
```

A dimension has no remaining capacity when:

```text
current_usage >= limit
```

Optional token limits with value `None` impose no scheduling restriction for that dimension.

Stage 2 does not reset, replenish, or mutate configured budget limits.

### 8.3 Limits checked before scheduling

Before admitting another worker execution, Stage 2 checks remaining target and fleet capacity for:

```text
max_cycles
max_model_calls
max_tool_calls
max_input_tokens       when configured
max_output_tokens      when configured
```

For a target in `REPAIR`, Stage 2 additionally checks:

```text
max_repair_cycles
```

at both applicable target and fleet scope.

`max_repair_cycles` does not affect first admission from `INITIALIZED`.

### 8.4 Budget eligibility rule

A candidate cannot be scheduled when any required applicable budget dimension has already reached its hard limit.

Examples:

```text
cycles == max_cycles
→ no further worker cycle

model_calls == max_model_calls
→ no further worker cycle

tool_calls == max_tool_calls
→ no further worker cycle

input_tokens >= max_input_tokens
→ no further worker cycle when the limit is configured

output_tokens >= max_output_tokens
→ no further worker cycle when the limit is configured

REPAIR and repair_cycles == max_repair_cycles
→ no further repair execution
```

Stage 2 evaluates the current authoritative counters. It does not predict future consumption.

### 8.5 What Stage 2 does not predict

Stage 2 does not attempt to determine:

* how many model calls the next cycle will require;
* how many tool calls the next cycle will require;
* the exact tokens a future call will consume;
* whether the remaining budget is sufficient to complete the entire target;
* whether a repair cycle will succeed.

Positive remaining headroom permits admission; exact execution-time limits remain enforced when usage is actually consumed.

### 8.6 Usage accounting

Stage 2 does not itself charge model/tool/token usage merely because a target becomes `SCHEDULED`.

It reads the existing authoritative usage and admits execution.

Actual execution stages own incrementing usage at the corresponding consumption boundaries.

The scheduler must nevertheless avoid knowingly admitting more cycles than a hard remaining fleet cycle/repair capacity permits in the current pass.

### 8.7 Target exhaustion

If a target is in:

```text
INITIALIZED
or
REPAIR
```

and its **own target budget** makes another worker execution impossible, Stage 2 transitions it to:

```text
EXHAUSTED
```

Its existing:

* candidate artifacts;
* completion state;
* evidence references;
* findings;
* usage;

remain intact.

Repair always consumes the remaining original target budget. Budgets never reset.

### 8.8 Fleet budget exhaustion

Fleet budget exhaustion does not automatically change unfinished targets to target-level `EXHAUSTED`.

If fleet-wide budget prevents admitting further work:

* no new targets are scheduled;
* individually valid target budgets remain unchanged.

If active targets still exist, the fleet remains `RUNNING` while that already-admitted work progresses.

The fleet becomes `EXHAUSTED` when:

```text
fleet-wide budget prevents any required further execution
AND
no active target remains capable of progressing the fleet
AND
the fleet is not ready to proceed to fleet validation
```

Target-level `EXHAUSTED` therefore means target budget exhaustion.

Fleet-level `EXHAUSTED` means fleet budget exhaustion or an irrecoverable no-progress fleet whose root unsuccessful condition is exhaustion.

---

## 9. Fleet-level scheduling behavior

### 9.1 Initial execution

A valid initialized fleet begins with:

```text
FleetRunState.phase = INITIALIZED
```

The first scheduler pass that successfully admits at least one target performs:

```text
FleetRunState.phase:
INITIALIZED → RUNNING
```

The transition occurs with the first successful target scheduling admission.

### 9.2 Runnable work and available slots

When at least one target is runnable and capacity is available:

* Stage 2 schedules up to available concurrency and budget capacity;
* selected targets transition to `SCHEDULED`;
* the fleet remains `RUNNING` after initial admission.

### 9.3 All slots occupied

If execution-eligible targets exist but every concurrency slot is already occupied:

```text
no new target is scheduled
fleet remains RUNNING
waiting target phases remain unchanged
```

This is a normal scheduler outcome.

### 9.4 Waiting on dependencies

If no candidate can currently run because one or more required dependencies are still progressing:

```text
no new target is scheduled
waiting target phases remain unchanged
fleet remains RUNNING
```

Temporary dependency waiting is not a fleet `BLOCKED` condition while another target can still satisfy the dependency.

### 9.5 No currently runnable target

An empty scheduling result is not itself a terminal condition.

Stage 2 distinguishes:

```text
no target runnable now
```

from:

```text
no target can ever become runnable through current execution
```

The former is a normal waiting/capacity condition.

### 9.6 Terminal no-progress fleet

A fleet has reached a terminal scheduling no-progress condition when all of the following are true:

```text
no active targets exist
no runnable target exists
no waiting dependency can still become ACCEPTED
not all required targets are ACCEPTED
```

At that point, the fleet terminal phase represents the root unsuccessful condition.

The deterministic V0 precedence is:

```text
required FAILED exists
    → FleetPhase.FAILED

else required EXHAUSTED exists
     or fleet-wide execution budget is exhausted
    → FleetPhase.EXHAUSTED

else required STOPPED exists
    → FleetPhase.STOPPED

else remaining unfinished required targets are BLOCKED
    → FleetPhase.BLOCKED
```

Dependency propagation may therefore produce blocked descendants without hiding the originating `FAILED`, `EXHAUSTED`, or `STOPPED` root cause.

A sibling failure does not immediately terminate the fleet while unrelated work remains active, runnable, or capable of becoming runnable.

### 9.7 All targets locally accepted

When all required targets are locally:

```text
ACCEPTED
```

Stage 2 schedules nothing.

Stage 2 does **not** perform:

```text
FleetRunState.phase = ACCEPTED
```

and does not perform fleet hard validation or reconciliation.

The fleet remains at the scheduling-stage boundary until Stage 11 takes control and performs the transition into fleet hard validation.

Fleet acceptance remains exclusively behind:

```text
Stage 11 — Fleet hard validation
Stage 12 — Fleet reconciliation
Stage 13 — Fleet acceptance
```

---

## 10. Scheduling interface

Stage 2 exposes one scheduling interface.

### Name

```text
schedule_runnable_targets
```

Conceptual contract:

```text
schedule_runnable_targets(
    MemoryFleetSpec,
    FleetRunState,
    TargetTaskSpec × N,
    TargetTaskState × N,
)
    → list[target_task_id]
```

No scheduling result wrapper is introduced.

### Responsibility

Deterministically evaluate current fleet scheduling state, apply dependency/budget/concurrency policy, transition newly admitted targets to `SCHEDULED`, and return the concrete target task IDs admitted by this scheduler pass.

### Inputs

```text
MemoryFleetSpec
FleetRunState
all TargetTaskSpec objects referenced by the fleet
all corresponding TargetTaskState objects
```

The interface operates only on the exact initialized fleet bound to the same `fleet_run_id`.

### Reads

The scheduler reads:

From `MemoryFleetSpec`:

```text
fleet_run_id
target_ids
fleet_budget
max_concurrent_targets
```

From `FleetRunState`:

```text
fleet_run_id
phase
target_task_ids
usage
```

From `TargetTaskSpec`:

```text
target_task_id
fleet_run_id
target_id
budget
depends_on_target_task_ids
```

From `TargetTaskState`:

```text
target_task_id
fleet_run_id
phase
usage
```

It does not read semantic completion state, generated knowledge contents, evidence, findings contents, prompts, traces, or repository data.

### Transformation

The interface performs, in deterministic order:

```text
1. validate fleet/spec/state identity and structural consistency
2. inspect explicit dependency states
3. transition dependency-impossible INITIALIZED/REPAIR targets to BLOCKED
4. transition target-budget-ineligible INITIALIZED/REPAIR targets to EXHAUSTED
5. count currently occupied concurrency slots
6. derive remaining INITIALIZED/REPAIR execution candidates
7. apply fleet budget eligibility
8. order candidates by MemoryFleetSpec.target_ids
9. select up to remaining concurrency and applicable budget capacity
10. transition selected targets to SCHEDULED
11. transition fleet INITIALIZED → RUNNING when first work is admitted
12. when applicable, derive a terminal fleet no-progress phase
13. return newly scheduled target_task_ids
```

### Mutations

Stage 2 may mutate only the scheduling-relevant lifecycle state defined by this document.

Target mutations:

```text
INITIALIZED → SCHEDULED
REPAIR      → SCHEDULED

INITIALIZED → BLOCKED
REPAIR      → BLOCKED

INITIALIZED → EXHAUSTED
REPAIR      → EXHAUSTED
```

Fleet mutations:

```text
INITIALIZED → RUNNING

RUNNING → FAILED
RUNNING → EXHAUSTED
RUNNING → STOPPED
RUNNING → BLOCKED
```

The latter transitions occur only for a provable terminal fleet no-progress condition.

Stage 2 does not mutate:

* `TargetCompletionState`;
* candidate artifacts;
* evidence;
* findings;
* source bindings;
* immutable specs;
* accepted results;
* checkpoints;
* trace contents;
* model/provider state.

### Output

The return value is:

```text
list[target_task_id]
```

containing only target tasks newly transitioned to `SCHEDULED` during that call.

The list is in deterministic scheduling order.

Already active targets are not returned.

An empty list is valid.

### Failure behavior

The interface fails on invalid or corrupt authoritative state, including:

* missing `TargetTaskSpec` or `TargetTaskState` referenced by the fleet;
* duplicate target task identities;
* target state/spec identity mismatch;
* fleet-run identity mismatch;
* dependency reference outside the fleet;
* dependency reference to a nonexistent task;
* self-dependency or dependency cycle surviving initialization;
* source/spec incompatibility that violates already-locked core invariants;
* impossible or malformed scheduling configuration;
* inconsistent state that would make deterministic scheduling unsafe.

These are invariant/configuration failures, not scheduling outcomes.

Budget exhaustion, dependency blocking, waiting, lack of capacity, and an empty runnable set are not exceptions.

### Side effects

The interface has no side effects beyond the authoritative runtime state mutations listed above.

It does not:

* hydrate context;
* invoke models;
* invoke repository tools;
* mutate target artifacts;
* restore checkpoints;
* create queue records;
* create leases;
* create scheduling artifacts.

---

## 11. Stage 2 state transitions

### Target transitions owned by Stage 2

| From          | To          | Condition                                                                                                                                  |
| ------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `INITIALIZED` | `SCHEDULED` | Dependencies accepted, target/fleet budgets eligible, fleet schedulable, concurrency available, target selected                            |
| `REPAIR`      | `SCHEDULED` | Dependencies accepted, target/fleet budgets including repair allowance eligible, fleet schedulable, concurrency available, target selected |
| `INITIALIZED` | `BLOCKED`   | At least one explicit dependency is `BLOCKED`, `EXHAUSTED`, `FAILED`, or `STOPPED`                                                         |
| `REPAIR`      | `BLOCKED`   | At least one explicit dependency is `BLOCKED`, `EXHAUSTED`, `FAILED`, or `STOPPED`                                                         |
| `INITIALIZED` | `EXHAUSTED` | Target's own remaining budget cannot permit another worker execution                                                                       |
| `REPAIR`      | `EXHAUSTED` | Target's own remaining budget or repair allowance cannot permit another repair execution                                                   |

### Fleet transitions owned by Stage 2

| From          | To          | Condition                                                                                                 |
| ------------- | ----------- | --------------------------------------------------------------------------------------------------------- |
| `INITIALIZED` | `RUNNING`   | At least one target is successfully transitioned to `SCHEDULED`                                           |
| `RUNNING`     | `FAILED`    | Terminal fleet no-progress and required failed work is the root unsuccessful condition                    |
| `RUNNING`     | `EXHAUSTED` | Terminal fleet no-progress caused by required target or fleet budget exhaustion                           |
| `RUNNING`     | `STOPPED`   | Terminal fleet no-progress caused by required stopped work and no stronger failure/exhaustion root exists |
| `RUNNING`     | `BLOCKED`   | Terminal fleet no-progress and remaining unfinished required work is blocked                              |

Stage 2 may inspect but does not transition targets out of:

```text
SCHEDULED
HYDRATING
WORKING
FINALIZING
VALIDATING
REVIEWING
ACCEPTED
BLOCKED
EXHAUSTED
FAILED
STOPPED
```

Stage 2 does not own target transitions into:

```text
HYDRATING
WORKING
FINALIZING
VALIDATING
REVIEWING
REPAIR
ACCEPTED
FAILED
STOPPED
```

except that `REPAIR` is consumed as a scheduling source phase.

Stage 2 does not transition the fleet into or out of:

```text
VALIDATING
REVIEWING
REPAIRING
ACCEPTED
```

and never transitions a terminal fleet phase back to `RUNNING`.

---

## 12. Invariants

1. Stage 2 operates only on one fully initialized fleet produced by Stage 1.
2. `MemoryFleetSpec`, `TargetTaskSpec`, and their source bindings remain immutable.
3. Every `FleetRunState.target_task_id` must resolve to exactly one `TargetTaskSpec` and one `TargetTaskState`.
4. Every target spec/state processed by the scheduler must belong to the same `fleet_run_id`.
5. Exactly one target task exists per activated `(fleet_run_id, target_id)`.
6. Stage 2 never creates another target task for first start, repair, or recovery.
7. `TargetTaskState.phase` remains the sole target lifecycle authority.
8. `FleetRunState.phase` remains the sole fleet lifecycle authority.
9. Runnable eligibility is derived and never persisted.
10. No `SchedulerState`, queue, lease, runnable flag, or parallel scheduling authority exists in V0.
11. Only `INITIALIZED` and `REPAIR` may be admitted by Stage 2.
12. A target already in `SCHEDULED` or another active phase is never scheduled twice.
13. `SCHEDULED` reserves one target-concurrency slot immediately.
14. The number of slot-occupying target phases must never exceed `MemoryFleetSpec.max_concurrent_targets`.
15. Concurrency availability is derived from current target phases; no separate slot counter is authoritative.
16. Scheduling order is deterministic and follows `MemoryFleetSpec.target_ids`.
17. No fairness, priority, aging, or scheduling-history state changes that ordering.
18. Dependencies influence scheduling only through `TargetTaskSpec.depends_on_target_task_ids`.
19. No semantic or implicit dependencies may be inferred.
20. A dependency is satisfied only by `TargetPhase.ACCEPTED`.
21. A dependency still capable of reaching `ACCEPTED` causes waiting, not `BLOCKED`.
22. A terminal unsuccessful dependency causes an otherwise schedulable dependent target to become `BLOCKED`.
23. Stage 2 never reopens `BLOCKED`, `EXHAUSTED`, `FAILED`, `STOPPED`, or `ACCEPTED` targets.
24. Sibling target failure does not cancel or rerun unrelated active, runnable, or accepted targets.
25. An accepted target is never rerun merely because another target fails.
26. Target budget eligibility is evaluated against `TargetTaskSpec.budget` and `TargetTaskState.usage`.
27. Fleet budget eligibility is evaluated against `MemoryFleetSpec.fleet_budget` and `FleetRunState.usage`.
28. Budget and usage contracts are not reset during repair.
29. `REPAIR` additionally requires remaining repair-cycle allowance.
30. Stage 2 does not predict future token/tool/model consumption.
31. Stage 2 does not mark a target `EXHAUSTED` solely because the fleet-wide budget is exhausted.
32. Target-level `EXHAUSTED` preserves current artifacts, evidence, findings, completion state, and usage.
33. `TargetCompletionState` is neither read as a scheduling predicate nor mutated by Stage 2.
34. Stage 2 does not inspect repository content or generated artifact contents.
35. Stage 2 never performs `SCHEDULED → HYDRATING`.
36. Recovery never occurs implicitly by rescheduling an already active target.
37. An empty scheduler result does not imply fleet failure.
38. Temporary lack of concurrency capacity does not alter target or fleet terminal state.
39. Temporary dependency waiting does not alter target or fleet terminal state.
40. Fleet terminal scheduling state is entered only when no active/runnable/future-unblocked execution can still make progress.
41. Stage 2 never performs fleet hard validation, fleet reconciliation, or fleet acceptance.
42. All locally accepted targets is a handoff condition to Stage 11, not a Stage 2 acceptance transition.
43. Stage 2 introduces no mutation of upstream repository, graph, enrichment, or source identity state.

---

## 13. Failure and non-error outcomes

### Errors / exceptions

The following are invalid runtime conditions and must fail scheduling rather than be silently repaired:

```text
fleet/spec/state identity mismatch
missing target spec/state
duplicate target task identity
dependency reference outside the fleet
dependency reference to missing target
dependency cycle surviving Stage 1
self-dependency surviving Stage 1
malformed max_concurrent_targets
invalid lifecycle/state combination
source/spec incompatibility
other violation of locked core or Stage 1 invariants
```

Stage 2 does not reconstruct or reinterpret corrupt state.

### Normal scheduler outcomes

The following are **not errors**:

```text
no target currently runnable
all concurrency slots occupied
dependency still progressing
target dependency permanently failed
target budget exhausted
fleet budget unable to admit more work
all targets already active
all targets locally accepted
terminally non-runnable fleet
```

Their behavior is:

| Condition                                                          | Outcome                                                |
| ------------------------------------------------------------------ | ------------------------------------------------------ |
| No currently runnable target, but future progress remains possible | Return no newly scheduled IDs; preserve phases         |
| No free concurrency slot                                           | Return no newly scheduled IDs; preserve waiting phases |
| Dependency still progressing                                       | Dependent remains `INITIALIZED`/`REPAIR`               |
| Dependency terminally unsuccessful                                 | Dependent becomes `BLOCKED`                            |
| Target budget cannot permit another cycle                          | Target becomes `EXHAUSTED`                             |
| Fleet budget cannot admit new work but active work exists          | Schedule nothing further; fleet remains `RUNNING`      |
| Fleet has no possible further progress                             | Transition fleet to the appropriate terminal phase     |
| All required targets are locally `ACCEPTED`                        | Schedule nothing; hand control to Stage 11             |

Ordinary absence of runnable work is therefore never treated as an exception by itself.

---

## 14. Explicitly deferred items

The following are intentionally outside Stage 2.

### Stage 3 — Context hydration

Deferred:

```text
WorkerContext
context compiler
context selection
prompt assembly
token estimation for compiled context
SCHEDULED → HYDRATING
```

### Stage 4 — Worker cycle

Deferred:

```text
model execution
provider conversation handling
repository tool loop
worker tool permissions
artifact mutation
evidence recording
completion-state updates
working-summary updates
exact execution-cycle accounting
model/tool/token usage increments
```

### Stage 5 — Persistence and recovery

Deferred:

```text
trace/event schema
checkpoint schema
checkpoint creation
checkpoint validation
process-crash recovery
safe-phase restoration
resume from durable state
atomic persistence mechanics
```

Stage 2 only ensures that recovered active work is not scheduled twice.

### Stage 6 — Finalization

Deferred:

```text
TargetFinalizationRequest
finalization control
FINALIZING semantics beyond concurrency occupancy
```

### Stage 7 — Hard validation

Deferred:

```text
validation contracts
hard-gate policy
validation findings
```

### Stage 8 — Target review

Deferred:

```text
review context
reviewer invocation
review verdict
review findings
```

### Stage 9 — Repair

Deferred:

```text
finding generation
repair-context construction
exact repair-cycle accounting point
reopening decisions
```

Stage 2 only admits a target that is already authoritatively in `REPAIR`.

### Stage 10 — Target acceptance

Deferred:

```text
accept_target
AcceptedTargetResult
ACCEPTED transition policy
```

### Stages 11–13 — Fleet completion

Deferred:

```text
fleet hard validation
fleet validation reports/findings
fleet reconciliation
fleet reopening decisions
fleet review
AcceptedMemoryFleetResult
fleet acceptance
```

### Runtime/provider policies

Deferred:

```text
provider-specific semaphores
adaptive rate limiting
provider retry/backoff
transient model/provider failure handling
dynamic model allocation
cost-based scheduling
```

### Distributed scheduling machinery

Not introduced for V0:

```text
distributed scheduler service
persistent work queue
worker leases
heartbeats
distributed locks
work stealing
scheduler leadership
cross-process scheduling protocol
```

Any future distributed execution model must preserve the Stage 2 semantics defined here rather than introduce a second lifecycle or scheduling authority.
