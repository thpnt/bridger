# Core states and contracts

```text
MemoryFleetSpec
│
├── FleetRunState
│     └── references TargetTaskState × N
│
└── TargetTaskSpec × N
      │
      └── TargetTaskState
            │
            └── TargetCompletionState
                  └── CompletionItemState × N

Alongside, but not embedded:
- candidate knowledge artifacts
- evidence records
- findings/reports
- trace events
- checkpoints
- accepted results
```

This preserves the hierarchy already established in `agentic-contracts.md`: immutable run definition → shallow fleet state → immutable task assignment → operational task state → logically distinct semantic completion state. 

## 1. Shared supporting types

I would keep the supporting vocabulary this small for V0.

```python
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class CompletionStatus(StrEnum):
    UNINVESTIGATED = "uninvestigated"
    COVERED = "covered"
    NOT_APPLICABLE = "not-applicable"
    UNKNOWN = "unknown"


class TargetPhase(StrEnum):
    INITIALIZED = "initialized"
    SCHEDULED = "scheduled"
    HYDRATING = "hydrating"
    WORKING = "working"
    FINALIZING = "finalizing"
    VALIDATING = "validating"
    REVIEWING = "reviewing"
    REPAIR = "repair"

    ACCEPTED = "accepted"

    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"
    FAILED = "failed"
    STOPPED = "stopped"


class FleetPhase(StrEnum):
    INITIALIZED = "initialized"
    RUNNING = "running"

    VALIDATING = "validating"
    REVIEWING = "reviewing"
    REPAIRING = "repairing"

    ACCEPTED = "accepted"

    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"
    FAILED = "failed"
    STOPPED = "stopped"


class FindingOrigin(StrEnum):
    HARD_VALIDATION = "hard-validation"
    TARGET_REVIEW = "target-review"
    FLEET_VALIDATION = "fleet-validation"
    FLEET_REVIEW = "fleet-review"


class SourceBinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    repository_id: str
    repository_revision: str
    graph_snapshot_id: str
    enrichment_overlay_id: str | None = None


class ExecutionBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_cycles: PositiveInt
    max_model_calls: PositiveInt
    max_tool_calls: PositiveInt
    max_repair_cycles: PositiveInt

    # Optional because fake agents or some providers may not expose them.
    max_input_tokens: PositiveInt | None = None
    max_output_tokens: PositiveInt | None = None


class ExecutionUsage(BaseModel):
    cycles: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    repair_cycles: int = Field(default=0, ge=0)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class FindingRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    finding_id: str
    origin: FindingOrigin


class CandidateArtifactRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str
    relative_path: str
    revision: int = Field(ge=1)
    digest: str
```

### Lifecycle decision

I recommend **one lifecycle enum per runtime level**, rather than separate `phase` and `status` fields.

Otherwise states such as:

```text
phase = REVIEW
status = RUNNING
```

create two partly redundant authorities that must always remain synchronized.

The target enum directly represents the locked target path:

```text
INITIALIZED
→ SCHEDULED
→ HYDRATING
→ WORKING
→ FINALIZING
→ VALIDATING
→ REVIEWING
→ ACCEPTED
```

with `REPAIR` loops and explicit `BLOCKED / EXHAUSTED / FAILED / STOPPED` exits. This corresponds directly to the existing stage map and high-level termination design.  

`FINALIZING` is worth keeping even though it may be brief: it gives the runtime an explicit durable state between receiving the worker's finalization request and beginning validation.

---

# 2. `MemoryFleetSpec`

### Semantic definition

`MemoryFleetSpec` is the immutable definition of **one exact memory-generation run**. It is created by the fleet runtime when the upstream repository/graph authorities and run configuration are bound, and never changes afterward.

It answers:

> **What exact fleet run are we performing?**

It owns configuration and immutable identity, not execution progress. This follows the locked distinction in `agentic-contracts.md`. 

### Schema

```python
class MemoryFleetSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    fleet_run_id: str

    source: SourceBinding

    target_catalog_id: str
    target_catalog_version: str

    # Semantic target identities, e.g. "architecture", "testing".
    target_ids: list[str]

    runtime_profile_id: str
    default_worker_profile_id: str
    default_reviewer_profile_id: str
    default_permission_profile_id: str

    fleet_budget: ExecutionBudget
    default_target_budget: ExecutionBudget

    max_concurrent_targets: PositiveInt = 1

    # Runtime/private state and generated memory remain separate.
    runtime_root: str
    output_root: str
```

### Ownership / mutability

| Property   | Rule                                     |
| ---------- | ---------------------------------------- |
| Created by | `bind_memory_run` / fleet runtime        |
| Mutable by | Nobody                                   |
| Persisted  | Yes                                      |
| Lifetime   | Entire fleet run and retained provenance |
| Parent     | None                                     |
| Children   | `FleetRunState`, `TargetTaskSpec × N`    |

### Important invariants

* `fleet_run_id` uniquely identifies this execution.
* `target_ids` are unique.
* All source authorities represented by `SourceBinding` refer to compatible upstream artifacts.
* `enrichment_overlay_id`, when present, must correspond to the bound graph/source revision.
* `max_concurrent_targets >= 1`.
* Budget limits are positive.
* The spec cannot change after target initialization begins.
* `runtime_root` and `output_root` represent distinct authority domains even if their physical layout is decided later.

