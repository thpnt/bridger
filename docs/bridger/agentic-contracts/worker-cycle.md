# Stage 4 — Worker Cycle

## 1. Responsibility

Stage 4 is the bounded **worker execution** stage.

Its lifecycle boundary is:

```text
Stage 3
TargetTaskState.phase = HYDRATING
+
compiled WorkerContext
        ↓
Stage 4
resolve execution surface
preflight first request
HYDRATING → WORKING
worker model/tool trajectory
        ↓
        ├── worker yields bounded work → WORKING → SCHEDULED → fresh Stage 3
        ├── worker requests finalization → Stage 6
        ├── target execution budget prevents further work → EXHAUSTED
        └── runtime/context/provider interruption → Stage 5 boundary
````

Stage 4 owns:

* `HYDRATING → WORKING` immediately before actual worker execution begins;
* one bounded worker execution cycle;
* enforcing the deterministic semantic focus selected by Stage 3;
* provider request/conversation handling around the already-rendered Stage 3 context;
* transient provider continuation and reasoning continuity within the cycle;
* pressure-triggered compaction of only the transient provider trajectory;
* the model/tool control loop;
* concrete worker tool exposure and execution;
* repository exploration through the existing `RepositoryNavigator`;
* target-local candidate Markdown mutation through `TargetWorkspace`;
* evidence creation through a controlled evidence recorder;
* semantic completion updates through a controlled completion updater;
* working-summary and open-question updates;
* the Stage-4-facing finalization control affordance;
* bounded active-context growth during the execution;
* reuse of the existing `ContextWindowManager` before every model request;
* actual `ExecutionUsage` consumption for worker execution;
* runtime permission enforcement for every worker action.

Stage 4 does **not** own:

* scheduling or concurrency admission;
* Stage 3 context compilation or canonical `WorkerContext` rendering;
* checkpoint contracts or crash recovery;
* trace/event persistence semantics;
* retry/backoff policy;
* context-reset recovery policy;
* `TargetFinalizationRequest` or `WORKING → FINALIZING`;
* hard validation;
* target review;
* repair routing;
* target acceptance;
* fleet reconciliation or fleet acceptance.

The worker remains autonomous in repository investigation and target-local knowledge organization, but lifecycle authority and mutation enforcement remain runtime-owned.

---

## 2. Existing authorities consumed

Stage 4 consumes the already-locked authorities:

```text
MemoryFleetSpec
FleetRunState

TargetTaskSpec
TargetTaskState
TargetCompletionState

WorkerContext
TargetDefinition

candidate artifact state
evidence state
open-question state

worker profile
permission profile

RepositoryNavigator
ContextWindowManager
existing LLMClient/model abstraction
```

Stage 4 does not copy or replace these authorities.

In particular:

```text
RepositoryNavigator
    = existing Layer 6 read capability

WorkerContext
    = immutable Stage 3 execution view

TargetTaskState
    = authoritative operational state

TargetCompletionState
    = authoritative semantic progress state

candidate artifacts
    = authoritative current product candidate

evidence records
    = authoritative durable grounding references
```

The active model conversation remains transient execution context and is never a task authority.

---

# 3. Worker execution cycle

## 3.1 Meaning of one cycle

One Stage 4 **cycle** is one hydrated worker execution, not one model turn.

It is also one bounded semantic execution unit. A normal cycle receives one
primary unresolved completion obligation selected deterministically by Stage 3.
A repair cycle receives the complete currently routed repair finding set in
persisted order. A final-readiness cycle receives the whole-target coherence
check only after no obligation remains `UNINVESTIGATED`.

A single cycle may contain many model/tool turns:

```text
WorkerContext
    ↓
model call
    ↓
tool calls
    ↓
tool results
    ↓
model call
    ↓
tool calls
    ↓
...
```

No additional `max_turns_per_cycle` contract is introduced in V0.

The already-locked execution budgets bound the trajectory through:

```text
max_model_calls
max_tool_calls
max_input_tokens?
max_output_tokens?
```

while:

```text
max_cycles
max_repair_cycles
```

bound how many worker executions may begin.

One primary obligation does not mean exactly one obligation may change. The
worker may preserve directly related discoveries, but must not deliberately
advance through unrelated unresolved obligations in one cycle.

## 3.2 Cycle start

Before actual execution begins, Stage 4 resolves:

```text
worker/model profile
allowed model-tool definitions
runtime-bound tool handlers
first provider request envelope
context-window fit
next-action budget availability
```

Only after this preflight succeeds does Stage 4 perform:

```text
HYDRATING → WORKING
```

and charge the cycle.

Therefore:

```text
HYDRATING
    = context compiled; execution not yet started

WORKING
    = worker execution has actually begun
```

A Stage 4 failure detected before the transition does not consume a cycle.

## 3.3 Normal ends

A bounded trajectory has two normal semantic ends:

```text
yield_cycle()
    → persist no new cycle object
    → WORKING → SCHEDULED
    → fresh Stage 3 hydration

request_finalization()
    → transfer the complete target to Stage 6
```

`yield_cycle()` means the intended bounded work is complete, or useful durable
progress has been preserved and a fresh cycle should continue. It never invokes
finalization, validation, review, repair routing, or acceptance.

`request_finalization()` means only that the worker believes the complete current
candidate is ready for evaluation. It does not mean the target is complete,
valid, reviewed, or accepted.

Other trajectory exits are runtime outcomes such as:

```text
target budget exhaustion
fleet budget preventing another action
provider/runtime interruption
active-context capacity interruption
```

---

# 4. Worker model/tool control loop

The runtime controls continuation.

The model chooses among the tools and control affordances it is allowed to request, but it never decides whether an operation is legally executable or whether lifecycle state may advance.

Conceptually:

```text
while target is WORKING:

    verify another model call is allowed
    verify next request fits context policy

    invoke model
    account actual model usage

    inspect requested tool calls

    if valid standalone yield request:
        perform WORKING → SCHEDULED
        stop Stage 4 without entering evaluation

    if valid standalone finalization request:
        stop Stage 4 and transfer control to Stage 6

    validate requested operational tool batch
    execute allowed tools sequentially
    account tool usage
    collect bounded results

    update transient execution-state projection
    update recent tool working set

    continue
