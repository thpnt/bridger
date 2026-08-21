# 20. OpenAI prompt caching

Prompt caching should be treated as a separate optimization from provider reasoning continuity and context compaction.

The three mechanisms serve different purposes:

```text
Prompt caching
    = reuse identical input prefixes cheaply

previous_response_id
    = preserve provider reasoning/interaction continuity

responses.compact()
    = compress accumulated transient provider trajectory
````

They are complementary and should remain conceptually separate.

For OpenAI workers, Bridger should structure requests so that the most reusable and stable input appears first, while volatile execution state appears later.

OpenAI prompt caching is prefix-based. Identical input prefixes can be reused when subsequent requests share the same rendered prefix. Stable content should therefore precede changing state, tool results, and other volatile inputs.

For GPT-5.6 workers, use explicit prompt-cache boundaries rather than relying only on automatic cache-prefix selection.

## Cache layout

The Stage 4 request should be ordered conceptually as follows:

```text
┌──────────────────────────────────────────────────┐
│ 1. GLOBAL STABLE PREFIX                          │
│                                                  │
│ shared worker system instructions                │
│ general worker execution protocol                │
│ stable tool definitions                          │
├──────────── CACHE BREAKPOINT 1 ──────────────────┤
│                                                  │
│ 2. TARGET-STABLE PREFIX                          │
│                                                  │
│ target-specific worker instructions              │
│ target semantic contract                         │
│ source binding                                   │
│ global/cross-target ownership guidance           │
├──────────── CACHE BREAKPOINT 2 ──────────────────┤
│                                                  │
│ 3. CYCLE-STABLE PREFIX                           │
│                                                  │
│ deterministic cycle focus                        │
│ hydrated completion state at cycle start         │
│ hydrated artifact/question state                 │
│ other immutable Stage 3 cycle-start context      │
├──────────── CACHE BREAKPOINT 3 ──────────────────┤
│                                                  │
│ 4. DYNAMIC EXECUTION SUFFIX                      │
│                                                  │
│ current authoritative execution overlay          │
│ new tool outputs                                 │
│ newly changed completion state                   │
│ newly recorded evidence                          │
│ latest interaction input                         │
└──────────────────────────────────────────────────┘
```

The objective is to maximize reuse at the longest valid unchanged prefix.

The first prefix may be reusable across many targets and cycles.

The second prefix may be reusable across multiple cycles of the same target and source binding.

The third prefix is normally reusable across multiple model calls inside one worker cycle.

The dynamic suffix is expected to change and should not be treated as a reusable cache prefix.

---

## Explicit cache breakpoints

For supported OpenAI models, Bridger should use explicit prompt-cache breakpoints around meaningful stable boundaries.

Conceptually:

```text
global stable context
    ↓
CACHE BREAKPOINT

target-stable context
    ↓
CACHE BREAKPOINT

cycle-stable context
    ↓
CACHE BREAKPOINT

dynamic state and tool interaction
```

Explicit breakpoints are preferred because Stage 4 contains substantial changing context.

Without an intentional boundary, an automatically selected cache prefix may include volatile state or tool history. Once that suffix changes, an otherwise large stable prefix may fail to achieve the intended cache reuse.

The exact number of breakpoints is an implementation/tuning choice rather than a semantic harness contract.

The important invariant is:

> Stable reusable context must come before volatile execution context, and cache boundaries should be placed before volatile sections.

---

## Cache keys

For OpenAI workers, use a deterministic `prompt_cache_key` derived from stable request identity.

The cache key should distinguish inputs that must not share a cache entry while remaining stable across requests that should share one.

Conceptually, useful stable inputs include:

```text
worker prompt/profile version
target identity
target contract version
source binding identity where relevant
tool-surface/schema version
```

Do not include volatile execution state such as:

```text
current completion mutations
working summary changes
tool results
remaining budget
response IDs
current provider trajectory
```

The cache key is an optimization hint only.

It must not become durable execution authority or affect correctness.

If a cache miss occurs, the request must behave identically apart from cost/latency.

---

## Relationship with exact Bridger instructions

Prompt caching must not alter the exact-context invariant.

Stage 4 still supplies:

```text
exact canonical hydrated base
+
exact current authoritative execution overlay
```

to the model.

Caching only changes how OpenAI processes repeated identical input prefixes.

It does not permit Bridger to omit authoritative instructions or assume that cached state replaces them.

In particular:

```text
canonical stable context
    → resend exactly
    → likely cache hit

current authoritative overlay
    → resend exactly
    → usually uncached because it changes
