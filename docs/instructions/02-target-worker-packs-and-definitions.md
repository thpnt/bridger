# Per-target worker instruction packs and complete TargetDefinitions

Target order is the current catalog order. For every target, this volume provides the complete target-specific worker prompt and its exact runtime YAML TargetDefinition. The YAML includes activation, dependencies, all semantic fields, and each completion obligation with all fields currently present. No current obligation declares `condition_hint`.

### `src/prompts/worker/targets/repository.md`

```markdown
# Target: Repository

## Objective

Build the canonical shallow orientation layer for this repository.

Answer:

"What is this repository, what major things does it contain, and where should someone go for deeper understanding?"

Your job is to give a new engineer or coding agent the terrain of the repository without duplicating the deeper specialist memory targets.

## Abstraction level

Stay deliberately shallow.

Focus on:
- what exists;
- where it is;
- what its broad responsibility is;
- where deeper understanding should be sought.

Do not deeply explain how systems work.

## Investigate

Resolve the following where applicable:

- repository purpose and identity;
- major languages, frameworks, and toolchains;
- repository shape and top-level organization;
- major applications, services, packages, libraries, or workspaces;
- high-level responsibility of each major area;
- principal entry surfaces;
- important source, configuration, documentation, generated, and vendored regions;
- major monorepo/workspace boundaries;
- major generated-code/client regions;
- important developer-facing commands useful for orientation;
- unusual repository organization that a new contributor must understand.

## Do not own

Do not deeply document:
- runtime architecture;
- business/domain rules;
- state and persistence;
- API/integration contracts;
- testing strategy;
- coding conventions;
- deployment/operations;
- UI/design decisions.

Those may be briefly mentioned to orient the reader.

## Investigation guidance

Begin with deterministic inventory, manifests, workspace/package declarations, top-level documentation, graph structure, and major entry surfaces.

Use deeper source inspection only when needed to correctly identify the responsibility of an important repository area.

Do not turn this target into a file-tree dump.

## Completion obligations

You must meaningfully resolve:

- repository purpose/orientation;
- major languages/frameworks/toolchain;
- major applications/packages/workspaces;
- top-level source organization;
- principal entry surfaces;
- important generated/vendor/special regions where present;
- orientation toward deeper specialist knowledge.

The result should let a new engineer quickly answer:

"What is this repo, what are its major pieces, where should I start, and where should I look next?"
```

### `src/memory/default-targets/targets/repository.yaml`

```yaml
schema_version: 1
target_id: repository
target_contract_version: v1
activation: {mode: always}
depends_on: []
canonical_question: What is this repository, what are its major areas, and where should someone look next?
purpose: Provide the Repository Brain orientation layer.
expected_abstraction: Shallow repository-level orientation.
always_relevant_scope: [Repository purpose, major areas, and navigation entry points.]
conditional_scope: []
exclusions: [Detailed specialist explanations owned by other targets.]
boundary_guidance: [Keep this target an index rather than a generic wiki.]
investigation_expectations: [Use deterministic inventory and source evidence to orient future readers.]
evidence_expectations: [Ground structural claims in the pinned repository revision.]
completion_obligations:
  - obligation_id: repository-orientation
    description: Resolve the repository purpose, major areas, and useful entry points.
    applicability: always
output_quality_expectations: [Be concise, navigable, and repository-specific.]
```

### `src/prompts/worker/targets/business-logic.md`

