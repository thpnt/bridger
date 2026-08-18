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



# Stage 4 — Worker Cycle

## 1. Responsibility

Stage 4 is the bounded **worker execution** stage.

Its lifecycle boundary is:

```text
Stage 3
TargetTaskState.phase = HYDRATING
+
compiled WorkerContext
        ↓
Stage 4
resolve execution surface
preflight first request
HYDRATING → WORKING
worker model/tool trajectory
        ↓
        ├── worker requests finalization → Stage 6
        ├── target execution budget prevents further work → EXHAUSTED
        └── runtime/context/provider interruption → Stage 5 boundary
````

Stage 4 owns:

* `HYDRATING → WORKING` immediately before actual worker execution begins;
* one bounded worker execution cycle;
* provider request/conversation handling around the already-rendered Stage 3 context;
* the model/tool control loop;
* concrete worker tool exposure and execution;
* repository exploration through the existing `RepositoryNavigator`;
* target-local candidate Markdown mutation through `TargetWorkspace`;
* evidence creation through a controlled evidence recorder;
* semantic completion updates through a controlled completion updater;
* working-summary and open-question updates;
* the Stage-4-facing finalization control affordance;
* bounded active-context growth during the execution;
* reuse of the existing `ContextWindowManager` before every model request;
* actual `ExecutionUsage` consumption for worker execution;
* runtime permission enforcement for every worker action.

Stage 4 does **not** own:

* scheduling or concurrency admission;
* Stage 3 context compilation or canonical `WorkerContext` rendering;
* checkpoint contracts or crash recovery;
* trace/event persistence semantics;
* retry/backoff policy;
* context-reset recovery policy;
* `TargetFinalizationRequest` or `WORKING → FINALIZING`;
* hard validation;
* target review;
* repair routing;
* target acceptance;
* fleet reconciliation or fleet acceptance.

The worker remains autonomous in repository investigation and target-local knowledge organization, but lifecycle authority and mutation enforcement remain runtime-owned.

---

## 2. Existing authorities consumed

Stage 4 consumes the already-locked authorities:

```text
MemoryFleetSpec
FleetRunState

TargetTaskSpec
TargetTaskState
TargetCompletionState

WorkerContext
TargetDefinition

candidate artifact state
evidence state
open-question state

worker profile
permission profile

RepositoryNavigator
ContextWindowManager
existing LLMClient/model abstraction
```

Stage 4 does not copy or replace these authorities.

In particular:

```text
RepositoryNavigator
    = existing Layer 6 read capability

WorkerContext
    = immutable Stage 3 execution view

TargetTaskState
    = authoritative operational state

TargetCompletionState
    = authoritative semantic progress state

candidate artifacts
    = authoritative current product candidate

evidence records
    = authoritative durable grounding references
```

The active model conversation remains transient execution context and is never a task authority.

---

# 3. Worker execution cycle

## 3.1 Meaning of one cycle

One Stage 4 **cycle** is one hydrated worker execution, not one model turn.

A single cycle may contain many model/tool turns:

```text
WorkerContext
    ↓
model call
    ↓
tool calls
    ↓
tool results
    ↓
model call
    ↓
tool calls
    ↓
...
```

No additional `max_turns_per_cycle` contract is introduced in V0.

The already-locked execution budgets bound the trajectory through:

```text
max_model_calls
max_tool_calls
max_input_tokens?
max_output_tokens?
```

while:

```text
max_cycles
max_repair_cycles
```

bound how many worker executions may begin.

## 3.2 Cycle start

Before actual execution begins, Stage 4 resolves:

```text
worker/model profile
allowed model-tool definitions
runtime-bound tool handlers
first provider request envelope
context-window fit
next-action budget availability
```

Only after this preflight succeeds does Stage 4 perform:

```text
HYDRATING → WORKING
```

and charge the cycle.

Therefore:

```text
HYDRATING
    = context compiled; execution not yet started

WORKING
    = worker execution has actually begun
```

A Stage 4 failure detected before the transition does not consume a cycle.

## 3.3 Normal end

The only normal semantic end of the worker trajectory is:

```text
request_finalization()
```

That means only:

> The worker believes the current candidate is ready to transfer to the finalization/evaluation path.

It does not mean the target is complete, valid, reviewed, or accepted.

Other trajectory exits are runtime outcomes such as:

```text
target budget exhaustion
fleet budget preventing another action
provider/runtime interruption
active-context capacity interruption
```

---

# 4. Worker model/tool control loop

The runtime controls continuation.

The model chooses among the tools and control affordances it is allowed to request, but it never decides whether an operation is legally executable or whether lifecycle state may advance.

Conceptually:

```text
while target is WORKING:

    verify another model call is allowed
    verify next request fits context policy

    invoke model
    account actual model usage

    inspect requested tool calls

    if valid standalone finalization request:
        stop Stage 4 and transfer control to Stage 6

    validate requested operational tool batch
    execute allowed tools sequentially
    account tool usage
    collect bounded results

    update transient execution-state projection
    update recent tool working set

    continue
```

The runtime, not the model, owns:

```text
continuation legality
budget enforcement
permission enforcement
tool argument validation
mutation validation
lifecycle transitions
completion authority
```

No durable `WorkerRun`, `WorkerCycleResult`, or provider-conversation contract is introduced.

The Stage 4 runner may return a small internal control outcome such as:

```text
FINALIZATION_REQUESTED
TARGET_BUDGET_EXHAUSTED
FLEET_BUDGET_STOP
EXECUTION_INTERRUPTED
```

but this is an implementation return value, not another persisted authority.

---

# 5. Provider request boundary and Stage 3 rendering ownership

Stage 3 remains the **sole owner** of:

```text
WorkerContext
    ↓
