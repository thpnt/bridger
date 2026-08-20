# Stage 12 — Fleet Reconciliation

## 1. Responsibility

Stage 12 is the semantic **fleet-reconciliation boundary** over the exact mechanically valid fleet passed by Stage 11.

Its lifecycle boundary is:

```text
Stage 11
FleetRunState.phase = REVIEWING
+
FleetValidationReport = PASS
+
report.accepted_target_result_refs
    = exact current accepted fleet
        ↓
Stage 12
compile fresh full-corpus review context
invoke tool-less fleet reviewer
persist FleetReviewVerdict
        │
        ├── PASS
        │     ↓
        │  remain REVIEWING
        │     ↓
        │  Stage 13
        │
        └── NEEDS_WORK
              ↓
           FleetReviewFinding[]
              ↓
           REVIEWING → REPAIRING
              ↓
           reopen affected targets
              ↓
           REPAIRING → RUNNING
              ↓
           normal target repair lifecycle
```

Stage 12 owns:

* validating fleet-review admission;
* consuming exactly the Stage 11-passed fleet;
* compiling the transient `FleetReviewContext`;
* invoking one fresh fleet reviewer over the complete accepted corpus;
* evaluating cross-target semantic and organizational quality;
* creating immutable `FleetReviewFinding` records;
* creating the immutable `FleetReviewVerdict`;
* maintaining the current `FLEET_REVIEW` finding projection;
* performing `REVIEWING → REPAIRING` on `NEEDS_WORK`;
* routing findings to the smallest actionable affected-target set;
* reopening affected targets through `ACCEPTED → REPAIR`;
* performing `REPAIRING → RUNNING` after repair routing is durably established;
* model/token usage accounting for the fleet reviewer;
* preserving review idempotency and crash recovery.

Stage 12 does **not** own:

* repository exploration or rediscovery;
* repository-navigation tools;
* source-grounding verification;
* artifact mutation;
* completion-state mutation;
* evidence mutation;
* deterministic fleet validation already owned by Stage 11;
* target-local hard validation;
* target-local review;
* repair execution;
* target acceptance;
* fleet acceptance;
* Repository Brain publication.

Its purpose is:

> **Determine whether the exact mechanically valid set of locally accepted target outputs forms one semantically coherent and well-organized memory corpus.**

---

## 2. Existing authorities consumed

Stage 12 consumes the already-locked authorities:

```text
MemoryFleetSpec
MemoryTargetCatalog
TargetDefinition

FleetRunState

TargetTaskSpec
TargetTaskState

AcceptedTargetResult
CandidateArtifactRef
CompletionItemState

FleetValidationReport

FindingRef
FindingOrigin

ExecutionBudget
ExecutionUsage

TaskEvent
Stage 5 persistence / recovery machinery
```

Stage 12 does not replace or reinterpret these authorities.

In particular:

```text
MemoryFleetSpec.target_ids
```

remains the activated target scope and target ordering.

```text
MemoryTargetCatalog
+
TargetDefinition
```

remain the semantic ownership authorities.

```text
TargetTaskState.last_accepted_result_ref
```

remains the current locally accepted result selector.

```text
AcceptedTargetResult
```

remains the immutable accepted-target provenance authority.

```text
FleetValidationReport.accepted_target_result_refs
```

defines the exact fleet that Stage 12 is permitted to review.

No second fleet-candidate authority is introduced.

---

## 3. Stage 12 admission

Stage 12 may begin only when:

```text
FleetRunState.phase == REVIEWING
```

and there exists a valid:

```text
FleetValidationReport
    verdict = PASS
```

whose:

```text
accepted_target_result_refs
```

exactly equal the fleet's current accepted-result refs in `MemoryFleetSpec.target_ids` order.

Every activated target must still be:

```text
TargetTaskState.phase == ACCEPTED
```

and every:

```text
last_accepted_result_ref
```

must still resolve to the accepted result referenced by the PASS report.

Stage 12 does not independently choose its review subject.

It must not derive the fleet from:

```text
current filesystem contents
latest artifact revisions
mutable target workspaces
historical accepted results
timestamps
trace ordering
conversation history
```

The central admission invariant is:

```text
fleet hard-validated
    =
fleet sent to fleet reconciliation
```

If any target has been reopened or has acquired a different locally accepted result after the Stage 11 PASS, that PASS no longer authorizes Stage 12.

The changed fleet must return through Stage 11.

---

## 4. Runtime corruption versus semantic reconciliation failure

Stage 12 separates runtime integrity failure from legitimate reviewer findings.

### Runtime / persistence integrity failure

If Stage 12 cannot reconstruct the exact Stage 11-passed corpus because an already-guaranteed durable invariant is broken, review does not begin or fails as runtime/persistence corruption.

Examples:

```text
FleetValidationReport.PASS does not resolve

accepted_target_result_refs differ from current accepted refs

AcceptedTargetResult is missing

accepted historical artifact version is missing

artifact digest no longer matches

target/fleet/source identity is incompatible

accepted target is no longer ACCEPTED
without a new Stage 11 validation path
```

These conditions do not produce:

```text
FleetReviewVerdict.NEEDS_WORK
FleetReviewFinding
worker repair
```

Workers cannot repair corrupted provenance.

### Semantic reconciliation failure

Once the exact valid accepted corpus has been reconstructed, a material semantic or organizational defect visible in that corpus is a legitimate Stage 12 finding.

The distinction is:

```text
cannot trust or reconstruct review subject
    → runtime/persistence failure

trusted exact accepted corpus
but semantic fleet quality is insufficient
    → NEEDS_WORK
```

---

## 5. Reviewer authority

The fleet reviewer applies the locked target catalog and cross-target ownership model.

The central ownership rule remains:

> The target whose primary question is being answered owns the canonical detailed explanation. Other targets may repeat only enough context to explain their own concern, then should reference the canonical owner rather than reproducing its detail.

Stage 12 may judge:

```text
cross-target duplication
cross-target contradictions
terminology consistency
semantic target ownership
scope leakage
cross-target coupling
global organization
global navigability
semantic link quality
```

### Duplication

Context-setting overlap is allowed.

Stage 12 should reject material duplicated ownership, not every repeated sentence.

Example:

```text
architecture/
    briefly states that payment orchestration activates entitlement

business-logic/
    owns the detailed entitlement rules
```

is valid.

Two detailed, substantially equivalent explanations of the same canonical responsibility may require reconciliation.

### Contradictions

Stage 12 may identify that two accepted artifacts make incompatible statements.

It does not determine repository truth by rediscovering source.

When the correct resolution cannot be established from:

```text
target ownership rules
+
the accepted generated corpus
```

the relevant target workers are reopened so repository investigation can occur through the normal worker path.

### Terminology

Materially inconsistent vocabulary for the same important repository concept may be rejected when it harms understanding or navigation.

Minor stylistic wording differences are not themselves blocking.

### Ownership and scope leakage

Stage 12 applies the semantic ownership boundaries already defined by the target catalog.

It does not invent new target boundaries.