```

This is desirable.

Caching is a provider optimization below the semantic context contract.

---

## Relationship with system/user/instruction roles

Prompt caching is based primarily on identical input prefixes, not on whether content is labelled `system`, `developer`, `user`, or another role.

Role selection should continue to follow instruction-authority semantics.

Do not move changing information into a different role merely to influence caching.

The important caching property is ordering:

```text
stable content first
changing content later
```

rather than:

```text
system = cacheable
user = non-cacheable
```

For the OpenAI Stage 4 path, exact Bridger control context may be mapped to the Responses API `instructions` surface as defined elsewhere in this design.

Stable portions of that instruction content should be ordered before the mutable execution overlay so that reusable prefixes remain stable.

---

## Tool definitions

Stable tool definitions should be included in the reusable prefix where supported by the provider cache behavior.

The worker tool surface is largely stable within a cycle and usually stable across cycles for the same permission profile.

Therefore:

```text
worker instructions
+
stable tool schemas
+
target contract
```

are good candidates for cache reuse.

Do not reorder, regenerate, or serialize equivalent tool definitions inconsistently between requests.

Stable deterministic serialization is required for reliable prefix matching.

Changes to:

```text
tool name
description
schema
ordering
permission-derived tool surface
```

should naturally produce a different effective cache prefix.

---

## Within-cycle behavior

A normal OpenAI cycle should behave approximately as:

```text
FIRST MODEL CALL

global stable prefix              → cache write / miss
target-stable prefix              → cache write / miss
cycle-stable prefix               → cache write / miss
dynamic initial state             → uncached
        ↓
response A
        ↓
tool execution
        ↓

SECOND MODEL CALL

same global stable prefix         → cache hit
same target-stable prefix         → cache hit
same cycle-stable prefix          → cache hit
updated authoritative overlay     → uncached
new tool output                   → uncached
previous_response_id              → provider continuation
        ↓
response B
```

Subsequent model calls follow the same pattern.

The growing provider reasoning trajectory is handled separately through `previous_response_id`.

It does not require Bridger to replay the entire historical reasoning or tool trajectory as ordinary prompt input.

---

## Cross-cycle behavior

A cycle boundary intentionally discards:

```text
previous_response_id
provider reasoning trajectory
compacted provider context
transient recent working set
```

but it does not invalidate OpenAI's prompt cache.

The next cycle is freshly hydrated from durable Bridger state:

```text
fresh WorkerContext
    ↓
same global worker prefix         → may still cache-hit
same target contract prefix       → may still cache-hit
new cycle focus/state             → new or shorter-prefix hit
```

Therefore Bridger gets a useful combination:

```text
fresh semantic/model trajectory every cycle

while

stable large input prefixes may remain cheaply reusable
```

This is one reason to keep long-lived stable target semantics separated from cycle-specific state.

---

## Relationship with `previous_response_id`

Prompt caching does not replace reasoning continuity.

For OpenAI:

```text
stable input prefix
    → prompt cache

provider reasoning state
    → previous_response_id
```

A cache hit means OpenAI can reuse computation associated with an identical input prefix.

It does **not** mean that the model's hidden reasoning from a previous response is recreated from the prompt cache.

Reasoning continuity remains the responsibility of the provider continuation mechanism.

---

## Can model reasoning itself be prompt-cached?

Not directly.

Reasoning tokens are generated model output and are not made prompt-cacheable simply by changing system/user prompt boundaries.

Do not attempt to optimize reasoning reuse through prompt-role manipulation.

The mechanisms are:

```text
stable instructions / repeated input
    → prompt caching

hidden/provider reasoning trajectory
    → previous_response_id

large old reasoning/tool trajectory
    → responses.compact()
```

OpenAI may internally benefit from persisted reasoning in ways that improve effective cache efficiency, but Bridger should not model hidden reasoning tokens as ordinary cached prompt input.

---

## Relationship with compaction

Compaction and prompt caching should preserve the same split-context architecture.

Before compaction:

```text
CACHED / EXACT
────────────────────────────
global stable prefix
target-stable prefix
cycle-stable exact context

DYNAMIC / EXACT
────────────────────────────
current authoritative overlay

TRANSIENT PROVIDER STATE
────────────────────────────
reasoning trajectory
historical tool interaction
previous_response_id chain
```

At context pressure:

```text
transient provider trajectory
        ↓
responses.compact()
        ↓