```markdown
# Target: Business Logic

## Objective

Build the repository's durable product/domain semantic model.

Answer:

"What product or domain behavior does this software implement, and what semantic rules must remain true regardless of incidental technical implementation?"

Business logic is not equivalent to runtime behavior.

For non-commercial repositories, interpret "business logic" as the repository's product or domain semantics.

## Abstraction level

Be deeply implementation-grounded while explaining behavior in domain terms.

Prefer:
- what a capability means;
- what rules govern it;
- what states and outcomes are meaningful;

over:
- which framework object happens to execute it.

A useful boundary test:

"If the implementation technology changed but this rule would still conceptually remain true, it probably belongs here."

## Investigate

Resolve where applicable:

- principal domain/product concepts;
- repository/domain terminology;
- important actors;
- major user or external-system actions;
- principal product/domain workflows;
- business/domain rules;
- invariants;
- validation and eligibility rules;
- business-significant authorization rules;
- meaningful domain states;
- allowed and forbidden state transitions;
- lifecycle rules;
- business-significant calculations;
- pricing/billing/entitlement logic where present;
- quotas, limits, approvals, scheduling, or similar domain constraints;
- meaningful outcomes and side effects;
- domain-specific failure and exceptional paths;
- relationships between important domain concepts;
- implementation locations needed to ground those conclusions.

For central workflows, aim to understand:

trigger
→ domain decisions and rules
→ meaningful state transitions
→ business-significant side effects
→ alternate/failure outcomes

## Do not own

Do not canonically explain:
- application bootstrap;
- dependency injection;
- generic routing/middleware;
- runtime component composition;
- persistence schema details;
- transaction/storage mechanics;
- external protocol mechanics;
- deployment/configuration;
- test infrastructure;
- coding conventions;
- visual presentation.

## Boundary reminders

Domain-state meaning belongs here.
Technical representation of that state belongs to Data & State.

What an external interaction means to the product belongs here.
How the protocol/provider boundary works belongs to Interfaces & Integrations.

What the user is allowed to do belongs here.
How that capability is presented belongs to Design.

## Evidence expectations

Central rules and workflows require source-level behavioral evidence.

Use tests heavily for invariants, edge cases, and expected failures, but verify accessible production behavior.

Do not infer product rules from names, comments, or graph labels alone.

## Completion obligations

Meaningfully resolve:

- principal domain/product concepts and their relationships;
- major product/system actions;
- central workflows;
- important rules and invariants;
- important domain states and transitions;
- validation/eligibility rules;
- business-significant authorization where present;
- meaningful side effects;
- domain-specific failures and alternate outcomes;
- conditional domain areas relevant to this repository.

The target should let a future agent answer:

"If I change this behavior, what semantic rules, states, and outcomes must I preserve?"
```

### `src/memory/default-targets/targets/business-logic.yaml`

```yaml
schema_version: 1
target_id: business-logic
target_contract_version: v1
activation: {mode: always}
depends_on: []
canonical_question: What product or domain behavior does the software implement, and what semantic rules must remain true?
purpose: Explain product meaning, rules, invariants, states, and transitions.
expected_abstraction: Repository-level domain semantics.
always_relevant_scope: [Product behavior and semantic rules.]
conditional_scope: []
exclusions: [Runtime component mechanics and technical state representation.]
boundary_guidance: [Own domain meaning rather than implementation mechanics.]
investigation_expectations: [Trace central product behavior through implementation evidence.]
evidence_expectations: [Ground behavioral claims in source and relevant tests.]
completion_obligations:
  - obligation_id: domain-behavior
    description: Resolve the repository's product behavior and important semantic rules.
    applicability: always
output_quality_expectations: [Explain rules and invariants with concrete repository evidence.]
```

### `src/prompts/worker/targets/architecture.md`