### Global organization

Stage 12 may reject a corpus whose target-level outputs are individually acceptable but collectively difficult to navigate or understand.

### Semantic link quality

Stage 11 proves whether generated-memory links mechanically resolve.

Stage 12 may judge:

```text
whether a cross-target link makes semantic sense
whether duplicated detail should become a link
whether navigation between canonical owners is materially unclear
```

Zero cross-target links is not automatically a failure.

---

## 6. What the reviewer may not judge

The reviewer has no authority to independently determine:

```text
whether repository implementation actually supports a claim

whether an undiscovered repository subsystem exists

whether a worker selected the best source evidence

whether a different source file contradicts the generated knowledge

whether an EvidenceReference semantically proves a claim

whether an unknown could have been resolved with more repository exploration

whether a not-applicable decision is actually true in repository reality
```

Those require repository rediscovery or source-grounding verification.

Repository semantic discovery remains worker-owned and is measured independently through Bridger's offline evaluation.

Stage 12 judges the generated fleet as a corpus.

---

## 7. Fleet reconciliation rubric

The fleet reconciliation prompt/rubric is an evaluation artifact.

It may define:

```text
criterion identifiers
quality interpretation
examples of acceptable context overlap
examples of duplicated ownership
contradiction examples
terminology expectations
scope-leakage examples
global navigation expectations
semantic-link expectations
```

It may not introduce:

```text
new memory targets
new target completion obligations
new semantic ownership rules
new repository-grounding requirements
new target activation requirements
new target exclusions
```

Therefore:

```text
MemoryTargetCatalog + TargetDefinition
    = semantic authority

fleet reconciliation rubric
    = how the existing authority is evaluated
```

No second fleet semantic contract is introduced.

---

## 8. `FleetReviewContext`

`FleetReviewContext` is a transient, immutable, provider-neutral review input.

It is compiled fresh for one exact Stage 11 PASS and is not durable execution authority.

Conceptually:

```text
FleetReviewContext

review identity
├── fleet_review_id
├── fleet_run_id
├── source binding
├── target_catalog_id
├── target_catalog_version
└── fleet_validation_report_ref

semantic contract
├── global cross-target ownership rules
└── activated TargetDefinition values
    ├── purpose / canonical question
    ├── scope
    ├── exclusions
    ├── boundary guidance
    └── output-quality expectations

accepted fleet
└── ordered accepted targets
    ├── target identity
    ├── target contract version
    ├── AcceptedTargetResult identity
    ├── exact frozen accepted artifact contents
    ├── artifact paths / revisions / digests
    └── accepted completion-item snapshot when relevant

evaluation
├── Stage 11 PASS report
├── fleet reviewer instructions
├── fleet reconciliation rubric
└── structured review-output contract
```

Accepted artifact contents resolve from the immutable artifact versions referenced by the `AcceptedTargetResult` objects named by the Stage 11 PASS report.

The mutable target workspace is never substituted for those versions.

---

## 9. Full-corpus review

V0 uses exactly one:

```text
fresh
tool-less
full-corpus
fleet reviewer execution
```

The complete accepted fleet is mandatory review context.

Stage 12 does not:

```text
review only selected targets
sample documents
silently omit large artifacts
rank artifacts for inclusion
use artifact-reading tools
use repository retrieval tools
run parallel sub-reviewers
perform hierarchical review
perform multi-pass reconciliation
summarize away required corpus content
```

This follows the same V0 philosophy as Stage 8.

The full generated corpus is the object being reconciled, so partial corpus review would not establish the required fleet-level property.

### Context capacity

Before the reviewer invocation, the runtime performs the existing model/context-capacity preflight against the complete request.

If the required full-corpus review request cannot fit:

```text
review does not run
```

The runtime must not silently reduce the review subject.

Context-capacity failure is a runtime/configuration failure, not:

```text
NEEDS_WORK
```

Tool-backed or hierarchical fleet review may be introduced later only if real accepted-corpus sizes demonstrate a concrete need.

---

## 10. Context exclusions

The fleet reviewer does not receive:

```text
RepositoryNavigator
raw source repository
FileIndex / SymbolIndex exploration
graph-navigation capability
source-reading tools

TargetWorkspace
EvidenceRecorder
shell
mutation tools

worker transcripts
worker reasoning
target reviewer reasoning
TaskEvent history
historical rejected candidates
historical accepted candidates no longer selected
provider conversation state
```

Previous fleet-review reasoning and previous fleet-review findings are excluded from the fresh reviewer context by default.

The repair workers already receive actionable previous findings.

A subsequent Stage 12 review independently evaluates the complete newly accepted corpus instead of merely checking whether earlier criticisms were addressed.

Historical review records remain available for observability and offline harness evaluation.

---

## 11. Reviewer execution profile

Stage 12 reuses the reviewer profile already bound by the fleet configuration.

V0 does not introduce a new:

```text
FleetReviewProfile
fleet-review model contract
fleet-review permission profile
```

The exact reviewer profile used by the committed review is recorded in the verdict.

The reviewer receives no tools, so no reviewer permission/tool contract is required.

---

## 12. Review verdict vocabulary

Stage 12 reuses the exact existing Stage 8 reviewer verdict vocabulary:

```text
PASS
NEEDS_WORK
```

Implementation should reuse the existing reviewer verdict enum/type rather than introduce a fleet-specific semantic status taxonomy.

No additional status such as:

```text
ISSUES
UNCERTAIN
PARTIAL_PASS
PASS_WITH_WARNINGS
```

is introduced.

### `PASS`

Means:

> No material issue within Stage 12's legitimate fleet-reconciliation authority blocks final fleet acceptance.

Invariant:

```text
PASS
→ zero FleetReviewFinding records
```

A Stage 12 PASS does not itself accept the fleet.

### `NEEDS_WORK`

Means:

> At least one material cross-target semantic or organizational defect must be repaired before final fleet acceptance.

Invariant:

```text
NEEDS_WORK
→ one or more FleetReviewFinding records
```

Provider errors, malformed reviewer output, context failure, persistence failure, or budget failure are not semantic `NEEDS_WORK` verdicts.

---

## 13. `FleetReviewFinding`

One persisted `FleetReviewFinding` represents one concrete blocking fleet-reconciliation issue.

Conceptually:

```text
FleetReviewFinding
├── finding_id
├── fleet_review_id
├── fleet_run_id
├── criterion_id
├── affected_target_task_ids[]
├── affected_artifact_paths[]
├── message
└── required_outcome
```

### `criterion_id`

`criterion_id` identifies the fleet-review concern.

Representative V0 criteria include:

```text
cross-target-duplication
cross-target-contradiction
terminology-consistency
semantic-ownership
scope-leakage
global-organization
semantic-link-quality
```

Exact identifiers belong to the fleet-review rubric.

### Affected targets

```text
affected_target_task_ids
```

contains the smallest set of target tasks whose mutable candidates must change or be reinvestigated to resolve the finding.

A target mentioned only as comparison context is not automatically reopened.

Example:

