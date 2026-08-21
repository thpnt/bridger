# Reviewer rubric: Conventions

Judge whether the target captures evidence-backed recurring engineering rules rather than isolated implementation observations or generic advice.

Look specifically for:

1. Recurrence
- Are patterns presented as conventions only when they appear recurring or explicitly enforced?

2. Strength of claims
- Are explicit/enforced rules distinguishable from observed recurring patterns?
- Are local patterns scoped rather than falsely generalized repository-wide?

3. Actionability
Does the artifact help contributors understand recurring expectations around:
- naming;
- placement;
- module organization;
- dependency patterns;
- construction/DI;
- typing/schemas;
- errors/logging;
- configuration;
- async behavior;
- data access;
- APIs;
- frontend implementation;
- test-writing style;
- formatting/lint/static analysis?

4. Generic-advice avoidance
Flag textbook or industry-best-practice guidance that is not presented as repository-specific convention.

5. Conventions vs Architecture
One architecture decision does not automatically become a convention.
Flag architectural description without a recurring contributor rule.

6. Conventions vs Design
Design meaning belongs to Design.
Engineering patterns for implementing that design may belong here.

7. Conventions vs Testing
Testing strategy belongs to Testing.
Recurring style for authoring individual tests may belong here.

8. Internal variation
- Does the artifact preserve meaningful area-specific conventions where the repository is not uniform?

Acceptance question:

"Could a future coding agent use this target to write code that looks structurally and stylistically native to the repository without being taught generic software-engineering practices?"