canonical deterministic model-facing serialization
```

Stage 4 must not implement a second `WorkerContext` renderer.

The corrected boundary is:

```text
Stage 3
WorkerContext
    ↓
existing canonical serializer
    ↓
canonical model-facing base payload
    ↓
Stage 4
provider envelope
+ stable tool definitions
+ transient Stage 4 execution context
    ↓
LLMClient
```

The same pure canonical serialization and fixed-request assembly/counting path used by Stage 3 for initial 32K request validation must be reused by Stage 4 when constructing the first real request. The initial Stage 4 request must therefore use the same canonical base content and allowed tool definitions that Stage 3 already budgeted. Stage 4 must not silently add a second copy of instructions or otherwise invalidate the successful Stage 3 size check.

If implementation currently embeds this assembly/counting logic inside Stage 3 hydration, the shared pure helper should be reused or extracted rather than reproduced. Stage 4 may cache the resulting canonical base serialization in memory for the lifetime of the cycle; that cache remains transient and non-authoritative.

Stage 4 owns only the provider-specific envelope around that canonical content.

Exact provider-native message roles are adapter concerns. They must not cause the Stage 3 content to be reinterpreted, reordered, or independently rendered.

Stage 4 must preserve the stable-prefix rule already locked in Stage 3:

```text
canonical stable Stage 3 context
+ stable allowed tool definitions
        ↓
dynamic execution overlay
+ recent tool interactions
```

No generic provider framework is introduced for V0.

---

# 6. Provider conversation state

Within one Stage 4 cycle, the runtime may retain immediate model/tool interaction state in process memory.

It is:

```text
transient
execution-local
non-authoritative
replaceable from durable task state after recovery
```

V0 correctness must not depend on:

```text
provider thread IDs
provider conversation IDs
previous-response handles
remote conversation persistence
full historical transcript replay
```

If an existing provider/client supports those mechanisms, they may be used as transport optimizations only when they do not become required for correctness or recovery.

Normal worker responses use provider-native tool calling.

The V0 worker protocol is action-oriented: each worker turn is expected to return one or more tool/control calls rather than an unconstrained prose-only final answer. For providers such as OpenAI that support required tool choice, Stage 4 uses the provider's required-tool mode. Provider-specific emulation for clients without that capability is an adapter concern.

No structured final-answer schema is required because worker progress is expressed through tools and finalization control.

---

# 7. Multiple tool calls

A model response may request multiple operational tools.

V0 executes them:

```text
sequentially
in model-provided order
without parallel tool execution
```

Sequential execution preserves deterministic mutation ordering and avoids unnecessary concurrency complexity inside one target worker.

Before executing a multi-tool response, Stage 4 preflights the whole operational batch against the currently remaining tool-call capacity.

If the complete batch cannot legally execute under the current applicable hard budget:

```text
execute none of the operational calls
```

and stop or route the execution according to the exhausted budget scope.

A finalization request is different.

```text
request_finalization()
```

must be the **sole model tool/control call in its response**.

A response that mixes finalization with another requested operation cannot finalize the target. The finalization control call is rejected with a worker-correctable protocol error; independently valid operational calls may still execute normally in their model-provided order and return their results. The worker must observe those results and request finalization again in a later standalone response. This prevents ambiguous ordering such as:

```text
edit artifact
+
request finalization
```

without the worker first observing whether the mutation succeeded.

---

# 8. Worker tool runtime

The model receives tool definitions resolved from:

```text
WorkerContext.allowed_tool_ids
+
TargetTaskSpec.permission_profile_id
```

Every model-visible tool maps through:

```text
model tool schema
    ↓
argument validation
    ↓
permission validation
    ↓
runtime-bound handler
    ↓
authoritative operation
    ↓
bounded tool result
```

Tool handlers are bound to the current task by runtime state.

The model does not provide authority-bearing values that the runtime already knows, such as:

```text
target_task_id
fleet_run_id
target_workspace root
repository root
SourceBinding
```

This prevents cross-target or cross-repository access by construction.

Tool exposure and tool execution both enforce permissions:

```text
exposure
    → do not advertise forbidden capabilities

execution
    → independently reject forbidden calls even if malformed/provider-generated
```

Prompt instructions are not the permission boundary.

---

# 9. Repository discovery tool surface

Stage 4 reuses the existing Layer 6 `RepositoryNavigator`.

No repository-search, graph-navigation, file-index, symbol-index, or source-read implementation is recreated inside the memory harness.

The minimal V0 model-facing repository surface is:

```text
Orientation
-----------
search_repository

Graph
-----
get_graph_entity
get_graph_neighbors
get_graph_path
get_graph_community

Repository structure
--------------------
list_files
get_file_overview
search_symbols

Source investigation
--------------------
search_source_content
read_symbol_excerpt
read_file_ranges
```

The following Layer 6 capabilities are not initially exposed as worker tools:

```text
get_graph_subgraph
get_graph_central_nodes

graph_to_file
graph_to_symbols
file_to_graph
symbol_to_graph

list_symbols
read_around_match
```

They remain Layer 6 capabilities and may be exposed later if execution traces demonstrate a repeated need.

The V0 subset is intentionally small but complete enough to support:

```text
repository orientation
→ graph-guided exploration
→ file/symbol localization
→ bounded source verification
```

Every repository operation remains read-only.

---

# 10. `TargetWorkspace`

`TargetWorkspace` is the controlled filesystem-backed mutation surface for the current target's candidate Markdown.

It is bound to:

```text
TargetTaskSpec.target_workspace
```

and never accepts an arbitrary workspace root from the model.

The V0 interface is:

```text
list_target_artifacts()

