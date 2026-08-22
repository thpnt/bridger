# Fleet reconciliation and locked catalog comparison

Fleet reconciliation receives the shared reviewer system prompt from volume 04 and the reconciliation rubric below in the sorted-key JSON user context. The context contains the active source binding, catalog identity, ownership rules, every complete runtime TargetDefinition, accepted target results, accepted artifact contents, and the Stage 11 fleet validation report. The request builder attaches no tools.

## Documentation discrepancy

The implemented runtime contract is the YAML in volumes 01–02. The locked catalog document below contains much richer target-contract sections—multiple named completion obligations and detailed scope/boundary guidance—than the current YAML runtime definitions, which each have one obligation and concise lists. This volume preserves the entire locked document for direct comparison; no reconciliation or inference has been applied.

### `src/prompts/reviewer/reconciliation.md`

```markdown
You are the Bridger memory fleet reconciler.

Your job is to perform a final artifact-level reconciliation across all locally accepted memory targets before the memory fleet can be accepted.

You are not a repository-discovery agent.

You do not navigate, inspect, or reinterpret the source repository.

You receive:
- the locked memory target catalog and semantic ownership rules;
- all locally accepted target folders;
- relevant target metadata and completion information;
- the Stage 11 fleet hard-validation PASS report.

Your job is to judge whether the collection works as one coherent Repository Brain knowledge layer.

# 1. Core responsibility

Review the fleet as a whole for:

- duplicated canonical ownership;
- contradictions across targets;
- terminology inconsistencies;
- semantic scope leakage;
- inappropriate abstraction levels;
- repeated detailed explanations that should have one canonical owner;
- weak cross-target division of responsibility;
- confusing or missing contextual links where related knowledge should connect;
- orientation quality of `repository/`;
- overall navigability and usefulness.

Do not independently verify repository truth.

Do not reopen accepted targets merely because you would have organized them differently.

# 2. Canonical ownership model

Use these primary ownership questions:

repository/
"What exists, where is it, and where should I look next?"

business-logic/
"What does the product/domain mean and what semantic rules must remain true?"

architecture/
"How is the running software structurally composed and how does execution move through it?"

data-and-state/
"What state exists, where does truth live, and how is it represented and changed technically?"

interfaces-and-integrations/
"What crosses meaningful system boundaries and what contracts govern those interactions?"

testing/
"How does the repository establish correctness and how should changes be verified?"

conventions/
"What recurring engineering patterns should contributors reproduce?"

operations/
"How does source become a configured, deployed, observable, operable runtime or release?"

design/
"What user-facing visual and interaction system does the implemented product embody?"

The target whose primary question is being answered owns the canonical detailed explanation.

Small contextual overlap is acceptable.
Detailed duplicated ownership is not.

Evidence may legitimately overlap across targets.

# 3. Important boundary rules

Apply these distinctions consistently:

Business Logic vs Architecture
- domain meaning/rules → Business Logic
- runtime realization/component mechanics → Architecture

Business Logic vs Data & State
- semantic state meaning/transitions → Business Logic
- technical state representation/lifecycle → Data & State

Business Logic vs Interfaces
- product meaning of external interaction → Business Logic
- boundary contract/mechanics → Interfaces & Integrations

Business Logic vs Design
- what users may do / what outcomes mean → Business Logic
- how that is presented/interacted with → Design

Architecture vs Data & State
- component-level state responsibility → Architecture
- actual state representation/authority/lifecycle → Data & State

Architecture vs Interfaces
- placement of boundary/adapters → Architecture
- contract crossing the boundary → Interfaces & Integrations

Architecture vs Operations
- behavior inside the running application → Architecture
- build/configure/deploy/observe/operate runtime → Operations

Architecture vs Design
- frontend software structure → Architecture
- user-facing design/interaction → Design

Architecture vs Conventions
- what the system currently is → Architecture
- recurring implementation pattern contributors should reproduce → Conventions

Testing vs Conventions
- verification strategy/infrastructure → Testing
- recurring style for individual tests → Conventions

Design vs Conventions
- what UI should look/feel/mean → Design
- engineering pattern used to implement it → Conventions

Repository vs all targets
- shallow orientation → Repository
- detailed explanation → specialist owner

# 4. Repository target

`repository/` is the canonical orientation/index layer.

It may summarize other targets one abstraction level above their detailed knowledge.

Flag if:
- it becomes a duplicate Architecture document;
- it reproduces detailed Business Logic, Data, Interfaces, Testing, Operations, Conventions, or Design content;
- its terminology materially conflicts with specialist targets;
- it fails to orient readers toward the deeper knowledge structure.

# 5. Duplication

Do not flag every repeated concept.

Acceptable overlap:
- one or two sentences needed to establish local context;
- terminology definitions necessary to make a target understandable;
- cross-target summaries;
- references to the same source evidence from different semantic perspectives.

Problematic duplication:
- two targets both attempt to be the canonical explanation of the same concern;
- large passages explain the same workflow from the same semantic perspective;
- neighboring targets repeat details instead of linking or summarizing;
- a target becomes broad enough that a specialist target is redundant.

When duplication exists, identify:
- the canonical owner;
- the target that should reduce/reframe its content;
- what bounded context may remain.

# 6. Contradictions

Identify contradictions between generated targets.

Examples:
- incompatible terminology for the same concept;
- conflicting descriptions of ownership;
- incompatible workflow descriptions;
- inconsistent component names/responsibilities;
- conflicting claims about where state or interfaces are owned.

Do not attempt to determine which description is factually correct from repository knowledge.

Instead:
- identify the conflict;
- identify affected targets;
- determine whether one target clearly violates semantic ownership;
- otherwise request reconciliation from the affected workers.

Preserve genuine explicit uncertainty rather than forcing artificial agreement.

# 7. Terminology

The fleet should use coherent repository/domain terminology.

Flag:
- one concept described under incompatible names without explanation;
- one name used for different concepts in ways likely to confuse retrieval;
- specialist targets using terminology inconsistent with `repository/` orientation;
- business terminology being replaced unnecessarily by implementation terminology.

Do not demand cosmetic word-for-word uniformity.

# 8. Abstraction levels

Check that:

repository/
is shallow.

business-logic/
is semantic and product/domain oriented.

architecture/
is structural/runtime oriented.

data-and-state/
is technical state/lifecycle oriented.

interfaces-and-integrations/
is boundary-contract oriented.

testing/
is verification-strategy oriented.

conventions/
is recurring contributor-practice oriented.

operations/
is source-to-runtime operational.

design/
is UI/UX/design-system oriented.

Flag targets whose abstraction level makes their purpose indistinguishable from a neighbor.

# 9. Cross-target links

Cross-target links are useful when they reduce duplication and improve navigation.

Do not require links everywhere.

Recommend links when:
- one target necessarily references another target's canonical concept;
- a workflow naturally crosses semantic boundaries;
- the reader would otherwise struggle to locate the detailed owner;
- duplicated explanation can be replaced by a concise summary plus reference.

# 10. Reconciliation outcome

Return:

PASS
or
NEEDS_WORK

Use PASS when:
- no material cross-target ownership, contradiction, duplication, terminology, or navigability issue remains.

Use NEEDS_WORK when:
- at least one material fleet-level issue requires target changes.

Do not directly edit artifacts.

# 11. Reconciliation output

Return only the requested structured result with:

- `outcome`: `pass` or `needs-work`;
- `summary`: a short assessment of the fleet as one knowledge system;
- `findings`: concrete acceptance-blocking issues only.

Each finding must contain:

- `criterion_id`;
- `affected_target_task_ids`: only targets that actually require mutation or
  repository reinvestigation;
- `affected_artifact_paths`: normalized fleet-relative paths when applicable;
- `message`: the concrete issue and relevant ownership decision;
- `required_outcome`: what must become true, without prescribing repair steps.

Use an empty findings list for `pass` and one or more findings for `needs-work`.
Do not assign finding IDs; the runtime owns identity.

Do not reopen unaffected targets.

Do not request repository rediscovery unless the repair itself genuinely requires the worker to revisit its own grounding.

The runtime decides the next execution step.
```

### `src/models/fleet_review.py:1-149`

```python
sed: src/models/fleet_review.py:1-149: No such file or directory
```

### `src/memory/fleet_review.py:55-180`

```python
sed: src/memory/fleet_review.py:55-180: No such file or directory
```

### `src/memory/fleet_review.py:475-535`

```python
sed: src/memory/fleet_review.py:475-535: No such file or directory
```

### `docs/bridger/product-system-design/bridger_memory_target_catalog.md`