### Identity decision

No separate `fleet_spec_id` is needed.

```text
fleet_run_id
```

identifies both the run specification and the execution associated with it.

---

# 3. `FleetRunState`

### Semantic definition

`FleetRunState` is the authoritative **global execution state** of that fleet run. The fleet runtime creates and mutates it; workers and reviewers never do.

It answers:

> **Where is the fleet globally?**

It stays deliberately shallow: target execution details remain owned by each `TargetTaskState`. This is explicitly required by the current source of truth. 

### Schema

```python
class FleetRunState(BaseModel):
    schema_version: int = 1

    fleet_run_id: str
    phase: FleetPhase = FleetPhase.INITIALIZED

    # References only. FleetRunState does not embed TargetTaskState.
    target_task_ids: list[str] = Field(default_factory=list)

    usage: ExecutionUsage = Field(default_factory=ExecutionUsage)

    # Only unresolved fleet-level validation/reconciliation findings.
    open_finding_refs: list[FindingRef] = Field(default_factory=list)

    # Detailed errors belong to trace/error records.
    last_error_ref: str | None = None
    termination_reason: str | None = None

    # Populated only once the final immutable fleet result exists.
    accepted_result_ref: str | None = None
```

### Important design choice: no copied target phases

I would **not** persist this:

```python
targets = {
    "architecture": "working",
    "testing": "accepted",
}
```

inside `FleetRunState`.

That creates a second copy of authoritative target lifecycle state.

Instead:

```python
target_task_ids: list[str]
```

references the target executions, and the scheduler/runtime loads their `TargetTaskState` objects when it needs current phases.

For a local V0 fleet of roughly 8–9 targets, avoiding synchronization bugs is worth far more than avoiding a handful of state loads.

This still satisfies the conceptual requirement that fleet state tracks the fleet's targets without embedding their detailed state. 

### Ownership / mutability

| Property   | Rule                                            |
| ---------- | ----------------------------------------------- |
| Created by | Fleet runtime during initialization             |
| Mutable by | Fleet runtime only                              |
| Persisted  | Yes                                             |
| Lifetime   | Entire fleet run                                |
| Parent     | `MemoryFleetSpec` via `fleet_run_id`            |
| References | `TargetTaskState × N` through `target_task_ids` |

### Important invariants

* `fleet_run_id` must resolve to exactly one `MemoryFleetSpec`.
* `target_task_ids` are unique.
* Once initialization completes, they correspond exactly to instantiated target tasks for the fleet scope.
* Source identities are **not duplicated here**; they are obtained from `MemoryFleetSpec`.
* `usage` is monotonic.
* `open_finding_refs` contains only currently unresolved fleet-level findings.
* `ACCEPTED` requires:

  * all required targets locally accepted;
  * fleet hard validation passed;
  * fleet reconciliation passed.
* `accepted_result_ref` must exist iff final fleet acceptance has produced the immutable result.
* `BLOCKED`, `EXHAUSTED`, `FAILED`, and `STOPPED` are runtime-owned outcomes, never worker decisions.

### Fleet transitions

Conceptually:

```text
INITIALIZED
    ↓
RUNNING
    ↓
VALIDATING
    ↓
REVIEWING
    ↓
ACCEPTED
```

Global repair:

```text
VALIDATING / REVIEWING
    ↓ findings
REPAIRING
    ↓ affected targets reopen
RUNNING
```

The fleet remains `RUNNING` while ordinary local target validation/review/repair happens concurrently. `REPAIRING` is specifically useful for a **fleet-level reopening round**.

---

# 4. `TargetTaskSpec`

### Semantic definition

TargetTaskSpec is the immutable assignment for one instantiated target execution. The fleet runtime creates it from MemoryFleetSpec, the target catalog and exact TargetDefinition, and resolved runtime profiles.

It answers:

> **What exactly was this target assigned?**

It contains no mutable progress. The high-level design explicitly requires target identity, contract/version, source binding, profiles, permissions, budgets, and workspace to become fixed before execution. 

### Schema

```python
class TargetTaskSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    target_task_id: str
    fleet_run_id: str

    # Stable semantic catalog identity, e.g. "architecture".
    target_id: str

    target_contract_version: str

    # Immutable copy of the exact upstream binding used by this task.
    source: SourceBinding

    worker_profile_id: str
    reviewer_profile_id: str
    permission_profile_id: str

    budget: ExecutionBudget

    # Exact writable target boundary for this task.
    target_workspace: str

    # Resolved execution dependencies, normally empty for V0.
    depends_on_target_task_ids: list[str] = Field(default_factory=list)
```

### Identity structure

I recommend keeping all three IDs:

```text
fleet_run_id
target_id
target_task_id
```

They are not equivalent.

**`target_id`** is semantic and stable across runs:

```text
architecture
testing
business-logic
```

**`fleet_run_id`** identifies one memory fleet execution.

**`target_task_id`** identifies the instantiated execution of that target inside that run. This becomes the natural namespace for task state, trace, checkpoints, findings, artifacts, etc.

A good V0 rule is:

```text
one target_task_id per (fleet_run_id, target_id)
```

The ID can be generated deterministically from those two values; its textual encoding does not need to be part of the contract.

No additional execution-attempt ID is needed for V0. Repair continues the same target task.

