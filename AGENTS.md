# AGENTS.md

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

# TypeScript / Frontend rules

Stack:

- TypeScript
- npm
- shadcn/ui
- Tailwind CSS

### General frontend style

- Use functional components.
- Prefer simple, explicit, readable code.
- Avoid complex syntax.
- Avoid arrow functions when a named function is clearer.
- Keep UI logic and business logic separated.
- Organize frontend code by feature folders.

### Typing

- Strong typing is required.
- Prefer `interface` over `type` unless there is a clear reason not to.
- Avoid `any` unless absolutely necessary.
- Make props, return values, and shared contracts explicit.

### Components and UI

- Prefer existing shadcn/ui components first.
- When creating new components, prefer composing from existing components instead of inventing completely new patterns.
- Keep components focused and readable.
- Split growing features into smaller components or files rather than building oversized component files.

### Naming and structure

- Use PascalCase for TypeScript files and components.
- Use feature-based folder organization.
- Keep related UI, logic, and local helpers near the feature that owns them.

---

## Dependencies

- Prefer existing libraries already used in the project.
- Do not add new dependencies unless they are clearly required.
- Do not add overlapping libraries that solve the same problem.
- When a new dependency is necessary, keep usage narrow and justified.

---

## Safety boundaries

Never change the following unless explicitly requested by the user:

- environment files
- secrets
- deployment configuration
- CI/CD configuration
- Docker configuration
- infrastructure configuration
- database migrations
- lockfiles
- unrelated project configuration

If a task appears to require one of these, only touch the minimum necessary surface area and keep the change explicit.

---

## Preferred decision-making defaults

When multiple valid options exist, prefer this order:

1. existing project pattern
2. simplest explicit implementation
3. strongly typed solution
4. smallest safe change

Avoid:

- premature abstractions
- framework-heavy patterns without need
- giant files
- hidden magic
- overly generic base classes
- centralizing unrelated responsibilities

---

## Summary for agents

When editing this repository:

- be explicit
- keep code short
- keep code readable
- keep code typed
- keep code local to the business domain
- prefer Pydantic on backend
- prefer interfaces on frontend
- avoid `any`
- avoid unnecessary abstractions
- avoid unrelated refactors
- do not rename files
- validate changed areas before finishing
- Minimal desing local override. USe the global CSS and shadcn config as much as possible.


@/Users/theopinto--dalle/.codex/RTK.md