```markdown
# Target: Architecture

## Objective

Build the repository's durable structural and runtime system model.

Answer:

"How is the software structurally composed, and how does runtime execution move through its major components?"

## Abstraction level

Provide deep runtime and implementation understanding.

Explain:
- responsibilities;
- boundaries;
- composition;
- dependencies;
- execution paths;

rather than producing a file-by-file inventory.

## Investigate

Resolve where applicable:

- principal runtime entrypoints;
- applications, services, processes, or runtime-significant packages;
- bootstrap and initialization;
- runtime composition;
- major components and subsystem boundaries;
- responsibilities of important components;
- dependency direction;
- important internal interfaces;
- major control/execution paths;
- orchestration;
- synchronous vs asynchronous execution;
- background workers;
- queues/events/schedulers;
- concurrency where architecturally significant;
- component-level state ownership;
- plugin/extension mechanisms;
- frontend runtime architecture where present;
- caches where they affect system composition;
- important runtime error propagation;
- retry/recovery/resilience behavior;
- major architectural patterns evidenced by the implementation.

Use graph communities and centrality as exploration cues, not as proof of architectural meaning.

## Do not own

Do not canonically explain:
- domain rules and product semantics;
- detailed schemas or persistence lifecycle;
- public/external protocol contracts;
- provider-specific mappings;
- deployment topology;
- operational observability;
- UI/UX design;
- testing strategy;
- contributor conventions.

## Boundary reminders

Architecture owns where stateful responsibilities live.
Data & State owns the state model and lifecycle.

Architecture owns where external adapters fit.
Interfaces & Integrations owns the boundary contracts.

Architecture owns how the running application works.
Operations owns how it is built, configured, deployed, observed, and kept running.

Architecture owns frontend software structure.
Design owns user-facing interaction and visual behavior.

## Evidence expectations

Graph/import relationships can establish structural facts.

Runtime responsibilities, component semantics, and control flow require source inspection.

Central execution paths should normally be grounded across the meaningful components they cross.

## Completion obligations

Meaningfully resolve:

- principal runtime entrypoints;
- major runtime applications/processes/components;
- component responsibilities;
- important dependencies/interactions;
- principal execution/control paths;
- initialization/bootstrap/composition;
- asynchronous/background execution where present;
- component-level state ownership;
- extension/plugin mechanisms where present;
- important runtime error/recovery behavior.

The target should let a future agent answer:

"Where does this change belong, what runtime path am I entering, and which major components will it affect?"
```

### `src/memory/default-targets/targets/architecture.yaml`

```yaml
schema_version: 1
target_id: architecture
target_contract_version: v1
activation: {mode: always}
depends_on: []
canonical_question: How is the running software structurally composed and how does execution move through its major components?
purpose: Explain composition, responsibilities, and central runtime paths.
expected_abstraction: Repository-level runtime architecture.
always_relevant_scope: [Components, composition, control flow, and execution paths.]
conditional_scope: []
exclusions: [Detailed domain rules and state-representation ownership.]
boundary_guidance: [Describe runtime structure without duplicating specialist ownership.]
investigation_expectations: [Trace central execution paths across component boundaries.]
evidence_expectations: [Ground architectural claims in implementation evidence.]
completion_obligations:
  - obligation_id: runtime-composition
    description: Resolve major components and the central execution paths between them.
    applicability: always
output_quality_expectations: [Prefer explanatory flow over component inventories.]
```

### `src/prompts/worker/targets/data-and-state.md`

```markdown
# Target: Data & State

## Objective

Build the repository's durable technical state model.

Answer:

"What state exists, where does truth live, who owns it, and how is it represented, read, changed, and kept consistent?"

## Abstraction level

Focus deeply on state authority, representation, ownership, mutation, lifecycle, and consistency.

Do not reduce this target to a schema dictionary.

## Investigate

Resolve where applicable:

- major state categories;
- canonical/authoritative stores;
- persisted entities/models;
- state ownership;
- read ownership;
- write ownership;
- data-access boundaries;
- important mutation paths;
- persistent vs ephemeral state;
- authoritative vs derived state;
- serialization;
- consistency assumptions;
- transaction boundaries;
- relational or NoSQL schemas;
- migrations/schema evolution;
- caches and invalidation;
- sessions;
- browser/client state;
- filesystem state;
- object/blob storage;
- event stores;
- queues carrying durable state;
- derived/materialized views;
- replication;
- locking/concurrency controls;
- retention/expiry;
- data versioning.

For significant state, understand:

what exists
→ what is authoritative
→ where it lives
→ who reads it
→ who changes it
→ how changes are coordinated
→ what derived copies exist
→ how lifecycle/versioning/invalidation works

## Do not own

Do not canonically explain:
- domain meaning of states;
- legal business-state transitions;
- whole-system architecture;
- external API contracts;
- deployment/infrastructure state;
- secrets/environment configuration.

## Boundary reminders

"Order becomes eligible for fulfilment after payment"
belongs to Business Logic.

"Order.status is stored and transactionally updated here"
belongs here.

External representations crossing API/provider boundaries belong to Interfaces & Integrations; this target owns the internal/canonical state representation.

## Evidence expectations

Inspect schemas/models together with their readers and writers.

Use migrations and configuration for storage evolution and setup.

Use tests to strengthen conclusions about transaction, migration, persistence, and invalidation behavior.

## Completion obligations

Meaningfully resolve:

- principal state categories and stores;
- authoritative sources of truth;
- important state/data models;
- read/write ownership;
- important mutation and lifecycle paths;
- consistency/transaction semantics where present;
- migrations/schema evolution where present;
- caches/derived/materialized state and invalidation where present;
- retention/versioning/locking mechanisms where material.

The target should let a future agent answer:

"If I change this state, schema, cache, or persistence path, what else must I understand and preserve?"
```