```

The runtime, not the model, owns:

```text
continuation legality
budget enforcement
permission enforcement
tool argument validation
mutation validation
lifecycle transitions
completion authority
```

No durable `WorkerRun`, `WorkerCycleResult`, `YieldRequest`, or
provider-conversation contract is introduced.

The Stage 4 runner may return a small internal control outcome such as:

```text
FINALIZATION_REQUESTED
CYCLE_YIELDED
TARGET_BUDGET_EXHAUSTED
FLEET_BUDGET_STOP
EXECUTION_INTERRUPTED
```

but this is an implementation return value, not another persisted authority.

---

# 5. Provider request boundary and Stage 3 rendering ownership

Stage 3 remains the **sole owner** of:

```text
WorkerContext
    ↓
canonical deterministic model-facing serialization
```

Stage 4 must not implement a second `WorkerContext` renderer.

The corrected boundary is:

```text
Stage 3
WorkerContext
    ↓
existing canonical serializer
    ↓
canonical model-facing base payload
    ↓
Stage 4
provider envelope
+ stable tool definitions
+ transient Stage 4 execution context
    ↓
LLMClient
```

The same pure canonical serialization and fixed-request assembly/counting path used by Stage 3 for initial 32K request validation must be reused by Stage 4 when constructing the first real request. The initial Stage 4 request must therefore use the same canonical base content and allowed tool definitions that Stage 3 already budgeted. Stage 4 must not silently add a second copy of instructions or otherwise invalidate the successful Stage 3 size check.

If implementation currently embeds this assembly/counting logic inside Stage 3 hydration, the shared pure helper should be reused or extracted rather than reproduced. Stage 4 may cache the resulting canonical base serialization in memory for the lifetime of the cycle; that cache remains transient and non-authoritative.

Stage 4 owns only the provider-specific envelope around that canonical content.

Exact provider-native message roles are adapter concerns. They must not cause the Stage 3 content to be reinterpreted, reordered, or independently rendered.

Stage 4 must preserve the stable-prefix rule already locked in Stage 3:

```text
canonical stable Stage 3 context
+ stable allowed tool definitions
        ↓
dynamic execution overlay
+ recent tool interactions
```

No generic provider framework is introduced for V0.

---

# 6. Provider conversation state

Within one Stage 4 cycle, the runtime may retain immediate model/tool interaction
and provider reasoning state in process memory.

It is:

```text
transient
execution-local
non-authoritative
replaceable from durable task state after recovery
```

V0 correctness must not depend on:

```text
provider thread IDs
provider conversation IDs
previous-response handles
remote conversation persistence
full historical transcript replay
```

Provider-native continuation is nevertheless used inside the active cycle when
supported. The generic `LLMRequest.continuation_ref` carries only a transient,
provider-neutral handle. OpenAI maps it to `previous_response_id`, resends the
exact current control context through `instructions` on every turn, enables
request storage for the active chain, and configures GPT-5.6 worker reasoning as
resolved by the worker profile (including `xhigh` / `all_turns`).

The continuation reference is discarded on yield, finalization, interruption,
recovery, or any other cycle boundary. It is never checkpointed or written to
`TargetTaskState`.

Normal worker responses use provider-native tool calling.

The V0 worker protocol is action-oriented: each worker turn is expected to return one or more tool/control calls rather than an unconstrained prose-only final answer. For providers such as OpenAI that support required tool choice, Stage 4 uses the provider's required-tool mode. Provider-specific emulation for clients without that capability is an adapter concern.

No structured final-answer schema is required because worker progress is expressed through tools and finalization control.

---

# 7. Multiple tool calls

A model response may request multiple operational tools.

V0 executes them:

```text
sequentially
in model-provided order
without parallel tool execution
```

Sequential execution preserves deterministic mutation ordering and avoids unnecessary concurrency complexity inside one target worker.

Before executing a multi-tool response, Stage 4 preflights the whole operational batch against the currently remaining tool-call capacity.

If the complete batch cannot legally execute under the current applicable hard budget:

```text
execute none of the operational calls
```

and stop or route the execution according to the exhausted budget scope.

A finalization request is different.

```text
request_finalization()
```

must be the **sole model tool/control call in its response**.

A response that mixes finalization with another requested operation cannot finalize the target. The finalization control call is rejected with a worker-correctable protocol error; independently valid operational calls may still execute normally in their model-provided order and return their results. The worker must observe those results and request finalization again in a later standalone response. This prevents ambiguous ordering such as:

```text
edit artifact
+
request finalization
```

without the worker first observing whether the mutation succeeded.

`yield_cycle()` is the sibling control and follows the same standalone/no-argument
discipline. A response mixing an operational call with yield rejects yield but
may execute valid operations. A response containing both control calls succeeds
as neither control request. The worker must observe returned protocol/mutation
results before ending the cycle.

---

# 8. Worker tool runtime

The model receives tool definitions resolved from:

```text
WorkerContext.allowed_tool_ids
+
TargetTaskSpec.permission_profile_id
```

Every model-visible tool maps through:

```text
model tool schema
    ↓
argument validation
    ↓
permission validation
    ↓
runtime-bound handler
    ↓
authoritative operation
    ↓
bounded tool result
```

Tool handlers are bound to the current task by runtime state.

The model does not provide authority-bearing values that the runtime already knows, such as:

```text
target_task_id
fleet_run_id
target_workspace root
repository root
SourceBinding
```

This prevents cross-target or cross-repository access by construction.

Tool exposure and tool execution both enforce permissions:

```text
exposure
    → do not advertise forbidden capabilities

execution
    → independently reject forbidden calls even if malformed/provider-generated
```

Prompt instructions are not the permission boundary.

---

# 9. Repository discovery tool surface

Stage 4 reuses the existing Layer 6 `RepositoryNavigator`.

No repository-search, graph-navigation, file-index, symbol-index, or source-read implementation is recreated inside the memory harness.

The minimal V0 model-facing repository surface is:

```text
Orientation
-----------
search_repository

Graph
-----
get_graph_entity
get_graph_neighbors
get_graph_path
get_graph_community

Repository structure
--------------------
list_files
get_file_overview
search_symbols

Source investigation
--------------------
search_source_content
read_symbol_excerpt
read_file_ranges
```

The following Layer 6 capabilities are not initially exposed as worker tools:

```text
get_graph_subgraph
get_graph_central_nodes

