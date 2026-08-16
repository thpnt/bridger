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