### `src/memory/default-targets/targets/data-and-state.yaml`

```yaml
schema_version: 1
target_id: data-and-state
target_contract_version: v1
activation: {mode: always}
depends_on: []
canonical_question: What state exists, where does truth live, and how is it represented and changed technically?
purpose: Explain technical state authority, persistence, mutation, and consistency.
expected_abstraction: Repository-level technical state model.
always_relevant_scope: [State authority, representation, lifecycle, and persistence.]
conditional_scope: []
exclusions: [Product meaning of state transitions.]
boundary_guidance: [Own technical state details, not domain meaning.]
investigation_expectations: [Trace state creation, mutation, persistence, and recovery paths.]
evidence_expectations: [Ground state claims in source and schema evidence.]
completion_obligations:
  - obligation_id: state-authority
    description: Resolve where important state lives and how it changes.
    applicability: always
output_quality_expectations: [Make state ownership and lifecycle explicit.]
```

### `src/prompts/worker/targets/interfaces-and-integrations.md`

```markdown
# Target: Interfaces & Integrations

## Objective

Build the repository's durable boundary-contract model.

Answer:

"What capabilities cross system boundaries, through what contracts, and how are those boundaries implemented?"

## Abstraction level

Focus on meaningful inbound and outbound boundaries, their contracts, mappings, and boundary-specific behavior.

Do not document every third-party dependency merely because it appears in a manifest.

## Investigate

Identify significant boundary families where present:

- HTTP/REST;
- GraphQL;
- RPC;
- CLI;
- public library/module APIs;
- webhooks;
- events/messages;
- sockets/streams;
- plugin interfaces;
- external providers/SDKs;
- generated clients.

For important boundaries, understand:

- direction: inbound or outbound;
- purpose;
- entry/exit surface;
- request/input/payload contract;
- response/output contract;
- serialization;
- validation;
- authentication;
- boundary authorization mechanics;
- mapping between external and internal models;
- idempotency;
- timeouts;
- retries;
- provider/protocol-specific failures;
- callbacks;
- webhook/event behavior;
- versioning and compatibility;
- repository-encoded rate-limit or provider constraints.

Trace important boundaries through:

contract definition
→ handler/client/adapter
→ validation/authentication
→ mapping
→ internal handoff
→ response/callback
→ failure/retry behavior

## Do not own

Do not canonically explain:
- underlying product rules;
- generic internal component interactions;
- persistence internals;
- deployment/observability providers;
- visual presentation.

## Boundary reminders

Product meaning of an integration belongs to Business Logic.

Placement of the adapter/component belongs to Architecture.

Contract, payload, mapping, authentication, idempotency, and provider-specific behavior belong here.

Operational providers such as deployment systems and observability infrastructure belong primarily to Operations.

## Evidence expectations

Use route/schema/protocol/event/public-export definitions as strong contract evidence.

Inspect actual handlers, clients, and adapters for mapping and behavioral claims.

Use integration/contract tests where available.

Do not fill repository-absent external-provider behavior from general model knowledge.

## Completion obligations

Meaningfully resolve:

- significant inbound interfaces;
- significant outbound integrations;
- important contracts/payloads and mappings;
- boundary authentication/security mechanics where present;
- error/retry/idempotency semantics where relevant;
- callbacks/events/webhooks where present;
- versioning/compatibility constraints where present;
- connection between each important boundary and internal implementation.

The target should let a future agent answer:

"If I change this boundary, what contract must remain compatible, who consumes it, and where is adaptation performed?"
```

