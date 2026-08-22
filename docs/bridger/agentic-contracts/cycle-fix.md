# Bridger — Bounded Worker Cycles & Reasoning Continuity Fix

## 1. Objective

Change the worker execution model from:

```text
hydrate whole target
    ↓
worker keeps working
    ↓
potentially investigates all obligations
    ↓
request_finalization()
```

to:

```text
hydrate whole target
+
deterministically select current cycle focus
    ↓
worker investigates that bounded focus
    ↓
multiple model/tool turns
with reasoning continuity
    ↓
split context compaction if necessary
    ↓
yield_cycle()
    ↓
fresh Stage 3 hydration
    ↓
next deterministic focus
```

until:

```text
all completion obligations resolved
    ↓
final readiness cycle
    ↓
request_finalization()
    ↓
existing Stages 6+
```

This keeps:

- the **target** as the semantic unit of acceptance;
- the **completion contract** as the definition of target completeness;
- the **cycle** as a bounded execution unit;
- durable Bridger state as the long-horizon authority;
- exact hydrated/runtime state outside lossy compaction;
- provider reasoning/conversation state as transient within-cycle cognition.

For OpenAI workers, within-cycle reasoning continuity uses the Responses API `previous_response_id` mechanism.

No new planner, task queue, subtask state, durable conversation state, or generic agent framework should be introduced.

---

# 2. Current implementation and exact gap

The current `WorkerContext` contains the whole target contract, all completion obligations, repair findings, working summary, open questions, budget and artifact inventory, but no explicit current-cycle objective.

Hydration currently derives only:

```text
INITIAL
or
REPAIR
```

and projects the complete obligation/finding state.

Stage 4 then allows an unbounded sequence of:

```text
model
→ tools
→ model
→ tools
→ ...
```

whose only normal semantic exit is currently `request_finalization()`.

The shared worker prompt reinforces whole-target thinking: it tells the worker to investigate every criterion and then request finalization once the complete contract is satisfied.

So the model currently has no reason to stop after one useful semantic unit.

There is a second related implementation gap.

Stage 4 currently reconstructs subsequent requests from the canonical hydrated context, execution-state overlay, and recent tool history. This preserves visible interaction history but does not preserve OpenAI's opaque reasoning state between tool turns.

The OpenAI adapter already normalizes the provider response ID, but does not use it for continuation. It also currently uses `store=False`.

The fix should therefore address two connected concerns:

1. bound one worker cycle around one deterministic semantic objective;
2. preserve transient provider reasoning within that bounded cycle without making provider state authoritative.

---

# 3. Locked behavior for one worker cycle

## Normal execution

One cycle receives **one primary unresolved completion obligation**.

Selection must be deterministic:

```python
for obligation in target_definition.completion_obligations:
    if corresponding_state.status == UNINVESTIGATED:
        return obligation
```

Use the canonical order already present in `TargetDefinition.completion_obligations`.

Do **not** let the model choose the next obligation.

The complete target contract and all completion states remain visible. The focus controls what the worker should actively pursue; it does not hide the rest of the target.

Example:

```text
Target: architecture

All obligations:

✓ runtime-entrypoints
○ runtime-components        ← CURRENT CYCLE FOCUS
○ control-flow
○ async-execution
○ recovery

Cycle instruction:

Investigate runtime-components deeply enough to resolve it.

Do not deliberately expand into unrelated unresolved obligations.

If the same investigation directly resolves another obligation,
you may update it as well.
```

This distinction matters:

> **One primary obligation per cycle, not exactly one obligation changed per cycle.**

The worker should not discard useful discoveries.

---

## Repair execution

Repair should preserve the existing repair model rather than redesign Stage 9.

The current hydration already resolves the authoritative `open_finding_refs` into `repair_findings`.

For repair mode:

```text
cycle focus = currently routed open repair findings
```

in deterministic persisted order.

Do **not initially force one finding per repair cycle**, because that would change the semantics of `max_repair_cycles` and potentially turn one review round containing several related findings into many artificial repair cycles.

So:

```text
NORMAL cycle
    → one primary uninvestigated obligation

REPAIR cycle
    → current deterministic repair finding set
```

This is the smallest change consistent with the current system.

---

## Final-readiness cycle

When no obligation remains `UNINVESTIGATED`, hydration should not invent another obligation.

Instead:

```text
cycle focus = FINALIZATION_READINESS
```

The model is told to:

- inspect the current target as a whole;
- make any necessary final coherence/organization fixes;
- verify the completion state;
- request finalization.

This preserves the useful existing whole-target check, but moves it to the correct time.

---

# 4. Add a transient `cycle_focus` to Stage 3 hydration

Add one small transient model under `src/models/hydration.py`.

Conceptually:

```python
class WorkerCycleFocusKind(StrEnum):
    OBLIGATION = "obligation"
    REPAIR_FINDINGS = "repair-findings"
    FINALIZATION_READINESS = "finalization-readiness"


class WorkerCycleFocus(BaseModel):
    kind: WorkerCycleFocusKind
    obligation_id: str | None = None
    finding_ids: tuple[str, ...] = ()
```

Then:

```python
class WorkerContext(...):
    ...
    cycle_focus: WorkerCycleFocus
```

Do **not** persist this separately.

It is a deterministic projection of existing authorities:

```text
TargetDefinition
+
TargetCompletionState
+
TargetTaskState.open_finding_refs
        ↓
WorkerCycleFocus
```

Therefore it is reconstructable and non-authoritative, exactly like the rest of `WorkerContext`.

### Hydration selection

Add something equivalent to:

```python
_select_cycle_focus(
    definition,
    completion_state,
    repair_findings,
)
```

Rules:

```text
if repair findings exist:
    REPAIR_FINDINGS

else if first UNINVESTIGATED obligation exists:
    OBLIGATION(first unresolved in definition order)

else:
    FINALIZATION_READINESS
```

No ranking model. No heuristic scoring. No new scheduler contract.

### Serialization

`serialize_worker_context()` should include a prominent current-cycle section before the full obligation list:

```text
# Current cycle objective

kind: obligation
obligation_id: runtime-components

Your primary responsibility during this cycle is to investigate
and resolve this obligation.

Keep the complete target in mind, but do not deliberately move
on to unrelated unresolved obligations.

If the same evidence directly resolves closely related obligations,
you may update them too.

Once this cycle's intended work is complete:

- use yield_cycle if the target still requires work;
- use request_finalization only if the complete target is ready.
```

This instruction should be **generated by the harness**, not copied into every target prompt.

---

# 5. Add `yield_cycle()` beside `request_finalization()`

The current implementation already treats finalization as a special control tool that is always appended to the worker surface rather than permission-configured like operational tools.

`yield_cycle()` should use exactly the same pattern.

In `worker_tools.py`:

```python
FINALIZATION_TOOL_ID = "request_finalization"
YIELD_CYCLE_TOOL_ID = "yield_cycle"
```

Both are control tools, not operational tools.

Both:

```text
take no arguments
must be the sole tool call in their response
are always exposed
do not consume repository/workspace permissions
```

Suggested description:

```text
yield_cycle:

End the current bounded worker cycle after preserving useful progress.

Use this when the current cycle objective is complete, or when continuing
it is better handled from a fresh hydrated context.

This must be the only tool call in the response.
```

### Control-call protocol

Generalize the existing finalization handling:

```text
operational call + yield_cycle
    → yield protocol error
    → operational calls may execute

operational call + request_finalization
    → existing finalization protocol behavior

yield_cycle + request_finalization
    → neither control request succeeds
```

The worker must observe preceding mutation results before ending the cycle.

---

# 6. Yield lifecycle semantics

Add:

```python
class WorkerCycleOutcome(StrEnum):
    ...
    CYCLE_YIELDED = "cycle-yielded"
```

A successful yield should produce:

```text
WORKING
    ↓ yield_cycle()
SCHEDULED
```

and return:

```text
WorkerCycleOutcome.CYCLE_YIELDED
```

No:

```text
YieldRequest
CycleResult
YieldCheckpoint
CycleState
```

should be introduced.

`TargetTaskState` already contains all durable progress needed for the next hydration.

`SCHEDULED` is the correct existing phase to reuse because Stage 3 already requires `SCHEDULED` and immediately performs:

```text
SCHEDULED → HYDRATING
```

It also preserves the target's existing concurrency ownership.

The loop becomes:

```text
SCHEDULED
    ↓
HYDRATING
    ↓
WORKING
    ↓
yield_cycle
    ↓
SCHEDULED
    ↓
HYDRATING
    ↓
WORKING
```