```markdown
# Bridger — Memory Target Catalog and Completion Contracts

**Status:** Locked for V0  
**Date:** 12 August 2026  
**Scope:** Memory target taxonomy, semantic ownership boundaries, cross-target ownership rules, completion vocabulary, target activation, and target-level semantic completion contracts.  
**Next design phase:** Memory-agent runtime contracts, state, tools, prompts, validation, review, scheduling, persistence, and recovery.

---

## 1. Purpose

This document locks the knowledge-product contract for Bridger's V0 memory-agent fleet before runtime implementation begins.

The memory-agent harness already assumes that:

- memory targets are predefined;
- one bounded worker task is assigned per target folder;
- the target is a semantic folder scope, not a predetermined list of Markdown files;
- the worker owns repository exploration strategy;
- the worker owns the number, names, segmentation, and organization of Markdown files inside its target;
- target completion is semantic rather than filename-based;
- target contracts are predefined and versioned rather than negotiated at runtime;
- workers own repository semantic discovery and source grounding;
- the runtime owns lifecycle and completion;
- hard validation checks objective/mechanical integrity;
- reviewer agents judge generated artifact quality and coherence;
- production reviewers do not independently rediscover the repository.

This document defines the target catalog that those runtime mechanisms will later execute.

The design follows these product principles:

- the repository at the pinned revision remains the ultimate authority;
- deterministic repository facts remain separate from AI-derived knowledge;
- important knowledge must remain evidence-backed;
- uncertainty and contradictions must be represented explicitly;
- target boundaries should reflect durable semantic responsibilities rather than arbitrary code folders or technical layers;
- the resulting Repository Brain should preserve the kinds of understanding a staff-level engineer repeatedly uses when designing, debugging, reviewing, or extending a codebase;
- V0 should prefer a small number of strong semantic targets over a fragmented wiki taxonomy.

---

# 2. Locked V0 target catalog

The V0 target catalog is:

```text
repository/
business-logic/
architecture/
data-and-state/
interfaces-and-integrations/
testing/
conventions/
operations/
design/                     # conditional
```

All targets except `design/` are part of the normal V0 fleet.

`design/` is conditionally instantiated when deterministic repository facts indicate a meaningful frontend application or frontend/design-system stack, for example through a recognized framework/library such as React, Vue, Angular, Svelte, or another supported frontend technology.

The exact deterministic detection table is a later runtime/intake contract. The semantic decision is locked:

```text
recognized frontend stack detected
    → instantiate design/ exactly like any other target

no recognized frontend stack detected
    → design/ is absent from the fleet
```

`design/` is therefore not represented as a permanently present empty target and does not require the worker to decide whether it applies.

---

# 3. Global semantic ownership model

Each target owns a different primary repository-understanding question.

| Target | Canonical question |
|---|---|
| `repository/` | What is this repository, what are its major areas, and where should someone look next? |
| `business-logic/` | What product/domain behavior does the software implement, and what semantic rules must remain true? |
| `architecture/` | How is the software structurally composed, and how does runtime execution move through its major components? |
| `data-and-state/` | What state exists, where does truth live, who owns it, and how is it represented and changed technically? |
| `interfaces-and-integrations/` | What capabilities cross system boundaries, through what contracts, and how are those boundaries implemented? |
| `testing/` | How does the repository establish correctness, and how should a contributor verify a change? |
| `conventions/` | What recurring engineering rules and implementation patterns should contributors reproduce? |
| `operations/` | How does the repository become a runnable/released system, how is that runtime configured, and how is it operated? |
| `design/` | What user-facing visual system, interaction model, and UX/design decisions does the implemented product embody? |

This produces the following mental model:

```text
                         repository/
                   shallow orientation layer
                             │
              ┌──────────────┴──────────────┐
              │                             │
        PRODUCT MEANING                SYSTEM REALITY
              │                             │
      business-logic/                 architecture/
                                      data-and-state/
                               interfaces-and-integrations/
                                      operations/
                                      design/
              │                             │
              └──────────────┬──────────────┘
                             │
                    ENGINEERING PRACTICE
                             │
                       conventions/
                         testing/
```

This is a semantic map, not an execution dependency graph.

---

# 4. Global cross-target ownership rule

## 4.1 Canonical ownership principle

> **The target whose primary question is being answered owns the canonical detailed explanation. Other targets may repeat only enough context to explain their own concern, then should reference the canonical owner rather than reproducing its detail.**

The goal is to prevent duplicated ownership, not every repeated sentence.

A small amount of context-setting overlap is desirable when it makes an individual document understandable.

## 4.2 Evidence is not exclusively owned

The same source file, symbol, test, migration, configuration file, graph entity, or implementation range may support claims in multiple targets.

For example, one `PaymentService` may provide evidence for:

- product rules in `business-logic/`;
- runtime orchestration in `architecture/`;
- transaction behavior in `data-and-state/`;
- provider interaction in `interfaces-and-integrations/`;
- implementation patterns in `conventions/`;
- test strategy in `testing/`.

The target boundary applies to the **semantic explanation**, not to evidence ownership.

## 4.3 Context-setting overlap

Another target may summarize an externally owned concept when it is necessary to understand its own material.

Example:

```text
architecture/
    "Payment orchestration ultimately activates subscriptions."

business-logic/
    owns the detailed rules governing activation,
    eligibility, renewal, cancellation, and failure states.
```

The Architecture explanation is acceptable because it establishes component purpose. It should not reproduce the full subscription rule system.

## 4.4 Cross-target links

Cross-target links are desirable where they reduce duplication.

Targets do not need to depend on sibling generated knowledge during initial exploration. The repository remains the common authority.

The preferred lifecycle is:

```text
independent target generation
    ↓
local hard validation and target review
    ↓
all required targets locally accepted
    ↓
fleet reconciliation
    ↓
cross-target duplication / contradiction / terminology review
    ↓
reopen affected targets when needed
    ↓
refine links, ownership, summaries, and terminology
```

## 4.5 Concurrency

Targets may run concurrently by default.

No target is required to consume another target's generated knowledge to understand the repository.

`repository/` is the canonical orientation/index layer for consumers, but it is not an execution dependency for specialist workers.

---

# 5. Completion vocabulary

Every semantic completion obligation uses exactly four states:

```text
uninvestigated
covered
not-applicable
unknown
```

## 5.1 `uninvestigated`

Default state.

Meaning:

> The worker has not yet meaningfully attempted to discover, understand, or resolve this semantic obligation.

This implements the default-fail principle from the long-running-agent design.

No applicable criterion begins as passing.

## 5.2 `covered`

Meaning:

> The worker investigated the obligation and produced sufficiently grounded, useful knowledge for the target.

`covered` does not mean exhaustive knowledge of every file. It means the semantic responsibility has been investigated and documented to the depth required by the target contract.

## 5.3 `not-applicable`

Meaning:

> The worker investigated enough to establish that the concept does not meaningfully apply to this repository or target.

Examples:

- no queues/background jobs exist for an Architecture conditional criterion;
- no database migrations exist for a Data & State conditional criterion;
- no visual theming exists for a Design conditional criterion.

`not-applicable` must not be used as a shortcut for unexplored work.

## 5.4 `unknown`

Meaning:

> The worker investigated the obligation but could not establish a sufficiently grounded conclusion.

Typical causes include:

- conflicting implementations;
- contradictory source and documentation;
- inaccessible evidence;
- ambiguous behavior;
- incomplete implementation;
- unsupported inference;
- repository evidence insufficient to determine intent or actual behavior.

`unknown` is a legitimate terminal semantic state when the uncertainty itself is represented clearly.

## 5.5 Hard completion gate

A target cannot be successfully accepted while any required or applicable completion criterion remains:

```text
uninvestigated
```

Therefore:

```text
uninvestigated
    → unresolved / default fail

covered
not-applicable
unknown
    → semantically resolved states
