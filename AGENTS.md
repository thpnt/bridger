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

## Core principles

- Write code that is easy to scan and easy to maintain.
- Keep files under 500 lines; when a file grows beyond that, reorganize the module and split the code into clear, cohesive, logically named components.
- Prefer explicit code over framework tricks.
- Prefer local clarity over DRY abstractions.
- Do not introduce unnecessary abstraction layers.
- Only create abstractions when repetition is visible and justified.
- Keep functions short and focused.
- One function or method should do one thing.
- Follow SOLID principles when using OOP.
- Reuse existing patterns in the codebase before inventing new ones.
- Do not mix competing architectural styles in the same area of the codebase.


---

## Scope of changes

- Keep changes tightly scoped to the request.
- Do not refactor unrelated code.
- Do not rename files unless explicitly requested.
- Do not move files or reorganize folders unless the task requires it.
- DO NOT preserve backward compatibility for API contracts unless explicitly asked to.
- Prefer minimal diffs.

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

Do not preserve backward compatibility. Remove obsolete paths instead of adding compatibility layers, fallbacks, or migrations.

Choose the simplest implementation that fully meets the current requirements. Avoid speculative abstractions, configuration, and indirection.

Grow the system in layers. Start from the smallest version that works end to end, and add each new capability on top of a product that already works. Never trade a working product for unfinished complexity.

Keep components modular and concerns clearly separated.

Prefer established, well-maintained libraries when they reduce overall complexity or improve reliability. Do not reimplement common functionality without a clear reason.

Lean on the dependencies already in the project before writing your own implementation or adding packages. Do not assume a library lacks a capability without checking its documentation and types.

Make architectural decisions for the long term. Do not accept a stopgap that only works for now and is meant to be replaced later.



@/Users/theopinto--dalle/.codex/RTK.md