graph_to_file
graph_to_symbols
file_to_graph
symbol_to_graph

list_symbols
read_around_match
```

They remain Layer 6 capabilities and may be exposed later if execution traces demonstrate a repeated need.

The V0 subset is intentionally small but complete enough to support:

```text
repository orientation
→ graph-guided exploration
→ file/symbol localization
→ bounded source verification
```

Every repository operation remains read-only.

---

# 10. `TargetWorkspace`

`TargetWorkspace` is the controlled filesystem-backed mutation surface for the current target's candidate Markdown.

It is bound to:

```text
TargetTaskSpec.target_workspace
```

and never accepts an arbitrary workspace root from the model.

The V0 interface is:

```text
list_target_artifacts()

read_target_artifact(
    path,
    optional range bounds
)

write_target_artifact(
    path,
    content,
    expected_revision?
)

edit_target_artifact_range(
    path,
    expected_revision,
    start_line,
    end_line,
    replacement
)

delete_target_artifact(
    path,
    expected_revision
)

move_target_artifact(
    source_path,
    destination_path,
    expected_revision
)
```

## 10.1 Mutation strategy

V0 deliberately uses:

```text
whole-file create/replace
+
simple line-range replacement
```

rather than a generic patch/diff language.

This supports both:

```text
large structural rewrite
    → whole-file replacement

small repair/refinement
    → bounded line-range edit
```

without forcing the model to re-emit a large Markdown document for every small change.

## 10.2 Revision behavior

Candidate artifact mutations use optimistic revision checks.

Conceptually:

```text
create new path
    → new artifact_id
    → revision = 1

replace/edit existing artifact
    → expected_revision must match
    → same artifact_id
    → revision += 1
    → new digest

move existing artifact
    → expected_revision must match
    → same artifact_id
    → new relative_path
    → revision += 1

delete artifact
    → expected_revision must match
    → current CandidateArtifactRef removed
```

Every successful mutation returns the authoritative current `CandidateArtifactRef`, and `TargetTaskState.artifact_refs` is updated accordingly.

The exact persistence/atomicity protocol for file + state mutation belongs to Stage 5.

## 10.3 Workspace enforcement

Every workspace handler mechanically enforces:

```text
relative target-local paths only
normalized paths
no absolute paths
no `..` escape
no symlink escape
resolved path remains inside exact target workspace
no sibling target access
no source-repository writes
no runtime-state JSON writes
candidate Markdown only
```

The worker remains free to choose file names, file count, segmentation, and target-local organization.

Mutation results return compact metadata rather than echoing the complete written document back into model context.

---

# 11. `EvidenceReference`

Stage 4 introduces the durable evidence contract that was intentionally deferred by the core-state design.

`EvidenceReference` represents one validated, revision-bound grounding reference created by the worker through the runtime.

Conceptually:

```python
class EvidenceKind(StrEnum):
    FILE = "file"
    SOURCE_RANGE = "source-range"
    SYMBOL = "symbol"
    GRAPH_ENTITY = "graph-entity"


class FileEvidenceLocator(BaseModel):
    path: str


class SourceRangeEvidenceLocator(BaseModel):
    path: str
    start_line: int
    end_line: int
    content_digest: str


class SymbolEvidenceLocator(BaseModel):
    symbol_id: str


class GraphEntityEvidenceLocator(BaseModel):
    target_type: str
    target_ref: str


class EvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    target_task_id: str
    source: SourceBinding
    kind: EvidenceKind
    locator: (
        FileEvidenceLocator
        | SourceRangeEvidenceLocator
        | SymbolEvidenceLocator
        | GraphEntityEvidenceLocator
    )
```

The exact Pydantic union/discriminator syntax is an implementation detail; the semantic contract above is locked.

## 11.1 Evidence locator families

V0 supports exactly:

```text
FILE
SOURCE_RANGE
SYMBOL
GRAPH_ENTITY
```

No evidence type is introduced for:

```text
conversation messages
tool-result blobs
search-result blobs
arbitrary model claims
```

Those are transient observations, not source authorities.

`GRAPH_ENTITY` resolves through the bound deterministic graph/composite navigation view. AI enrichment may be visible while inspecting an entity, but enrichment does not create a separate evidence-locator family.

## 11.2 Evidence authority

An `EvidenceReference` is:

```text
durable
immutable
bound to one target task
bound to the task SourceBinding
runtime-validated before creation
```

The model never invents an `evidence_id`.

The runtime creates or resolves the ID only after validating the locator.

---

# 12. Evidence recording

The worker-facing operation is conceptually:

```text
record_evidence(locator)
    → EvidenceReference
```

At write time the runtime validates, as applicable:

```text
TargetTaskSpec / source binding match
repository revision match
path exists in authoritative FileIndex
source range resolves inside the bound file
source-range digest matches the referenced content
symbol exists in authoritative SymbolIndex
graph entity exists in the bound graph snapshot
repository read policy permits the referenced source evidence
```

Successful recording:

```text
creates or reuses EvidenceReference
+
adds evidence_id to TargetTaskState.evidence_refs
```

## 12.1 Deduplication

Evidence is deduplicated within one target task using the canonical key:

```text
source binding
+
evidence kind
+
canonical locator
```

Recording the same evidence again returns the existing `evidence_id`.

Cross-target evidence deduplication is unnecessary because the target catalog explicitly allows the same source evidence to support different semantic owners.

## 12.2 Evidence and Markdown

The evidence registry is the authority for evidence identity.

A path or symbol name merely written into Markdown does not create durable evidence.

Candidate knowledge may refer to durable evidence IDs, and completion items may reference those IDs through their existing `evidence_refs` field.

Stage 4 does not lock the final Repository Brain claim-sidecar or publication citation syntax. It only locks durable evidence identity and worker recording semantics.

---

# 13. Completion-state updates

The worker never edits `TargetCompletionState` JSON directly.

Stage 4 exposes one controlled semantic operation:

```text
update_completion_item(
    obligation_id,
    status,
    resolution_note,
    evidence_refs
)
```

The operation atomically replaces the mutable resolution fields for that obligation.

## 13.1 Runtime validation

Stage 4 validates mechanically that:

```text
obligation_id exists in the locked TargetDefinition
status is one of:
    covered
    not-applicable
    unknown