### `src/memory/default-targets/targets/interfaces-and-integrations.yaml`

```yaml
schema_version: 1
target_id: interfaces-and-integrations
target_contract_version: v1
activation: {mode: always}
depends_on: []
canonical_question: What capabilities cross system boundaries, through what contracts, and how are those boundaries implemented?
purpose: Explain external and internal system-boundary contracts.
expected_abstraction: Repository-level boundary mechanics.
always_relevant_scope: [Interfaces, integrations, contracts, and adapters.]
conditional_scope: []
exclusions: [Detailed product meaning and general runtime composition.]
boundary_guidance: [Own boundary contracts and mechanics.]
investigation_expectations: [Trace meaningful boundary crossings and failure behavior.]
evidence_expectations: [Ground contract claims in source, configuration, and tests.]
completion_obligations:
  - obligation_id: boundary-contracts
    description: Resolve meaningful interfaces and integration contracts.
    applicability: always
output_quality_expectations: [Identify contracts, adapters, and important failure semantics.]
```

### `src/prompts/worker/targets/testing.md`

```markdown
# Target: Testing

## Objective

Build the repository's durable verification model.

Answer:

"How does this repository establish correctness, and how should a contributor verify a change?"

## Abstraction level

Focus on testing strategy, verification layers, test infrastructure, and practical validation workflows.

Do not recreate a wiki of every behavior that happens to have a test.

## Investigate

Resolve where applicable:

- test frameworks;
- test configuration;
- test layout;
- principal test categories;
- unit testing;
- integration testing;
- database testing;
- E2E/browser testing;
- contract testing;
- snapshot testing;
- visual testing;
- accessibility testing;
- performance/security testing where present;
- standard test/validation commands;
- fixtures;
- factories;
- mocks/fakes/stubs;
- test isolation;
- external service handling;
- test containers/services;
- CI-triggered test execution;
- coverage tooling;
- sharding/parallel execution;
- relationship between typical change types and appropriate verification levels;
- meaningful testing gaps encountered during investigation.

Inspect representative tests across important repository areas rather than inferring the testing model from one folder or configuration file.

## Do not own

Do not canonically explain:
- complete business behaviors;
- production architecture;
- deployment/release mechanics;
- general coding style for individual tests.

## Boundary reminders

Business Logic owns what behavior must hold.
Testing owns how that behavior is verified.

Conventions owns recurring rules about how individual tests are written.
Testing owns the strategy, layers, setup, and verification surfaces.

## Evidence expectations

Test source and configuration are primary evidence.

Use manifest scripts for standard commands.

Use CI definitions to establish which suites actually run automatically.

## Completion obligations

Meaningfully resolve:

- test frameworks and principal verification levels;
- test organization;
- fixtures/factories/setup;
- isolation and external-dependency strategy;
- standard validation commands;
- mapping from change types to appropriate test levels;
- CI-triggered verification where present;
- E2E/contract/visual/accessibility/etc. strategies where present;
- material testing gaps encountered during investigation without pretending to perform exhaustive gap analysis.

The target should let a future agent answer:

"I changed X. Which tests should I add or run, and how are tests normally executed here?"
```

### `src/memory/default-targets/targets/testing.yaml`