read_target_artifact(
    path,
    optional range bounds
)

write_target_artifact(
    path,
    content,
    expected_revision?
)

edit_target_artifact_range(
    path,
    expected_revision,
    start_line,
    end_line,
    replacement
)

delete_target_artifact(
    path,
    expected_revision
)

move_target_artifact(
    source_path,
    destination_path,
    expected_revision
)
```

## 10.1 Mutation strategy

V0 deliberately uses:

```text
whole-file create/replace
+
simple line-range replacement
```

rather than a generic patch/diff language.

This supports both:

```text
large structural rewrite
    → whole-file replacement

small repair/refinement
    → bounded line-range edit
```

without forcing the model to re-emit a large Markdown document for every small change.

## 10.2 Revision behavior

Candidate artifact mutations use optimistic revision checks.

Conceptually:

```text
create new path
    → new artifact_id
    → revision = 1

replace/edit existing artifact
    → expected_revision must match
    → same artifact_id
    → revision += 1
    → new digest

move existing artifact
    → expected_revision must match
    → same artifact_id
    → new relative_path
    → revision += 1

delete artifact
    → expected_revision must match
    → current CandidateArtifactRef removed
```

Every successful mutation returns the authoritative current `CandidateArtifactRef`, and `TargetTaskState.artifact_refs` is updated accordingly.

The exact persistence/atomicity protocol for file + state mutation belongs to Stage 5.

## 10.3 Workspace enforcement

Every workspace handler mechanically enforces:

```text
relative target-local paths only
normalized paths
no absolute paths
no `..` escape
no symlink escape
resolved path remains inside exact target workspace
no sibling target access
no source-repository writes
no runtime-state JSON writes
candidate Markdown only
```

The worker remains free to choose file names, file count, segmentation, and target-local organization.

Mutation results return compact metadata rather than echoing the complete written document back into model context.

---

# 11. `EvidenceReference`

Stage 4 introduces the durable evidence contract that was intentionally deferred by the core-state design.

`EvidenceReference` represents one validated, revision-bound grounding reference created by the worker through the runtime.

Conceptually:

```python
class EvidenceKind(StrEnum):
    FILE = "file"
    SOURCE_RANGE = "source-range"
    SYMBOL = "symbol"
    GRAPH_ENTITY = "graph-entity"


class FileEvidenceLocator(BaseModel):
    path: str


class SourceRangeEvidenceLocator(BaseModel):
    path: str
    start_line: int
    end_line: int
    content_digest: str


class SymbolEvidenceLocator(BaseModel):
    symbol_id: str


class GraphEntityEvidenceLocator(BaseModel):
    target_type: str
    target_ref: str


class EvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    target_task_id: str
    source: SourceBinding
    kind: EvidenceKind
    locator: (
        FileEvidenceLocator
        | SourceRangeEvidenceLocator
        | SymbolEvidenceLocator
        | GraphEntityEvidenceLocator
    )
```

The exact Pydantic union/discriminator syntax is an implementation detail; the semantic contract above is locked.

## 11.1 Evidence locator families

V0 supports exactly:

```text
FILE
SOURCE_RANGE
SYMBOL
GRAPH_ENTITY
```

No evidence type is introduced for:

```text
conversation messages
tool-result blobs
search-result blobs
arbitrary model claims
```

Those are transient observations, not source authorities.

`GRAPH_ENTITY` resolves through the bound deterministic graph/composite navigation view. AI enrichment may be visible while inspecting an entity, but enrichment does not create a separate evidence-locator family.

## 11.2 Evidence authority

An `EvidenceReference` is:

```text
durable
immutable
bound to one target task
bound to the task SourceBinding
runtime-validated before creation
```

The model never invents an `evidence_id`.

The runtime creates or resolves the ID only after validating the locator.

---

# 12. Evidence recording

The worker-facing operation is conceptually:

```text
record_evidence(locator)
    → EvidenceReference
```

At write time the runtime validates, as applicable:

```text
TargetTaskSpec / source binding match
repository revision match
path exists in authoritative FileIndex
source range resolves inside the bound file
source-range digest matches the referenced content
symbol exists in authoritative SymbolIndex
graph entity exists in the bound graph snapshot
repository read policy permits the referenced source evidence
```

Successful recording:

```text
creates or reuses EvidenceReference
+
adds evidence_id to TargetTaskState.evidence_refs
```

## 12.1 Deduplication

Evidence is deduplicated within one target task using the canonical key:

```text
source binding
+
evidence kind
+
canonical locator
```

Recording the same evidence again returns the existing `evidence_id`.

Cross-target evidence deduplication is unnecessary because the target catalog explicitly allows the same source evidence to support different semantic owners.

## 12.2 Evidence and Markdown

The evidence registry is the authority for evidence identity.

A path or symbol name merely written into Markdown does not create durable evidence.

Candidate knowledge may refer to durable evidence IDs, and completion items may reference those IDs through their existing `evidence_refs` field.

Stage 4 does not lock the final Repository Brain claim-sidecar or publication citation syntax. It only locks durable evidence identity and worker recording semantics.

---

# 13. Completion-state updates

The worker never edits `TargetCompletionState` JSON directly.

Stage 4 exposes one controlled semantic operation:

```text
update_completion_item(
    obligation_id,
    status,
    resolution_note,
    evidence_refs
)
```

The operation atomically replaces the mutable resolution fields for that obligation.

## 13.1 Runtime validation

Stage 4 validates mechanically that:

```text
obligation_id exists in the locked TargetDefinition
status is one of:
    covered
    not-applicable
    unknown

