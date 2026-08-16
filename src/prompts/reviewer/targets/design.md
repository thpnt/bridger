# Reviewer rubric: Design

Judge whether the target acts as a useful repository-grounded design reference for the implemented user interface.

Do not evaluate whether the interface is aesthetically good in an abstract sense.
Evaluate whether the artifact successfully captures the repository's implemented design system and UX decisions.

Look specifically for:

1. Visual language
Where present, are important:
- semantic colors;
- typography;
- spacing;
- sizing;
- borders/radii;
- elevation;
- tokens;
- theming;
- iconography;
- motion;
explained coherently?

2. Component/design patterns
- Are important reusable design patterns and semantic variants explained?
- Flag raw component inventories without design synthesis.

3. Layout and hierarchy
- Are important page shells, navigation models, hierarchy, density, and recurring layouts understandable?

4. Responsive behavior
- Are meaningful mobile/desktop adaptations described where present?

5. Interaction and feedback
Where standardized, are:
- loading;
- empty;
- error;
- confirmation;
- destructive;
- optimistic;
- progressive-disclosure;
patterns covered?

6. Accessibility
Where implemented, are significant:
- keyboard;
- focus;
- semantic markup;
- ARIA;
- reduced motion;
- contrast/theme;
patterns represented?

7. Local vs global design
- Flag one-off component choices incorrectly generalized into product-wide design rules.

8. Design vs Business Logic
User capability/rule semantics belong to Business Logic.
How those states/actions are presented belongs here.

9. Design vs Architecture
Frontend software structure and state/routing architecture do not belong here.

10. Design vs Conventions
Design-system meaning belongs here.
Coding techniques used to implement it belong to Conventions.

11. Design vs Testing
Verification mechanism belongs to Testing.

12. Rendered-certainty discipline
If the artifact claims visual behavior that could not reasonably have been established from its available evidence, uncertainty should remain explicit.

Acceptance question:

"Could a future engineer or coding agent use this target to create a new UI surface that looks and behaves consistently with the implemented product?"