worker does not explicitly set uninvestigated
resolution_note is present and non-empty
referenced evidence IDs exist
referenced evidence belongs to the same target/source binding
not-applicable is used only for a CONDITIONAL obligation
```

The worker may correct one resolved state into another:

```text
covered → unknown
unknown → covered
not-applicable → covered
...
```

A resolved obligation is not moved back to `uninvestigated`.

Stage 4 intentionally does **not** decide:

```text
whether evidence semantically proves the conclusion
whether covered is sufficiently complete
whether unknown is justified
whether not-applicable is substantively correct
whether a minimum evidence count is sufficient
```

Those concerns remain part of downstream hard validation/review/offline evaluation as already assigned by the target-contract design.

---

# 14. Working summary and open questions

`TargetTaskState.working_summary` remains the compact durable continuation mechanism for the worker.

It is not:

```text
a transcript summary
target knowledge prose
a hidden chain of thought
```

It should contain only the compact state future executions need to resume investigation correctly.

Stage 4 exposes one logical progress operation:

```text
update_progress(
    working_summary?,
    questions_to_open?,
    question_refs_to_resolve?
)
```

`working_summary`, when supplied, replaces the previous summary rather than appending indefinitely.

## 14.1 `OpenQuestion`

Stage 4 completes the already-existing `open_question_refs` design with one minimal durable contract:

```python
class OpenQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    target_task_id: str
    text: str
```

No separate question lifecycle enum is introduced.

The current open-question set is represented by:

```text
TargetTaskState.open_question_refs
```

Therefore:

```text
question ref present
    → currently open

question ref removed
    → no longer operationally open
```

A question's text is immutable. Revising a question means resolving the old question and opening another.

Historical creation/resolution events belong to Stage 5 trace, not to the question contract.

## 14.2 Bounds

The runtime/profile must bound:

```text
working_summary size
individual question size
number of simultaneously open questions
completion resolution-note size
```

because Stage 3 treats these continuation objects as mandatory hydration when present.

The exact V0 limits are profile/runtime configuration, not new domain contracts.

---

# 15. Cycle controls

Stage 4 always exposes two no-argument lifecycle controls:

```text
yield_cycle()
request_finalization()
```

Each must be the sole tool call in its response and neither consumes the
operational `tool_calls` budget.

Stage 4 interprets `yield_cycle()` as:

```text
stop issuing worker model/tool actions
perform WORKING → SCHEDULED
return CYCLE_YIELDED
```

It creates no yield artifact and invokes no evaluation stage.

Stage 4 interprets `request_finalization()` only as:

```text
stop issuing worker model/tool actions
transfer control to Stage 6
```

Stage 4 does not:

```text
create the final TargetFinalizationRequest contract
set pending_finalization_request_ref
perform WORKING → FINALIZING
check hard completion gates
run validation
run review
mark the target complete or accepted
```

Those semantics remain Stage 6+ responsibility.

The worker is allowed to request finalization even when it is mistaken about readiness. Downstream runtime validation remains the completion authority.

`request_finalization()` remains the only worker control that transfers the
complete target toward evaluation.

---

# 16. Active context model

Stage 4 deliberately does **not** accumulate an unbounded provider transcript.

The effective Stage 4 context has four logical segments:

```text
1. canonical Stage 3 base context
   immutable for this worker execution

2. current Stage 4 execution-state overlay
   compact derived view of authoritative mutations since hydration

3. provider trajectory
   transient reasoning, assistant calls, tool outputs and interaction state

4. protected recent tool batches
   bounded exact replay anchors
```

This gives:

```text
durable state
    → authoritative continuity

recent tool results
    → immediate reasoning context

provider trajectory
    → transient within-cycle cognition only
```

For OpenAI, the exact canonical base plus current overlay are supplied through
`instructions` on every request. `previous_response_id` represents only the
transient provider trajectory. Ordinary continued requests send only incremental
tool outputs rather than replaying the whole transcript.

The first two segments remain exact and are never replaced by compaction. Only
the provider trajectory is lossy-compacted. The protected recent batches remain
as a bounded exact replay anchor after compaction and a provider-neutral fallback.

The profile's 32K hard cap applies to the complete Bridger-constructed input of
every normal provider generation request, including the initial request and all
later requests. Stage 4 uses the existing deterministic working-set eviction
machinery when removable material causes a later request to exceed that cap.
The actual model context window remains a separate capacity limit.

The runtime owns a separate active working-context soft limit. It determines when
Bridger compacts, while the resolved model profile determines whether the
provider can accept that compaction request. A compaction request may therefore
temporarily exceed the active soft limit; it needs only to fit the provider's
actual context capacity and the normal execution budgets. Unlike a normal
generation turn, compaction does not reserve response-token capacity in its
provider-context fit calculation.

---

# 17. Stage 4 execution-state overlay

Because `WorkerContext` is immutable for the cycle, successful Stage 4 mutations can make parts of the original Stage 3 view stale.

Stage 4 therefore appends a compact **derived execution-state overlay** to later requests.

This overlay is:

```text
transient
non-authoritative
recomputed from current authoritative state
not another WorkerContext
not persisted as task state
```

It contains only information changed since hydration that the worker needs to avoid reasoning from stale Stage 3 state.

Conceptually:

```text
completion items changed since hydration
    → latest status/note/evidence refs

candidate artifacts changed since hydration
    → complete current candidate-artifact inventory

working summary changed
    → current working summary

open questions changed
    → complete current open-question set

new evidence recorded
    → compact new evidence identities/locators needed for continued work