worker does not explicitly set uninvestigated
resolution_note is present and non-empty
referenced evidence IDs exist
referenced evidence belongs to the same target/source binding
not-applicable is used only for a CONDITIONAL obligation
```

The worker may correct one resolved state into another:

```text
covered → unknown
unknown → covered
not-applicable → covered
...
```

A resolved obligation is not moved back to `uninvestigated`.

Stage 4 intentionally does **not** decide:

```text
whether evidence semantically proves the conclusion
whether covered is sufficiently complete
whether unknown is justified
whether not-applicable is substantively correct
whether a minimum evidence count is sufficient
```

Those concerns remain part of downstream hard validation/review/offline evaluation as already assigned by the target-contract design.

---

# 14. Working summary and open questions

`TargetTaskState.working_summary` remains the compact durable continuation mechanism for the worker.

It is not:

```text
a transcript summary
target knowledge prose
a hidden chain of thought
```

It should contain only the compact state future executions need to resume investigation correctly.

Stage 4 exposes one logical progress operation:

```text
update_progress(
    working_summary?,
    questions_to_open?,
    question_refs_to_resolve?
)
```

`working_summary`, when supplied, replaces the previous summary rather than appending indefinitely.

## 14.1 `OpenQuestion`

Stage 4 completes the already-existing `open_question_refs` design with one minimal durable contract:

```python
class OpenQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    target_task_id: str
    text: str
```

No separate question lifecycle enum is introduced.

The current open-question set is represented by:

```text
TargetTaskState.open_question_refs
```

Therefore:

```text
question ref present
    → currently open

question ref removed
    → no longer operationally open
```

A question's text is immutable. Revising a question means resolving the old question and opening another.

Historical creation/resolution events belong to Stage 5 trace, not to the question contract.

## 14.2 Bounds

The runtime/profile must bound:

```text
working_summary size
individual question size
number of simultaneously open questions
completion resolution-note size
```

because Stage 3 treats these continuation objects as mandatory hydration when present.

The exact V0 limits are profile/runtime configuration, not new domain contracts.

---

# 15. Finalization control

Stage 4 exposes exactly one finalization affordance:

```text
request_finalization()
```

It takes no semantic arguments in V0.

Stage 4 interprets it only as:

```text
stop issuing worker model/tool actions
transfer control to Stage 6
```

Stage 4 does not:

```text
create the final TargetFinalizationRequest contract
set pending_finalization_request_ref
perform WORKING → FINALIZING
check hard completion gates
run validation
run review
mark the target complete or accepted
```

Those semantics remain Stage 6+ responsibility.

The worker is allowed to request finalization even when it is mistaken about readiness. Downstream runtime validation remains the completion authority.

`request_finalization()` is lifecycle control rather than an operational worker tool and therefore does not consume the `tool_calls` execution budget.

---

# 16. Active context model

Stage 4 deliberately does **not** accumulate an unbounded provider transcript.

Every subsequent model request is conceptually composed from:

```text
1. canonical Stage 3 base context
   immutable for this worker execution

2. current Stage 4 execution-state overlay
   compact derived view of authoritative mutations since hydration

3. recent tool-interaction working set
   bounded transient model/tool context
```

This gives:

```text
durable state
    → authoritative continuity

recent tool results
    → immediate reasoning context

old transcript
    → not required
```

The Stage 3 32K hard cap remains specifically the **complete initial provider-input cap**.

Stage 4 does not reinterpret 32K as a hard cap for every later request. Later requests are governed by the model's actual context capacity through the existing `ContextWindowManager`, plus the bounded recent-tool working-set policy below.

---

# 17. Stage 4 execution-state overlay

Because `WorkerContext` is immutable for the cycle, successful Stage 4 mutations can make parts of the original Stage 3 view stale.

Stage 4 therefore appends a compact **derived execution-state overlay** to later requests.

This overlay is:

```text
transient
non-authoritative
recomputed from current authoritative state
not another WorkerContext
not persisted as task state
```

It contains only information changed since hydration that the worker needs to avoid reasoning from stale Stage 3 state.

Conceptually:

```text
completion items changed since hydration
    → latest status/note/evidence refs

candidate artifacts changed since hydration
    → complete current candidate-artifact inventory

working summary changed
    → current working summary

open questions changed
    → complete current open-question set

new evidence recorded
    → compact new evidence identities/locators needed for continued work
```

The overlay replaces itself on every request rather than accumulating a history of deltas. When the overlay contains a field also represented in the immutable Stage 3 base, the overlay's current value explicitly supersedes the stale Stage 3 value for the remainder of this execution.

Detailed artifact contents and detailed source evidence still remain on-demand tool retrieval concerns.

---

# 18. Recent tool-interaction working set

A tool result must remain available long enough for the worker to reason over it, but results must not accumulate indefinitely.

V0 therefore uses a **bounded recent-tool working set**, not a one-turn result policy and not an infinite transcript.

## 18.1 Tool batch

A tool batch is:

```text
one model response's operational tool call(s)
+
the corresponding tool result(s)
```

The complete call/result batch is retained as one context unit.

## 18.2 Protected recent working set

The **3 most recent tool batches** are protected from ordinary eviction.

This is a minimum recency guarantee, not an expiration timer.

A result does not disappear merely because three newer turns occurred.

Once a batch becomes older than the protected recent set, it becomes **evictable**, not immediately deleted.

If active context remains comfortably bounded, useful older results may stay available.

## 18.3 Soft tool-context budget

The recent-tool working set has a runtime/profile-owned soft token budget.

The exact token value is not a new domain contract. A V0 implementation may use a value in the approximate 16K-token range, but the policy is authoritative rather than that exact tuning value.

The soft budget exists to prevent:

```text
unbounded context growth
attention decay from stale observations
needless repetition of large source excerpts
```

The `ContextWindowManager` remains the final context-capacity authority.

## 18.4 Eviction order

When the recent-tool working set exceeds its soft budget or the next provider request experiences context pressure, Stage 4 evicts only unprotected old material using deterministic pressure-first rules:

```text
1. duplicate or clearly superseded old results
2. old unprotected large result bodies
3. remaining unprotected results oldest-first
```

No LLM relevance classifier, summarizer, or semantic context manager is introduced in V0.

Examples of superseded results include:

```text
older read of an artifact after a newer revision has been read
repeated retrieval of the same source range
older duplicate search result already replaced by a newer equivalent result
```

## 18.5 Evicted-result placeholders

When a full old result body is evicted, Stage 4 may retain a compact placeholder such as:

```text
read_file_ranges(src/runtime.py, 120-220)
→ previous result removed from active context;
  retrieve again if needed
