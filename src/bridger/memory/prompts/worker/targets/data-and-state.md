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