### Source identity: copied intentionally

`TargetTaskSpec.source` should be an immutable **copy** of `MemoryFleetSpec.source`.

Normally duplication is undesirable, but here it has concrete value:

* a target task is independently resumable;
* accepted target provenance is self-contained;
* source compatibility can be mechanically checked;
* target persistence does not require reconstructing critical provenance from mutable state.

Invariant:

```python
target_spec.source == fleet_spec.source
```

By contrast, `TargetTaskState` should **not** copy these identities again.

### Ownership / mutability

| Property          | Rule                                      |
| ----------------- | ----------------------------------------- |
| Created by        | Fleet runtime during target instantiation |
| Mutable by        | Nobody                                    |
| Persisted         | Yes                                       |
| Lifetime          | Entire task/run provenance                |
| Parent            | `MemoryFleetSpec`                         |
| Mutable execution | `TargetTaskState`                         |

### Important invariants

* Immutable once created.
* `fleet_run_id` resolves to the owning fleet.
* Exactly one `TargetTaskSpec` exists per `(fleet_run_id, target_id)`.
* `source` exactly matches the owning `MemoryFleetSpec`.
* `target_id` belongs to the activated target catalog/version.
* worker/reviewer/permission profiles are resolved before execution begins.
* `target_workspace` is within the fleet's permitted output root and unique to the target.
* dependencies reference tasks in the same fleet.
* no task depends on itself.
* target budget does not reset during repair.
* TargetTaskSpec.target_contract_version must resolve to exactly one TargetDefinition.
* TargetCompletionState.items must correspond exactly to the completion obligations defined by that TargetDefinition version.
* No completion obligation may be added or removed during the target execution.

Target independence and explicit-only dependencies are already locked V0 behavior. 

---

# 5. `TargetTaskState`

### Semantic definition

`TargetTaskState` is the authoritative operational state of one target execution. It is created and mutated by the target runtime and is the main runtime object used to determine what the target may do next after a crash, context reset, validation failure, or repair.

It answers:

> **Where is this target execution now?**

It contains references to products/evidence/findings, not the product itself, and remains separate from the append-only execution trace. 

### Schema

```python
class TargetTaskState(BaseModel):
    schema_version: int = 1

    target_task_id: str
    fleet_run_id: str

    phase: TargetPhase = TargetPhase.INITIALIZED

    usage: ExecutionUsage = Field(default_factory=ExecutionUsage)

    # Compact continuation state, not generated knowledge.
    working_summary: str | None = None
    open_question_refs: list[str] = Field(default_factory=list)

    # Current candidate products/evidence are external authoritative objects.
    artifact_refs: list[CandidateArtifactRef] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)

    # Current unresolved validation/review/reconciliation feedback.
    open_finding_refs: list[FindingRef] = Field(default_factory=list)

    # Recovery / no-progress state.
    last_checkpoint_ref: str | None = None
    last_progress_signature: str | None = None
    stall_count: int = Field(default=0, ge=0)

    # Exists only around the finalization handoff when applicable.
    pending_finalization_request_ref: str | None = None

    # Detailed runtime failure belongs elsewhere.
    last_error_ref: str | None = None
    termination_reason: str | None = None

    # Preserved even if fleet reconciliation later reopens the target.
    last_accepted_result_ref: str | None = None
```

This intentionally does **not** contain:

```text
source code
generated Markdown contents
full EvidenceReference objects
validation finding contents
review finding contents
trace history
model messages
reviewer messages
repository navigation results
```

Those are different authorities.

The source documents already make this state-vs-trace/product separation explicit. 

### Findings projection

The target state should store only:

```python
open_finding_refs: list[FindingRef]
```

not copies of findings.

Example:

```python
FindingRef(
    finding_id="finding-42",
    origin=FindingOrigin.TARGET_REVIEW,
)
```

The actual future finding object owns:

```text
message
criterion
affected artifact
severity
evidence
etc.
```

Repair context later dereferences the currently open findings.

This gives the state exactly what it needs to answer:

> What unresolved feedback currently blocks this target?

without creating duplicated review state. This matches the provisional repair-finding design already recorded in `agentic-contracts.md`. 

### Artifact/evidence projection

For candidate artifacts, the core state needs enough information to identify **the exact current version**:

```text
artifact_id
path
revision
digest
```

It does not need contents.

For evidence, only stable IDs are needed now:

```python
evidence_refs: list[str]
```

The detailed `EvidenceReference` schema should remain deferred as requested.

### Ownership / mutability

| Property        | Rule                                       |
| --------------- | ------------------------------------------ |
| Created by      | Target runtime during fleet initialization |
| Mutable by      | Target runtime                             |
| Worker access   | Only through controlled operations         |
| Reviewer access | Read-only projected context; no mutation   |
| Persisted       | Yes                                        |
| Lifetime        | Whole target execution, including repairs  |
| Parent          | Fleet execution / `TargetTaskSpec`         |
| Semantic child  | `TargetCompletionState`                    |

### Important invariants