until:

```text
WORKING
    ↓
request_finalization
    ↓
existing Stage 6
```

Document `WORKING → SCHEDULED` as a legal target transition.

---

# 7. What `yield_cycle()` should mean to the model

The prompt should establish a precise distinction:

```text
yield_cycle()

"I have completed the intended bounded work for this cycle,
or I have persisted enough useful progress that a fresh cycle
should continue from durable state."
```

versus:

```text
request_finalization()

"I believe the complete target is ready for validation and review."
```

A normal trajectory should look like:

```text
cycle focus: runtime-entrypoints
    ↓
investigate
    ↓
record evidence
    ↓
write/refine knowledge
    ↓
update completion item
    ↓
update progress if useful
    ↓
yield_cycle
```

If the obligation itself is large:

```text
investigate
    ↓
persist partial progress
    ↓
yield_cycle
```

is also legal.

Because the obligation remains `UNINVESTIGATED`, Stage 3 will select **the same obligation again** in the next cycle.

That gives us context resets even inside difficult obligations without introducing partial-obligation state.

---

# 8. Provider continuation and OpenAI `previous_response_id`

Provider continuation is a transient Stage 4 transport capability.

Do not expose OpenAI-specific terminology as durable harness state.

Add a small provider-neutral continuation field to the LLM request contract, conceptually:

```python
class LLMRequest(BaseModel):
    ...
    continuation_ref: str | None = None
```

`LLMResponse.response_id` already provides the corresponding provider response identity.

The OpenAI provider maps:

```text
LLMRequest.continuation_ref
        ↓
previous_response_id
```

Other providers may later map `continuation_ref` to an equivalent native mechanism or use reconstructed conversation history.

Stage 4 therefore owns only:

```text
last_response_id: str | None
```

in process memory for the active cycle.

It is:

```text
transient
cycle-local
non-authoritative
not checkpointed
not written into TargetTaskState
```

For OpenAI GPT-5.6, configure:

```text
reasoning.context = all_turns
```

and use the previous response as the continuation reference.

This allows reasoning items available through the Responses API to remain available across tool turns.

The normal OpenAI trajectory is:

```text
initial request
        ↓
response A
        ↓
execute tools
        ↓
continuation_ref = A.id
        ↓
response B
        ↓
execute tools
        ↓
continuation_ref = B.id
        ↓
response C
```

On:

```text
yield
finalization
interruption/recovery
```

discard the continuation reference.

The next worker cycle always begins from fresh Stage 3 hydration.

---

# 9. Exact control context and OpenAI storage

The exact Bridger control context must remain outside the provider continuation history wherever the provider allows it.

For OpenAI, use the Responses API `instructions` field for the current exact control context.

OpenAI does not automatically carry previous `instructions` forward when using `previous_response_id`.

This is desirable for Bridger.

Every OpenAI worker request should therefore explicitly resend the current exact control context.

Conceptually:

```text
exact_control_context
=
canonical Stage 3 WorkerContext
+
current authoritative execution-state overlay
```

The canonical Stage 3 portion remains byte-for-byte stable for the cycle.

The execution-state overlay is recomputed from authoritative runtime state and may change after tool execution.

The previous model response chain does **not** become the authority for either.

For OpenAI worker calls, make request storage configurable and enable it for the active response chain:

```python
class LLMRequest:
    ...
    store: bool = False
```

Stage 4 OpenAI worker calls use:

```python
store=True
```

Other existing operations retain their current default unless they independently need stored continuation.

This storage choice is an OpenAI transport requirement, not durable Bridger state.

---

# 10. Split Stage 4 context model

The effective Stage 4 context is divided into four logical segments.