```

This does not mean every `unknown` or `not-applicable` claim is automatically valid. Their justification remains subject to the relevant hard-validation, artifact-review, and offline-evaluation responsibilities defined later.

---

# 6. Common completion and evaluation ownership

The target contracts below identify completion responsibility conceptually across four layers.

## Worker responsibility — `W`

The worker owns:

- repository exploration;
- determining which conditional obligations apply;
- locating implementation evidence;
- tracing important workflows;
- interpreting repository behavior;
- grounding substantive claims;
- identifying unknowns and contradictions;
- producing useful target knowledge;
- moving criteria out of `uninvestigated` only after meaningful investigation.

## Hard deterministic validation — `H`

Hard validation can later enforce objective/mechanical integrity such as:

- no required criterion remains `uninvestigated`;
- allowed completion vocabulary is used;
- artifact and evidence references are structurally valid;
- referenced repository identities/revisions match;
- required generated sidecars/metadata resolve;
- target write boundaries are respected;
- no upstream deterministic/enrichment artifacts were modified;
- no sibling target workspace was modified.

Hard validation cannot determine whether a worker truly understood the repository correctly.

## Artifact reviewer — `R`

The production reviewer can judge properties visible from the generated artifact and explicit target contract:

- visible semantic-contract coverage;
- internal consistency;
- organization and navigability;
- unnecessary duplication;
- scope leakage;
- terminology;
- writing quality;
- useful depth;
- unsupported certainty visible from the prose;
- visible treatment of unknowns/contradictions;
- quality of file segmentation;
- cross-target ownership issues when reviewing the fleet.

The reviewer does not independently rediscover the repository.

## Offline Bridger evaluation — `O`

Offline evaluation determines properties production review cannot independently establish, including:

- correctness of central repository interpretations;
- whether important repository areas were missed;
- whether source evidence actually supports semantic claims;
- whether better or contradictory evidence existed elsewhere;
- whether `not-applicable` or `unknown` was justified by the repository;
- whether target investigation was sufficiently complete.

---

# 7. Cross-target boundary decisions

The following decisions resolve the important overlaps in the target catalog.

## 7.1 Business Logic ↔ Architecture

**Decision:** Business Logic owns domain/product meaning and rules. Architecture owns runtime realization and component interaction.

Useful test:

> If the implementation technology changed while the conceptual rule remained valid, it is probably Business Logic.

Examples:

```text
"A cancelled subscription cannot renew."
→ business-logic/

"RenewalController calls SubscriptionService,
which publishes RenewalRequested."
→ architecture/
```

Architecture may explain that a component exists to execute a domain capability, but detailed business semantics remain owned by Business Logic.

---

## 7.2 Business Logic ↔ Data & State

**Decision:** Business Logic owns the meaning of domain state and legal transitions. Data & State owns the technical representation, persistence, authority, consistency, and lifecycle of that state.

```text
"An order becomes fulfilment-eligible after payment."
→ business-logic/

"Order.status is persisted as an enum column and updated
inside the payment transaction."
→ data-and-state/
```

---

## 7.3 Business Logic ↔ Interfaces & Integrations

**Decision:** Business Logic owns what an external interaction means to the product. Interfaces & Integrations owns the contract and mechanics of crossing the boundary.

```text
"Successful payment activates entitlement."
→ business-logic/

"Stripe payment_succeeded is signature-verified,
mapped to PaymentSucceeded, and processed idempotently."
→ interfaces-and-integrations/
```

---

## 7.4 Business Logic ↔ Design

**Decision:** Business Logic owns what users may do and what outcomes mean. Design owns how those capabilities, states, constraints, and decisions are expressed through the UI/UX.

```text
"Only project owners may permanently delete a project."
→ business-logic/

"Destructive actions use a confirmation dialog,
danger styling, and explicit project-name confirmation."
→ design/
```

---

## 7.5 Business Logic ↔ Testing

**Decision:** Business Logic owns expected domain behavior. Testing owns how the repository verifies that behavior.

Testing may identify the test surfaces used to verify a workflow, but should not reproduce the complete business-rule documentation.

---

## 7.6 Architecture ↔ Data & State

**Decision:** Architecture owns where stateful responsibilities sit in the system. Data & State owns the state model and technical lifecycle itself.

```text
"BillingService coordinates subscription persistence."
→ architecture/

"Subscriptions are stored in tables X/Y; writes use transaction Z;
cache entries are invalidated after commit."
→ data-and-state/
```

---

## 7.7 Architecture ↔ Interfaces & Integrations

**Decision:** Architecture owns the existence and placement of system boundaries and adapters. Interfaces & Integrations owns their exposed/consumed contracts and boundary behavior.

```text
"WebhookAdapter feeds BillingApplicationService."
→ architecture/

"Webhook routes, payloads, authentication,
mapping, idempotency and provider errors."
→ interfaces-and-integrations/
```

---

## 7.8 Architecture ↔ Operations

**Decision:** Architecture owns how the application operates once running. Operations owns how source becomes a running system and how that runtime is built, configured, deployed, observed, and operated.

Useful rule:

```text
inside the running application
→ architecture/

getting, configuring, deploying, observing,
and keeping the application running
→ operations/
```

Example:

```text
"A background worker consumes retry jobs."
→ architecture/

"The worker runs as a separate Kubernetes deployment
with queue configuration injected from the environment."
→ operations/
```

Configuration can legitimately have multiple semantic perspectives:

- Operations: where runtime configuration comes from and how environments/secrets inject it;
- Architecture: how important configuration alters runtime composition/behavior;
- Business Logic: configuration values that directly encode product/domain rules.

---

## 7.9 Architecture ↔ Design

**Decision:** Architecture owns frontend software structure. Design owns user-facing structure, interaction, visual behavior, and UX decisions.

```text
"React Router defines route composition and TanStack Query
owns server-state synchronization."
→ architecture/

"The dashboard uses persistent side navigation; forms use inline
validation; mobile navigation collapses into a drawer."
→ design/
```

`design/` is not a frontend-architecture target.

---

## 7.10 Architecture ↔ Conventions

**Decision:** Architecture describes what this system actually is. Conventions describes recurring patterns contributors are expected to reproduce.

```text
"Billing is split into API, application, and adapter layers."
→ architecture/

"New integrations use an adapter implementing the provider interface
and live under integrations/<provider>."
→ conventions/
```

One architectural occurrence does not automatically become a repository convention.

---

## 7.11 Architecture ↔ Repository

**Decision:** Repository provides a shallow orientation map. Architecture provides the detailed runtime/system model.

```text
repository/
    "The monorepo contains an API, worker, and web application."

architecture/
    detailed composition and interaction of those applications.
```

---

## 7.12 Data & State ↔ Interfaces & Integrations

**Decision:** Data & State owns internal/canonical state representation. Interfaces & Integrations owns representations crossing system boundaries and mappings between external and internal models.

```text
"Internal Customer entity and persistence schema."
→ data-and-state/

"CustomerResponse API shape and mapping to/from Customer."
→ interfaces-and-integrations/
```

---

## 7.13 Data & State ↔ Operations

**Decision:** Product/application state belongs to Data & State. Operational/environment/infrastructure state belongs to Operations.

```text
database entities, application cache, persisted session
→ data-and-state/

deployment secrets, environment configuration, infrastructure state,
container volumes, CI artifacts
→ operations/
```

---

## 7.14 Interfaces & Integrations ↔ Operations

**Decision:** External systems used by product/application behavior belong to Interfaces & Integrations. External systems used to build, deploy, observe, or operate the application belong to Operations.

```text
Stripe, GitHub product integration, customer webhooks
→ interfaces-and-integrations/

Datadog, deployment registry, Terraform provider, CI service
→ operations/
```

Observability belongs primarily to Operations.

---

## 7.15 Design ↔ Conventions

**Decision:** Design owns what the interface should look, feel, and behave like. Conventions owns how engineers implement those decisions consistently.

```text
"Buttons have primary, secondary, and destructive semantic variants."
→ design/

"Button variants are expressed through cva() and components
do not use raw color classes."
→ conventions/
```

Design-token meaning belongs to Design. Engineering rules for consuming tokens belong to Conventions.

---

## 7.16 Design ↔ Testing

**Decision:** Design owns UI/UX behavior. Testing owns mechanisms for verifying it.

```text
"Modals trap focus and Escape dismisses them."
→ design/

"Modal accessibility behavior is verified with Playwright and axe."
→ testing/
```

---

## 7.17 Testing ↔ Conventions

**Decision:** Testing owns verification strategy, levels, environments, and verification surfaces. Conventions owns how individual tests are normally structured and written.

```text
"Unit vs integration vs E2E strategy."
→ testing/

"Fixture naming and Arrange/Act/Assert pattern."
→ conventions/
```

---

## 7.18 Repository ↔ all targets

**Decision:** `repository/` may summarize every target one abstraction level above its canonical detail, solely for orientation.

It may answer:

```text
What exists?
Where is it?
Where should I look next?
```

It should not attempt to answer in depth:

```text
How exactly does it work?
What are all of its rules?
```

---

# 8. Cross-cutting concerns that are not standalone V0 targets

## 8.1 Security

Security is important but remains cross-cutting in V0.

Ownership follows the semantic concern:

```text
business authorization / domain eligibility
→ business-logic/

API authentication / protocol security
→ interfaces-and-integrations/

runtime trust/process boundaries
→ architecture/

secrets / deployment permissions / operational security
→ operations/

security verification
→ testing/

secure coding patterns
→ conventions/

privacy/security UX
→ design/
```

A separate `security/` target is not part of V0.

## 8.2 Workflows

There is no generic `workflows/` target.

Workflow ownership depends on the question:

```text
checkout workflow semantics
→ business-logic/

request-processing runtime path
→ architecture/

deployment workflow
→ operations/

webhook exchange
→ interfaces-and-integrations/
```

## 8.3 Failure behavior

There is no generic `failures/` target.

Failures stay with the semantic owner:

```text
business rejection
→ business-logic/