* `target_task_id` resolves to one immutable `TargetTaskSpec`.
* `fleet_run_id` equals the spec's fleet.
* No source binding is copied into task state.
* `phase` is the only target lifecycle authority.
* `usage` and `stall_count` are non-negative; usage counters are monotonic.
* artifact IDs/paths represent only current candidate artifacts inside the target workspace.
* evidence refs must eventually resolve to evidence bound to the same source revision.
* `open_finding_refs` contains only unresolved findings routed to this target.
* entering `REPAIR` requires at least one actionable repair finding.
* `FINALIZING` requires a pending finalization request reference.
* the worker cannot directly set `VALIDATING`, `REVIEWING`, `ACCEPTED`, or any terminal failure state.
* `ACCEPTED` may only be entered after hard validation + target review pass.
* `last_accepted_result_ref` exists once at least one local target acceptance has occurred.

### Important nuance: `ACCEPTED` is reopenable

Local target acceptance is not necessarily the end of that task's life.

The locked fleet design permits:

```text
ACCEPTED
    ↓ fleet finding
REPAIR
    ↓
WORKING
→ VALIDATING
→ REVIEWING
→ ACCEPTED
```

Therefore the previous `AcceptedTargetResult` remains immutable and referenced by:

```python
last_accepted_result_ref
```

while the mutable target execution is reopened.

This directly preserves the later fleet-reconciliation design. 

---

# 6. `TargetCompletionState`

### Semantic definition

TargetCompletionState is the runtime materialization of the completion obligations defined by the TargetDefinition identified by TargetTaskSpec.target_contract_version. It is semantically part of the target execution but separate from generic operational progress because it answers a different question:

> **Which semantic obligations have actually been investigated/resolved?**

The runtime creates it by instantiating the completion_obligations of that TargetDefinition. The worker may update individual obligations only through controlled runtime operations; the runtime owns validation and acceptance. 

### Recommended relationship

I would lock:

> **Logical child of `TargetTaskState`, physically persisted separately, keyed 1:1 by `target_task_id`.**

Therefore we do **not** need:

```text
completion_state_id
```

or:

```text
completion_state_ref
```

The relation is simply:

```text
TargetTaskState.target_task_id
        ==
TargetCompletionState.target_task_id
```

When restoring a target execution, both objects are loaded as one logical runtime unit.

This is the simplest arrangement consistent with the architectural intent already recorded in `agentic-contracts.md`. 

### Completion item

A submodel is necessary here; otherwise the semantic state is not concrete enough.

```python
class CompletionItemState(BaseModel):
    obligation_id: str

    status: CompletionStatus = CompletionStatus.UNINVESTIGATED

    # Short explanation of why the terminal resolution was chosen.
    # This is not the target knowledge prose itself.
    resolution_note: str | None = None

    # Stable IDs only; detailed EvidenceReference comes later.
    evidence_refs: list[str] = Field(default_factory=list)


class TargetCompletionState(BaseModel):
    schema_version: int = 1

    target_task_id: str

    items: list[CompletionItemState]
```

### Why the item does not copy obligation definitions

It should **not** duplicate:

```text
obligation title
description
required/conditional metadata
investigation guidance
target-specific semantics
```


The runtime state only stores the mutable resolution.

This gives:

```text
TargetDefinition.completion_obligations
    = what must be investigated

TargetCompletionState
    = what happened to each obligation
```

### Ownership / mutability

| Property         | Rule                                     |
| ---------------- | ---------------------------------------- |
| Created by       | Runtime from TargetDefinition completion obligations |
| Mutable by       | Runtime                                  |
| Worker influence | Controlled completion-update interface   |
| Reviewer         | Cannot mutate                            |
| Persisted        | Yes, separately recommended              |
| Lifetime         | Entire target execution                  |
| Parent           | Logical child of `TargetTaskState`       |
| Key              | Same `target_task_id`                    |

### Important invariants

At initialization:

```text
every item.status == uninvestigated
```

The four values are exactly the vocabulary already locked in the target catalog. 

Further invariants:

* obligation IDs are unique.
* TargetCompletionState.items must correspond exactly to the completion obligations defined by the TargetDefinition identified by TargetTaskSpec.target_contract_version.
* no obligation may be added or removed during a target run.
* `uninvestigated` is the default-fail state.
* a worker cannot mark the target accepted by modifying completion state.
* workers move obligations through a controlled runtime interface, not by editing persisted state directly.
* a successfully accepted target may not retain `uninvestigated` for any required/applicable obligation.
* `covered`, `not-applicable`, and `unknown` require a non-empty `resolution_note`.
* referenced evidence IDs must eventually resolve against the same repository/source binding.
* completion state is not equivalent to validation PASS or reviewer PASS.

I would also make completion resolution effectively monotonic with respect to investigation:

```text
uninvestigated
    → covered
    → not-applicable
    → unknown
```

More precisely:

```text
uninvestigated → any terminal semantic resolution

terminal resolution → another terminal resolution
    allowed when new investigation changes the conclusion

terminal resolution → uninvestigated
    forbidden in normal execution
```

Once meaningful investigation has happened, saying that it was never investigated again is semantically incorrect.

This fits the target catalog's definitions: `covered`, `not-applicable`, and `unknown` are all legitimate resolved states; only `uninvestigated` means the obligation has not yet been meaningfully addressed. 

### Evidence requirement

I would **not yet enforce**:

```python
len(evidence_refs) >= 1
```

at the Pydantic-schema level for every terminal status.

