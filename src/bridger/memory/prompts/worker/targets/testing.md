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