```

The provider-native tool-call/result pairing must remain structurally valid.

Placeholders are themselves part of the bounded working set and may later be evicted entirely. They do not create an unbounded second history.

## 18.6 Protected-set overflow

Repository and workspace tools must already return bounded results.

If, after removing every evictable old result, the complete next request still cannot fit while preserving:

```text
canonical Stage 3 base
current execution-state overlay
protected 3 recent tool batches
required response headroom
```

Stage 4 does **not** silently discard mandatory base context or the protected recent working set.

It stops the active trajectory with an active-context-capacity interruption and crosses into the Stage 5 recovery/reset boundary.

V0 introduces no automatic summarization or compaction machinery inside Stage 4.

---

# 19. Tool-result bounding

Context control begins at the tool boundary.

Every worker tool must have domain-specific bounds such as:

```text
result count
source line/range limits
maximum returned bytes/tokens
graph traversal limits
artifact read ranges
```

The tool runtime additionally applies a final serialized-result safety ceiling so an implementation defect cannot inject an unexpectedly large payload into model context.

When truncation is necessary, the result must preserve enough identity and range information for the worker to request the missing detail explicitly.

Mutation tools return compact state deltas or references rather than complete rewritten artifact contents.

This preserves Bridger's progressive-disclosure model:

```text
retrieve narrowly
reason
externalize durable progress
retrieve again when necessary
```

---

# 20. `ContextWindowManager` during Stage 4

Stage 4 reuses the exact `ContextWindowManager` introduced in Stage 3.

No second context-capacity authority is introduced.

Before **every** provider model request, Stage 4 evaluates the complete effective request:

```text
canonical Stage 3 base
+
stable tool definitions
+
current execution-state overlay
+
recent tool working set
+
provider/request overhead
+
reserved output headroom
```

The manager determines whether the request fits the actual resolved model context capacity.

The output reservation uses the actual maximum output Stage 4 will allow for that call, not the model's theoretical maximum by default.

Stage 4 first applies ordinary recent-tool eviction when context pressure exists.

It does not:

```text
drop mandatory Stage 3 context
silently drop current authoritative-state corrections
summarize the active trajectory with another model
create a new context database
```

If the minimum valid next request still cannot fit, execution is interrupted and Stage 5 owns any future reset/recovery policy.

---

# 21. Usage accounting

Stage 4 does not redefine `ExecutionBudget` or `ExecutionUsage`.

Stage 2 already owns admission against the current monotonic counters and explicitly does not predict future execution consumption.

Stage 4 only locks **when actual execution usage is charged**.

| Counter         | Stage 4 accounting rule                                                  |
| --------------- | ------------------------------------------------------------------------ |
| `cycles`        | `+1` exactly once when `HYDRATING → WORKING` occurs                      |
| `repair_cycles` | `+1` at the same transition when `WorkerContext.mode == REPAIR`          |
| `model_calls`   | `+1` immediately before every actual provider/model invocation attempt   |
| `tool_calls`    | `+1` immediately before every attempted operational worker-tool dispatch |
| `input_tokens`  | add actual provider-reported input usage when reported                   |
| `output_tokens` | add actual provider-reported output usage when reported                  |

A cycle therefore may consume many:

```text
model_calls
tool_calls
input_tokens
output_tokens
```

while consuming exactly one:

```text
cycle
```

and optionally one:

```text
repair_cycle
```

## 21.1 Target and fleet usage

Every consumption delta is applied consistently to both:

```text
TargetTaskState.usage
FleetRunState.usage
```

The two scopes must not drift.

The persistence/transaction mechanism that makes this crash-safe belongs to Stage 5, but Stage 4's semantic accounting operation is one target+fleet usage delta.

## 21.2 Failed provider calls

An actual provider invocation attempt consumes:

```text
model_calls += 1
```

even if the provider invocation fails.

Otherwise provider/retry failures would create unbounded free attempts.

Token usage is charged when the provider reports that tokens were consumed.

Stage 5 may later retry the call; every retry is another model-call attempt under the same original budget.

## 21.3 Rejected/invalid tool calls

An operational tool request counts once Stage 4 attempts runtime dispatch, including controlled rejection because of:

```text
invalid arguments
unknown object
permission failure
stale artifact revision
workspace-boundary rejection
unknown/disallowed tool identity
```

Invalid actions are therefore not free attempts.

`request_finalization()` is excluded because it is lifecycle control rather than operational tool work.

---

# 22. Execution-time budget enforcement

Before every new model or operational tool action, Stage 4 checks the existing target and fleet budget authorities for the exact action that is about to begin.

## 22.1 Model call

Before a model invocation:

```text
remaining model-call capacity must be positive
exact next input must fit configured remaining input-token capacity when bounded
remaining output-token capacity must be positive when bounded
ContextWindowManager must permit the request
```

The provider output limit is bounded by:

```text
worker/model profile per-call output limit
remaining target output-token budget
remaining fleet output-token budget
provider/model capability
available context headroom
```

No model request starts when one of its applicable hard capacities has already been exhausted.

## 22.2 Tool call

Before an operational tool batch:

```text
remaining target tool-call capacity
+
remaining fleet tool-call capacity
```

must permit the whole requested batch.

## 22.3 Cycle budgets

`max_cycles` and `max_repair_cycles` govern whether a cycle may start.

They do not interrupt a cycle merely because the current cycle itself consumed the final allowed cycle slot.

## 22.4 Target-scope exhaustion during WORKING

If the target's own hard execution budget prevents the next required Stage 4 action:

```text
WORKING → EXHAUSTED
```

Existing candidate artifacts, completion progress, evidence, questions, findings, and usage remain intact.

This is consistent with the existing meaning that target `EXHAUSTED` represents target-budget exhaustion.

## 22.5 Fleet-scope exhaustion during active work

Fleet-budget exhaustion does **not** relabel a target as target-level `EXHAUSTED`.

If fleet-wide remaining capacity prevents the next action:

```text
Stage 4 stops issuing further actions
reports a fleet-budget stop to the fleet runtime
```

The existing fleet-level exhaustion semantics remain authoritative.

Safe durable handling/reconstruction of an interrupted `WORKING` target belongs to Stage 5.

---

# 23. Concurrent fleet token reservations

Input size is known before a model call; output size is not.

With concurrent targets, model calls must not independently spend the same remaining fleet token capacity. The model-call preflight is therefore concurrency-safe for both configured input and output token limits.

V0 requires a lightweight in-flight reservation mechanism:

```text
count exact next request input
compute maximum allowed output for this call
        ↓