transaction/consistency failure
→ data-and-state/

provider/protocol failure
→ interfaces-and-integrations/

runtime recovery/retry behavior
→ architecture/

deployment/operational failure
→ operations/
```

## 8.4 Unknowns and contradictions

Unknowns and contradictions are properties of every target.

They must never be hidden merely to make a target appear complete.

---

# 9. Target contract — `business-logic/`

## 9.1 Purpose

Answer:

> **What product/domain behavior does this repository implement, and what semantic rules must remain true regardless of incidental technical implementation?**

For libraries, developer tools, frameworks, or infrastructure repositories, "business logic" means the repository's domain/product semantics rather than strictly commercial rules.

## 9.2 Expected abstraction

Deep semantic understanding.

Implementation-grounded, but technology-independent wherever possible.

The target should explain what the software *means and guarantees*, not merely list the services/classes that execute it.

## 9.3 Always-relevant semantic scope

The worker should attempt to discover, where meaningful:

- primary domain/product concepts and terminology;
- important actors or categories of actor;
- major user/system actions;
- principal product/domain workflows;
- business/domain rules;
- invariants;
- meaningful validation and eligibility rules;
- meaningful authorization rules;
- domain states;
- allowed, forbidden, and important state transitions;
- business-significant calculations;
- product outcomes and side effects;
- important relationships between domain concepts;
- domain-specific exceptional/failure paths;
- implementation locations necessary to ground and navigate the behavior.

## 9.4 Conditional coverage

When present:

- pricing and billing;
- subscriptions and entitlements;
- quotas and limits;
- approvals;
- scheduling rules;
- domain-specific permissions;
- lifecycle rules;
- domain-specific calculations;
- regulatory/domain constraints represented in code;
- external-provider interactions whose semantics affect product behavior.

Absent concepts should resolve to `not-applicable`, not fabricated sections.

## 9.5 Explicit exclusions

Do not canonically own:

- startup/bootstrap;
- dependency injection;
- generic routing;
- generic middleware;
- component construction;
- persistence schema detail;
- database/transaction implementation detail;
- provider protocol detail;
- deployment;
- operational configuration;
- test infrastructure;
- coding conventions;
- visual presentation and interaction design.

## 9.6 Boundary examples

```text
belongs:
"An invoice cannot be paid twice."

does not belong:
"PaymentService is instantiated during FastAPI lifespan."
```

```text
belongs:
"A successful payment activates the subscription."

does not belong:
"The Stripe client is created from environment configuration."
```

```text
belongs:
"A suspended account cannot create new projects."

does not belong:
"Authorization middleware reads the bearer token."
```

## 9.7 Investigation expectations

A competent investigation should:

1. identify the principal domain/product areas;
2. establish core terminology;
3. locate major actions/workflows;
4. trace important workflows from trigger to domain outcome;
5. identify decisions, validations, invariants, and legal/illegal transitions;
6. inspect alternate/error paths with domain meaning;
7. verify important rules against implementation rather than names or graph labels alone;
8. inspect tests/config/docs when they materially clarify or contradict behavior;
9. preserve unresolved ambiguity.

For central workflows, the investigation should generally establish:

```text
trigger
→ domain decision/rule
→ meaningful state transition
→ business-significant side effects
→ alternate/failure outcomes
```

## 9.8 Evidence expectations

- Central domain rules require implementation-level source evidence.
- Tests are strong supporting evidence for invariants, state transitions, and edge cases.
- Tests should not replace implementation evidence when implementation is accessible.
- Repository documentation may establish terminology and intended behavior.
- Source implementation remains authoritative when documentation conflicts with it; the contradiction should be surfaced.
- Graph/community evidence is useful for discovery and navigation, but graph structure alone is not proof of business behavior.
- Central workflows should normally be grounded across the relevant implementation chain, not from a single isolated source location.

## 9.9 Completion contract

Each applicable obligation begins `uninvestigated`.

A successful candidate must resolve the following semantically:

| Obligation | Expected terminal outcome | Primary enforcement |
|---|---|---|
| Principal domain/product concepts are identified and related | `covered`, `not-applicable`, or justified `unknown` | W / R / O |
| Major user/system actions are understood | resolved | W / R / O |
| Central product/domain workflows are explained end-to-end semantically | resolved | W / R / O |
| Important rules and invariants are explicit | resolved | W / R / O |
| Important domain states and transitions are explicit | resolved | W / R / O |
| Important domain validation/eligibility rules are covered | resolved | W / R / O |
| Business-significant authorization rules are covered when present | resolved | W / R / O |
| Business-significant side effects are covered | resolved | W / R / O |
| Domain-specific failures/alternate outcomes are covered | resolved | W / R / O |
| Conditional domain areas are explicitly resolved | no `uninvestigated` | H / W |
| Important knowledge remains source-grounded | valid evidence mechanically; semantic correctness offline | H / W / O |
| Unknowns/contradictions are explicit rather than converted to certainty | visible quality | W / R / O |

## 9.10 Output-quality expectations

The result should:

- use repository/domain terminology consistently;
- synthesize behavior rather than list files;
- provide useful depth on important rules;
- avoid generic domain-analysis filler;
- separate semantic rules from incidental technical implementation;
- remain navigable for humans and coding agents;
- make implementation locations discoverable without becoming Architecture;
- avoid repeating detailed protocol/persistence/testing explanations owned elsewhere.

A downstream agent should be able to answer:

> **If I change this behavior, which semantic rules and outcomes must I preserve?**

---

# 10. Target contract — `architecture/`

## 10.1 Purpose

Answer:

> **How is the software structurally composed, and how does runtime execution move through its major components?**

## 10.2 Expected abstraction

Deep structural and runtime implementation understanding.

Architecture is the system model, not the repository orientation page and not the product/domain model.

## 10.3 Always-relevant semantic scope

Where meaningful:

- applications/services/packages with runtime significance;
- principal runtime entrypoints;
- bootstrap and initialization;
- runtime composition;
- major components and responsibilities;
- subsystem boundaries;
- dependency direction;
- important internal interfaces;
- main control/execution paths;
- orchestration;
- synchronous vs asynchronous execution;
- component-level state ownership;
- major architectural patterns;
- extension/plugin points;
- important runtime error propagation and recovery behavior.

## 10.4 Conditional coverage

When present:

- background workers;
- queues/events;
- schedulers;
- multi-process architecture;
- distributed runtime boundaries;
- frontend runtime architecture;
- concurrency/parallelism;
- plugin/extension systems;
- caching where architecturally significant;
- event-driven orchestration;
- runtime feature/config composition.

## 10.5 Explicit exclusions

Do not canonically own detailed:

- domain/business rules;
- domain state semantics;
- data schema/storage lifecycle;
- public/external protocol contracts;
- provider-specific contract mechanics;
- deployment and environment topology;
- visual/interaction design;
- testing strategy;
- contributor conventions.

## 10.6 Boundary examples

```text
belongs:
"WebhookAdapter routes validated events to BillingApplicationService."

does not belong:
"A successful payment activates a subscription."
```

```text
belongs:
"The worker process consumes retry jobs and invokes RetryCoordinator."

does not belong:
"The worker is deployed as three Kubernetes replicas."
```

```text
belongs:
"TanStack Query owns server-state synchronization in the frontend runtime."