```text
┌──────────────────────────────────────────────┐
│ 1. CANONICAL HYDRATED BASE — EXACT          │
│                                              │
│ shared worker instructions                   │
│ target instructions                          │
│ source binding                               │
│ target semantic contract                     │
│ cycle focus                                  │
│ completion contract + hydrated states        │
│ permissions                                  │
│ hydrated artifacts/questions/etc.            │
└──────────────────────────────────────────────┘
                     +
┌──────────────────────────────────────────────┐
│ 2. CURRENT EXECUTION OVERLAY — EXACT         │
│                                              │
│ current completion changes                   │
│ current artifact changes                     │
│ working summary                              │
│ open questions                               │
│ new evidence                                 │
│ remaining budget                             │
└──────────────────────────────────────────────┘
                     +
┌──────────────────────────────────────────────┐
│ 3. PROVIDER TRAJECTORY — TRANSIENT           │
│                                              │
│ model reasoning state                        │
│ assistant tool calls                         │
│ tool outputs                                 │
│ previous within-cycle interaction state      │
└──────────────────────────────────────────────┘
                     +
┌──────────────────────────────────────────────┐
│ 4. PROTECTED RECENT TOOL BATCHES — EXACT     │
│                                              │
│ bounded local copies of latest tool calls    │
│ and results                                  │
└──────────────────────────────────────────────┘
```

The first two segments are authoritative control context.

They must **never be replaced by compaction**.

The third segment is the provider's transient reasoning/interaction trajectory.

It is the primary target of compaction.

The fourth segment is a bounded local exact replay anchor used after compaction and remains useful as a provider-neutral fallback.

---

## OpenAI representation

For OpenAI:

```text
instructions
    =
    canonical hydrated base
    +
    current authoritative execution overlay

previous_response_id
    =
    transient provider trajectory

input
    =
    only new tool outputs / incremental interaction items
```

Do not encode the repeatedly changing authoritative execution overlay as ordinary user history on the OpenAI path.

It should remain in the exact `instructions` layer so that:

- it does not accumulate across response chaining;
- stale state snapshots do not become permanent conversation history;
- compaction cannot replace the current authoritative state;
- every model turn receives the exact latest Bridger state.

The same applies to the canonical hydrated base.

---

## Role of `_RecentToolWorkingSet`

Retain `_RecentToolWorkingSet`.

Its responsibility changes slightly for the OpenAI continuation path.

It is no longer the sole representation of the whole active model trajectory.

Instead it provides:

1. bounded exact copies of recent tool interactions;
2. exact recent-batch replay after compaction;
3. a provider-neutral reconstruction fallback;
4. bounded debugging/context diagnostics.

The existing protected-recent-batch philosophy remains useful.

For V0, preserve the current protected recent batch count unless evidence justifies changing it.

---

# 11. Split compaction semantics

Add `compact()` to `LLMClient`.

Conceptually:

```python
async def compact(
    self,
    request: LLMCompactionRequest,
) -> LLMCompactionResult:
    ...
```

Add an opaque compacted-context representation:

```python
class LLMCompactedContext(BaseModel):
    provider: str
    payload: JsonValue


class LLMCompactionResult(BaseModel):
    context: LLMCompactedContext
    usage: LLMUsage
    retry_count: int = 0
```

The harness must not interpret or rewrite `payload`.

It is transient provider context.

For OpenAI, the provider maps this to the output items returned by:

```text
responses.compact(...)
```

The resulting compaction item may contain provider-internal compressed reasoning/interaction state and must remain opaque to Bridger.

---

## What gets compacted

When OpenAI context pressure is reached:

```text
DO NOT COMPACT

canonical Stage 3 base
current authoritative execution overlay


COMPACT

provider reasoning trajectory
historical tool interactions
historical assistant/tool state
```

The exact recent tool batches are retained locally as an additional bounded replay anchor.

The compaction call should receive:

```text
instructions =
    exact canonical base
    +
    exact current execution overlay

previous_response_id =
    latest active response ID

input =
    any currently pending tool outputs required to complete
    the latest model-requested tool batch
```

Conceptually:

```text
exact instructions
        │
        ├──────────────────────────────────┐
        │                                  │
previous_response_id                 pending tool results
        │                                  │
        └─────────────┬────────────────────┘
                      ▼
             responses.compact(...)
                      ↓
              opaque compacted output
```

The exact instructions inform the compaction operation but are not replaced by the compaction result.

---

## Starting a new chain after compaction

After compaction, **do not continue using the old `previous_response_id` chain**.

The next model request starts a fresh provider chain.

Its effective context is:

```text
exact canonical hydrated base
+
exact current execution overlay
+
opaque compacted trajectory
+
exact protected recent tool batches
```

For OpenAI:

```text
responses.create(
    instructions = exact_control_context,

    input = [
        compacted_output,
        exact protected recent tool batches,
    ],

    previous_response_id = NONE,
)
```

Capture the resulting response ID:

```text
new response
    ↓
new continuation_ref
    ↓
normal previous_response_id chaining resumes
```

Therefore:

```text
old response chain
        ↓
compact()
        ↓
opaque compacted trajectory
        +
exact recent tool anchor
        +
exact authoritative context
        ↓
new response chain
```

The old response chain is no longer used for continuation.

---

## Why replay recent tool batches after compaction

Native compaction intentionally compresses the provider trajectory.

This is useful for long-horizon reasoning, but the latest repository observations are often the most operationally important context.

Bridger therefore keeps a small bounded number of recent tool batches exact.

After compaction:

```text
compacted trajectory
    = broad historical continuity
      including provider reasoning

protected recent batches
    = exact latest repository observations

execution overlay
    = exact latest Bridger authority
```

Some information from the protected batches may also be represented inside the compacted provider state.

That bounded semantic overlap is intentional.

It trades a small amount of duplicated context for preserving exact recent evidence while retaining compacted hidden reasoning.

Do not replay the entire historical working set.

Only the protected recent batches are replayed exactly.

---

## Repeated compaction

Compaction may occur more than once inside an unusually long cycle.

Example:

```text
Base + Overlay
    ↓
provider chain A
    ↓
compact
    ↓
Compact A + exact recent batches
    ↓
provider chain B
    ↓
compact
    ↓
Compact B + exact recent batches
    ↓
provider chain C
```

At every compaction boundary:

- exact canonical context is regenerated from the existing cycle base;
- exact current execution overlay is recomputed from authoritative state;
- only bounded recent tool batches are replayed exactly;
- the provider trajectory is replaced by the new compacted representation;
- a new response continuation chain begins.

Compacted provider context never crosses a worker-cycle boundary.

---

# 12. Compaction trigger

Do not compact every N turns.

Compact based on **context pressure**.

### Initial request

The first request continues using the existing deterministic `ContextWindowManager` checks.

The harness knows the complete initial input locally.

### Chained requests

Once `previous_response_id` is active, local message serialization no longer represents the complete effective provider context because it does not expose the persisted reasoning trajectory.

Use provider usage as the primary context-pressure signal.

Before the next normal model inference, estimate:

```text
projected_next_context
≈
latest_response.input_tokens
+
latest_response.output_tokens
+
pending_incremental_input
+
reserved_next_response_headroom
```

If the projected context exceeds a configured soft threshold:

```text
compact before the next normal model inference
```

A reasonable initial V0 tuning value is approximately:

```text
75% of the configured model context window
```

but the percentage is runtime tuning configuration, not semantic contract.

Conceptually:

```python
class WorkerRuntimeLimits:
    ...
    compaction_trigger_ratio: float = 0.75
```

### Why conservative headroom matters

Reasoning models may consume substantial reasoning tokens during the next inference.

Compaction should therefore happen before the hard provider limit becomes imminent.

The runtime must retain enough headroom for:

- pending exact tool results;
- exact control instructions;
- protected recent-batch replay after compaction;
- the next model response and reasoning allocation.

---

# 13. Compaction accounting

Compaction is model execution overhead, not free housekeeping.

Charge:

```text
compaction API attempt
    → model_calls

compaction input usage
    → input_tokens

compaction output usage
    → output_tokens
```

against both:

```text
TargetTaskState.usage
FleetRunState.usage
```

using the existing coordinator/budget machinery where practical.

Do not introduce:

```text
compaction_budget
compaction_tokens
compaction_attempts
```

for V0.

If there is insufficient hard execution budget to perform required compaction, preserve the existing target/fleet budget-stop semantics.

If compaction fails because of provider/runtime failure, cross the existing Stage 5 interruption/recovery boundary.

Do not silently discard the provider trajectory and continue as though compaction succeeded.

---

# 14. LLM contract changes

The provider-neutral LLM layer should gain only the minimum contracts needed by this feature.

## Exact instructions

Add an explicit exact instruction surface:

```python
class LLMRequest(BaseModel):
    ...
    instructions: str | None = None
```

Semantics:

> Highest-priority exact instruction/control context for the current request.

For OpenAI this maps to Responses API `instructions`.

Other providers may map it to their equivalent system/developer instruction mechanism.

For Stage 4, it contains:

```text
canonical hydrated base
+
current authoritative execution overlay
```

---

## Continuation

Add:

```python
class LLMRequest(BaseModel):
    ...
    continuation_ref: str | None = None
```

The OpenAI adapter maps:

```text
continuation_ref
    → previous_response_id
```

`LLMResponse.response_id` remains the source of the next continuation reference.

Do not introduce a durable continuation model.

---

## Storage

Add request-level storage configuration:

```python
class LLMRequest(BaseModel):
    ...
    store: bool = False
```

OpenAI Stage 4 worker requests that use stored response continuation set:

```text
store = true
```

---

## Reasoning configuration

Extend the current reasoning contract to support the worker model.

At minimum support:

```python
class LLMReasoningConfig(BaseModel):
    effort: ... | "xhigh" | "max"
    context: "auto" | "current_turn" | "all_turns" | None
```

For the intended GPT-5.6 worker configuration:

```text
effort = xhigh
context = all_turns
```

Do not hard-code these values inside `WorkerRunner`.

They belong in resolved model/worker configuration.

---

## Compacted context

Add:

```python
class LLMRequest(BaseModel):
    ...
    compacted_context: LLMCompactedContext | None = None
```

A provider adapter is responsible for translating its own opaque compacted payload into valid provider input.

The generic harness must not inspect that payload.

Provider compatibility must be enforced:

```text
compacted_context.provider
must match
active provider
```

unless a future explicit conversion mechanism exists.

---

## Compaction operation

Extend `LLMClient`:

```python
class LLMClient(Protocol):

    async def generate(...) -> LLMResponse:
        ...

    async def compact(
        self,
        request: LLMCompactionRequest,
    ) -> LLMCompactionResult:
        ...
```

For OpenAI:

```text
generate()
    → responses.create(...)

compact()
    → responses.compact(...)
```

Other providers may later:

- implement an equivalent native compaction API;
- implement provider-specific context reduction;
- fall back to a Bridger-managed compaction strategy.

Stage 4 should depend on the `LLMClient` capability, not directly on OpenAI SDK objects.

---

# 15. Prompt changes

The main prompt change belongs in:

```text
src/prompts/worker/system.md
```

Target-specific packs should remain predominantly semantic.

Update the shared prompt in four places.

### Bounded responsibility

Clarify:

```text
The target is your overall responsibility.

The harness also gives you one current cycle objective.

Concentrate the present investigation on that objective.
```

### Investigation standard

Replace wording that encourages immediately investigating every criterion with:

```text
Across successive cycles, every applicable completion criterion must
eventually be meaningfully investigated.

During the current cycle, prioritize the cycle objective supplied
by the harness.
```

### Working toward completion

Add:

```text
Do not deliberately move through all remaining obligations in one cycle.

If the current investigation naturally resolves a closely related
obligation, recording that resolution is allowed.
```

### Cycle termination

Add a dedicated distinction:

```text
yield_cycle

    current bounded work should end;
    target execution continues later


request_finalization

    complete target appears ready for evaluation
```

The prompt should explicitly tell the model:

```text
When your current cycle objective has been adequately handled and
uninvestigated target obligations remain, call yield_cycle.

When no required/applicable obligation remains uninvestigated and
the target as a whole is ready, call request_finalization.
```

The harness-provided `cycle_focus` carries the concrete per-cycle directive.

The shared system prompt explains the general execution protocol only.

---

# 16. Important non-goals

Do **not** introduce:

- a planner selecting obligations;
- an LLM deciding the next obligation;
- a durable `CycleTask`;
- a durable `CycleFocus`;
- a `YieldRequest` artifact;
- provider conversation/response IDs in `TargetTaskState`;
- durable persisted compacted provider context;
- durable persisted provider reasoning;
- one Markdown file per obligation;
- a hard requirement that only the focused obligation may change;
- a separate compaction budget;
- one repair cycle per finding;
- arbitrary fixed `max_turns_per_cycle` initially.

`previous_response_id`, provider response IDs, and compacted provider context exist only in the active Stage 4 execution.

They must be discarded on:

```text
yield
finalization
interruption/recovery
cycle termination
```

The last non-goal regarding `max_turns_per_cycle` is intentional.

With:

```text
one deterministic semantic focus
+
explicit yield control
+
strong prompt discipline
+
reasoning continuity
+
context compaction
+
existing overall budgets
```

inspect real traces before adding another mechanical turn cap.