`covered` should normally have evidence, and `unknown` / `not-applicable` must result from meaningful investigation, but the target catalog explicitly leaves the mechanical proof of those claims to later validation/evaluation design. 

The core state should support evidence linkage now without prematurely locking the future hard-validator policy.

---

# 7. Budget and usage decision

A reusable pair is warranted:

```text
ExecutionBudget
ExecutionUsage
```

because both fleet and target runtimes need exactly the same basic mechanism:

```text
immutable limits
+
mutable monotonic consumption
```

The implementation-oriented course uses the same basic pattern, including cycles/model/tool/token usage and runtime-owned exhaustion rather than prompt advice. 

For V0 I would deliberately **not** introduce separate:

```text
WorkerBudget
ReviewerBudget
ToolBudget
RepairBudget
TokenBudget
CostBudget
```

objects.

The core counters are sufficient:

```text
cycles
model calls
tool calls
repair cycles
input/output tokens
```

The trace can later provide finer attribution such as:

```text
worker vs reviewer
provider retry
specific tool
specific model
```

without bloating authoritative state.

An exhausted target becomes:

```python
phase = TargetPhase.EXHAUSTED
```

while its candidate artifacts, completion state, findings and evidence remain inspectable.

Repair consumes the **remaining original target budget**; it does not receive a fresh allocation.

---

# 8. Resulting lifecycle authority

The core design now has very clear authority boundaries:

```text
MemoryFleetSpec
    immutable run configuration

FleetRunState
    mutable global control state

TargetTaskSpec
    immutable target assignment

TargetTaskState
    mutable operational target state

TargetCompletionState
    mutable semantic investigation state
```

And separately:

```text
Candidate artifacts
    generated knowledge

EvidenceReference[]
    repository grounding

TaskEvent[]
    execution history

validation/review findings
    evaluation outputs

AcceptedTargetResult
    immutable locally accepted candidate

AcceptedMemoryFleetResult
    immutable fleet-level result
```

That matches the central requirement that runtime state, product state, trace and evaluation remain separate authorities rather than becoming one giant agent-state object. 

---

# 9. Compact contract table

| Contract / State        | Immutable? | Authority                                  | Parent                      | Main purpose                   |
| ----------------------- | ---------: | ------------------------------------------ | --------------------------- | ------------------------------ |
| `MemoryFleetSpec`       |        Yes | Fleet runtime at creation                  | —                           | Exact run definition           |
| `FleetRunState`         |         No | Fleet runtime                              | `MemoryFleetSpec`           | Global execution reality       |
| `TargetTaskSpec`        |        Yes | Fleet runtime at creation                  | `MemoryFleetSpec`           | Exact target assignment        |
| `TargetTaskState`       |         No | Target runtime                             | Fleet / `TargetTaskSpec`    | Operational target execution   |
| `TargetCompletionState` |         No | Runtime; worker through controlled updates | `TargetTaskState` logically | Semantic obligation resolution |
| `CompletionItemState`   |         No | Runtime-controlled worker updates          | `TargetCompletionState`     | Resolution of one obligation   |

---


The already-locked runtime contracts/states remain untouched. `MemoryFleetSpec` is still the immutable Stage-0 product, and Stage 1 still materializes `FleetRunState`, `TargetTaskSpec`, `TargetTaskState`, and `TargetCompletionState`.  The target semantics also remain unchanged: predefined targets, deterministic activation of `design/`, independent execution by default, and default-`uninvestigated` semantic completion. 

```text
STATIC ARTIFACTS

MemoryTargetCatalog
        │
        └── references TargetDefinition × N
                         │
                         └── contains completion_obligations[]


STAGE 0

upstream authorities
+ MemoryTargetCatalog
+ TargetDefinition × N
+ runtime configuration
        │
        ├── resolve_target_activation()
        │
        └── bind_memory_run()
                 │
                 ▼
          MemoryFleetSpec


STAGE 1

MemoryFleetSpec
+ exact catalog/definitions
        │
        └── initialize_fleet()
                 │
                 ├── FleetRunState
                 ├── TargetTaskSpec × N
                 ├── TargetTaskState × N
                 └── TargetCompletionState × N
```

No worker, reviewer, scheduler, prompt compilation, evidence creation, trace, or checkpointing occurs yet.

---

# 1. Artifact format

I recommend **YAML for these static human-authored artifacts**, parsed and validated into typed immutable Python models when loaded.

Conceptual artifact bundle:

```text
memory-target-catalog/
├── catalog.yaml
└── targets/
    ├── repository.yaml
    ├── business-logic.yaml
    ├── architecture.yaml
    ├── data-and-state.yaml
    ├── interfaces-and-integrations.yaml
    ├── testing.yaml
    ├── conventions.yaml
    ├── operations.yaml
    └── design.yaml
```

There is deliberately **no `completion.yaml`** anymore.

---

# 2. `[A] MemoryTargetCatalog`

## Role

`MemoryTargetCatalog` defines **which target contracts constitute one catalog version** and contains the global cross-target ownership policy.

It answers:

> What target contracts belong to this version of the Bridger memory fleet?

It does **not** say which targets are active for a particular repository. That resolved result belongs to `MemoryFleetSpec.target_ids`.

### Logical schema