opaque compacted trajectory
```

After compaction:

```text
global stable prefix             → reusable/cached
target-stable prefix             → reusable/cached
cycle-stable exact context       → reusable/cached where unchanged
current authoritative overlay    → exact dynamic input
compacted provider trajectory    → transient compacted input
protected recent tool batches    → exact recent input
```

The first post-compaction response starts a new provider continuation chain as defined in the compaction section.

Compaction must not alter the cacheable canonical prefixes.

---

## Deterministic serialization

Reliable caching requires stable serialization.

Equivalent Bridger state should render identically when it is intended to share a cache prefix.

In particular:

* preserve deterministic section ordering;
* preserve deterministic tool-definition ordering;
* use deterministic JSON serialization;
* avoid timestamps, random IDs, or volatile diagnostics inside stable prefixes;
* place volatile fields after the final reusable cache boundary;
* avoid cosmetic prompt changes between model calls.

The current deterministic `WorkerContext` serialization should remain the basis for this behavior.

---

## Usage and observability

OpenAI usage reporting should be retained through the normalized LLM usage model.

Where exposed by the provider, track at least:

```text
input_tokens
cached_input_tokens
cache_write_tokens
output_tokens
reasoning_tokens
```

Cache statistics are operational diagnostics and cost/latency telemetry.

They do not affect semantic execution state.

Useful Stage 4 diagnostics include:

```text
effective input tokens
cached input tokens
cache write tokens
cache-hit ratio
active cache key
selected cache breakpoints
```

Do not introduce cache-specific execution budgets for V0.

Normal input-token accounting should continue to follow provider-reported usage.

---

## OpenAI-specific implementation

For the OpenAI provider, configure prompt caching through the supported Responses API cache controls.

Conceptually:

```text
responses.create(
    ...
    prompt_cache_key = deterministic stable key
    prompt_cache_options = {
        mode: explicit
    }
)
```

and place provider-supported cache breakpoints at the stable boundaries described above.

The exact SDK representation should follow the installed OpenAI SDK version and current Responses API contract.

The installed Responses API contract permits `prompt_cache_breakpoint` on
`input_text` content blocks, but not inside the top-level `instructions` string.
The adapter therefore retains the generic request's exact `instructions` value as
the semantic authority and renders it, without omission or reordering, as one
ordered developer message containing global-, target-, cycle-, and dynamic
`input_text` blocks. The first three blocks carry explicit breakpoints. Compacted
provider context and incremental interaction input remain after that developer
message and after the final reusable boundary.

If the configured OpenAI model family does not support explicit breakpoints, the
adapter omits the cache controls and sends the same exact instructions through
the ordinary top-level instruction surface. Unsupported cache controls must not
turn an otherwise valid worker request into a provider error.

This behavior belongs inside the OpenAI adapter.

The provider-neutral Stage 4 runtime should express only the necessary cache intent/metadata and must not depend on OpenAI-specific cache objects for correctness.

Other providers may later implement equivalent prefix caching without changing worker-cycle semantics.

---

## Caching invariants

The following rules are normative:

```text
1. Prompt caching is an optimization only.
   Cache misses must never change semantic behavior.

2. Stable reusable input must precede volatile input.

3. Canonical Bridger context is always supplied exactly;
   a provider cache never becomes context authority.

4. Mutable execution state must not be placed inside a supposedly
   stable cache segment merely to increase cache reuse.

5. Provider reasoning is not modeled as prompt-cached state.

6. previous_response_id owns within-cycle reasoning continuity.

7. responses.compact() owns transient trajectory reduction under
   context pressure.

8. Cache state may survive worker-cycle boundaries at the provider,
   but Bridger does not persist or rely on it.

9. Deterministic serialization and stable tool ordering should be
   preserved to maximize cache-prefix reuse.

10. The OpenAI adapter is the first caching implementation;
    provider-neutral harness correctness must not depend on cache hits.
```

## Resulting OpenAI context/caching architecture

```text
                    STAGE 3 HYDRATION
                           │
                           ▼

        ┌────────────────────────────────────┐
        │ GLOBAL STABLE PREFIX               │
        │                                    │
        │ shared worker instructions         │
        │ protocol + stable tool surface     │
        └─────────────────┬──────────────────┘
                          │
                  CACHE BREAKPOINT 1
                          │
                          ▼
        ┌────────────────────────────────────┐
        │ TARGET-STABLE PREFIX               │
        │                                    │
        │ target instructions                │
        │ target contract                    │
        │ source / ownership context         │
        └─────────────────┬──────────────────┘
                          │
                  CACHE BREAKPOINT 2
                          │
                          ▼
        ┌────────────────────────────────────┐
        │ CYCLE-STABLE PREFIX                │
        │                                    │
        │ deterministic cycle focus          │
        │ hydrated cycle-start state         │
        └─────────────────┬──────────────────┘
                          │
                  CACHE BREAKPOINT 3
                          │
                          ▼
        ┌────────────────────────────────────┐
        │ DYNAMIC EXACT STATE                │
        │                                    │
        │ current execution overlay          │
        │ latest tool outputs                │
        └─────────────────┬──────────────────┘
                          │
                          ▼
                     Luna xhigh
                          │
                          ▼
                  reasoning / tools
                          │
                          ▼
                previous_response_id
                          │
                          ▼
                 next model request
                          │
                 stable prefixes
                  mostly cache-hit
                          │
                          ▼
                context pressure?
                    │          │
                   no         yes
                    │          │
                    │          ▼
                    │   responses.compact()
                    │          │
                    │          ▼
                    │   compacted trajectory
                    │          +
                    │   exact cached prefixes
                    │          +
                    │   exact current overlay
                    │          +
                    │   exact recent tool batches
                    │          │
                    │          ▼
                    │   new response chain
                    │
                    ▼
               continue cycle
```

The overall optimization model is therefore:

```text
LONG-LIVED STABLE INPUT
    → prompt cache

CURRENT AUTHORITATIVE STATE
    → exact uncached suffix

WITHIN-CYCLE REASONING
    → previous_response_id

LONG WITHIN-CYCLE TRAJECTORY
    → responses.compact()

NEXT CYCLE
    → fresh reasoning trajectory
    → stable prompt prefixes may still cache-hit
```

This preserves the core architecture: Bridger owns exact durable context and execution state, while OpenAI caching, continuation, and compaction are transient provider optimizations layered underneath it.