does not belong:
"Mobile navigation collapses into a drawer."
```

## 10.7 Investigation expectations

A competent investigation should:

1. identify runtime entry surfaces;
2. establish major applications/processes;
3. identify major structurally important components;
4. inspect responsibilities at source level;
5. establish dependency direction;
6. trace principal runtime paths;
7. identify asynchronous/background paths;
8. establish component-level state responsibility;
9. understand runtime composition/initialization;
10. identify extension mechanisms and architectural patterns;
11. examine important failure/recovery/control behavior.

Graph communities and centrality are useful orientation signals but do not themselves prove architectural meaning.

## 10.8 Evidence expectations

- Deterministic graph/import relations are strong evidence for structural relationships.
- Manifest/configuration declarations can establish entrypoints and process surfaces.
- Runtime responsibility and control-flow claims require source inspection.
- Tests may support lifecycle and architectural behavior.
- Documentation may supplement architectural intent but must not override contradictory implementation without surfacing the conflict.
- Central execution paths should normally use multiple evidence locations where the flow crosses meaningful components.

## 10.9 Completion contract

| Obligation | Expected terminal outcome | Primary enforcement |
|---|---|---|
| Principal runtime entrypoints are identified | resolved | W / R / O |
| Major runtime applications/processes/components are identified | resolved | W / R / O |
| Major component responsibilities are explained | resolved | W / R / O |
| Important dependencies/interactions are explained | resolved | W / R / O |
| Principal execution/control paths are explained mechanically | resolved | W / R / O |
| Initialization/bootstrap/composition is understood | resolved | W / R / O |
| Async/background execution is covered when present | resolved | W / R / O |
| Component-level state ownership is identified | resolved | W / R / O |
| Major extension/plugin mechanisms are covered when present | resolved | W / R / O |
| Important runtime error/recovery behavior is covered when present | resolved | W / R / O |
| Conditional runtime concerns have no `uninvestigated` state | resolved | H / W |
| Evidence references are mechanically valid | pass | H |
| Artifact stays within Architecture scope | acceptable | R |
| Important architecture is not replaced by file-by-file inventory or generic prose | acceptable | R / O |

## 10.10 Output-quality expectations

The result should:

- describe the system in terms of responsibilities and interactions;
- make important execution paths navigable;
- avoid a file-by-file inventory;
- avoid vague architecture labels unsupported by concrete system structure;
- separate runtime mechanics from Business Logic;
- keep persistence/interface/operations detail at the level needed to explain architecture, then defer detailed ownership to specialist targets.

A downstream agent should be able to answer:

> **Where does this change belong, what runtime path am I entering, and which major components will it affect?**

---

# 11. Target contract — `data-and-state/`

## 11.1 Purpose

Answer:

> **What state exists, where does truth live, who owns it, and how is it represented, read, changed, and kept consistent?**

## 11.2 Expected abstraction

Deep technical state and persistence model.

## 11.3 Always-relevant semantic scope

Where meaningful:

- important state categories;
- canonical/authoritative stores;
- persisted entities/models;
- state ownership;
- read/write ownership;
- data-access boundaries;
- mutation paths;
- consistency assumptions;
- transaction boundaries;
- data lifecycle;
- serialization;
- persistent vs ephemeral state;
- derived vs authoritative state.

## 11.4 Conditional coverage

When present:

- relational/NoSQL schemas;
- migrations;
- caches;
- cache invalidation;
- sessions;
- browser/client state;
- filesystem state;
- event stores;
- object/blob storage;
- queues carrying durable state;
- derived/materialized views;
- replication;
- optimistic/pessimistic locking;
- retention/expiry;
- data versioning;
- schema evolution.

## 11.5 Explicit exclusions

Do not canonically own:

- semantic meaning of domain transitions;
- complete system architecture;
- public/external API shapes;
- deployment/environment state;
- infrastructure state;
- secrets/config injection;
- business rules merely because schemas constrain them.

## 11.6 Boundary examples

```text
belongs:
"Subscription status is persisted in the subscriptions table and
updated transactionally with entitlement records."

does not belong:
"A subscription enters grace period after renewal failure."
```

```text
belongs:
"CustomerResponse maps from the canonical Customer entity."

does not belong:
"The public CustomerResponse contract contains fields X/Y/Z."
```

## 11.7 Investigation expectations

For each significant state area, establish:

```text
what state exists
→ what is authoritative
→ where it is represented/stored
→ who reads it
→ who changes it
→ how changes are coordinated
→ what derived/cached copies exist
→ how lifecycle/versioning/invalidation works
```

The worker should trace important state through both definition and usage, rather than documenting schemas in isolation.

## 11.8 Evidence expectations

- Schemas, migrations, model declarations, persistence configuration, and serialization definitions are primary evidence for representation.
- Source-level readers/writers are required for ownership/lifecycle claims.
- Tests are useful supporting evidence for transactions, persistence, migrations, consistency, and cache invalidation.
- Graph structure can help locate state owners but is not sufficient for semantics such as authoritative ownership or transactional guarantees.
- Documentation can supplement lifecycle expectations; executable configuration/source remains authoritative.

## 11.9 Completion contract

| Obligation | Expected terminal outcome | Primary enforcement |
|---|---|---|
| Principal state categories/stores are identified | resolved | W / R / O |
| Authoritative sources of truth are distinguished from derived/cache state | resolved | W / R / O |
| Important persisted/data models are explained technically | resolved | W / R / O |
| Read/write ownership is explained | resolved | W / R / O |
| Important mutation/lifecycle paths are covered | resolved | W / R / O |
| Consistency/transaction semantics are covered where present | resolved | W / R / O |
| Migration/schema evolution is covered where present | resolved | W / R / O |
| Caches/derived/materialized state and invalidation are covered where present | resolved | W / R / O |
| Important retention/versioning/locking mechanisms are covered where present | resolved | W / R / O |
| Conditional state concerns contain no `uninvestigated` criteria | resolved | H / W |
| Unknown/contradictory ownership or lifecycle behavior is explicit | acceptable | W / R / O |

## 11.10 Output-quality expectations

The target should emphasize:

- authority;
- ownership;
- lifecycle;
- consistency;
- relationships between state representations.

It should not devolve into an exhaustive field dictionary.

A downstream agent should be able to answer:

> **If I modify this state, schema, cache, or persistence path, what else must I understand and preserve?**

---

# 12. Target contract — `interfaces-and-integrations/`

## 12.1 Purpose

Answer:

> **What capabilities cross repository/system boundaries, through what contracts, and how are those boundaries implemented?**

## 12.2 Expected abstraction

Boundary-contract and external-interaction understanding.

## 12.3 Always-relevant semantic scope

For significant boundaries:

- direction: inbound/outbound;
- purpose;
- entry/exit surface;
- request/input/payload contract;
- response/output contract;
- serialization;
- mapping to/from internal models;
- authentication mechanics;
- authorization mechanics at the boundary;
- idempotency;
- timeouts/retries where relevant;
- boundary/provider-specific failure behavior;
- versioning/compatibility;
- important callbacks/webhooks/events.

## 12.4 Conditional interface families

When present:

- HTTP/REST;
- GraphQL;
- RPC;
- CLI;
- public library/module APIs;
- webhooks;
- messages/events;
- sockets/streams;
- plugin interfaces;
- external provider SDKs/APIs;
- generated clients;
- external callback flows;
- rate limits encoded by repository behavior.

## 12.5 Explicit exclusions

Do not canonically own:

- underlying product/domain rules;
- generic internal component interactions;
- internal persistence details;
- deployment/observability provider integrations;
- frontend presentation.

## 12.6 Boundary examples

```text
belongs:
"Stripe payment_succeeded is verified, decoded, mapped,
and processed idempotently."

does not belong:
"Successful payment activates entitlement."
```

```text
belongs:
"CustomerResponse is the external API representation and maps
to internal Customer."

does not belong:
"Customer persistence uses PostgreSQL table customers."
```

## 12.7 Investigation expectations

For each significant boundary:

```text
contract definition
→ adapter/client/handler
→ validation/authentication
→ mapping
→ internal handoff
→ response/callback
→ boundary-specific failure/retry behavior
```

A dependency appearing in a manifest is not sufficient evidence that it is a meaningful integration.

## 12.8 Evidence expectations

- Routes, schemas, protocol definitions, event definitions, public exports, and SDK adapter definitions are primary evidence.
- Source handlers/clients/adapters are required for runtime mapping and behavior.
- Contract/integration tests are especially valuable.
- External facts not represented in the repository must not be filled in from model knowledge as though repository-grounded.
- Documentation may supplement declared contracts but conflicts must be surfaced.
- Graph relations help locate boundaries but do not prove protocol semantics.

## 12.9 Completion contract

| Obligation | Expected terminal outcome | Primary enforcement |
|---|---|---|
| Significant inbound interfaces are identified | resolved | W / R / O |
| Significant outbound integrations are identified | resolved | W / R / O |
| Important contracts/payloads and mappings are explained | resolved | W / R / O |
| Boundary authentication/security mechanics are covered when present | resolved | W / R / O |
| Error/retry/idempotency semantics are covered where relevant | resolved | W / R / O |
| Callbacks/events/webhooks are covered where present | resolved | W / R / O |
| Versioning/compatibility constraints are covered where present | resolved | W / R / O |
| Boundary-to-internal implementation handoff is clear | resolved | W / R / O |
| Conditional interface families have no `uninvestigated` criteria | resolved | H / W |
| External unknowns remain explicit rather than invented | acceptable | W / R / O |

## 12.10 Output-quality expectations

The target should allow an engineer or coding agent to answer:

> **If I change this boundary, who consumes it, what contract must remain compatible, and where is the adaptation performed?**

Avoid duplicating Architecture's internal runtime structure or Business Logic's product semantics.

---

# 13. Target contract — `testing/`

## 13.1 Purpose

Answer:

> **How does this repository establish correctness, and how should a contributor verify a change?**

## 13.2 Expected abstraction

Verification strategy and practical validation model.

## 13.3 Always-relevant semantic scope

Where meaningful:

- test frameworks;
- test configuration;
- test layout;
- principal test categories/layers;
- standard execution commands;
- fixture/factory strategy;
- mocks/fakes/stubs;
- isolation model;
- representative testing patterns;
- relationship between change type and appropriate test level.

## 13.4 Conditional coverage

When present:

- integration tests;
- database tests;
- E2E/browser tests;
- contract tests;
- snapshot tests;
- visual tests;
- accessibility tests;
- performance tests;
- security tests;
- test containers/services;
- CI test execution;
- coverage tooling;
- sharding/parallelism;
- special local validation workflows.

## 13.5 Explicit exclusions

Do not canonically own:

- complete descriptions of domain behavior being tested;
- production architecture;
- CI/release mechanics beyond their role in executing verification;
- generic individual-test coding style that belongs to Conventions.

## 13.6 Boundary examples

```text
belongs:
"Subscription transitions are primarily verified with integration
tests using fixture X and database rollback isolation."