```

The overlay replaces itself on every request rather than accumulating a history of deltas. When the overlay contains a field also represented in the immutable Stage 3 base, the overlay's current value explicitly supersedes the stale Stage 3 value for the remainder of this execution.

Detailed artifact contents and detailed source evidence still remain on-demand tool retrieval concerns.

---

# 18. Recent tool-interaction working set

A tool result must remain available long enough for the worker to reason over it, but results must not accumulate indefinitely.

V0 therefore retains a **bounded recent-tool working set**, not a one-turn result
policy and not an infinite transcript. On native-continuation paths it is no
longer the sole representation of the active provider trajectory.

## 18.1 Tool batch

A tool batch is:

```text
one model response's operational tool call(s)
+
the corresponding tool result(s)
```

The complete call/result batch is retained as one context unit.

## 18.2 Protected recent working set

The **3 most recent tool batches** are protected from ordinary eviction.

This is a minimum recency guarantee, not an expiration timer.

A result does not disappear merely because three newer turns occurred.

Once a batch becomes older than the protected recent set, it becomes **evictable**, not immediately deleted.

If active context remains comfortably bounded, useful older results may stay available.

## 18.3 Soft tool-context budget

The recent-tool working set has a runtime/profile-owned soft token budget.

The exact token value is not a new domain contract. A V0 implementation may use a value in the approximate 16K-token range, but the policy is authoritative rather than that exact tuning value.

The soft budget exists to prevent:

```text
unbounded context growth
attention decay from stale observations
needless repetition of large source excerpts
```

The `ContextWindowManager` remains the final context-capacity authority.

## 18.4 Eviction order

When the recent-tool working set exceeds its soft budget or the next provider request experiences context pressure, Stage 4 evicts only unprotected old material using deterministic pressure-first rules:

```text
1. duplicate or clearly superseded old results
2. old unprotected large result bodies
3. remaining unprotected results oldest-first
```

No LLM relevance classifier, summarizer, or semantic context manager is introduced in V0.

Examples of superseded results include:

```text
older read of an artifact after a newer revision has been read
repeated retrieval of the same source range
older duplicate search result already replaced by a newer equivalent result
```

## 18.5 Evicted-result placeholders

When a full old result body is evicted, Stage 4 may retain a compact placeholder such as:

```text
read_file_ranges(src/runtime.py, 120-220)
→ previous result removed from active context;
  retrieve again if needed
```

The provider-native tool-call/result pairing must remain structurally valid.

Placeholders are themselves part of the bounded working set and may later be evicted entirely. They do not create an unbounded second history.

## 18.6 Protected-set overflow

Repository and workspace tools must already return bounded results.

If, after removing every evictable old result, the complete next request still cannot fit while preserving:

```text
canonical Stage 3 base
current execution-state overlay
protected 3 recent tool batches
required response headroom
```

Stage 4 does **not** silently discard mandatory base context or the protected recent working set.

When native provider trajectory pressure reaches the configured soft threshold,
Stage 4 first compacts that transient trajectory. If the minimum valid request
still cannot fit, or required compaction cannot run, the active trajectory is
interrupted and crosses the existing Stage 5 recovery/reset boundary.

---

# 19. Tool-result bounding

Context control begins at the tool boundary.

Every worker tool must have domain-specific bounds such as:

```text
result count
source line/range limits
maximum returned bytes/tokens
graph traversal limits
artifact read ranges
```

The tool runtime additionally applies a final serialized-result safety ceiling so an implementation defect cannot inject an unexpectedly large payload into model context.

When truncation is necessary, the result must preserve enough identity and range information for the worker to request the missing detail explicitly.

Mutation tools return compact state deltas or references rather than complete rewritten artifact contents.

This preserves Bridger's progressive-disclosure model:

```text
retrieve narrowly
reason
externalize durable progress
retrieve again when necessary
```

---

# 20. `ContextWindowManager` during Stage 4

Stage 4 reuses the exact `ContextWindowManager` introduced in Stage 3.

No second context-capacity authority is introduced.

Before the initial provider request, Stage 4 evaluates the complete locally known
request:

```text
canonical Stage 3 base
+
stable tool definitions
+
current execution-state overlay
+
recent tool working set
+
provider/request overhead
+
reserved output headroom
```

The manager determines whether the request fits the actual resolved model context capacity.

The output reservation uses the actual maximum output Stage 4 will allow for that call, not the model's theoretical maximum by default.

After stored continuation begins, local message serialization no longer exposes
the complete reasoning trajectory. Provider-reported input/output usage becomes
the primary pressure signal. Before the next normal inference, Stage 4 projects
the latest effective context plus pending tool outputs and reserved response
headroom against a runtime-owned soft threshold (initially approximately 75%).

Stage 4 first applies ordinary recent-tool eviction where appropriate, then
compacts the transient provider trajectory when continuation pressure requires it.

It does not:

```text
drop mandatory Stage 3 context
silently drop current authoritative-state corrections
replace exact control context with compacted provider output
create a new context database
```

If the minimum valid next request still cannot fit, execution is interrupted and Stage 5 owns any future reset/recovery policy.

## 20.1 Provider compaction

`LLMClient.compact()` receives exact current instructions, the latest transient
continuation reference, and pending tool outputs needed to complete the latest
tool batch. For OpenAI it maps to `responses.compact(...)` and returns opaque
provider output items.

After compaction, the old continuation chain is discarded. The next request
starts a new chain with:

```text
exact canonical Stage 3 base
+ exact current execution overlay
+ opaque compacted provider trajectory
+ exact protected recent tool batches
```

The first post-compaction response ID begins the new continuation chain. Repeated
compaction follows the same rule recursively. Neither compacted context nor a
continuation reference crosses a cycle boundary.

---

# 21. Usage accounting

Stage 4 does not redefine `ExecutionBudget` or `ExecutionUsage`.

Stage 2 already owns admission against the current monotonic counters and explicitly does not predict future execution consumption.

Stage 4 only locks **when actual execution usage is charged**.

| Counter         | Stage 4 accounting rule                                                  |
| --------------- | ------------------------------------------------------------------------ |
| `cycles`        | `+1` exactly once when `HYDRATING → WORKING` occurs                      |
| `repair_cycles` | `+1` at the same transition when `WorkerContext.mode == REPAIR`          |
| `model_calls`   | `+1` immediately before every actual provider/model invocation attempt   |
| `tool_calls`    | `+1` immediately before every attempted operational worker-tool dispatch |
| `input_tokens`  | add actual provider-reported input usage when reported                   |
| `output_tokens` | add actual provider-reported output usage when reported                  |

A native provider compaction is a model/provider invocation for these existing
counters. Every compaction attempt consumes `model_calls`, retry attempts are
charged individually, and provider-reported compaction input/output tokens are
added at both target and fleet scope. There is no separate compaction budget.

A cycle therefore may consume many:

```text
model_calls
tool_calls
input_tokens
output_tokens
```

while consuming exactly one:

```text
cycle
```

and optionally one:

```text
repair_cycle
```

## 21.1 Target and fleet usage

Every consumption delta is applied consistently to both:

```text
TargetTaskState.usage
FleetRunState.usage
```

The two scopes must not drift.

The persistence/transaction mechanism that makes this crash-safe belongs to Stage 5, but Stage 4's semantic accounting operation is one target+fleet usage delta.

## 21.2 Failed provider calls

An actual provider invocation attempt consumes:

```text
model_calls += 1
```

even if the provider invocation fails.

Otherwise provider/retry failures would create unbounded free attempts.

Token usage is charged when the provider reports that tokens were consumed.

Stage 5 may later retry the call; every retry is another model-call attempt under the same original budget.

## 21.3 Rejected/invalid tool calls

An operational tool request counts once Stage 4 attempts runtime dispatch, including controlled rejection because of:

```text
invalid arguments
unknown object
permission failure
stale artifact revision
workspace-boundary rejection
unknown/disallowed tool identity
```

Invalid actions are therefore not free attempts.

`request_finalization()` and `yield_cycle()` are excluded because they are
lifecycle controls rather than operational tool work.

---

# 22. Execution-time budget enforcement

Before every new model or operational tool action, Stage 4 checks the existing target and fleet budget authorities for the exact action that is about to begin.

## 22.1 Model call

Before a model invocation:

```text
remaining model-call capacity must be positive
exact next input must fit configured remaining input-token capacity when bounded
remaining output-token capacity must be positive when bounded
ContextWindowManager must permit the request
```

The provider output limit is bounded by:

```text
worker/model profile per-call output limit
remaining target output-token budget
remaining fleet output-token budget
provider/model capability
available context headroom
```

No model request starts when one of its applicable hard capacities has already been exhausted.

## 22.2 Tool call

Before an operational tool batch:

```text
remaining target tool-call capacity
+
remaining fleet tool-call capacity
```

must permit the whole requested batch.

## 22.3 Cycle budgets

`max_cycles` and `max_repair_cycles` govern whether a cycle may start.

They do not interrupt a cycle merely because the current cycle itself consumed the final allowed cycle slot.

## 22.4 Target-scope exhaustion during WORKING

If the target's own hard execution budget prevents the next required Stage 4 action:

```text
WORKING → EXHAUSTED
```

Existing candidate artifacts, completion progress, evidence, questions, findings, and usage remain intact.

This is consistent with the existing meaning that target `EXHAUSTED` represents target-budget exhaustion.

## 22.5 Fleet-scope exhaustion during active work

Fleet-budget exhaustion does **not** relabel a target as target-level `EXHAUSTED`.

If fleet-wide remaining capacity prevents the next action:

```text
Stage 4 stops issuing further actions
reports a fleet-budget stop to the fleet runtime
```

The existing fleet-level exhaustion semantics remain authoritative.

Safe durable handling/reconstruction of an interrupted `WORKING` target belongs to Stage 5.

---

# 23. Concurrent fleet token reservations

Input size is known before a model call; output size is not.

With concurrent targets, model calls must not independently spend the same remaining fleet token capacity. The model-call preflight is therefore concurrency-safe for both configured input and output token limits.

V0 requires a lightweight in-flight reservation mechanism:

```text
count exact next request input
compute maximum allowed output for this call
        ↓