```text
architecture/runtime.md
duplicates detailed business-rule ownership
already correctly held by business-logic/
```

may require:

```text
affected_target_task_ids = [architecture]
```

If a contradiction cannot safely be resolved from target ownership and the accepted artifacts alone:

```text
affected_target_task_ids
    = all targets that genuinely require repository re-investigation
      or candidate mutation
```

Every affected target must belong to the reviewed fleet.

At least one affected target is required for a persisted blocking finding.

### Affected artifacts

`affected_artifact_paths` uses normalized fleet-relative generated-memory paths from the exact accepted fleet.

Examples:

```text
architecture/runtime.md
business-logic/subscriptions.md
```

The list may be empty for a target-wide or corpus-wide issue.

No new global artifact-identity contract is introduced.

### Required outcome

`required_outcome` states what must become true without prescribing the worker's repair implementation.

Example:

```text
message:
    architecture/runtime.md and business-logic/subscriptions.md
    both contain detailed canonical explanations of subscription
    renewal rules

required_outcome:
    retain the detailed product rule explanation in business-logic/
    and reduce architecture/ to the runtime context required for
    understanding component interaction
```

V0 introduces no:

```text
severity
confidence
priority
repair strategy
repair plan
root-cause graph
nested critique hierarchy
```

Every persisted fleet-review finding is acceptance-blocking.

---

## 14. Finding identity

The reviewer model does not create authoritative finding IDs.

After validating structured reviewer output, the runtime assigns finding identity.

A simple V0 identity may be derived from:

```text
fleet_review_id
+
finding ordinal
```

The exact textual encoding is implementation-private.

Historical findings are immutable.

Provider retries before a committed verdict do not create durable semantic finding history.

---

## 15. `FleetReviewVerdict`

`FleetReviewVerdict` is the immutable persisted semantic result of Stage 12.

Conceptually:

```text
FleetReviewVerdict
├── fleet_review_id
├── fleet_run_id
├── fleet_validation_report_ref
├── verdict
├── finding_refs[]
└── reviewer_profile_id
```

The verdict does not duplicate:

```text
accepted_target_result_refs
```

because the referenced immutable `FleetValidationReport` already defines the exact ordered fleet review subject.

The provenance chain is:

```text
FleetReviewVerdict
        ↓
fleet_validation_report_ref
        ↓
FleetValidationReport.PASS
        ↓
accepted_target_result_refs[]
        ↓
AcceptedTargetResult[]
```

This is sufficient to establish the exact fleet that was reconciled.

### PASS

```text
verdict = PASS
finding_refs = []
```

### NEEDS_WORK

```text
verdict = NEEDS_WORK
finding_refs != []
```

Every finding ref must use:

```text
FindingOrigin.FLEET_REVIEW
```

and resolve to a `FleetReviewFinding` belonging to the verdict.

---

## 16. Fleet review identity

One successful Stage 11 PASS report has at most one committed `FleetReviewVerdict`.

Conceptually:

```text
one FleetValidationReport.PASS
    → one logical fleet_review_id
    → at most one committed FleetReviewVerdict
```

Provider retries do not create new semantic review rounds.

No separate:

```text
FleetReviewAttempt
FleetReviewSession
FleetReviewerConversation
FleetReviewState
```

contract is introduced.

A new fleet review round requires a new valid Stage 11 handoff after repair has produced a changed accepted fleet.

---

## 17. Successful Stage 12 path

A committed PASS establishes:

```text
FleetRunState.phase = REVIEWING

FleetReviewVerdict
    verdict = PASS

FleetReviewVerdict.fleet_validation_report_ref
    → exact Stage 11 PASS

current FLEET_REVIEW finding projection = []
```

Stage 12 leaves:

```text
FleetRunState.phase = REVIEWING
```

Stage 13 exclusively owns:

```text
REVIEWING → ACCEPTED
```

The reviewer cannot directly accept the fleet.

---

## 18. Failed Stage 12 path

A committed `NEEDS_WORK` produces:

```text
FleetReviewVerdict.NEEDS_WORK
+
FleetReviewFinding[]
```

and the fleet repair path:

```text
REVIEWING
    ↓
persist verdict/findings
    ↓
REPAIRING
    ↓
route findings
    ↓
affected target(s)
ACCEPTED → REPAIR
    ↓
REPAIRING → RUNNING
```

Only targets identified as requiring repair are reopened.

Unaffected targets remain:

```text
ACCEPTED
```

and keep their current:

```text
last_accepted_result_ref
```

Stage 12 does not invalidate or rewrite their historical accepted provenance.

---

## 19. `REPAIRING` semantics

Stage 12 reuses the exact fleet-level `REPAIRING` semantics established by Stage 11.

`REPAIRING` means:

> A fleet-level evaluation result has been durably committed, but the affected target repair states and current finding projections have not yet been fully and durably installed.

While:

```text
FleetRunState.phase == REPAIRING
```

ordinary Stage 2 scheduling is prohibited.

After every affected target has durably reached:

```text
TargetTaskState.phase = REPAIR
```

and its current `FLEET_REVIEW` finding refs are installed, the fleet runtime completes:

```text
REPAIRING → RUNNING
```

Normal Stage 2 scheduling may then resume.

No second reopening state or fleet-repair state object is introduced.

---

## 20. Fleet-review finding projection

Fleet review verdicts and findings are immutable history.

Runtime state contains only the current unresolved projection.

Current fleet-level reconciliation findings are projected through:

```text
FleetRunState.open_finding_refs
```

and affected target findings through:

```text
TargetTaskState.open_finding_refs
```

using:

```text
FindingOrigin.FLEET_REVIEW
```

Every completed Stage 12 review replaces only the current:

```text
FLEET_REVIEW
```

projection.

It must not clear findings owned by:

```text
HARD_VALIDATION
TARGET_REVIEW
FLEET_VALIDATION
```

unless their owning stages separately replace or clear them.

### PASS

```text
previous current FLEET_REVIEW refs
    → removed

new FLEET_REVIEW refs
    → none
```

### NEEDS_WORK

```text
previous current FLEET_REVIEW refs
    → removed

new verdict finding refs
    → installed at fleet scope
    → installed on affected target states
```

Historical verdicts and findings remain immutable.

---

## 21. Findings across local re-acceptance

A target reopened by Stage 12 may later pass its local gates and earn a new `AcceptedTargetResult`.

That proves only:

```text
the repaired target is locally acceptable
```

It does not prove:

```text
the cross-target reconciliation defect is globally resolved
```

Therefore renewed local acceptance does **not** clear the current:

```text
FLEET_REVIEW
```

finding projection.

The finding remains current until the next completed Stage 12 review replaces that projection.

This preserves the separation:

```text
Stage 10
    proves local target quality

Stage 11
    proves deterministic fleet composition

Stage 12
    proves semantic fleet reconciliation
```

---

## 22. Repair re-entry

Affected targets use the ordinary target lifecycle:

```text
REPAIR
    ↓ Stage 2
SCHEDULED
    ↓ Stage 3
HYDRATING
    ↓ Stage 4
WORKING
    ↓ Stage 6
FINALIZING
    ↓ Stage 7
VALIDATING
    ↓ Stage 8
REVIEWING
    ↓ Stage 10
ACCEPTED
```

Stage 12 does not permit:

```text
fleet finding
    → direct artifact mutation
    → remain ACCEPTED
```

or:

```text
fleet finding
    → Stage 8 directly
```

A repaired target must pass its normal local validation and review gates again.

If its candidate changes and passes local acceptance, Stage 10 creates a new immutable `AcceptedTargetResult`.

Historical accepted results remain immutable and resolvable.

---

## 23. Revalidation after fleet repair

When every activated target is again:

```text
ACCEPTED
```

the fleet returns first to:

```text
Stage 11 — Fleet Hard Validation
```

Stage 12 may not directly re-review the repaired fleet.

The progression is always:

```text
repaired targets locally accepted
        ↓
Stage 11 — full fleet hard validation
        ↓
Stage 12 — fresh full-corpus reconciliation
```

V0 implements neither:

```text
incremental fleet validation
incremental fleet review
affected-target-only fleet review
finding-specific reconciliation
```

The small fixed V0 fleet makes full re-evaluation simpler and safer.

---

## 24. Persistence boundary

The fleet reviewer model invocation occurs outside the durable mutation transaction.

Conceptually:

```text
1. validate Stage 12 admission

2. resolve exact FleetValidationReport.PASS
   and its accepted fleet

3. return existing committed FleetReviewVerdict
   when one already exists

4. compile FleetReviewContext

5. perform context / fleet-budget preflight

6. invoke reviewer

7. parse and validate structured output

8. assign runtime-owned finding identities

9. atomically persist the semantic review outcome

10. route lifecycle according to PASS / NEEDS_WORK
```

### PASS commit

One logical durable operation establishes:

```text
FleetReviewVerdict = PASS
+
clear current FLEET_REVIEW finding refs
+
fleet review usage / TaskEvent state
```

The fleet remains:

```text
REVIEWING
```

### NEEDS_WORK commit

A durable operation establishes:

```text
FleetReviewFinding records
+
FleetReviewVerdict = NEEDS_WORK
+
replace current FLEET_REVIEW finding refs
+
REVIEWING → REPAIRING
+
fleet review usage / TaskEvent state
```

Repair routing then durably performs:

```text
affected targets:
    ACCEPTED → REPAIR

install affected target FLEET_REVIEW refs

REPAIRING → RUNNING
```

Stage 12 reuses Stage 5 persistence and recovery machinery.

No Stage-12-specific transaction or checkpoint protocol is introduced.

---

## 25. Recovery and idempotency

Stage 12 uses:

```text
at-least-once reviewer execution
+
at-most-one committed verdict
```

for one logical fleet review.

### REVIEWING with no committed verdict

Recovery reconstructs the exact `FleetReviewContext` from durable state and may invoke the reviewer again.

No previous provider conversation is required.

### Reviewer response existed only in memory

If the process crashes after model response but before verdict persistence, the response has no durable authority.

Recovery may invoke the reviewer again.

A different probabilistic result is acceptable because no earlier verdict was committed.

### Verdict already committed

Recovery reuses the committed verdict.

The reviewer must not be reinvoked merely because later lifecycle routing was interrupted.

### NEEDS_WORK committed but routing incomplete

The fleet remains or is restored to:

```text
REPAIRING
```

until affected target phases and finding projections are durably established.

### Corrupt state

Impossible states such as:

```text
FleetReviewVerdict bound to a non-PASS FleetValidationReport

PASS FleetReviewVerdict with findings

NEEDS_WORK without findings

REVIEWING with current accepted refs different
from the verdict's Stage 11 report

REPAIRING with missing committed fleet-review verdict

FLEET_REVIEW refs that do not resolve
```

are runtime/persistence integrity failures.

They are not converted into new worker findings.

---

## 26. Usage and budgets

Stage 12 uses the existing fleet `ExecutionUsage` and `ExecutionBudget`.

Every actual fleet-review provider invocation attempt increments:

```text
FleetRunState.usage.model_calls += 1
```

Provider-reported usage increments:

```text
FleetRunState.usage.input_tokens
FleetRunState.usage.output_tokens
```

Reviewer retries consume additional model calls and tokens.

Stage 12 does not increment:

```text
cycles
repair_cycles
tool_calls
```

because:

* no worker cycle begins;
* repair-cycle accounting occurs only when a reopened worker execution begins;
* the fleet reviewer has no tools.

### No target usage charge

Fleet review is not the execution of any one target.

Its model and token usage is therefore charged to:

```text
FleetRunState.usage
```

only.

Stage 12 does not arbitrarily attribute fleet-review usage to one target or duplicate it across all targets.

### Budget

Before each reviewer invocation, the existing fleet hard model/token budget is checked.

Stage 12 introduces no:

```text
fleet-review budget
reconciliation budget
review token pool
```

If the existing fleet hard budget cannot permit the required full-corpus review, normal fleet-level exhaustion/runtime semantics apply.

No semantic `FleetReviewVerdict` is produced.

---

## 27. Concurrency

Stage 12 introduces no scheduling or concurrency contract.

It begins only when every activated target is:

```text
ACCEPTED
```

Accepted targets hold no target execution slot.

While the fleet is:

```text
REVIEWING
REPAIRING
```

ordinary target scheduling is already prohibited by the existing fleet-phase rules.

No:

```text
fleet-review queue
review semaphore
review slot
review lease
distributed lock
```

is introduced.

Generic provider-level concurrency/rate limiting may be reused where already available without becoming fleet lifecycle authority.

---

## 28. Stage 13 handoff

A successful Stage 12 boundary is:

```text
FleetRunState.phase = REVIEWING

all activated targets = ACCEPTED

FleetValidationReport V
    verdict = PASS
    accepted_target_result_refs
        = exact current accepted fleet

FleetReviewVerdict R
    verdict = PASS
    fleet_validation_report_ref = V

current FLEET_VALIDATION findings = []
current FLEET_REVIEW findings = []
```

This is the durable proof that:

> The exact current fleet passed both deterministic fleet composition and independent fleet semantic reconciliation.

Stage 13 must consume these explicit durable bindings.

It must not infer fleet success from:

```text
trace ordering
reviewer conversation
timestamps
ambient artifacts
current filesystem layout
```

---

## 29. Locked invariants

