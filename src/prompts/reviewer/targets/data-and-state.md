# Reviewer rubric: Data & State

Judge whether the target provides a useful technical model of state authority, representation, ownership, mutation, and lifecycle.

Look specifically for:

1. State inventory at the right level
- Are the important state categories and stores identified?
- Avoid exhaustive low-value field enumeration.

2. Authority
- Is it clear which state is canonical versus cached, derived, materialized, ephemeral, or replicated?

3. Ownership
- Are important read/write responsibilities understandable?

4. Representation
- Are significant models/schemas/serialization forms explained where they matter?

5. Mutation and lifecycle
- Are important mutation paths and lifecycle transitions explained technically?

6. Consistency
Where relevant, does the artifact explain:
- transactions;
- consistency assumptions;
- invalidation;
- locking;
- versioning;
- retention?

7. Evolution
Are migrations/schema evolution covered where present?

8. Data & State vs Business Logic
Flag semantic descriptions of what domain states mean when they become the main explanation.
This target owns technical representation and lifecycle.

9. Data & State vs Architecture
Do not require full system orchestration.
Architecture owns runtime component composition.

10. Data & State vs Interfaces
Internal canonical representation belongs here.
External API/provider schemas belong elsewhere.

11. Data & State vs Operations
Application/product state belongs here.
Deployment/infrastructure/environment state does not.

Acceptance question:

"Could a future engineer safely reason about modifying an important schema, state representation, cache, persistence path, or mutation lifecycle?"