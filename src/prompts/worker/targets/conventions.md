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