1. Stage 12 begins only from `FleetRunState.phase = REVIEWING`.
2. Stage 12 requires a valid Stage 11 `FleetValidationReport.PASS`.
3. The Stage 11 report's accepted-result refs must equal the fleet's exact current accepted-result refs.
4. Any changed accepted-result ref requires Stage 11 again before Stage 12.
5. Stage 12 never independently chooses or reconstructs a different fleet candidate.
6. Stage 12 reviews immutable accepted artifact versions, not mutable workspaces.
7. Runtime/provenance corruption never becomes semantic reviewer feedback.
8. The fleet reviewer always runs from a fresh compiled context.
9. V0 uses one full-corpus reviewer invocation.
10. The fleet reviewer is read-only.
11. The fleet reviewer is tool-less.
12. The fleet reviewer receives no `RepositoryNavigator`.
13. The complete accepted corpus is mandatory reviewer context.
14. Stage 12 never silently omit targets or artifacts to fit context.
15. Context-capacity failure is a runtime/configuration failure, not `NEEDS_WORK`.
16. Repository rediscovery and source-grounding verification are outside Stage 12.
17. `MemoryTargetCatalog` and `TargetDefinition` remain semantic ownership authorities.
18. The fleet-review rubric cannot invent new targets, obligations, or ownership rules.
19. Stage 12 reuses the existing reviewer verdict vocabulary: `PASS` / `NEEDS_WORK`.
20. PASS contains zero `FleetReviewFinding` records.
21. NEEDS_WORK contains at least one actionable `FleetReviewFinding`.
22. All persisted fleet-review findings are blocking.
23. Reviewer-model output does not control authoritative finding IDs.
24. Findings identify the smallest actionable set of affected targets.
25. Merely mentioning a target does not automatically reopen it.
26. Affected targets transition `ACCEPTED → REPAIR`.
27. Unaffected targets remain `ACCEPTED`.
28. `REPAIRING` is the existing durable fleet-level reopening boundary.
29. Stage 12 completes `REPAIRING → RUNNING` only after repair routing is durably established.
30. Reopened targets use the ordinary Stage 2–10 lifecycle.
31. Fleet repair never bypasses Stage 7 or Stage 8.
32. Historical `AcceptedTargetResult` objects remain immutable.
33. Renewed local acceptance does not itself clear a fleet-review finding.
34. A later Stage 12 run replaces the current `FLEET_REVIEW` projection.
35. Stage 12 clears or replaces only `FLEET_REVIEW` findings.
36. Historical fleet-review verdicts and findings are immutable.
37. After fleet repair, Stage 11 runs again before Stage 12.
38. V0 does not implement incremental reconciliation.
39. Previous fleet-review reasoning/findings are excluded from fresh reviewer context by default.
40. One Stage 11 PASS report has at most one committed `FleetReviewVerdict`.
41. Provider retries do not create separate semantic review rounds.
42. Provider conversation state is never recovery authority.
43. Stage 12 reuses Stage 5 persistence/recovery semantics.
44. A crash before verdict persistence may cause reviewer re-execution.
45. A crash after verdict persistence must reuse the committed verdict.
46. Fleet reviewer model/token usage is charged only at fleet scope.
47. Fleet review does not increment worker-cycle, repair-cycle, or tool-call counters.
48. No dedicated Stage 12 budget is introduced.
49. Stage 12 PASS leaves the fleet in `REVIEWING`.
50. Stage 13 exclusively owns final `REVIEWING → ACCEPTED`.

---

## 30. New Stage 12 surface

Stage 12 adds only:

### Durable contracts

```text
FleetReviewVerdict
FleetReviewFinding
```

### Transient contract

```text
FleetReviewContext
```

### Runtime interface

Conceptually:

```text
reconcile_fleet(fleet_run_id)
    → FleetReviewVerdict
```

### Lifecycle behavior

```text
Stage 11 PASS:
    fleet already REVIEWING

PASS:
    remain REVIEWING

NEEDS_WORK:
    REVIEWING → REPAIRING
    affected targets:
        ACCEPTED → REPAIR
    REPAIRING → RUNNING
```

Existing contracts are reused directly:

```text
MemoryFleetSpec
MemoryTargetCatalog
TargetDefinition

FleetRunState

TargetTaskSpec
TargetTaskState

AcceptedTargetResult
CandidateArtifactRef
CompletionItemState

FleetValidationReport

ExecutionBudget
ExecutionUsage

FindingRef
FindingOrigin

TaskEvent
Stage 5 persistence/recovery machinery
```

Stage 12 does **not** introduce:

```text
FleetCandidate
FleetReviewState
FleetReviewAttempt
FleetReviewSession
FleetReviewCheckpoint
FleetReviewBudget
FleetReviewUsage
fleet repair agent
fleet repair plan
review tool surface
artifact retrieval loop
repository-navigation access
multi-pass reviewer
sub-reviewer hierarchy
incremental reconciler
new persistence protocol
```

---

# Stage 13 — Fleet Acceptance

## 1. Responsibility

Stage 13 is the deterministic **final memory-fleet acceptance commit boundary**.

Its lifecycle boundary is:

```text
Stage 12
FleetRunState.phase = REVIEWING
+
all activated targets = ACCEPTED
+
FleetValidationReport = PASS
+
FleetReviewVerdict = PASS
        ↓
Stage 13
verify final fleet provenance
freeze exact accepted fleet
persist AcceptedMemoryFleetResult
REVIEWING → ACCEPTED
        ↓
Repository Brain publication layer
```

Stage 13 owns:

* validating final fleet-acceptance preconditions;
* proving that Stage 11 and Stage 12 apply to the exact same current accepted fleet;
* creating the immutable `AcceptedMemoryFleetResult`;
* persisting that result through the existing Stage 5 persistence boundary;
* setting `FleetRunState.accepted_result_ref`;
* performing `REVIEWING → ACCEPTED`;
* preserving final acceptance idempotency and crash recovery;
* producing the final memory-harness handoff consumed by Repository Brain publication.

Stage 13 does **not** own:

* repository exploration;
* artifact generation or mutation;
* evidence mutation;
* completion-state mutation;
* target validation;
* target review;
* target acceptance;
* fleet hard validation;
* fleet reconciliation;
* finding generation;
* finding resolution;
* repair;
* Repository Brain assembly;
* Repository Brain validation;
* Repository Brain snapshot identity;
* Repository Brain atomic publication;
* retrieval indexing or consumer exposure.

Stage 13 invokes no LLM.

It performs no new semantic judgment.

Its purpose is:

> **Freeze the exact memory fleet that has already passed both fleet-level gates and make that immutable provenance available to the publication layer.**

---

## 2. Existing authorities consumed

Stage 13 consumes:

```text
MemoryFleetSpec
FleetRunState

TargetTaskSpec
TargetTaskState

AcceptedTargetResult

FleetValidationReport
FleetReviewVerdict

FindingRef
FindingOrigin

SourceBinding
TaskEvent

Stage 5 persistence / recovery machinery
```

Stage 13 does not replace these authorities.

`FleetRunState.phase` remains the fleet lifecycle authority.

`TargetTaskState.last_accepted_result_ref` remains the current locally accepted-target selector.

`FleetValidationReport` remains the Stage 11 evaluation authority.

`FleetReviewVerdict` remains the Stage 12 evaluation authority.

---

## 3. Fleet acceptance meaning

Fleet acceptance means:

> The exact ordered set of locally accepted target results identified by the final fleet result passed Stage 11 deterministic fleet validation and Stage 12 semantic fleet reconciliation under one immutable fleet/source/catalog binding.

