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