does not belong:
"Subscription enters grace period after failed renewal."
```

```text
belongs:
"E2E tests run in Playwright against the built web application."

does not belong:
"The web application is deployed through Kubernetes."
```

## 13.7 Investigation expectations

The worker should inspect:

- test configuration;
- test commands;
- representative unit tests;
- representative integration tests when present;
- representative E2E/contract/visual tests when present;
- fixtures and factories;
- mocks/fakes/external-service handling;
- CI definitions showing what verification actually runs.

It should not infer strategy from only one test directory or one config file.

## 13.8 Evidence expectations

- Test source/configuration is primary evidence.
- Manifest scripts establish commands.
- CI workflows are strong evidence for automatically executed suites.
- Production source may clarify what tests target, but should not turn Testing into a duplicate behavior target.
- Repository docs may supplement contributor workflows.

## 13.9 Completion contract

| Obligation | Expected terminal outcome | Primary enforcement |
|---|---|---|
| Test frameworks and principal levels are identified | resolved | W / R / O |
| Test organization is explained | resolved | W / R / O |
| Fixtures/factories/setup are understood | resolved | W / R / O |
| Isolation and external-dependency strategy are covered | resolved | W / R / O |
| Standard validation commands are identified | resolved | W / R / O |
| Change types are mapped to appropriate verification surfaces | resolved | W / R / O |
| CI-triggered verification is identified when present | resolved | W / R / O |
| E2E/contract/visual/accessibility/etc. strategies are covered when present | resolved | W / R / O |
| Material testing gaps discovered during investigation are surfaced without claiming exhaustive gap analysis | resolved | W / R / O |
| Conditional testing categories have no `uninvestigated` criteria | resolved | H / W |

## 13.10 Output-quality expectations

The target should be practical rather than encyclopedic.

A downstream agent should be able to answer:

> **I changed X. Which tests should I add or run, and how are tests normally executed and structured here?**

---

# 14. Target contract — `conventions/`

## 14.1 Purpose

Answer:

> **What recurring engineering rules and implementation patterns should future contributors reproduce?**

## 14.2 Expected abstraction

Normative or recurring repository practice.

Conventions describe repeatable local engineering expectations, not isolated architecture decisions.

## 14.3 Semantic scope

Potential conventions include:

- naming;
- file/folder placement;
- module organization;
- import/dependency patterns;
- controller/service/repository patterns;
- dependency injection/construction;
- type/schema usage;
- error handling;
- logging;
- configuration access;
- async/concurrency style;
- data-access patterns;
- interface/API implementation style;
- frontend component implementation style;
- test-writing style;
- formatting;
- linting;
- static-analysis expectations.

## 14.4 Evidence threshold for a convention

A single observed implementation is not automatically a repository convention.

A convention should normally be supported by at least one of:

```text
explicit repository instruction or tooling/configuration
OR
a clear recurring implementation pattern across representative examples
```

The resulting knowledge should conceptually distinguish:

```text
ENFORCED / EXPLICIT
OBSERVED / RECURRING
LOCAL / AREA-SPECIFIC
```

No concrete persistence schema for these labels is locked here.

## 14.5 Explicit exclusions

Do not canonically own:

- one-off architecture decisions;
- product/domain rules;
- design-system semantics;
- testing strategy;
- generic industry best practices not grounded in the repository.

## 14.6 Boundary examples

```text
belongs:
"New provider integrations implement the Provider interface
and live under integrations/<provider>."

does not belong:
"The billing subsystem currently contains StripePaymentAdapter."
```

```text
belongs:
"Button variants are implemented through the shared cva() definition."

does not belong:
"Destructive buttons use the product's danger semantic color."
```

## 14.7 Investigation expectations

A competent worker should:

1. inspect explicit repository instructions and tool configuration;
2. sample representative code across multiple important areas;
3. identify repeated patterns;
4. distinguish repository-wide from local conventions;
5. avoid generalizing from one example;
6. distinguish enforced rules from observed patterns;
7. surface conflicting conventions where different areas legitimately differ.

## 14.8 Evidence expectations

- Formatting/lint/type/tool configuration is strong evidence for enforced conventions.
- Repository instructions/docs are strong evidence for explicit contributor rules.
- Observed conventions should use representative repeated examples.
- A single example may support a local pattern only when its scope is explicitly narrow and contextualized.
- External best practices are not evidence.

## 14.9 Completion contract

| Obligation | Expected terminal outcome | Primary enforcement |
|---|---|---|
| Major repository-wide naming/layout rules are identified | resolved | W / R / O |
| Recurring structural implementation patterns are identified | resolved | W / R / O |
| Error/logging/config patterns are covered when recurrent | resolved | W / R / O |
| Type/schema patterns are covered where recurrent | resolved | W / R / O |
| Data/interface/test/frontend implementation conventions are covered where recurrent | resolved | W / R / O |
| Enforced vs observed patterns are not presented with equal certainty | resolved | W / R / O |
| Local conventions are scoped rather than incorrectly generalized | resolved | W / R / O |
| Generic advice unsupported by the repository is absent | acceptable | R / O |
| Relevant convention dimensions have no `uninvestigated` criteria | resolved | H / W |

## 14.10 Output-quality expectations

The target should be concise, evidence-backed, and highly actionable.

A downstream agent should be able to answer:

> **How should code that looks native to this repository be structured and written?**

---

# 15. Target contract — `operations/`

## 15.1 Purpose

Answer:

> **How does this repository become a runnable/released system, how is that runtime configured, and how is it operated?**

`operations/` intentionally includes build, packaging, delivery, deployment, runtime configuration, observability, and operational lifecycle.

## 15.2 Expected abstraction

Source-to-runtime operational model.

## 15.3 Always-relevant semantic scope

Where meaningful:

- build/package process;
- runtime prerequisites;
- important developer/operator commands;
- configuration/environment model.

## 15.4 Conditional coverage

When present:

- containers;
- CI/CD;
- release/versioning;
- package publishing;
- deployment manifests;
- infrastructure-as-code;
- environments;
- secrets injection;
- runtime topology;
- deployment-time migrations;
- scheduled operational jobs;
- feature/config rollout;
- health checks;
- metrics;
- logging pipelines;
- tracing;
- alerting;
- rollback/recovery;
- scaling;
- production troubleshooting mechanisms.

## 15.5 Explicit exclusions

Do not canonically own:

- in-process component architecture;
- domain/business rules;
- product-facing external integrations;
- application data model;
- testing strategy itself;
- coding conventions.

## 15.6 Boundary examples

```text
belongs:
"The retry worker runs as a separate Kubernetes deployment
configured through environment variables."

does not belong:
"The retry worker consumes RetryRequested and invokes RetryCoordinator."
```

```text
belongs:
"Datadog receives production traces through OpenTelemetry configuration."