reserve applicable input allowance
+ maximum output allowance
against shared fleet capacity
        ↓
invoke provider
        ↓
charge actual provider-reported usage
        ↓
release unused reservation
```

The reservation is:

```text
runtime coordination state
not ExecutionUsage
not another ExecutionBudget
not another persisted domain contract
```

Known input size can be reserved exactly according to the V0 token-counting policy; the actual provider-reported usage remains the value ultimately charged to `ExecutionUsage`. The same concurrency-safe principle applies to shared model-call and tool-call capacity.

The exact crash handling and recovery of in-flight reservations belongs to Stage 5.

Equivalent concurrency-safe coordination may be used if it preserves the same hard-budget semantics.

---

# 24. Permission enforcement

`TargetTaskSpec.permission_profile_id` becomes concrete Stage 4 runtime enforcement.

At minimum V0 enforces:

```text
repository authorities
    → read only

target workspace
    → write only inside own target boundary

completion state
    → controlled completion operation only

evidence state
    → controlled evidence recording only

working summary / questions
    → controlled progress operation only

other target workspaces
    → inaccessible

runtime lifecycle/state JSON
    → runtime owned

FileIndex / SymbolIndex
RepositoryGraph / structural state
GraphEnrichmentOverlay
    → immutable
```

A worker cannot obtain a writable filesystem path merely because it knows one.

The allowed capability set must be enforced through handler binding and validation rather than through prompt instruction alone.

---

# 25. State mutation authority

Stage 4 preserves the existing separation between execution, semantic progress, product state, evidence state, continuation state, conversation state, and trace.

| Domain                                  | Stage 4 authority                           | Mutation path                                              |
| --------------------------------------- | ------------------------------------------- | ---------------------------------------------------------- |
| `TargetTaskState.phase`                 | Runtime only                                | `HYDRATING → WORKING`; target-budget `WORKING → EXHAUSTED` |
| `TargetTaskState.usage`                 | Runtime only                                | Stage 4 execution accounting                               |
| `FleetRunState.usage`                   | Runtime only                                | same Stage 4 usage delta                                   |
| `working_summary`                       | Worker-proposed, runtime-applied            | `update_progress`                                          |
| `open_question_refs`                    | Worker-proposed, runtime-applied            | `update_progress`                                          |
| `artifact_refs`                         | Runtime projection of workspace mutation    | `TargetWorkspace`                                          |
| `evidence_refs`                         | Runtime projection of evidence creation     | `EvidenceRecorder`                                         |
| `open_finding_refs`                     | No Stage 4 mutation                         | downstream validation/review/repair routing                |
| `last_checkpoint_ref`                   | No Stage 4 mutation                         | Stage 5                                                    |
| `last_progress_signature`               | No Stage 4 mutation                         | Stage 5/no-progress machinery                              |
| `stall_count`                           | No Stage 4 mutation                         | Stage 5/no-progress machinery                              |
| `pending_finalization_request_ref`      | No Stage 4 mutation                         | Stage 6                                                    |
| `last_error_ref`                        | No Stage 4 mutation                         | Stage 5 error/recovery handling                            |
| `last_accepted_result_ref`              | No Stage 4 mutation                         | Stage 10+                                                  |
| `TargetCompletionState`                 | Worker-proposed, runtime-validated mutation | `CompletionStateUpdater`                                   |
| Candidate Markdown                      | Worker-proposed, runtime-enforced mutation  | `TargetWorkspace`                                          |
| `EvidenceReference`                     | Runtime creates immutable record            | `EvidenceRecorder`                                         |
| `OpenQuestion`                          | Runtime creates immutable record            | progress updater                                           |
| Repository/index/graph/enrichment state | Never                                       | read-only Layer 6 access                                   |
| Active model conversation               | Transient only                              | Stage 4 runner                                             |
| Trace/checkpoints                       | Not Stage 4 authority                       | Stage 5                                                    |

The model proposes operations through tool calls. The runtime performs and validates every authoritative mutation.

---

# 26. Worker-correctable tool errors

Some failures are ordinary worker observations and do not end Stage 4.

Examples:

```text
invalid tool arguments
unknown repository path
unknown symbol
unknown graph reference
invalid source range
stale expected artifact revision
workspace-boundary rejection
invalid completion update
unknown evidence reference
mixed finalization + operational tool response
```

For these cases:

```text
no invalid mutation occurs
bounded structured tool error is returned
worker trajectory may continue if budget permits
```

These are not semantic repair findings and do not invoke Stage 5 recovery.

They are part of the active recent-tool working set like other immediate tool results.

---

# 27. Runtime execution interruptions

Stage 4 stops the active trajectory when the failure is not safely correctable by another ordinary worker tool call.

Examples:

```text
provider/network failure
unexpected LLMClient failure
unexpected tool-handler exception
authoritative state store unavailable
filesystem/runtime I/O failure
unexpected RepositoryNavigator failure
permission/profile configuration inconsistency
minimum valid active context no longer fits
process interruption
```

Stage 4 owns identifying:

```text
what operation was attempted
what semantic state change did or did not occur
why execution cannot safely continue in the current trajectory
```

Stage 4 does not itself decide:

```text
retry/backoff
checkpoint restoration
crash reconstruction
safe-phase reconstruction
provider retry count
context reset
terminal FAILED outcome
```

Those remain Stage 5 responsibilities.

An infrastructure/runtime interruption therefore must not be converted into worker semantic `REPAIR`.

---

# 28. Stage 4 ↔ Stage 5 integration points

Stage 4 defines the semantic operation boundaries that Stage 5 must later persist, trace, checkpoint, or recover.

Stage 5 must be able to observe operations such as:

```text
cycle started