If workers repeatedly ignore `yield_cycle`, a later per-cycle limit can be introduced based on evidence.

---

# 17. Main implementation files

The change should remain concentrated.

| File | Change |
| --- | --- |
| `src/models/hydration.py` | Add transient `WorkerCycleFocus`; add it to `WorkerContext` |
| `src/memory/hydration.py` | Deterministically select focus; serialize explicit cycle objective |
| `src/memory/worker_tools.py` | Add `yield_cycle` beside `request_finalization`; generalize control-call validation |
| `src/memory/worker_cycle.py` | Add `CYCLE_YIELDED`; `WORKING → SCHEDULED`; maintain transient continuation ref; build exact control instructions; trigger/account compaction; reset chain after compaction |
| `src/llm/models.py` | Add exact instructions, continuation ref, request storage, `xhigh`/reasoning context, compacted-context and compaction result/request contracts |
| `src/llm/client.py` | Add `compact()` |
| `src/llm/providers/openai.py` | Map continuation ref to `previous_response_id`; map exact instructions; request-level storage; implement `responses.compact()`; translate opaque compacted output back into future input |
| `src/llm/testing/dummy.py` | Script/record continuation and compaction behavior for deterministic tests |
| `src/prompts/worker/system.md` | Rewrite execution protocol around focused cycles/yield/finalization |
| per-target worker prompts | Audit only; retain semantic content unless a pack contains whole-cycle procedural wording |

The existing `_RecentToolWorkingSet` should remain.

For OpenAI it becomes primarily the bounded exact recent-interaction anchor and fallback rather than the sole continuation mechanism.

---

# 18. Required tests

The feature should not be considered complete without these behaviors.

## Hydration

- first `UNINVESTIGATED` obligation is selected in contract order;
- resolved obligations are skipped;
- all obligations remain visible;
- repair findings override normal obligation selection;
- zero unresolved obligations produces `FINALIZATION_READINESS`;
- repeated hydration after a yield deterministically selects the next current state.

## Cycle control

- `yield_cycle()` is always exposed;
- it requires no arguments;
- it must be standalone;
- mixed control/operational calls follow the same protocol discipline as finalization;
- valid yield returns `CYCLE_YIELDED`;
- valid yield preserves durable artifacts/evidence/completion/progress;
- valid yield transitions `WORKING → SCHEDULED`;
- the next Stage 3 hydration succeeds directly from that state.

## Exact control context

- canonical hydrated context remains unchanged for the duration of one cycle;
- current execution overlay is recomputed from authoritative state;
- OpenAI receives the exact control context through `instructions`;
- the exact control context is supplied on every chained response request;
- the exact control context is also supplied to compaction;
- canonical context and current authoritative state are never replaced by compacted output.

## OpenAI reasoning continuation

- the first worker response request has no continuation reference;
- the first response ID becomes the next continuation reference;
- subsequent OpenAI requests map that reference to `previous_response_id`;
- incremental tool outputs are sent without replaying the whole historical transcript;
- reasoning configuration reaches the provider as `xhigh` / `all_turns`;
- response IDs never enter durable target state;
- yield/finalization/interruption discard the continuation.

## Compaction

- no compaction occurs below the configured pressure threshold;
- context pressure is measured using provider usage once response chaining begins;
- compaction uses the latest response continuation;
- currently pending tool outputs are included where required to complete the current interaction;
- exact canonical/control instructions are supplied separately to compaction;
- compaction returns opaque provider context;
- the harness does not inspect that context;
- the old response chain is not reused after compaction;
- the first post-compaction response has no old `previous_response_id`;
- compacted provider output seeds the new response;
- protected recent tool batches are replayed exactly after compaction;
- current authoritative execution state is supplied exactly after compaction;
- the resulting response ID becomes the start of a new continuation chain;
- repeated compaction behaves the same way recursively;
- compacted context is discarded at the worker-cycle boundary;
- compaction usage is charged to fleet and target budgets;
- compaction failure follows existing provider/interruption semantics.

## Regression

- existing finalization semantics remain unchanged;
- Stage 3 initial context hard cap remains enforced;
- tool-result byte bounding remains enforced;
- recent-tool-batch protection remains bounded;
- tool-call sequencing remains deterministic;
- repair behavior still hydrates all routed findings;
- existing budget exhaustion behavior remains intact;
- provider-neutral fallback/reconstruction remains possible without changing durable harness contracts.