does not belong:
"Stripe is called during payment creation."
```

## 15.7 Investigation expectations

Trace the source-to-runtime lifecycle to the extent represented by the repository:

```text
source
→ build/package artifact
→ configuration/environment
→ deployment/release
→ runtime processes/topology
→ health/observability
→ recovery/rollback
```

Do not invent deployment or operations practices absent from repository evidence.

## 15.8 Evidence expectations

- Build scripts, manifests, CI workflows, Dockerfiles, IaC, deployment files, environment templates, and observability configuration are primary evidence.
- Source inspection is useful for health endpoints, configuration loading, lifecycle hooks, telemetry initialization, or runtime mode switches.
- Documentation may supplement operational procedures.
- Executable configuration/source is authoritative when documentation conflicts.
- Provider/platform behavior not encoded in the repository should not be invented.

## 15.9 Completion contract

| Obligation | Expected terminal outcome | Primary enforcement |
|---|---|---|
| Build/package path is identified | resolved | W / R / O |
| Runtime prerequisites and principal configuration model are explained | resolved | W / R / O |
| Environment distinctions are covered where present | resolved | W / R / O |
| CI/CD and release flow are covered where present | resolved | W / R / O |
| Deployment/runtime topology is covered where present | resolved | W / R / O |
| Secrets/config injection is covered where present | resolved | W / R / O |
| Health/observability mechanisms are covered where present | resolved | W / R / O |
| Migration/rollout/rollback mechanisms are covered where present | resolved | W / R / O |
| Scaling/scheduled operational mechanisms are covered where present | resolved | W / R / O |
| Important operator/developer commands are grounded | resolved | W / R / O |
| Conditional operational concerns have no `uninvestigated` criteria | resolved | H / W |

## 15.10 Output-quality expectations

A downstream engineer or agent should be able to answer:

> **How do I get this software from checkout to running/released, how is that runtime configured, and where do I look when its operational environment matters?**

---

# 16. Target contract — `design/`

## 16.1 Activation

`design/` is a conditional target.

It is instantiated deterministically when Bridger detects a recognized frontend framework/library or equivalent meaningful UI/design-system stack.

Examples include React and other supported common frontend technologies.

When no supported frontend stack is detected, `design/` is absent from the target fleet.

Once instantiated, it behaves like every other memory target:

- same lifecycle;
- same completion vocabulary;
- same worker autonomy;
- same validation/reviewer model;
- same repository-grounding expectations.

## 16.2 Purpose

Answer:

> **What user-facing design system, UX patterns, visual language, interaction model, and recurring design decisions does the implemented product embody?**

This target is intended to be a repository-grounded, substantially improved replacement for a traditional static `design.md`.

## 16.3 Expected abstraction

Product/interface design reference.

Not frontend engineering architecture.

## 16.4 Always-relevant semantic scope when the target is activated

Where meaningful:

### Visual language

- color system;
- typography;
- spacing;
- sizing;
- radii;
- borders;
- elevation/shadows;
- semantic tokens;
- theming;
- iconography;
- imagery/brand assets;
- motion/animation.

### Component/design system

- reusable UI primitives;
- semantic variants;
- component composition;
- forms;
- buttons/actions;
- navigation;
- overlays/dialogs;
- feedback components;
- data-display patterns.

The goal is to capture design decisions and rules, not produce an exhaustive component inventory.

### Layout and hierarchy

- page shells;
- navigation structure;
- common layouts;
- density;
- hierarchy;
- responsive patterns;
- mobile/desktop adaptation.

### Interaction and UX

- interaction patterns;
- feedback;
- loading states;
- empty states;
- error states;
- confirmations;
- destructive actions;
- optimistic interaction where visible;
- progressive disclosure;
- keyboard behavior;
- focus behavior.

### Accessibility

Where represented:

- semantic markup patterns;
- focus management;
- keyboard navigation;
- ARIA patterns;
- contrast/theme concerns;
- reduced motion;
- screen-reader behavior.

## 16.5 Conditional coverage

When present:

- Storybook/design-system tooling;
- multiple themes;
- white-labeling;
- localization-related layout behavior;
- charts/data visualization;
- rich editors;
- drag-and-drop;
- onboarding flows;
- mobile-specific navigation;
- visual-regression testing surfaces;
- design-token generation pipelines.

## 16.6 Explicit exclusions

Do not canonically own:

- React/Vue/etc. architecture;
- state-management architecture;
- routing implementation architecture;
- API integration implementation;
- domain/business rules;
- backend behavior;
- component filename/naming conventions;
- CSS/framework coding conventions;
- testing strategy.

## 16.7 Boundary examples

```text
belongs:
"Destructive actions use a danger semantic variant and require
an explicit confirmation interaction."

does not belong:
"Only project owners may delete projects."
```

```text
belongs:
"Dashboard navigation becomes a drawer on small viewports."

does not belong:
"React Router owns route composition."
```

```text
belongs:
"Button variants express primary, secondary, and destructive hierarchy."

does not belong:
"Button variants are implemented through cva()."
```

## 16.8 Investigation expectations

A competent worker should sample across:

- design tokens/themes;
- global styles;
- reusable UI components;
- representative page/layout components;
- major user-facing states;
- responsive implementations;
- assets/icons;
- Storybook/stories/docs when present;
- accessibility utilities/patterns;
- representative visual/component tests where present.

The worker should inspect multiple representative screens/components before generalizing a local visual choice into a product-wide design decision.

## 16.9 Evidence expectations

- Stylesheets, theme/token definitions, component implementations, and layout code are primary evidence.
- Storybook stories and committed design docs are useful supporting evidence.
- Repository assets/screenshots may provide direct visual evidence.
- Static source may not establish exact rendered visual quality; uncertain visual interpretation should remain explicit rather than overstated.
- Actual rendered visual fidelity is primarily an offline-evaluation concern unless future runtime tools provide direct render/browser evidence.

## 16.10 Completion contract

| Obligation | Expected terminal outcome | Primary enforcement |
|---|---|---|
| Core visual language is identified | resolved | W / R / O |
| Design-token/theme system is explained where present | resolved | W / R / O |
| Important reusable component/design patterns are explained | resolved | W / R / O |
| Major layout/navigation patterns are explained | resolved | W / R / O |
| Responsive behavior is covered where present | resolved | W / R / O |
| Important interaction/feedback patterns are covered | resolved | W / R / O |
| Loading/empty/error/destructive states are covered where materially standardized | resolved | W / R / O |
| Accessibility patterns are covered where implemented | resolved | W / R / O |
| Design-system tooling/documentation is covered where present | resolved | W / R / O |
| One-off visual choices are not generalized into global rules | acceptable | R / O |
| Conditional design concerns have no `uninvestigated` criteria | resolved | H / W |

## 16.11 Output-quality expectations

The result should allow an engineer or coding agent to create a new UI surface that:

- looks consistent with the existing product;
- follows established interaction patterns;
- reuses the correct semantic design system;
- handles common states consistently;
- respects known responsive/accessibility behavior.

It should not become a frontend architecture document or raw component catalog.

---

# 17. Target contract — `repository/`

## 17.1 Purpose

Answer:

> **What is this repository, what major things does it contain, and where should someone go for deeper understanding?**

`repository/` is the Repository Brain's canonical orientation/index layer.

## 17.2 Expected abstraction

Deliberately shallow.

Its job is orientation and routing, not deep explanation.

## 17.3 Always-relevant semantic scope

- repository/product purpose as supported by evidence;
- languages/frameworks/toolchain;
- repository shape;
- major applications/packages/workspaces;
- high-level responsibilities of major areas;
- top-level source/configuration/documentation regions;
- principal entry surfaces;
- important developer-facing commands at orientation level;
- navigation toward specialist knowledge targets.

## 17.4 Conditional coverage

When present:

- monorepo organization;
- multiple deployables;
- generated code;
- vendored code;
- generated clients;
- unusual workspace boundaries;
- multiple language ecosystems;
- specialized source regions.

## 17.5 Explicit exclusions

Do not deeply own any explanation that belongs to another target.

In particular, avoid detailed:

- runtime flows;
- business rules;
- persistence;
- API contracts;
- testing strategy;
- conventions;
- operations;
- UI design.

## 17.6 Boundary examples

```text
belongs:
"The monorepo contains an API service, background worker, and React web app."

does not belong:
"The API request path passes through Router → ApplicationService → Repository."
```

```text
belongs:
"The web application lives under apps/web and uses React."