```python
class TargetCatalogEntry(BaseModel):
    target_id: str
    target_contract_version: str


class MemoryTargetCatalog(BaseModel):
    schema_version: int

    catalog_id: str
    catalog_version: str

    targets: list[TargetCatalogEntry]

    # Global semantic ownership rules shared across targets.
    cross_target_ownership_rules: list[str]
```

### Placeholder YAML

```yaml
schema_version: 1

catalog_id: "<catalog-id>"
catalog_version: "<catalog-version>"

targets:
  - target_id: "<target-id>"
    target_contract_version: "<contract-version>"

  - target_id: "<target-id>"
    target_contract_version: "<contract-version>"

cross_target_ownership_rules:
  - "<global ownership rule>"
  - "<global ownership rule>"
```

The important point of storing `target_contract_version` here is that:

```text
catalog version X
    ↓
target architecture → contract v3
target testing      → contract v2
...
```

is explicit and reproducible.

### Invariants

* `(catalog_id, catalog_version)` identifies one immutable catalog.
* `target_id`s are unique.
* every entry resolves to exactly one `TargetDefinition`.
* the definition's `target_id` and `target_contract_version` must match the entry.
* changing target membership, target-version mappings, or global ownership rules requires a new `catalog_version`.
* catalog order should be deterministic.

The global ownership rules belong here rather than being copied into every target. That matches the target catalog's existing cross-target ownership model. 

---

# 3. `[A] TargetDefinition`

## Role

`TargetDefinition` is the complete immutable semantic contract for one target.

It answers:

> What does this target own, what should its worker investigate, and what semantic obligations must eventually be resolved?

The completion checklist is now simply one section of this artifact.

### Small supporting vocabulary

```python
class ActivationMode(StrEnum):
    ALWAYS = "always"
    CONDITIONAL = "conditional"


class ObligationApplicability(StrEnum):
    ALWAYS = "always"
    CONDITIONAL = "conditional"


class TargetActivation(BaseModel):
    mode: ActivationMode
    rule_id: str | None = None


class CompletionObligationDefinition(BaseModel):
    obligation_id: str
    description: str
    applicability: ObligationApplicability
    condition_hint: str | None = None
```

Then:

```python
class TargetDefinition(BaseModel):
    schema_version: int

    target_id: str
    target_contract_version: str

    activation: TargetActivation

    # Semantic execution dependencies. Normally [] in V0.
    depends_on: list[str]

    canonical_question: str
    purpose: str
    expected_abstraction: str

    always_relevant_scope: list[str]
    conditional_scope: list[str]
    exclusions: list[str]

    boundary_guidance: list[str]

    investigation_expectations: list[str]
    evidence_expectations: list[str]

    completion_obligations: list[CompletionObligationDefinition]

    output_quality_expectations: list[str]
```

This shape maps directly onto the semantic dimensions already present in the locked target catalog: purpose/question, scope, conditional coverage, exclusions, boundary guidance, investigation/evidence expectations, completion obligations, and output-quality expectations. 

### Placeholder YAML

```yaml
schema_version: 1

target_id: "<target-id>"
target_contract_version: "<contract-version>"

activation:
  mode: "<always | rule>"
  rule_id: "<rule-id | null>"

depends_on: []

canonical_question: "<placeholder>"
purpose: "<placeholder>"
expected_abstraction: "<placeholder>"

always_relevant_scope:
  - "<placeholder>"

conditional_scope:
  - "<placeholder>"

exclusions:
  - "<placeholder>"

boundary_guidance:
  - "<placeholder>"

investigation_expectations:
  - "<placeholder>"

evidence_expectations:
  - "<placeholder>"

completion_obligations:
  - obligation_id: "<stable-obligation-id>"
    description: "<placeholder>"
    applicability: "<always | conditional>"
    condition_hint: "<placeholder | null>"

output_quality_expectations:
  - "<placeholder>"
```

## Why `scope` and `completion_obligations` are not duplicates

There is some intentional conceptual overlap, but they serve different roles:

```text
scope
= what belongs to this target

completion_obligations
= the finite runtime checklist whose items receive statuses
```

For example:

```text
scope:
    background execution

completion obligation:
    "Background execution and its role are investigated when present."
```

Only the latter produces a `CompletionItemState`.

So the runtime transformation is:

```text
TargetDefinition.completion_obligations[]
                  ↓
        TargetCompletionState.items[]
```

and every item begins `uninvestigated`.

### Invariants

* `(target_id, target_contract_version)` identifies one immutable target contract.
* activation is either:

  * `always` with no `rule_id`; or
  * `rule` with exactly one recognized `rule_id`.
* dependencies are unique and cannot contain the target itself.
* completion obligation IDs are unique and stable within the contract.
* every completion obligation has applicability `always` or `conditional`.
* changing target semantics, activation, dependencies, scope/boundaries, or completion obligations requires a new `target_contract_version`.
* output filenames and Markdown segmentation are **not** specified here; those remain worker-owned. The target folder is the unit of work. 

---

# 4. Activation rule representation

For V0, I would explicitly reject a generic predicate/DSL such as:

```yaml
when:
  any:
    - language: typescript
    - dependency: react
```

That is unnecessary complexity.

Instead:

```yaml
activation:
  mode: conditional
  rule_id: frontend_stack_present_v1
```

The runtime has a small deterministic rule registry:

```text
rule_id
    ↓
deterministic activation function
```

