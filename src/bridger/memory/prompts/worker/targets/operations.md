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