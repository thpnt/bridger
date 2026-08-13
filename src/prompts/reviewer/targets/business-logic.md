# Reviewer rubric: Business Logic

Judge whether the target explains the repository's durable product/domain semantics rather than its incidental runtime mechanics.

Look specifically for:

1. Domain model quality
- Are principal product/domain concepts clearly identified?
- Are their important relationships understandable?
- Is repository/domain terminology used consistently?

2. Actions and workflows
- Are the major product/system actions explained?
- Are central workflows understandable from trigger through meaningful outcomes?

3. Rules and invariants
- Are important rules, validations, eligibility conditions, authorization semantics, calculations, and invariants explicit where applicable?

4. Domain state
- Are meaningful states and transitions described semantically?
- Do not require technical persistence detail.

5. Outcomes and failure semantics
- Are business-significant side effects, rejection paths, and exceptional outcomes explained?

6. Business Logic vs Architecture
Flag when the artifact spends substantial detail on:
- bootstrap;
- dependency injection;
- generic routing;
- component wiring;
- framework mechanics;
instead of explaining domain meaning.

7. Business Logic vs Data & State
Flag detailed schema/storage mechanics.
Domain-state meaning belongs here; technical representation does not.

8. Business Logic vs Interfaces
Boundary protocols should not dominate the document.
The target should explain what integrations mean to the product rather than fully documenting payload mechanics.

9. Business Logic vs Design
User permissions, actions, and outcomes belong here.
Visual/interaction presentation does not.

Acceptance question:

"Could a future engineer change product behavior while understanding the semantic rules, invariants, states, and outcomes that must remain true?"