---

# 19. Documentation updates

Because this corrects the meaning of a worker cycle and the within-cycle context model, update the normative docs alongside implementation.

At minimum:

```text
docs/bridger/agentic-contracts/hydrating.md
docs/bridger/agentic-contracts/worker-cycle.md
docs/bridger/agentic-contracts/agentic-contracts-docs.md
```

Update `core.md` if its lifecycle transition section exhaustively enumerates legal target transitions.

The key normative statements should become:

```text
One Stage 4 cycle is one bounded semantic worker execution.

Normal cycles receive one deterministic primary unresolved
completion obligation.

Repair cycles receive the current routed repair finding set.

A worker may call yield_cycle to end the current cycle without
requesting target evaluation.

Successful yield returns the target to SCHEDULED for fresh
Stage 3 hydration.

Durable Bridger state remains the sole long-horizon authority.

Provider reasoning/conversation state may be retained inside one
cycle but remains transient and non-authoritative.

The exact canonical hydrated context and current authoritative
execution-state overlay are never replaced by context compaction.

For providers supporting native continuation, Stage 4 may use a
transient continuation reference within the active cycle.

The OpenAI provider maps this continuation reference to the
Responses API previous_response_id mechanism.

For OpenAI, exact Bridger control context is resupplied through
the request instruction surface on every response and compaction
operation.

When within-cycle provider context approaches its configured soft
limit, Stage 4 may compact the transient provider trajectory.

Compaction replaces historical provider trajectory, not canonical
Bridger context.

After compaction, the next provider request receives:
- exact canonical hydrated context;
- exact current execution-state overlay;
- opaque compacted historical trajectory;
- bounded exact recent tool-interaction batches.

The old provider continuation chain is discarded after compaction.
A new continuation chain begins from the first post-compaction
response.

Provider continuation references and compacted context are discarded
at worker-cycle boundaries.

request_finalization remains the only worker control that transfers
the complete target toward evaluation.
```

## Resulting architecture

```text
                    TARGET DURABLE STATE
                            │
                            ▼
                    Stage 3 hydration
                            │
                  deterministic cycle focus
                            │
                            ▼
                ┌────── Stage 4 cycle ──────┐
                │                           │
                │ EXACT CONTROL CONTEXT     │
                │                           │
                │ canonical WorkerContext   │
                │ + current state overlay   │
                │         │                 │
                │         │ instructions    │
                │         ▼                 │
                │      Luna xhigh           │
                │         │                 │
                │         ▼                 │
                │       tools               │
                │         │                 │
                │         ▼                 │
                │ previous_response_id      │
                │         │                 │
                │         ▼                 │
                │ reasoning continues       │
                │         │                 │
                │         ▼                 │
                │       tools               │
                │                           │
                │ context pressure?         │
                │         │ yes             │
                │         ▼                 │
                │ responses.compact()       │
                │                           │
                │ compact only transient    │
                │ provider trajectory       │
                │         │                 │
                │         ▼                 │
                │ exact canonical context   │
                │ + exact current overlay   │
                │ + compacted trajectory    │
                │ + exact recent batches    │
                │         │                 │
                │         ▼                 │
                │ start NEW response chain  │
                │                           │
                └───────────┬───────────────┘
                            │
                 ┌──────────┴─────────┐
                 │                    │
            yield_cycle       request_finalization
                 │                    │
                 ▼                    ▼
             SCHEDULED             Stage 6
                 │
                 ▼
          fresh hydration
          next obligation
```

The central invariant is:

```text
Effective Stage 4 context
=
exact canonical hydrated base
+
exact current authoritative execution state
+
transient provider reasoning trajectory
+
bounded exact recent tool observations
```

Only the transient provider trajectory is lossy-compacted.

`previous_response_id` preserves reasoning continuity between ordinary OpenAI tool turns.

`responses.compact()` bounds that trajectory when it grows too large.

Every cycle boundary discards both mechanisms and reconstructs the worker from durable Bridger state.

This keeps provider-native cognition useful without allowing provider state to become part of Bridger's durable correctness model.

[1]: https://developers.openai.com/api/docs/guides/latest-model "Model guidance | OpenAI API"

[2]: https://developers.openai.com/api/reference/java/resources/responses/methods/compact "Compact a response | OpenAI API Reference"