# Reviewer rubric: Interfaces & Integrations

Judge whether the target explains the repository's meaningful system-boundary contracts.

Look specifically for:

1. Boundary identification
- Are significant inbound and outbound interfaces distinguished?
- Does the artifact avoid treating every dependency as an integration?

2. Contract clarity
For important boundaries, are the relevant:
- inputs/payloads;
- outputs/responses;
- serialization;
- mappings;
understandable?

3. Boundary mechanics
Where applicable, are these covered:
- authentication;
- authorization mechanics;
- idempotency;
- timeout/retry behavior;
- callbacks;
- webhooks/events;
- provider-specific failures;
- versioning/compatibility?

4. Internal handoff
- Is it clear where the boundary connects to internal implementation without duplicating Architecture?

5. Interfaces vs Business Logic
The product meaning of an interaction belongs to Business Logic.
Flag excessive domain-rule duplication.

6. Interfaces vs Architecture
The target should document the boundary contract, not recreate internal runtime structure.

7. Interfaces vs Data & State
Internal persistence/schema authority should not dominate.

8. Interfaces vs Operations
Product/application integrations belong here.
CI, deployment, registries, observability, and infrastructure providers primarily belong to Operations.

9. Unsupported external knowledge
Flag confident explanations of external-provider behavior that appear disconnected from the generated repository-grounded knowledge.

Acceptance question:

"Could a future engineer change an important boundary while understanding its contract, compatibility constraints, mappings, consumers/providers, and boundary-specific behavior?"