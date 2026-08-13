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