```yaml
schema_version: 1
target_id: testing
target_contract_version: v1
activation: {mode: always}
depends_on: []
canonical_question: How does the repository establish correctness, and how should a contributor verify a change?
purpose: Explain verification strategy and practical test surfaces.
expected_abstraction: Repository-level verification strategy.
always_relevant_scope: [Test architecture, validation commands, and correctness evidence.]
conditional_scope: []
exclusions: [Complete product behavior explained by business logic.]
boundary_guidance: [Own verification strategy rather than all behavior under test.]
investigation_expectations: [Inspect test organization and supported validation paths.]
evidence_expectations: [Ground verification guidance in repository commands and tests.]
completion_obligations:
  - obligation_id: verification-strategy
    description: Resolve how contributors should establish correctness for changes.
    applicability: always
output_quality_expectations: [Provide practical, repository-specific verification guidance.]
```

### `src/prompts/worker/targets/conventions.md`

```markdown
# Target: Conventions

## Objective

Build the repository's durable contributor-rule model.

Answer:

"What recurring engineering rules and implementation patterns should future contributors reproduce?"

## Abstraction level

Describe repeatable repository practice.

Do not convert isolated architectural choices into universal conventions.

## Evidence threshold

A single observed implementation is not automatically a convention.

Treat a pattern as a convention when it is supported by:

- explicit repository instructions, tooling, or configuration;
or
- clear recurring implementation behavior across representative examples.

Distinguish conceptually between:

ENFORCED / EXPLICIT
OBSERVED / RECURRING
LOCAL / AREA-SPECIFIC

Do not present these with equal strength.

## Investigate

Resolve recurrent patterns where present:

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
- API/interface implementation style;
- frontend component implementation style;
- test-writing style;
- formatting;
- linting;
- static-analysis expectations.

Sample multiple representative repository areas before generalizing.

Surface legitimate local variation rather than forcing false repository-wide uniformity.

## Do not own

Do not canonically explain:
- one-off architecture decisions;
- product/domain rules;
- design-system semantics;
- overall testing strategy;
- generic industry best practices unsupported by this repository.

## Boundary reminders

Architecture explains what the system currently is.
Conventions explains what recurring pattern contributors should reproduce.

Design explains what UI elements mean and how the interface should behave.
Conventions explains the implementation patterns used to realize those decisions.

Testing explains verification strategy.
Conventions explains recurring test-writing style.

## Evidence expectations

Tooling/configuration is strong evidence for enforced rules.

Repository instructions/docs are strong evidence for explicit contributor expectations.

Observed conventions require representative repeated source examples.

External best practices are not evidence.

## Completion obligations

Meaningfully resolve:

- major naming/layout rules;
- recurring structural implementation patterns;
- recurrent error/logging/config patterns;
- recurrent type/schema patterns;
- recurrent data/interface/test/frontend implementation patterns;
- which patterns are explicit/enforced versus observed;
- local conventions and their scope;
- conflicting conventions where legitimately present.

The target should let a future agent answer:

"How should I structure and write code so that it looks native to this repository?"
```

### `src/memory/default-targets/targets/conventions.yaml`

```yaml
schema_version: 1
target_id: conventions
target_contract_version: v1
activation: {mode: always}
depends_on: []
canonical_question: What recurring engineering rules and implementation patterns should contributors reproduce?
purpose: Explain established, repeatable engineering conventions.
expected_abstraction: Repository-level contributor conventions.
always_relevant_scope: [Recurring patterns, style, and contributor rules.]
conditional_scope: []
exclusions: [One-off implementation choices and complete testing strategy.]
boundary_guidance: [Describe recurring practice rather than isolated code details.]
investigation_expectations: [Identify conventions evidenced by source and project configuration.]
evidence_expectations: [Ground conventions in repeated implementation or enforcement.]
completion_obligations:
  - obligation_id: engineering-conventions
    description: Resolve recurring engineering rules contributors should reproduce.
    applicability: always
output_quality_expectations: [Distinguish enforced conventions from local coincidences.]
```

### `src/prompts/worker/targets/operations.md`

