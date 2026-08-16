# Reviewer rubric: Architecture

Judge whether the target provides a coherent structural and runtime system model.

Look specifically for:

1. Runtime composition
- Are principal applications, processes, components, and subsystem boundaries understandable?

2. Responsibilities
- Does the target explain what major components are responsible for rather than merely naming them?

3. Dependency and interaction model
- Are important dependencies and interactions clear?
- Is dependency direction understandable where significant?

4. Execution paths
- Are central runtime/control flows explained mechanically?
- Are important synchronous/asynchronous boundaries understandable?

5. Bootstrap/composition
- Is initialization/runtime composition covered at useful depth?

6. Special runtime mechanisms
Where present, are these covered appropriately:
- workers;
- queues/events;
- schedulers;
- concurrency;
- plugins/extensions;
- runtime recovery/retry behavior?

7. Architecture vs Business Logic
Flag domain-rule detail that belongs in Business Logic.

8. Architecture vs Data & State
Architecture should identify component-level state responsibility.
Flag detailed schema/persistence lifecycle duplication.

9. Architecture vs Interfaces
Architecture should show where boundaries fit.
Flag excessive payload/protocol/provider-contract detail.

10. Architecture vs Operations
Flag deployment, infrastructure, CI/CD, secrets, and observability detail that goes beyond what is needed to explain runtime composition.

11. Architecture vs Design
Frontend runtime architecture belongs here.
Visual/interaction design does not.

12. Architecture vs Conventions
Describe what the system is, not every reusable coding rule contributors should follow.

Acceptance question:

"Could a future engineer understand where a change belongs, which runtime path it participates in, and what major components it may affect?"