Fleet acceptance does not mean:

```text
Repository Brain snapshot has been assembled

all deterministic/enrichment publication components
have been revalidated for publication

Repository Brain manifest exists

publication checksums have been calculated

publication is atomic

snapshot is visible to consumers

retrieval indexes exist
```

Those remain publication-layer responsibilities.

The distinction is:

```text
MEMORY FLEET ACCEPTANCE
    final accepted evidence-backed knowledge result

REPOSITORY BRAIN PUBLICATION
    assemble and atomically publish the complete
    cross-layer Repository Brain snapshot
```

---

## 4. Stage 13 admission

`accept_fleet(fleet_run_id)` may succeed only when:

```text
FleetRunState.phase == REVIEWING
```

and every activated target is:

```text
TargetTaskState.phase == ACCEPTED
```

with a resolvable:

```text
last_accepted_result_ref
```

The runtime resolves the current ordered accepted fleet using:

```text
MemoryFleetSpec.target_ids
        ↓
TargetTaskState.last_accepted_result_ref
        ↓
AcceptedTargetResult[]
```

Stage 13 then requires a valid:

```text
FleetValidationReport V
    verdict = PASS
```

such that:

```text
V.accepted_target_result_refs
    == exact current ordered accepted fleet
```

and a valid:

```text
FleetReviewVerdict R
    verdict = PASS
```

such that:

```text
R.fleet_validation_report_ref == V
```

The resulting provenance chain must therefore be:

```text
current AcceptedTargetResult[]
        =
FleetValidationReport.PASS subject
        =
FleetReviewVerdict.PASS subject
```

---

## 5. Exact-fleet acceptance invariant

The central Stage 13 rule is:

> **The fleet accepted by Stage 13 must be exactly the fleet that passed both Stage 11 and Stage 12.**

Conceptually:

```text
fleet hard-validated
    =
fleet reconciled
    =
fleet accepted
```

If the current ordered accepted-result set differs from the Stage 11 PASS report, Stage 13 must not accept it.

Examples:

```text
[R1, A1, T1] validated and reviewed
```

does not authorize acceptance of:

```text
[R1, A2, T1]
```

even when:

```text
A1 and A2 belong to the same architecture target task
```

Stage 13 does not infer equivalence from:

```text
same target IDs
same artifact paths
similar content
timestamps
similar digests
ambient workspace contents
```

Any changed accepted result requires:

```text
Stage 11
    ↓
Stage 12
```

again before Stage 13.

---

## 6. Acceptance integrity versus repair

Stage 13 generates no findings.

If final acceptance provenance is inconsistent or corrupt, the operation fails explicitly.

Examples:

```text
missing FleetValidationReport

missing FleetReviewVerdict

FleetReviewVerdict refers to another validation report

current accepted-result refs differ from Stage 11 report

accepted result no longer resolves

accepted artifact historical version is missing

source binding mismatch

target catalog identity mismatch

PASS verdict unexpectedly contains findings

unresolved current fleet-level blocking finding exists
```

These are acceptance/runtime integrity failures.

Stage 13 must not:

```text
create FleetReviewFinding
reopen workers
guess intended provenance
silently rerun Stage 11
silently rerun Stage 12
accept approximately equivalent content
```

If semantic repair is required, it must originate from the appropriate evaluation stage rather than final acceptance.

---

## 7. Findings precondition

Final acceptance requires no current fleet-level blocker.

At minimum:

```text
current FLEET_VALIDATION projection = []
current FLEET_REVIEW projection = []
```

The accepted-target local lifecycle must also remain valid.

Stage 13 verifies this invariant but does not clear or resolve findings.

Historical findings from previous rounds remain immutable and may continue to exist as history.

They do not block acceptance when they are no longer part of the current unresolved projection.

---

## 8. `AcceptedMemoryFleetResult`

Stage 13 introduces one new durable contract:

```text
AcceptedMemoryFleetResult
```

No separate:

```text
FleetAcceptanceReport
FleetAcceptanceVerdict
FleetAcceptanceState
FleetAcceptanceAttempt
FleetAcceptanceCheckpoint
FleetAcceptanceManifest
```

is introduced.

### Semantic definition

`AcceptedMemoryFleetResult` is the immutable identity of the **exact final memory fleet that successfully passed both fleet-level gates**.

It answers:

> Which exact locally accepted target results make up the accepted memory fleet, against which source and target catalog, and through which fleet validation and reconciliation results was that fleet accepted?

It is the final durable product of the memory-agent harness.

---

## 9. `AcceptedMemoryFleetResult` contract

Conceptually:

```python
class AcceptedMemoryFleetResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1

    accepted_memory_fleet_result_id: str
    fleet_run_id: str

    source: SourceBinding

    target_catalog_id: str
    target_catalog_version: str

    accepted_target_result_refs: list[str]

    fleet_validation_report_ref: str
    fleet_review_verdict_ref: str
```

The exact Pydantic location and ID encoding are implementation details.

---

## 10. Source provenance

The final result copies:

```text
SourceBinding
```

from the immutable `MemoryFleetSpec`.

Invariant:

```text
AcceptedMemoryFleetResult.source
    == MemoryFleetSpec.source
    == every AcceptedTargetResult.source
```

The copy is intentional.

The final publication handoff should be independently sufficient to establish:

```text
repository identity
repository revision
graph snapshot
optional enrichment overlay
```

without reconstructing critical provenance from mutable runtime state.

Stage 13 never infers source identity from the current filesystem or repository checkout.

---

## 11. Target catalog provenance

The result also copies:

```text
target_catalog_id
target_catalog_version
```

from `MemoryFleetSpec`.

These values define the semantic target taxonomy and ownership rules under which fleet reconciliation succeeded.

Invariant:

```text
AcceptedMemoryFleetResult.target_catalog_id
    == MemoryFleetSpec.target_catalog_id

AcceptedMemoryFleetResult.target_catalog_version
    == MemoryFleetSpec.target_catalog_version
```

Stage 13 does not duplicate the complete target definitions inside the final result.

The catalog/version remains the static semantic authority.

---

## 12. Accepted target result set

`accepted_target_result_refs` freezes the exact final accepted fleet.

Ordering follows:

```text
MemoryFleetSpec.target_ids
```

For each activated target there is exactly one accepted-result reference.

Each referenced result must:

```text
exist

belong to the same fleet

belong to the expected target task / target identity

match the fleet SourceBinding

match the target contract version bound by its TargetTaskSpec

remain fully resolvable
```

The final result references `AcceptedTargetResult` rather than duplicating its contents.

Therefore Stage 13 does not copy:

```text
CandidateArtifactRef[]
CompletionItemState[]
EvidenceReference IDs
local TargetValidationReport
local TargetReviewVerdict
artifact contents
```

into the fleet result.

Those remain available through the immutable accepted-target provenance graph.

---

## 13. Fleet evaluation provenance

The final result references:

```text
fleet_validation_report_ref
fleet_review_verdict_ref
```

rather than embedding their contents.

The referenced chain must establish:

```text
FleetValidationReport
    verdict = PASS
    subject = accepted_target_result_refs

FleetReviewVerdict
    verdict = PASS
    fleet_validation_report_ref
        = that exact FleetValidationReport
```

Previous fleet validation reports, fleet review verdicts, failed rounds and repair findings remain immutable historical provenance.

Stage 13 does not rewrite or supersede them in place.

---

## 14. Why the final result remains compositional

`AcceptedMemoryFleetResult` intentionally does not duplicate:

```text
artifact inventories
artifact digest maps
completion-state snapshots
evidence metadata
finding histories
review summaries
trace history
working state
```

Those objects already have authoritative immutable locations.

The final result exists to freeze **composition and provenance**, not to create another memory-product storage authority.

The durable chain is:

```text
AcceptedMemoryFleetResult
        ↓
AcceptedTargetResult[]
        ↓
CandidateArtifactRef[]
        ↓
immutable accepted artifact versions
```

and:

```text
AcceptedMemoryFleetResult
        ↓
FleetValidationReport.PASS
        ↓
FleetReviewVerdict.PASS
```

This gives downstream publication everything needed to identify the exact accepted memory product without duplicating mutable state.

---

## 15. Runtime interface

The primary Stage 13 interface is conceptually:

```text
accept_fleet(fleet_run_id)
    → AcceptedMemoryFleetResult
```

The runtime resolves authoritative inputs internally.

The caller does not provide arbitrary:

```text
accepted target refs
artifact refs
source binding
catalog version
FleetValidationReport
FleetReviewVerdict
finding claims
```

as acceptance assertions.

The normal operation is:

```text
load MemoryFleetSpec
        ↓
load FleetRunState
        ↓
verify REVIEWING
        ↓
resolve exact current AcceptedTargetResult[]
        ↓
resolve applicable Stage 11 PASS
        ↓
resolve applicable Stage 12 PASS
        ↓
verify exact-fleet provenance
        ↓
verify no current blocking fleet findings
        ↓
construct AcceptedMemoryFleetResult
        ↓
persist immutable result
        ↓
update FleetRunState
        ↓
append acceptance / lifecycle trace
        ↓
return AcceptedMemoryFleetResult
```

No model is invoked.

---

## 16. Lifecycle mutation

On successful first acceptance:

```text
FleetRunState.phase
    REVIEWING → ACCEPTED
```

Stage 13 exclusively owns this transition.

The runtime sets:

```text
FleetRunState.accepted_result_ref
    = accepted_memory_fleet_result_id
```

Stage 13 does not create a copied per-target status map.

Individual target lifecycle remains authoritative through each:

```text
TargetTaskState.phase
```

All activated targets remain:

```text
ACCEPTED
```

---

## 17. Persistence commit

Stage 13 reuses Stage 5 persistence and recovery semantics.

The logical acceptance commit is:

```text
1. persist complete immutable AcceptedMemoryFleetResult

2. persist FleetRunState update:
       phase = ACCEPTED
       accepted_result_ref = result ID

3. append corresponding acceptance / lifecycle trace
```

The implementation must preserve:

```text
FleetRunState.phase == ACCEPTED
    ⇒
accepted_result_ref resolves to
a complete valid AcceptedMemoryFleetResult
```

The runtime must never expose durable state equivalent to:

```text
phase = ACCEPTED
accepted_result_ref = null
```

No second acceptance persistence protocol is introduced.

---

## 18. Idempotency

Fleet acceptance is idempotent for the same exact successful provenance chain.

Required semantic behavior:

```text
same fleet_run_id
+
same exact accepted_target_result_refs
+
same FleetValidationReport.PASS
+
same FleetReviewVerdict.PASS
        ↓
same AcceptedMemoryFleetResult
```

The exact ID/hash encoding is implementation-private.

Repeated acceptance must not create semantically duplicate final results because:

```text
caller retried
process retried
recovery reran acceptance
same operation was invoked twice
```

If:

```text
FleetRunState.phase = ACCEPTED
accepted_result_ref = X
```

and `X` is valid for the same acceptance provenance, another:

```text
accept_fleet()
```

returns `X` or its equivalent loaded result.

---

## 19. Crash recovery

### Crash before result persistence

Durable state remains:

```text
FleetRunState.phase = REVIEWING
```

with Stage 11 PASS and Stage 12 PASS already persisted.

Recovery may rerun Stage 13 acceptance.

Neither fleet validation nor fleet review needs to rerun solely because final acceptance itself was interrupted.

### Crash after result persistence but before fleet-state update

Recovery detects the already persisted valid result for the exact successful chain and completes:

```text
REVIEWING → ACCEPTED
```

without producing another semantic fleet result.

### Crash after fleet-state update

Recovery sees:

```text
FleetRunState.phase = ACCEPTED
accepted_result_ref = X
```

and validates that `X` resolves correctly.

No evaluation or target execution is repeated.

### Invalid partial state

Impossible combinations such as:

```text
ACCEPTED with no accepted_result_ref

accepted result belongs to another fleet

accepted result references a different source

accepted result target set differs from its Stage 11 report

accepted result references missing AcceptedTargetResult objects

fleet-review verdict does not bind to the recorded validation report
```

are runtime/persistence corruption.

They are not converted into target repair.

---

## 20. Usage and budgets

Stage 13 performs deterministic runtime work only.

It consumes:

```text
0 worker cycles
0 repair cycles
0 model calls
0 tool calls
0 input tokens
0 output tokens
```

Stage 13 does not mutate:

```text
ExecutionUsage
```

and introduces no acceptance-specific budget.

A fleet whose model execution budget is fully consumed may still complete Stage 13 if it already has valid Stage 11 and Stage 12 PASS provenance.

---

## 21. Concurrency and scheduling

Stage 13 introduces no scheduler or concurrency mechanism.

It begins while:

```text
FleetRunState.phase = REVIEWING
```

where ordinary target scheduling is already prohibited.

All activated targets are already:

```text
ACCEPTED
```

and hold no execution slot.

No:

```text
acceptance queue
acceptance worker slot
acceptance lease
lock service
```

is needed.

Successful:

```text
REVIEWING → ACCEPTED
```

makes the memory fleet terminal for this run.

---

## 22. Historical target and fleet provenance

Final fleet acceptance does not delete, rewrite or compact historical provenance.

The run retains:

```text
historical TargetFinalizationRequest objects
TaskCheckpoint history
TargetValidationReport history
TargetReviewVerdict history
AcceptedTargetResult history

FleetValidationReport history
FleetValidationFinding history

FleetReviewVerdict history
FleetReviewFinding history
```

The final result merely identifies which immutable accepted-target and fleet-evaluation chain became the successful final memory-fleet result.

Historical rejected or superseded candidates do not become part of the final accepted fleet unless explicitly referenced by the final result.

---

## 23. Final memory-harness boundary

After Stage 13 succeeds:

```text
FleetRunState.phase = ACCEPTED
+
FleetRunState.accepted_result_ref
    → AcceptedMemoryFleetResult
```