reserve applicable input allowance
+ maximum output allowance
against shared fleet capacity
        ↓
invoke provider
        ↓
charge actual provider-reported usage
        ↓
release unused reservation
```

The reservation is:

```text
runtime coordination state
not ExecutionUsage
not another ExecutionBudget
not another persisted domain contract
```

Known input size can be reserved exactly according to the V0 token-counting policy; the actual provider-reported usage remains the value ultimately charged to `ExecutionUsage`. The same concurrency-safe principle applies to shared model-call and tool-call capacity.

The exact crash handling and recovery of in-flight reservations belongs to Stage 5.

Equivalent concurrency-safe coordination may be used if it preserves the same hard-budget semantics.

---

# 24. Permission enforcement

`TargetTaskSpec.permission_profile_id` becomes concrete Stage 4 runtime enforcement.

At minimum V0 enforces:

```text
repository authorities
    → read only

target workspace
    → write only inside own target boundary

completion state
    → controlled completion operation only

evidence state
    → controlled evidence recording only

working summary / questions
    → controlled progress operation only

other target workspaces
    → inaccessible

runtime lifecycle/state JSON
    → runtime owned

FileIndex / SymbolIndex
RepositoryGraph / structural state
GraphEnrichmentOverlay
    → immutable
```

A worker cannot obtain a writable filesystem path merely because it knows one.

The allowed capability set must be enforced through handler binding and validation rather than through prompt instruction alone.

---

# 25. State mutation authority

Stage 4 preserves the existing separation between execution, semantic progress, product state, evidence state, continuation state, conversation state, and trace.

| Domain                                  | Stage 4 authority                           | Mutation path                                              |
| --------------------------------------- | ------------------------------------------- | ---------------------------------------------------------- |
| `TargetTaskState.phase`                 | Runtime only                                | `HYDRATING → WORKING`; yield `WORKING → SCHEDULED`; target-budget `WORKING → EXHAUSTED` |
| `TargetTaskState.usage`                 | Runtime only                                | Stage 4 execution accounting                               |
| `FleetRunState.usage`                   | Runtime only                                | same Stage 4 usage delta                                   |
| `working_summary`                       | Worker-proposed, runtime-applied            | `update_progress`                                          |
| `open_question_refs`                    | Worker-proposed, runtime-applied            | `update_progress`                                          |
| `artifact_refs`                         | Runtime projection of workspace mutation    | `TargetWorkspace`                                          |
| `evidence_refs`                         | Runtime projection of evidence creation     | `EvidenceRecorder`                                         |
| `open_finding_refs`                     | No Stage 4 mutation                         | downstream validation/review/repair routing                |
| `last_checkpoint_ref`                   | No Stage 4 mutation                         | Stage 5                                                    |
| `last_progress_signature`               | No Stage 4 mutation                         | Stage 5/no-progress machinery                              |
| `stall_count`                           | No Stage 4 mutation                         | Stage 5/no-progress machinery                              |
| `pending_finalization_request_ref`      | No Stage 4 mutation                         | Stage 6                                                    |
| `last_error_ref`                        | No Stage 4 mutation                         | Stage 5 error/recovery handling                            |
| `last_accepted_result_ref`              | No Stage 4 mutation                         | Stage 10+                                                  |
| `TargetCompletionState`                 | Worker-proposed, runtime-validated mutation | `CompletionStateUpdater`                                   |
| Candidate Markdown                      | Worker-proposed, runtime-enforced mutation  | `TargetWorkspace`                                          |
| `EvidenceReference`                     | Runtime creates immutable record            | `EvidenceRecorder`                                         |
| `OpenQuestion`                          | Runtime creates immutable record            | progress updater                                           |
| Repository/index/graph/enrichment state | Never                                       | read-only Layer 6 access                                   |
| Active provider continuation/compaction | Transient only                              | Stage 4 runner; discarded at every cycle boundary          |
| Trace/checkpoints                       | Not Stage 4 authority                       | Stage 5                                                    |

The model proposes operations through tool calls. The runtime performs and validates every authoritative mutation.

---

# 26. Worker-correctable tool errors

Some failures are ordinary worker observations and do not end Stage 4.

Examples:

```text
invalid tool arguments
unknown repository path
unknown symbol
unknown graph reference
invalid source range
stale expected artifact revision
workspace-boundary rejection
invalid completion update
unknown evidence reference
mixed finalization + operational tool response
mixed yield + operational tool response
yield + finalization response
```

For these cases:

```text
no invalid mutation occurs
bounded structured tool error is returned
worker trajectory may continue if budget permits
```

These are not semantic repair findings and do not invoke Stage 5 recovery.

They are part of the active recent-tool working set like other immediate tool results.

---

# 27. Runtime execution interruptions

Stage 4 stops the active trajectory when the failure is not safely correctable by another ordinary worker tool call.

Examples:

```text
provider/network failure
unexpected LLMClient failure
unexpected tool-handler exception
authoritative state store unavailable
filesystem/runtime I/O failure
unexpected RepositoryNavigator failure
permission/profile configuration inconsistency
minimum valid active context no longer fits
process interruption
```

Stage 4 owns identifying:

```text
what operation was attempted
what semantic state change did or did not occur
why execution cannot safely continue in the current trajectory
```

Stage 4 does not itself decide:

```text
retry/backoff
checkpoint restoration
crash reconstruction
safe-phase reconstruction
provider retry count
context reset
terminal FAILED outcome
```

Those remain Stage 5 responsibilities.

An infrastructure/runtime interruption therefore must not be converted into worker semantic `REPAIR`.

---

# 28. Stage 4 ↔ Stage 5 integration points

Stage 4 defines the semantic operation boundaries that Stage 5 must later persist, trace, checkpoint, or recover.

Stage 5 must be able to observe operations such as:

```text
cycle started