model invocation attempted
model response received

tool invocation attempted
tool result produced

candidate artifact mutation applied
EvidenceReference created
CompletionItemState updated
working summary updated
question opened/resolved

finalization control received
budget prevented further action
execution interrupted
```

The responsibility split is:

```text
Stage 4
    what happened
    what authoritative state should change

Stage 5
    how that change becomes durably persisted
    how trace is recorded
    how checkpoints are created
    how partially interrupted work is recovered
```

For example:

```text
Stage 4 semantic operation
    write target Markdown
    → new CandidateArtifactRef

Stage 5
    decides the crash-safe ordering/atomicity of
    filesystem write + ref persistence + event/checkpoint state
```

Stage 4 introduces no event bus, event-sourced authority, checkpoint contract, or database requirement.

---

# 29. Stage 4 ↔ Stage 6 boundary

The Stage 4 / Stage 6 handoff is deliberately narrow.

```text
worker requests request_finalization()
        ↓
Stage 4 stops model/tool execution
        ↓
Stage 6
materializes TargetFinalizationRequest
performs WORKING → FINALIZING
owns pending_finalization_request_ref
```

Stage 4 does not decide:

```text
target complete
target accepted
hard validation passed
review passed
```

A worker finalization request may be wrong.

For example:

```text
worker requests finalization
while obligations remain uninvestigated
        ↓
Stage 6/7 path
        ↓
hard validation fails
        ↓
normal repair routing later
```

This preserves the locked rule:

> The worker may believe the target is ready; the runtime remains the completion authority.

---

# 30. Initial execution

An initial Stage 4 cycle receives the Stage 3 `WorkerContext` in `INITIAL` mode.

Typical starting durable state is:

```text
all completion items = uninvestigated
working_summary = null
open_question_refs = []
artifact_refs = []
evidence_refs = []
open_finding_refs = []
```

The worker then progressively:

```text
orients through RepositoryNavigator
retrieves bounded source evidence
records durable EvidenceReference objects
creates candidate Markdown
updates completion obligations
maintains working summary/questions as useful
requests finalization when it believes the candidate is ready
```

Repository/artifact/evidence detail is discovered through tools rather than preloaded into the initial context.

---

# 31. Repair execution

A repair Stage 4 cycle uses the same worker architecture, tools, workspace, evidence store, completion state, and original remaining budget.

There is no separate repair agent or repair tool surface.

The Stage 3 repair context additionally contains the current routed findings.

The worker may:

```text
inspect additional repository evidence
re-read existing candidate artifacts
rewrite or reorganize candidate Markdown
record additional evidence
correct completion resolutions
update continuation state
request finalization again
```

The worker is not restricted to local patching. It may replace weak candidate structure when necessary.

All Stage 4 context-growth, permission, tool, and accounting rules remain identical during repair.

---

# 32. Minimal new Stage 4 contracts and interfaces

Stage 4 introduces only the new durable contracts that existing state references genuinely require.

## Durable contracts

```text
EvidenceReference
    + typed evidence locators

OpenQuestion
```

## Runtime interfaces/services

Conceptually:

```text
WorkerRunner
WorkerToolRuntime / tool registry

