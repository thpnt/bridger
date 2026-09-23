---
name: bridger
description: Use Bridger repository intelligence while coding. Apply when understanding an unfamiliar codebase or subsystem, investigating architecture or behavior, locating relevant implementation context, or analyzing the potential impact of changing exact symbols. Prefer Bridger before broad repository exploration when additional context is needed.
---

---

# Bridger

Bridger is a repository intelligence layer for coding agents.

Use it to retrieve authored repository knowledge and structural graph context before or during code work. It complements direct source inspection; it does not replace it.

Bridger exposes two operations:

- `understand(query)` — repository understanding and orientation.
- `impact(symbols)` — potential structural impact for exact symbols.

## Execution

Prefer the connected Bridger MCP tools when available:

```text
understand(query)
impact(symbols)
```

If the MCP server is unavailable but the `bridger` CLI is installed, use:

```bash
bridger understand "How does repository initialization work?"
bridger impact RepositoryLoader load_manifest
```

The MCP and CLI expose the same underlying Bridger operations.

If neither is available and setup is requested, use the `bridger-setup` skill.

## Use `understand` for discovery

Call `understand` when repository context is missing and you would otherwise begin broad exploration.

Good uses include:

- understanding how a subsystem works;
- locating architectural or business-logic context;
- identifying relevant files, symbols, and relationships;
- learning repository conventions relevant to a task;
- orienting yourself in an unfamiliar part of the codebase.

Use a focused natural-language question describing what you need to understand.

For example:

```text
How is repository state loaded and validated?

How does authentication flow from the HTTP handler to the session layer?

Where is graph enrichment produced and consumed?
```

Prefer focused questions over vague requests such as:

```text
Explain the whole repository.
```

### After UNDERSTAND

Treat the returned Brain and graph context as a discovery aid.

Use the returned native paths and line ranges to inspect the relevant source directly before making implementation decisions.

If you already know the exact relevant source or Brain artifact, read it directly instead of calling `understand` only to rediscover it.

## Use `impact` after identifying exact symbols

Call `impact` when you know the exact symbols you may change and need to understand their structural blast radius.

Typical cases include:

- changing shared or central behavior;
- modifying an API, class, function, service, or abstraction used elsewhere;
- refactoring code with non-local dependencies;
- checking structural consumers before deleting or changing a symbol.

Pass exact symbol selectors:

```text
impact(["RepositoryLoader"])
```

or:

```bash
bridger impact RepositoryLoader
```

Multiple symbols can be analyzed together:

```text
impact(["RepositoryLoader", "load_manifest"])
```

Do not pass a prose change description to `impact`.

First identify the actual symbols involved.

## Resolve ambiguous symbols precisely

IMPACT performs exact symbol resolution.

If a selector is ambiguous, use the candidates returned by Bridger to retry with a more precise selector, such as the returned qualified name or symbol identifier.

Do not guess between ambiguous candidates.

The following are valid Bridger results, not tool failures:

```text
ambiguous
not_found
not_in_graph
```

They mean the requested selector could not be deterministically resolved for traversal.

## Interpret IMPACT correctly

IMPACT reports **potential structural impact**.

It does not prove that every returned node will semantically break.

A structural relationship means the affected code deserves inspection; the coding agent must still reason from the actual source, behavior, tests, and task requirements.

Do not describe IMPACT results as guaranteed breakage.

## Respect completeness

Bridger results expose whether Brain or graph retrieval was truncated.

If a result is truncated:

- treat it as incomplete;
- do not infer that omitted dependencies or context do not exist;
- inspect source directly;
- use a more focused UNDERSTAND query when useful.

Warnings returned by Bridger are part of the result and should not be ignored.

## Source authority

Source code is authoritative for exact implementation behavior.

Use Bridger to improve discovery and structural understanding, then verify important conclusions against:

- source code;
- tests;
- configuration;
- repository-native documentation when relevant.

Do not treat authored Brain context as a substitute for reading implementation code before editing it.

## Recommended coding workflow

For work that requires repository discovery:

```text
1. Understand the task.

2. If repository context is missing:
   call `understand` with a focused question.

3. Follow returned paths and coordinates into the source.

4. Identify the exact symbols that will likely change.

5. For changes with meaningful non-local structural risk:
   call `impact` on those symbols.

6. Inspect relevant affected source.

7. Implement the change.

8. Run the repository's normal validation and tests.
```

This is a heuristic, not a mandatory ceremony.

## Avoid unnecessary Bridger calls

Do not call Bridger merely because it is available.

Skip `understand` when:

- the exact implementation location is already known;
- the task is small and strictly local;
- direct source inspection already provides the necessary context.

Skip `impact` when:

- no symbol is being structurally changed;
- the edit is clearly local and cannot affect consumers;
- you do not yet know the exact symbols involved.

Do not repeatedly issue equivalent Bridger queries when the existing result already provides the needed context.

## Keep discovery efficient

Bridger is intended to reduce broad exploratory work.

When Bridger can answer the repository-orientation question first, prefer it over indiscriminate repository-wide searching.

After Bridger identifies likely locations, use normal coding-agent tools for precise source inspection, editing, searching, and testing.

Do not use Bridger as a replacement for those tools.