model invocation attempted
model response received

tool invocation attempted
tool result produced

candidate artifact mutation applied
EvidenceReference created
CompletionItemState updated
working summary updated
question opened/resolved

provider compaction attempted
provider compacted context received
cycle yield control received
finalization control received
budget prevented further action
execution interrupted
```

The responsibility split is:

```text
Stage 4
    what happened
    what authoritative state should change

Stage 5
    how that change becomes durably persisted
    how trace is recorded
    how checkpoints are created
    how partially interrupted work is recovered
```

For example:

```text
Stage 4 semantic operation
    write target Markdown
    → new CandidateArtifactRef

Stage 5
    decides the crash-safe ordering/atomicity of
    filesystem write + ref persistence + event/checkpoint state
```

Stage 4 introduces no event bus, event-sourced authority, checkpoint contract, or database requirement.

---

# 29. Stage 4 ↔ Stage 6 boundary

The Stage 4 / Stage 6 handoff is deliberately narrow.

```text
worker requests request_finalization()
        ↓
Stage 4 stops model/tool execution
        ↓
Stage 6
materializes TargetFinalizationRequest
performs WORKING → FINALIZING
owns pending_finalization_request_ref
```

Stage 4 does not decide:

```text
target complete
target accepted
hard validation passed
review passed
```

A worker finalization request may be wrong.

For example:

```text
worker requests finalization
while obligations remain uninvestigated
        ↓
Stage 6/7 path
        ↓
hard validation fails
        ↓
normal repair routing later
```

This preserves the locked rule:

> The worker may believe the target is ready; the runtime remains the completion authority.

---

# 30. Initial execution

An initial Stage 4 cycle receives the Stage 3 `WorkerContext` in `INITIAL` mode.

Typical starting durable state is:

```text
all completion items = uninvestigated
working_summary = null
open_question_refs = []
artifact_refs = []
evidence_refs = []
open_finding_refs = []
```

The worker then progressively:

```text
works the deterministic current cycle focus
orients through RepositoryNavigator
retrieves bounded source evidence
records durable EvidenceReference objects
creates candidate Markdown
updates completion obligations
maintains working summary/questions as useful
yields when authoritative target work remains
requests finalization only from finalization-readiness focus when it believes
the complete target contract is ready
```

Repository/artifact/evidence detail is discovered through tools rather than preloaded into the initial context.

---

# 31. Repair execution

A repair Stage 4 cycle uses the same worker architecture, tools, workspace, evidence store, completion state, and original remaining budget.

There is no separate repair agent or repair tool surface.

The Stage 3 repair context additionally contains the current routed findings.

The worker may:

```text
address the routed repair-finding set as the current cycle focus
inspect additional repository evidence
re-read existing candidate artifacts
rewrite or reorganize candidate Markdown
record additional evidence
correct completion resolutions
update continuation state
yield when additional target work remains
request finalization again only when the complete target is ready
```

The worker is not restricted to local patching. It may replace weak candidate structure when necessary.

All Stage 4 context-growth, permission, tool, and accounting rules remain identical during repair.

---

# 32. Minimal new Stage 4 contracts and interfaces

Stage 4 introduces only the new durable contracts that existing state references genuinely require.

## Durable contracts

```text
EvidenceReference
    + typed evidence locators

OpenQuestion
```

## Runtime interfaces/services

Conceptually:

```text
WorkerRunner
WorkerToolRuntime / tool registry