The memory harness is complete.

The final output chain is:

```text
AcceptedMemoryFleetResult
        ↓
exact AcceptedTargetResult[]
        ↓
exact immutable accepted knowledge artifacts
```

with:

```text
FleetValidationReport.PASS
+
FleetReviewVerdict.PASS
```

providing the final fleet evaluation provenance.

---

## 24. Repository Brain publication boundary

`AcceptedMemoryFleetResult` is consumed by the later Repository Brain publication layer.

Stage 13 does **not**:

```text
assemble deterministic graph artifacts

assemble enrichment artifacts

copy accepted Markdown into a Repository Brain snapshot

construct the Repository Brain manifest

compute the Repository Brain snapshot identity

validate publication-level checksums

validate cross-layer publication consistency

build retrieval indexes

publish atomically

make the snapshot visible to consumers
```

Those remain publication-layer responsibilities.

The publication layer may dereference:

```text
AcceptedMemoryFleetResult
    → AcceptedTargetResult[]
    → exact accepted artifact versions
```

as its memory-layer input.

The memory harness grants no direct consumer-facing publication authority.

---

## 25. New run boundary

A successfully accepted memory fleet is historical immutable provenance for that fleet run.

Stage 13 does not reopen:

```text
FleetRunState.phase = ACCEPTED
```

for ordinary future repository changes.

A new repository revision, new graph/enrichment binding, changed target catalog, or intentionally new memory-generation execution creates a new:

```text
MemoryFleetSpec
+
fleet_run_id
```

according to the existing upstream binding rules.

An accepted historical fleet result is not silently mutated into a new source state.

---

## 26. Locked invariants

1. Stage 13 is deterministic and invokes no model.
2. Stage 13 begins only from `FleetRunState.phase = REVIEWING`.
3. Every activated target must still be locally `ACCEPTED`.
4. Every current `last_accepted_result_ref` must resolve.
5. Stage 13 resolves the exact current fleet in `MemoryFleetSpec.target_ids` order.
6. Stage 13 requires `FleetValidationReport.PASS`.
7. The Stage 11 PASS subject must equal the exact current accepted fleet.
8. Stage 13 requires `FleetReviewVerdict.PASS`.
9. The fleet-review verdict must explicitly reference the applicable Stage 11 PASS report.
10. The fleet hard-validated, reconciled and accepted target sets must be identical.
11. Any changed accepted-result ref requires Stage 11 and Stage 12 again.
12. Stage 13 performs no new semantic evaluation.
13. Stage 13 performs no new fleet composition evaluation beyond acceptance-integrity checks.
14. Acceptance-integrity corruption fails explicitly.
15. Acceptance corruption never becomes semantic repair feedback.
16. No current `FLEET_VALIDATION` or `FLEET_REVIEW` finding may block acceptance.
17. Historical resolved findings do not block acceptance.
18. `AcceptedMemoryFleetResult` is immutable.
19. `AcceptedMemoryFleetResult.source` equals `MemoryFleetSpec.source`.
20. Target catalog identity/version are copied from `MemoryFleetSpec`.
21. `accepted_target_result_refs` freeze the exact final fleet.
22. Accepted-result ordering follows `MemoryFleetSpec.target_ids`.
23. The result references existing accepted target results instead of duplicating their artifact/evidence/completion contents.
24. The result references the successful fleet-validation report instead of embedding it.
25. The result references the successful fleet-review verdict instead of embedding it.
26. No second accepted-artifact storage authority is introduced.
27. No fleet acceptance report/verdict/state/checkpoint/manifest is introduced.
28. Successful Stage 13 sets `FleetRunState.phase = ACCEPTED`.
29. Successful Stage 13 sets `FleetRunState.accepted_result_ref`.
30. `phase == ACCEPTED` requires a resolvable valid `AcceptedMemoryFleetResult`.
31. Fleet acceptance uses the existing Stage 5 persistence/recovery machinery.
32. Acceptance is idempotent for the same exact successful fleet provenance chain.
33. Duplicate acceptance execution must not create semantically duplicate results.
34. Recovery may complete interrupted Stage 13 acceptance without rerunning Stage 11 or Stage 12 when their durable PASS provenance remains valid.
35. Stage 13 consumes no worker/model/tool/token/repair budget.
36. `AcceptedMemoryFleetResult` is the final output contract of the memory-agent harness.
37. Stage 13 does not publish the Repository Brain.
38. Repository Brain assembly and atomic publication remain downstream authority.
39. An accepted memory fleet is not reopened in place for a different repository/source binding.
40. Simplicity remains preferred over additional fleet-finalization machinery.

---

## 27. New Stage 13 surface

Stage 13 adds only:

### Durable contract

```text
AcceptedMemoryFleetResult
```

### Runtime interface

```text
accept_fleet(fleet_run_id)
    → AcceptedMemoryFleetResult
```

### Lifecycle behavior

```text
REVIEWING → ACCEPTED

FleetRunState.accepted_result_ref
    → AcceptedMemoryFleetResult
```

Existing contracts are reused directly:

```text
MemoryFleetSpec
FleetRunState

TargetTaskSpec
TargetTaskState

SourceBinding
AcceptedTargetResult

FleetValidationReport
FleetReviewVerdict

FindingRef
FindingOrigin

TaskEvent
Stage 5 persistence/recovery machinery
```

Stage 13 does **not** introduce:

```text
FleetAcceptanceState
FleetAcceptanceReport
FleetAcceptanceVerdict
FleetAcceptanceAttempt
FleetAcceptanceCheckpoint
FleetAcceptanceManifest
accepted-artifact duplicate store
accepted-target duplicate store
fleet publication manifest
Repository Brain snapshot
new execution budget
new usage contract
new scheduler state
new persistence protocol
```

---

# Final Memory Agent Fleet Harness boundary

The completed V0 harness path is:

```text
target worker execution
        ↓
Stage 7 — Target Hard Validation
        ↓
Stage 8 — Target Review
        ↓
Stage 9 — Repair when required
        ↓
Stage 10 — Target Acceptance
        ↓
all activated targets locally accepted
        ↓
Stage 11 — Fleet Hard Validation
        ↓
Stage 12 — Fleet Reconciliation
        ↓
Stage 13 — Fleet Acceptance
        ↓
AcceptedMemoryFleetResult
        ↓
Repository Brain publication layer
```

The final authority split is:

```text
Stage 10
    freezes one exact locally successful target

Stage 11
    proves deterministic composition of the
    exact accepted target set

Stage 12
    judges semantic coherence of that exact
    generated memory corpus

Stage 13
    performs no new judgment;
    it freezes the successful fleet provenance
    into the final memory-harness result

Repository Brain publication
    owns later cross-layer assembly,
    validation and atomic publication
```

No stage after a fleet-level rejection bypasses the ordinary target-local lifecycle.

The central final invariant is:

```text
exact locally accepted targets
        =
exact Stage 11 validated fleet
        =
exact Stage 12 reconciled fleet
        =
exact Stage 13 accepted memory fleet
```