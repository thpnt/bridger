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