`design/` uses the frontend-stack rule; ordinary targets use:

```yaml
activation:
  mode: always
  rule_id: null
```

The target catalog already locks the semantic rule that `design/` is instantiated only when deterministic repository facts indicate a meaningful frontend stack; the worker does not decide this. 

The exact React/Vue/etc. detection implementation can remain inside `frontend_stack_present_v1`; it does not need to become another persisted artifact.

---

# 5. Interface 1 — `resolve_target_activation`

## Responsibility

Determine the exact target set applicable to this repository **before `MemoryFleetSpec` is frozen**.

```text
MemoryTargetCatalog
+ TargetDefinition × N
+ deterministic upstream facts
        ↓
resolve_target_activation
        ↓
ordered target_id[]
```

## Inputs

Conceptually:

```text
MemoryTargetCatalog
resolved TargetDefinition objects
RepositoryContext
FileIndex
SymbolIndex
GraphBuildResult / GraphSnapshotManifest
```

Only the deterministic upstream information actually required by registered activation rules needs to be inspected.

The optional AI enrichment overlay **must not influence activation**.

## Transformation

For each catalog entry, in deterministic catalog order:

```text
load exact TargetDefinition
        ↓
activation.mode == always
        → ACTIVE

activation.mode == conditional
        ↓
lookup rule_id
        ↓
evaluate against deterministic repository facts
        ↓
true  → ACTIVE
false → INACTIVE
```

Result:

```python
list[str]  # activated target_ids
```

No new `TargetActivationResult` contract is warranted.

## Failure behavior

The interface fails rather than guessing when:

* a catalog entry cannot resolve its exact target definition;
* target ID/version does not match;
* `rule_id` is unknown;
* required deterministic upstream information is unavailable;
* the activation rule itself fails to evaluate.

Crucially:

```text
activation evaluation failed
≠
inactive
```

An evaluation failure must never silently remove a target from the fleet.

## Side effects

None.

It does not create tasks, state, directories, or `MemoryFleetSpec`.

---

# 6. Interface 2 — `bind_memory_run`

## Responsibility

Turn validated immutable upstream authorities + the resolved target catalog + runtime configuration into **one exact immutable `MemoryFleetSpec`**.

```text
upstream authorities
+ target artifacts
+ runtime configuration
        ↓
validate identities
        ↓
resolve activation
        ↓
freeze run configuration
        ↓
MemoryFleetSpec
```

## Inputs

### Upstream authorities

```text
RepositoryContext
FileIndex
SymbolIndex
GraphBuildResult / GraphSnapshotManifest
GraphEnrichmentOverlay?      optional
```

`RepositoryNavigator` is an existing runtime capability over these authorities; it is **not serialized into `MemoryFleetSpec`** and does not require a new memory-harness contract. Layer 6 already exists precisely to provide this shared read surface. 

### Static target artifacts

```text
MemoryTargetCatalog
TargetDefinition × N
```

### Runtime configuration

Values required to populate the already-locked `MemoryFleetSpec`:

```text
runtime profile
worker profile
reviewer profile
permission profile

fleet budget
default target budget
max concurrency

runtime root
output root
```

For now these may resolve to placeholder/fake-agent profiles. Their own artifact schemas do not need to be designed in Stage 0.

## Transformation

`bind_memory_run`:

1. verifies upstream repository/revision/snapshot compatibility;
2. verifies the optional enrichment overlay belongs to the exact graph snapshot;
3. validates the catalog and referenced target definitions;
4. calls `resolve_target_activation`;
5. resolves runtime/profile/budget configuration;
6. allocates `fleet_run_id`;
7. builds the locked `SourceBinding`;
8. creates `MemoryFleetSpec` containing the resolved activated `target_ids`;
9. persists the immutable spec.

The binding layer verifies **cross-artifact compatibility**, not the correctness of Layers 1–6 again. Upstream layers remain authoritative for their own validation. Repository revision identity is required end-to-end by Bridger's architecture. 

## Output

Exactly:

```text
MemoryFleetSpec
```

No additional `BindMemoryRunResult` is needed.

## Failure behavior

Binding fails on:

```text
upstream repository/revision mismatch
graph snapshot incompatibility
provided enrichment mismatch
invalid/missing catalog
missing target definition
catalog ↔ target-definition version mismatch
activation-resolution failure
invalid runtime/profile/budget configuration
invalid runtime/output roots
MemoryFleetSpec persistence failure
```

Failure semantics:

> **No valid `MemoryFleetSpec` is produced or persisted.**

No degraded or partially bound run is allowed.

---

# 7. Interface 3 — `initialize_fleet`

## Responsibility

Expand the already-frozen `MemoryFleetSpec` into the exact initial fleet and target execution objects.

```text
MemoryFleetSpec
+ exact catalog
+ exact target definitions
        ↓
initialize_fleet
        ↓
FleetRunState
TargetTaskSpec × N
TargetTaskState × N
TargetCompletionState × N
```

This is exactly the Stage-1 responsibility identified in the system roadmap. 

## Inputs

```text
MemoryFleetSpec
MemoryTargetCatalog
TargetDefinition × activated N
```

The catalog and target definitions are loaded at the exact versions referenced by the run.

`initialize_fleet` **does not rerun activation**.

At this point:

```python
MemoryFleetSpec.target_ids
```

is authoritative.

