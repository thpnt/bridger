# Target: Design

## Objective

Build the durable repository-grounded design reference for this user-facing application.

Answer:

"What visual system, interaction model, UX patterns, and recurring design decisions does the implemented product embody?"

This target has already been activated by the runtime because a meaningful frontend/UI stack was detected. Do not reconsider whether the target should exist.

## Abstraction level

Describe product/interface design.

Do not describe frontend engineering architecture.

The goal is an evidence-backed, substantially improved equivalent of a traditional design.md that lets future contributors create UI that belongs naturally to this product.

## Investigate

Sample representative design sources across multiple screens/components.

Resolve where applicable:

### Visual language
- colors and semantic color roles;
- typography;
- spacing;
- sizing;
- radii;
- borders;
- elevation/shadows;
- design tokens;
- themes;
- iconography;
- imagery/brand assets;
- motion and animation.

### Component/design system
- reusable UI primitives;
- semantic variants;
- component composition patterns;
- forms;
- actions/buttons;
- navigation;
- overlays/dialogs;
- feedback components;
- data-display patterns.

Do not create a raw component inventory. Extract the reusable design decisions embodied by the components.

### Layout and hierarchy
- page shells;
- navigation structure;
- common layouts;
- visual hierarchy;
- density;
- responsive patterns;
- mobile/desktop adaptation.

### Interaction and UX
- feedback patterns;
- loading states;
- empty states;
- error states;
- confirmations;
- destructive-action patterns;
- optimistic interactions where visible;
- progressive disclosure;
- keyboard behavior;
- focus behavior.

### Accessibility
Where implemented:
- semantic markup patterns;
- focus management;
- keyboard navigation;
- ARIA usage;
- contrast/theme behavior;
- reduced-motion behavior;
- screen-reader considerations.

### Conditional areas
Where present:
- Storybook/design-system tooling;
- multiple themes;
- white-labeling;
- localization-related layout behavior;
- charts/data visualization;
- rich editors;
- drag-and-drop;
- onboarding;
- mobile-specific interaction;
- design-token generation;
- visual regression surfaces.

## Do not own

Do not canonically explain:
- React/Vue/etc. component architecture;
- routing architecture;
- frontend state-management architecture;
- API integration architecture;
- backend behavior;
- domain/business rules;
- component file/naming conventions;
- CSS/framework coding conventions;
- testing strategy.

## Boundary reminders

What users may do and what outcomes mean belongs to Business Logic.

How those actions, constraints, and states are communicated to users belongs here.

Frontend software structure belongs to Architecture.

What the interface should look, feel, and behave like belongs here.

Implementation rules used by engineers to reproduce the design belong to Conventions.

Verification of design/accessibility behavior belongs to Testing.

## Evidence expectations

Inspect:
- tokens/themes;
- global styles;
- reusable components;
- representative pages/layouts;
- major UI states;
- responsive implementation;
- assets/icons;
- Storybook/stories/docs;
- accessibility utilities;
- representative component/visual tests.

Do not generalize from one component or screen.

Static code may not establish exact rendered visual quality. State uncertainty rather than pretending to have visually observed behavior that the available evidence does not establish.

## Completion obligations

Meaningfully resolve:

- core visual language;
- token/theme system where present;
- important reusable design/component patterns;
- major layout/navigation patterns;
- responsive behavior where present;
- important interaction/feedback patterns;
- loading/empty/error/destructive states where standardized;
- accessibility patterns where implemented;
- design-system tooling/documentation where present;
- conditional specialized design areas relevant to the repository.

The target should let a future agent answer:

"How should a new UI surface look and behave so that it feels native to this product?"