```markdown
# Target: Operations

## Objective

Build the repository's durable source-to-runtime operational model.

Answer:

"How does this repository become a runnable or released system, how is that runtime configured, and how is it operated?"

## Abstraction level

Cover the path from repository source to operational runtime.

Operations includes build, packaging, delivery, deployment, runtime configuration, observability, and operational lifecycle.

## Investigate

Resolve where applicable:

- build process;
- packaging;
- runtime prerequisites;
- important developer/operator commands;
- runtime configuration;
- environment model;
- containers;
- CI/CD;
- release/versioning;
- package publishing;
- deployment manifests;
- infrastructure-as-code;
- environment distinctions;
- secrets injection;
- runtime/deployment topology;
- deployment-time migrations;
- scheduled operational jobs;
- feature/config rollout mechanisms;
- health checks;
- metrics;
- logging pipelines;
- tracing;
- alerting;
- scaling;
- rollback/recovery;
- production troubleshooting mechanisms.

Trace the repository-supported path:

source
→ build/package artifact
→ environment/configuration
→ deployment/release
→ runtime topology
→ health/observability
→ recovery/rollback

Do not invent operational practices that are not represented in the repository.

## Do not own

Do not canonically explain:
- in-process runtime architecture;
- business rules;
- product-facing external integrations;
- application data model;
- testing strategy;
- coding conventions.

## Boundary reminders

Inside the running application's component/control model belongs to Architecture.

Getting, configuring, deploying, observing, and keeping that application running belongs here.

Application/product state belongs to Data & State.
Infrastructure/environment/deployment state belongs here.

Product integrations belong to Interfaces & Integrations.
Operational integrations such as monitoring, registries, CI, and infrastructure providers belong here.

## Evidence expectations

Build scripts, manifests, CI workflows, containers, IaC, deployment files, environment templates, and observability configuration are primary evidence.

Inspect application source when needed for configuration loading, lifecycle hooks, health endpoints, telemetry initialization, or runtime modes.

## Completion obligations

Meaningfully resolve:

- build/package path;
- runtime prerequisites;
- principal configuration/environment model;
- environment distinctions where present;
- CI/CD and release flow where present;
- deployment/runtime topology where present;
- secrets/configuration injection where present;
- health and observability mechanisms where present;
- migration/rollout/rollback behavior where present;
- scaling/scheduled operational mechanisms where present;
- important operator/developer commands.

The target should let a future agent answer:

"How do I get this software from checkout to running or released, and where do I look when its runtime environment matters?"
```

### `src/memory/default-targets/targets/operations.yaml`

```yaml
schema_version: 1
target_id: operations
target_contract_version: v1
activation: {mode: always}
depends_on: []
canonical_question: How does source become a configured, deployed, observable, operable runtime or release?
purpose: Explain build, configuration, delivery, deployment, and operations.
expected_abstraction: Repository-level operational lifecycle.
always_relevant_scope: [Build, configuration, release, deployment, and observability.]
conditional_scope: []
exclusions: [Internal runtime component design.]
boundary_guidance: [Own source-to-runtime and operational lifecycle details.]
investigation_expectations: [Inspect scripts, configuration, and delivery surfaces.]
evidence_expectations: [Ground operational claims in repository configuration and automation.]
completion_obligations:
  - obligation_id: operational-lifecycle
    description: Resolve how the repository is built, configured, and operated.
    applicability: always
output_quality_expectations: [Make required configuration and operational paths explicit.]
```

### `src/prompts/worker/targets/design.md`

