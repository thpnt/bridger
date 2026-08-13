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