TargetWorkspace
EvidenceRecorder
CompletionStateUpdater
ProgressUpdater
FinalizationControl
```

Execution accounting and provider adaptation may be implemented as small helpers around the existing budget/state and `LLMClient` abstractions; they do not require new persisted domain contracts.

Stage 4 does **not** introduce:

```text
WorkerRun durable object
WorkerCycleResult durable object
conversation store
provider-thread authority
generic patch protocol
new repository retrieval stack
context database
context compaction service
generic memory system
repair agent
worker planner
event bus
new budget contract
new usage contract
```

---

# 33. Stage 4 invariants

1. Stage 4 begins only from a valid `HYDRATING` target with a compiled Stage 3 `WorkerContext`.
2. Stage 4 owns `HYDRATING → WORKING` immediately before actual worker execution begins.
3. One cycle means one hydrated worker execution and may contain multiple model/tool turns.
4. No additional model-turn limit exists in V0.
5. Stage 3 remains the sole owner of canonical `WorkerContext` rendering.
6. Stage 4 reuses the Stage 3 serializer and adds only provider envelope/tool/execution context.
7. Provider conversation state is transient and never required for correctness or recovery.
8. The runtime controls continuation; the model only requests allowed operations.
9. Multiple operational tool calls are executed sequentially in model-provided order.
10. A multi-tool batch must fit the remaining applicable tool budget before any call in the batch executes.
11. `request_finalization()` must be the sole call in its model response.
12. Repository discovery uses the existing read-only `RepositoryNavigator` only.
13. The worker cannot write outside `TargetTaskSpec.target_workspace`.
14. Candidate Markdown mutation uses whole-file create/replace plus bounded line-range editing in V0.
15. Candidate artifact mutations use optimistic revision checks.
16. `EvidenceReference` is immutable, target-bound and `SourceBinding`-bound.
17. Evidence IDs are created/validated by the runtime, never invented by the model.
18. Evidence is deduplicated within a target by canonical source+kind+locator identity.
19. The worker cannot mutate `TargetCompletionState` directly.
20. Completion updates may resolve obligations only to `covered`, `not-applicable`, or `unknown`.
21. `not-applicable` may only be used for conditional obligations.
22. Runtime validation of completion updates is mechanical; semantic sufficiency remains downstream responsibility.
23. `working_summary` is compact durable continuation state, not a transcript summary or target artifact.
24. Open questions are immutable records whose current openness is represented by `open_question_refs`.
25. Active Stage 4 context uses an immutable Stage 3 base + current execution-state overlay + bounded recent-tool working set.
26. The execution-state overlay is transient and replaces itself rather than accumulating deltas.
27. The 3 most recent tool batches are protected from ordinary eviction.
28. Older tool results remain available opportunistically and are evicted only under working-set/context pressure.
29. Tool results never accumulate without bound.
30. Evicted tool-result placeholders are themselves bounded and eventually evictable.
31. No LLM-based context summarizer/relevance classifier is introduced in Stage 4 V0.
32. Tool outputs are bounded at the tool boundary before entering model context.
33. The existing `ContextWindowManager` is consulted before every model request.
34. The Stage 3 32K limit applies to the complete initial provider request; later active context uses actual model capacity plus Stage 4 working-set controls.
35. Mandatory Stage 3 context and current authoritative-state corrections are never silently discarded.
36. `cycles` increments once on `HYDRATING → WORKING`.
37. `repair_cycles` increments at the same boundary only for `REPAIR` mode.
38. `model_calls` counts every actual provider invocation attempt.
39. `tool_calls` counts every attempted operational tool dispatch, including controlled rejected calls.
40. `request_finalization()` does not consume `tool_calls`.
41. Provider-reported input/output tokens are charged to the existing usage counters when reported.
42. Every usage delta is reflected consistently at target and fleet scope.
43. Target and fleet hard budgets are checked before every new Stage 4 action.
44. Target-budget exhaustion may produce `WORKING → EXHAUSTED`; fleet-budget exhaustion alone does not relabel the target as target-level `EXHAUSTED`.
45. Concurrent provider calls cannot double-spend remaining shared fleet output-token capacity.
46. Permission enforcement occurs both when tools are exposed and when handlers execute.
47. Upstream repository/index/graph/enrichment authorities remain immutable.
48. Worker-correctable tool errors return bounded structured results and do not become semantic repair findings.
49. Runtime/provider/context interruptions cross the Stage 5 recovery boundary rather than becoming worker repair.
50. Stage 4 does not create checkpoints, define trace persistence, or decide retry/backoff.
51. Stage 4 does not create `TargetFinalizationRequest` or perform `WORKING → FINALIZING`.
52. Stage 4 never decides that a target is complete or accepted.
53. Initial and repair executions use the same worker loop and tool semantics.
54. Repair consumes the same original remaining target budget and does not create a new target task.

---

# 34. Stage 5+ deferments

Stage 4 intentionally leaves the following downstream contracts and policies unresolved.

### Stage 5 — Persistence & Recovery

```text
TaskEvent schema
TaskCheckpoint schema
atomic mutation/checkpoint protocol
trace persistence
provider retry/backoff
crash restoration
safe-phase reconstruction
in-flight reservation recovery
context reset after interruption
no-progress/stall persistence semantics
```

### Stage 6 — Finalization

```text
TargetFinalizationRequest schema
request persistence
pending_finalization_request_ref semantics
WORKING → FINALIZING transition details
```

### Stage 7 — Hard validation

```text
mechanical final completion gate
artifact/evidence consistency validation
final evidence requirements
TargetValidationReport
```

### Stage 8 — Target review

```text
review context
review rubric execution
TargetReviewVerdict
```

### Stage 9+

```text
repair routing
local target acceptance
fleet validation/reconciliation
accepted-result freezing
Repository Brain publication
```

Stage 4 remains specifically the worker's bounded repository-investigation and candidate-knowledge execution loop under runtime-controlled tools, budgets, permissions, and context.



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
execution-state overlay
recent tool-result working set
```

`working_summary` should be current when possible but is **not** a correctness prerequisite for reset.

Recovery remains valid using the other durable authorities when interruption occurs before the worker can update the summary.

No LLM summarizer, compaction agent or generic context-reset service is introduced.

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