TargetWorkspace
EvidenceRecorder
CompletionStateUpdater
ProgressUpdater
FinalizationControl
```

Execution accounting and provider adaptation may be implemented as small helpers around the existing budget/state and `LLMClient` abstractions; they do not require new persisted domain contracts.

Stage 4 does **not** introduce:

```text
WorkerRun durable object
WorkerCycleResult durable object
conversation store
provider-thread authority
generic patch protocol
new repository retrieval stack
context database
context compaction service
generic memory system
repair agent
worker planner
event bus
new budget contract
new usage contract
```

---

# 33. Stage 4 invariants

1. Stage 4 begins only from a valid `HYDRATING` target with a compiled Stage 3 `WorkerContext`.
2. Stage 4 owns `HYDRATING → WORKING` immediately before actual worker execution begins.
3. One cycle means one hydrated worker execution and may contain multiple model/tool turns.
4. No additional model-turn limit exists in V0.
5. Stage 3 remains the sole owner of canonical `WorkerContext` rendering.
6. Stage 4 reuses the Stage 3 serializer and adds only provider envelope/tool/execution context.
7. Provider conversation state is transient and never required for correctness or recovery.
8. The runtime controls continuation; the model only requests allowed operations.
9. Multiple operational tool calls are executed sequentially in model-provided order.
10. A multi-tool batch must fit the remaining applicable tool budget before any call in the batch executes.
11. `request_finalization()` must be the sole call in its model response.
11a. `yield_cycle()` must be the sole call in its model response, takes no arguments, and cannot be combined with finalization.
12. Repository discovery uses the existing read-only `RepositoryNavigator` only.
13. The worker cannot write outside `TargetTaskSpec.target_workspace`.
14. Candidate Markdown mutation uses whole-file create/replace plus bounded line-range editing in V0.
15. Candidate artifact mutations use optimistic revision checks.
16. `EvidenceReference` is immutable, target-bound and `SourceBinding`-bound.
17. Evidence IDs are created/validated by the runtime, never invented by the model.
18. Evidence is deduplicated within a target by canonical source+kind+locator identity.
19. The worker cannot mutate `TargetCompletionState` directly.
20. Completion updates may resolve obligations only to `covered`, `not-applicable`, or `unknown`.
21. `not-applicable` may only be used for conditional obligations.
22. Runtime validation of completion updates is mechanical; semantic sufficiency remains downstream responsibility.
23. `working_summary` is compact durable continuation state, not a transcript summary or target artifact.
24. Open questions are immutable records whose current openness is represented by `open_question_refs`.
25. Active Stage 4 context separates exact Stage 3 control context, exact current authoritative state, transient provider trajectory, and bounded exact recent-tool replay.
26. The execution-state overlay is transient and replaces itself rather than accumulating deltas.
27. The 3 most recent tool batches are protected from ordinary eviction.
28. Older tool results remain available opportunistically and are evicted only under working-set/context pressure.
29. Tool results never accumulate without bound.
30. Evicted tool-result placeholders are themselves bounded and eventually evictable.
31. No LLM-based context summarizer/relevance classifier is introduced; native provider compaction may compact only the transient provider trajectory.
32. Tool outputs are bounded at the tool boundary before entering model context.
33. The existing `ContextWindowManager` is consulted before every model request.
34. The 32K normal provider-generation limit applies to every complete Bridger-constructed worker request; compaction uses actual model capacity plus Stage 4 working-set controls.
35. Mandatory Stage 3 context and current authoritative-state corrections are never silently discarded.
36. `cycles` increments once on `HYDRATING → WORKING`.
37. `repair_cycles` increments at the same boundary only for `REPAIR` mode.
38. `model_calls` counts every actual provider invocation attempt.
39. `tool_calls` counts every attempted operational tool dispatch, including controlled rejected calls.
40. `request_finalization()` and `yield_cycle()` do not consume `tool_calls`.
41. Provider-reported input/output tokens are charged to the existing usage counters when reported.
42. Every usage delta is reflected consistently at target and fleet scope.
43. Target and fleet hard budgets are checked before every new Stage 4 action.
44. Target-budget exhaustion may produce `WORKING → EXHAUSTED`; fleet-budget exhaustion alone does not relabel the target as target-level `EXHAUSTED`.
45. Concurrent provider calls cannot double-spend remaining shared fleet output-token capacity.
46. Permission enforcement occurs both when tools are exposed and when handlers execute.
47. Upstream repository/index/graph/enrichment authorities remain immutable.
48. Worker-correctable tool errors return bounded structured results and do not become semantic repair findings.
49. Runtime/provider/context interruptions cross the Stage 5 recovery boundary rather than becoming worker repair.
50. Stage 4 does not create checkpoints, define trace persistence, or decide retry/backoff.
51. Stage 4 does not create `TargetFinalizationRequest` or perform `WORKING → FINALIZING`.
52. Stage 4 never decides that a target is complete or accepted.
53. Initial and repair executions use the same worker loop and tool semantics.
54. Repair consumes the same original remaining target budget and does not create a new target task.
55. A successful yield performs `WORKING → SCHEDULED`, invokes no later evaluation stage, and requires fresh Stage 3 hydration.
56. Provider continuation references and compacted provider state are cycle-local and never durable authority.
57. OpenAI within-cycle continuation uses stored responses and `previous_response_id`; exact instructions are supplied on every request.
58. Native compaction receives exact control instructions separately, replaces only transient provider trajectory, resets the old continuation chain, and replays the protected recent batches exactly.
59. Compaction attempts and provider-reported usage use the existing model-call and token accounting at target and fleet scope.

---

# 34. Stage 5+ deferments

Stage 4 intentionally leaves the following downstream contracts and policies unresolved.

### Stage 5 — Persistence & Recovery

```text
TaskEvent schema
TaskCheckpoint schema
atomic mutation/checkpoint protocol
trace persistence
provider retry/backoff
crash restoration
safe-phase reconstruction
in-flight reservation recovery
context reset after interruption
no-progress/stall persistence semantics
```

### Stage 6 — Finalization

```text
TargetFinalizationRequest schema
request persistence
pending_finalization_request_ref semantics
WORKING → FINALIZING transition details
```

### Stage 7 — Hard validation

```text
mechanical final completion gate
artifact/evidence consistency validation
final evidence requirements
TargetValidationReport
```

### Stage 8 — Target review

```text
review context
review rubric execution
TargetReviewVerdict
```

### Stage 9+

```text
repair routing
local target acceptance
fleet validation/reconciliation
accepted-result freezing
Repository Brain publication
```

Stage 4 remains specifically the worker's bounded repository-investigation and candidate-knowledge execution loop under runtime-controlled tools, budgets, permissions, and context.