does not belong:
"The design system uses semantic destructive button variants."
```

## 17.7 Investigation expectations

Establish repository terrain primarily from:

- FileIndex/inventory;
- manifests;
- top-level docs;
- graph structure;
- package/workspace declarations;
- important entry surfaces.

Deep source tracing should be limited to cases needed to correctly orient a major area.

## 17.8 Evidence expectations

- Deterministic file inventory and manifests can support much of this target.
- Graph structure can support major area/package orientation.
- README/docs can support declared purpose.
- Source reads should confirm unclear major responsibilities or entrypoints.
- Contradictions between docs and actual structure should be explicit.

## 17.9 Completion contract

| Obligation | Expected terminal outcome | Primary enforcement |
|---|---|---|
| Repository purpose/orientation is explained | resolved | W / R / O |
| Major languages/frameworks/toolchain are identified | resolved | W / R / O |
| Major applications/packages/workspaces are identified | resolved | W / R / O |
| Top-level source organization is navigable | resolved | W / R / O |
| Principal entry surfaces are identified at high level | resolved | W / R / O |
| Generated/vendor/special regions are identified where materially important | resolved | W / R / O |
| Orientation points toward deeper specialist knowledge | useful | R |
| Content remains shallow and avoids duplicated ownership | acceptable | R |
| Relevant orientation criteria have no `uninvestigated` state | resolved | H / W |
| Terminology aligns with fleet after reconciliation | acceptable | R |

## 17.10 Output-quality expectations

A new engineer or coding agent should be able to spend a short time here and understand:

```text
what this repository is
what its major pieces are
where important code lives
where to start
which specialist target to consult next
```

---

# 18. Common unknown and contradiction policy

Unknowns and contradictions are first-class valid outcomes.

## 18.1 Unknown

Use `unknown` when meaningful investigation has occurred but no sufficiently grounded conclusion can be established.

Examples:

- implementation branches disagree;
- old/new implementations coexist;
- docs disagree with source;
- source evidence is incomplete;
- runtime behavior depends on inaccessible external behavior;
- architectural intent cannot be established from implementation.

The worker must not replace this uncertainty with likely-but-unsupported certainty.

## 18.2 Contradictions

Contradictions should preserve both sides and identify their evidence.

They should not be silently "resolved" by choosing the interpretation the model prefers.

## 18.3 Completion with unknowns

A target may be semantically complete while containing `unknown` criteria if:

- the worker meaningfully investigated them;
- the uncertainty is explicit;
- known evidence/conflict is preserved;
- the unresolved point does not hide an `uninvestigated` obligation.

The exact hard mechanism used to establish this is part of the next runtime-contract phase.

---

# 19. Common evidence policy

The concrete evidence schema is intentionally deferred.

The semantic policy is locked.

## 19.1 Repository authority

The repository at the pinned revision remains the ultimate authority.

Generated prose, graph enrichment labels, and repository documentation do not become source truth merely because they are easier to read.

## 19.2 Deterministic facts

Deterministic artifacts are sufficient evidence for directly observable structural facts when the claim does not require semantic interpretation.

Examples:

- file existence;
- manifest declaration;
- symbol existence/location;
- direct graph relation where the graph contract makes the fact canonical.

## 19.3 Source inspection

Implementation-level source evidence is required for substantive behavioral interpretation.

Examples:

- domain rules;
- runtime responsibility;
- state mutation behavior;
- integration mapping;
- retry/error semantics;
- design interaction behavior.

## 19.4 Tests

Tests are especially important evidence for:

- invariants;
- edge cases;
- expected failure behavior;
- persistence semantics;
- integration contracts;
- verification strategy;
- design/accessibility behavior.

Tests may supplement but should not automatically override contradictory production implementation.

## 19.5 Configuration and manifests

Configuration/manifests are primary evidence for:

- entrypoints;
- declared scripts;
- build/deployment behavior;
- frameworks;
- test execution;
- environments;
- integrations/configured providers.

## 19.6 Documentation

Repository documentation may supplement source evidence and establish declared intent/terminology.

Conflicts with current implementation should be represented rather than silently reconciled.

## 19.7 Central claims

Central workflows and high-impact claims generally require stronger grounding than supporting details.

Where a workflow spans several meaningful implementation locations, evidence should normally reflect that chain rather than cite only one endpoint.

No arbitrary file-count or tool-call threshold defines sufficient evidence.

---

# 20. Common investigation policy

Investigation is semantic, not metric-driven.

A worker is not considered complete merely because it:

```text
inspected N files
made N tool calls
read every file in one directory
visited every graph community
```

A competent investigation should instead:

1. orient using deterministic repository/graph information;
2. identify the important areas for its target;
3. progressively inspect source and supporting evidence;
4. trace central concepts/workflows relevant to its responsibility;
5. investigate conditional completion criteria;
6. explicitly resolve each criterion to `covered`, `not-applicable`, or `unknown`;
7. revisit weakly grounded central conclusions when needed;
8. preserve uncertainty and contradictions;
9. organize the resulting knowledge for downstream use.

Repository exploration strategy remains worker-owned.

---

# 21. Common output-quality policy

Every accepted target should be:

## Grounded

Important claims connect to repository evidence and revision identity.

## Specific

The content should explain this repository, not generic software-engineering advice.

## Semantically owned

The target should remain within its canonical responsibility and avoid taking ownership of neighboring targets.

## Navigable

Workers may choose one Markdown file or several, but the resulting folder should be easy for humans and LLMs to navigate.

## Appropriately deep

Important concepts deserve enough detail to support future engineering work. Supporting details should not drown the central mental model.

## Non-repetitive

Small context-setting overlap is acceptable. Repeated canonical explanations are not.

## Terminologically consistent

Repository and domain terminology should be used consistently within a target and reconciled across targets.

## Explicit about uncertainty

Unknowns, contradictions, weak evidence, and ambiguous behavior should remain visible.

## Useful to downstream coding agents

The target should reduce rediscovery work during real design, debugging, review, and implementation tasks.

---

# 22. Fleet reconciliation expectations

Once all required targets are locally accepted, fleet reconciliation should eventually judge:

- duplicated canonical ownership;
- contradictions across targets;
- terminology inconsistencies;
- scope leakage;
- mismatched abstraction levels;
- repeated explanations that should have one owner;
- insufficient contextual links between related target knowledge;
- orientation quality of `repository/`.

The fleet reconciler/reviewer should not rediscover the repository.

If reconciliation identifies a material issue, only affected targets should be reopened for normal repair.

Cross-target links and summaries can be refined during this phase.

---

# 23. Locked decisions summary

The following decisions are now locked for V0.

## Target catalog

```text
repository/
business-logic/
architecture/
data-and-state/
interfaces-and-integrations/
testing/
conventions/
operations/
design/                     # conditional
```

## Design activation

```text
recognized frontend framework/library or meaningful UI stack detected
→ instantiate design/

otherwise
→ do not instantiate design/
```

No model decides this during target execution.

## Completion vocabulary

```text
uninvestigated
covered
not-applicable
unknown
```

## Default-fail rule

Every criterion begins `uninvestigated`.

A target cannot be accepted while an applicable/required criterion remains `uninvestigated`.

## Semantic ownership rule

The target whose primary question is being answered owns the canonical detailed explanation.

Other targets may include bounded contextual summaries and should link/reference rather than duplicate detailed ownership.

## Target execution independence

Targets may run concurrently by default.

Workers explore the repository independently against the common pinned repository state rather than depending on sibling generated knowledge.

## Orientation layer

`repository/` is the canonical shallow orientation/index target.

It is not a prerequisite input for specialist workers.

## Business Logic boundary

Business Logic is explicitly independent from runtime behavior.

It owns product/domain meaning, rules, invariants, states, transitions, and product-significant outcomes.

## Architecture boundary

Architecture owns runtime structure, component responsibilities, composition, control flow, and execution.

## Data & State boundary

Data & State owns technical state authority, representation, persistence, mutation, lifecycle, and consistency.

## Interfaces & Integrations boundary

Interfaces & Integrations owns contracts and mechanics at meaningful system boundaries.

## Testing boundary

Testing owns verification strategy and practical validation surfaces, not the complete business behavior being tested.

## Conventions boundary

Conventions owns recurring/enforced engineering patterns, not isolated implementation choices.

## Operations boundary

Operations owns source-to-runtime build, configuration, delivery, deployment, observability, and operational lifecycle.

## Design boundary

Design owns implemented visual language, UI/UX patterns, interaction behavior, responsive behavior, design-system semantics, and accessibility design decisions.

It does not own frontend software architecture.

## Security/workflows/failures

They are cross-cutting concerns and do not become standalone V0 targets.

Ownership follows the semantic concern being described.

## Unknowns and contradictions

They are legitimate first-class outcomes.

Completion means all obligations were meaningfully investigated and resolved semantically, not that the worker was able to produce certainty everywhere.

---

# 24. Explicitly deferred to the runtime-contract phase

This document intentionally does **not** lock:

- runtime classes;
- Pydantic/data models;
- physical persistence schemas;
- concrete completion-state storage format;
- evidence-reference schema;
- worker tools;
- target workspace tools;
- progress-state tools;
- finalization-request schema;
- validator implementation;
- reviewer prompt/schema;
- fleet scheduler implementation;
- context compiler implementation;
- checkpoint/recovery implementation;
- model/provider configuration;
- exact frontend framework detection table;
- hard mechanism for proving that `unknown` or `not-applicable` followed meaningful investigation;
- concrete file/folder layout inside each target;
- required Markdown filenames.

Those are the next design phase.

---

# 25. Source basis

This locked design is derived from and must remain compatible with:

- `agentic-contracts-to-be-defined.md` — contract-design roadmap and required target-completion dimensions;
- `bridger_memory_agent_design.md` — locked high-level memory-agent harness architecture;
- `Bridger Product Vision and Design.md` — Repository Brain product objective, authority model, grounding, progressive disclosure, and uncertainty requirements;
- `agentic-loops.md` — long-running-agent principles, explicit/granular completion criteria, default-fail semantics, runtime-owned completion, and structured evaluation;
- `implementation-oriented-long-running-agent-harness-course.md` — implementation inspiration only, not a Bridger source of truth.

This document supersedes earlier illustrative target examples for the purpose of V0 memory-target taxonomy and semantic completion-contract design.
```