```markdown
# Target: Design

## Objective

Build the durable repository-grounded design reference for this user-facing application.

Answer:

"What visual system, interaction model, UX patterns, and recurring design decisions does the implemented product embody?"

This target has already been activated by the runtime because a meaningful frontend/UI stack was detected. Do not reconsider whether the target should exist.

## Abstraction level

Describe product/interface design.

Do not describe frontend engineering architecture.

The goal is an evidence-backed, substantially improved equivalent of a traditional design.md that lets future contributors create UI that belongs naturally to this product.

## Investigate

Sample representative design sources across multiple screens/components.

Resolve where applicable:

### Visual language
- colors and semantic color roles;
- typography;
- spacing;
- sizing;
- radii;
- borders;
- elevation/shadows;
- design tokens;
- themes;
- iconography;
- imagery/brand assets;
- motion and animation.

### Component/design system
- reusable UI primitives;
- semantic variants;
- component composition patterns;
- forms;
- actions/buttons;
- navigation;
- overlays/dialogs;
- feedback components;
- data-display patterns.

Do not create a raw component inventory. Extract the reusable design decisions embodied by the components.

### Layout and hierarchy
- page shells;
- navigation structure;
- common layouts;
- visual hierarchy;
- density;
- responsive patterns;
- mobile/desktop adaptation.

### Interaction and UX
- feedback patterns;
- loading states;
- empty states;
- error states;
- confirmations;
- destructive-action patterns;
- optimistic interactions where visible;
- progressive disclosure;
- keyboard behavior;
- focus behavior.

### Accessibility
Where implemented:
- semantic markup patterns;
- focus management;
- keyboard navigation;
- ARIA usage;
- contrast/theme behavior;
- reduced-motion behavior;
- screen-reader considerations.

### Conditional areas
Where present:
- Storybook/design-system tooling;
- multiple themes;
- white-labeling;
- localization-related layout behavior;
- charts/data visualization;
- rich editors;
- drag-and-drop;
- onboarding;
- mobile-specific interaction;
- design-token generation;
- visual regression surfaces.

## Do not own

Do not canonically explain:
- React/Vue/etc. component architecture;
- routing architecture;
- frontend state-management architecture;
- API integration architecture;
- backend behavior;
- domain/business rules;
- component file/naming conventions;
- CSS/framework coding conventions;
- testing strategy.

## Boundary reminders

What users may do and what outcomes mean belongs to Business Logic.

How those actions, constraints, and states are communicated to users belongs here.

Frontend software structure belongs to Architecture.

What the interface should look, feel, and behave like belongs here.

Implementation rules used by engineers to reproduce the design belong to Conventions.

Verification of design/accessibility behavior belongs to Testing.

## Evidence expectations

Inspect:
- tokens/themes;
- global styles;
- reusable components;
- representative pages/layouts;
- major UI states;
- responsive implementation;
- assets/icons;
- Storybook/stories/docs;
- accessibility utilities;
- representative component/visual tests.

Do not generalize from one component or screen.

Static code may not establish exact rendered visual quality. State uncertainty rather than pretending to have visually observed behavior that the available evidence does not establish.

## Completion obligations

Meaningfully resolve:

- core visual language;
- token/theme system where present;
- important reusable design/component patterns;
- major layout/navigation patterns;
- responsive behavior where present;
- important interaction/feedback patterns;
- loading/empty/error/destructive states where standardized;
- accessibility patterns where implemented;
- design-system tooling/documentation where present;
- conditional specialized design areas relevant to the repository.

The target should let a future agent answer:

"How should a new UI surface look and behave so that it feels native to this product?"
```

### `src/memory/default-targets/targets/design.yaml`

```yaml
schema_version: 1
target_id: design
target_contract_version: v1
activation: {mode: conditional, rule_id: frontend_stack_present_v1}
depends_on: []
canonical_question: What user-facing visual system, interaction model, and UX or design decisions does the implemented product embody?
purpose: Explain the implemented visual and interaction system when a frontend stack exists.
expected_abstraction: Repository-level design and UX semantics.
always_relevant_scope: [Visual language, interaction behavior, accessibility, and design-system semantics.]
conditional_scope: []
exclusions: [Frontend software architecture.]
boundary_guidance: [Own user-facing design rather than implementation architecture.]
investigation_expectations: [Inspect implemented interface evidence and design-system surfaces.]
evidence_expectations: [Ground design claims in implemented UI and tests where available.]
completion_obligations:
  - obligation_id: user-experience
    description: Resolve the implemented visual and interaction system.
    applicability: always
output_quality_expectations: [Describe implemented UX rather than generic design advice.]
```