## Transformation

For every activated `target_id`:

### A. Resolve the exact contract

```text
MemoryFleetSpec.target_catalog_id/version
        ↓
catalog entry
        ↓
target_contract_version
        ↓
exact TargetDefinition
```

### B. Instantiate target identity

Create the single:

```text
target_task_id
```

for:

```text
(fleet_run_id, target_id)
```

Repair will later continue this task rather than create a new one.

### C. Resolve immutable assignment

Create the already-locked `TargetTaskSpec` using:

```text
fleet identity
target identity
target contract version
copied SourceBinding
resolved worker/reviewer/permission profiles
target budget
target workspace
resolved dependency task IDs
```

No new fields are introduced here.

### D. Materialize operational state

Create `TargetTaskState` using its already-locked initial/default values.

In particular:

```text
phase = INITIALIZED
usage = zero
no artifacts
no evidence
no findings
no checkpoint
no error
no accepted result
```

This is simply construction of the locked state, not a new contract design. 

### E. Materialize semantic completion state

For each:

```text
TargetDefinition.completion_obligations[]
```

create the corresponding already-locked `CompletionItemState` with:

```text
same obligation_id
status = uninvestigated
no resolution
no evidence refs
```

Conditional obligations also start `uninvestigated`.

They are **not** pre-evaluated during initialization; the worker must meaningfully investigate them before resolving them to `covered`, `not-applicable`, or `unknown`. This preserves the target catalog's default-fail semantics. 

### F. Resolve target workspace

For V0:

```text
target_workspace = output_root / target_id
```

The runtime creates the empty target boundary, but no Markdown filenames are predetermined.

### G. Resolve dependencies

`TargetDefinition.depends_on` contains semantic target IDs.

Stage 1 translates:

```text
target_id
    ↓
target_task_id
```

into the existing:

```text
TargetTaskSpec.depends_on_target_task_ids
```

V0 definitions should normally contain:

```yaml
depends_on: []
```

because target execution is independent by default. 

### H. Materialize fleet state

Only after every target has been instantiated successfully:

```text
FleetRunState.phase = INITIALIZED
FleetRunState.target_task_ids = all instantiated task IDs
```

All global usage/finding/termination state uses the already-locked initial values.

Stage 2—not initialization—will later move targets into scheduling/execution phases.

---

# 8. `initialize_fleet` failure behavior

Initialization fails on:

```text
MemoryFleetSpec ↔ catalog identity/version mismatch
activated target absent from catalog
missing TargetDefinition
target contract version mismatch
duplicate or malformed completion obligation IDs
invalid dependency
dependency on inactive target
self-dependency
dependency cycle
target task identity collision
workspace outside output_root
workspace collision
workspace creation failure
state/spec persistence failure
```

Most importantly, Stage 1 should have **all-or-nothing semantics**:

```text
all target specs/states/workspaces valid
        ↓
commit initialized fleet

otherwise
        ↓
no runnable fleet exists
```

We do not need to decide the exact filesystem transaction/temporary-file strategy yet.

If Stage 1 fails, the valid `MemoryFleetSpec` from Stage 0 may still exist:

```text
BOUND RUN
but
NOT INITIALIZED
```

That distinction is useful and clean.

---

# 9. Versioning rules

I would lock these now because the interfaces depend on them.

### `schema_version`

Changes when the **serialized shape** of an artifact changes.

Example:

```text
TargetDefinition YAML gets a new required structural field.
```

### `target_contract_version`

Changes when the **meaning of a target contract** changes:

```text
purpose
scope
exclusions
boundary guidance
activation
dependencies
investigation expectations
evidence expectations
completion obligations
output quality expectations
```

`TargetTaskSpec.target_contract_version` records exactly this version.

### `catalog_version`

Changes when the fleet-level catalog changes:

```text
target added/removed
target contract version mapping changed
global cross-target ownership rules changed
```

This gives a clean provenance chain:

```text
MemoryFleetSpec
    target_catalog_version
            │
            ▼
MemoryTargetCatalog
            │
            ├── architecture → contract v3
            ├── testing → contract v2
            └── ...
                         │
                         ▼
                 TargetTaskSpec
                 target_contract_version
```

---

# 10. Final Stage 0–1 boundary

After these decisions, I would consider Stage 0–1 fully specified at the design-contract level as:

| Item                        | Kind                 | Responsibility                                                           |
| --------------------------- | -------------------- | ------------------------------------------------------------------------ |
| `MemoryTargetCatalog`       | Static YAML artifact | Fleet target/version inventory + global ownership rules                  |
| `TargetDefinition`          | Static YAML artifact | Complete semantic contract + embedded completion obligations             |
| `resolve_target_activation` | Interface            | Deterministically resolve applicable target set                          |
| `bind_memory_run`           | Interface            | Validate/bind immutable inputs into `MemoryFleetSpec`                    |
| `initialize_fleet`          | Interface            | Materialize exact target assignments and zeroed runtime/completion state |

The only implementation-policy detail I would leave intentionally open inside this phase is the **exact deterministic detection logic behind `frontend_stack_present_v1`**. The interface contract does not depend on whether that rule ultimately checks manifests, graph facts, file metadata, or a combination; it only requires the rule to be deterministic, versioned, and fail explicitly when it cannot be evaluated.


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
