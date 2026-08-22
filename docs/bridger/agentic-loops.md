# Building Agents That Run for Hours

## A technical course based on Anthropic’s workshop by Ash Prabaker & Andrew Wilson

### Source scope

This course is based primarily on Anthropic engineers Ash Prabaker and Andrew Wilson’s 75-minute workshop *Build Agents That Run for Hours*. I cross-referenced the workshop with Anthropic’s official *Effective Harnesses for Long-Running Agents*, *Harness Design for Long-Running Application Development*, and their published `cwc-long-running-agents` harness examples.

---

# 1. The fundamental problem

A long-running agent is not simply an LLM allowed to make more tool calls.

A useful long-running agent must maintain **coherent progress toward an objective over a long time horizon**, potentially across:

* many tool calls;
* many reasoning cycles;
* context compactions;
* context resets;
* multiple agents;
* failed implementations;
* verification cycles;
* hours of execution.

Anthropic identifies three fundamental sources of failure.

## 1.1 Context degradation

Context windows are finite. More importantly, even before the hard context limit is reached, behavior can degrade.

The workshop distinguishes several phenomena:

**Amnesia**

A fresh agent session does not inherently know what previous sessions accomplished.

**Context rot**

As a session becomes longer and more information accumulates, the model can become less coherent about earlier details.

**Context anxiety**

Some model generations become increasingly inclined to wrap things up as they perceive themselves approaching the context limit. The result may be premature completion rather than deliberate continuation.

Compaction helps with the size problem but does not necessarily solve the coherence problem. A lossy summary may preserve broad intent while deleting precisely the details a future iteration needs.

This gives us an important distinction:

```text
Context capacity ≠ task memory
Context compaction ≠ coherent task state
```

A robust harness therefore needs **state outside the active model context**.

---

# 2. Planning failures become more dangerous with time

Models often try to perform too much work at once.

Given:

```text
Build me a complete browser.
```

a naive agent may attempt to:

1. choose an architecture;
2. implement most of the application;
3. wire components together;
4. test it;
5. finish everything

inside one continuous trajectory.

That creates a major long-horizon problem.

If the agent makes an incorrect architectural assumption at minute 10, a four-hour execution can spend the remaining 3h50 implementing consequences of that mistake.

Anthropic's earlier harness therefore deliberately restricted agents to **incremental progress**: choose one unfinished feature, implement it, verify it, commit it, update persistent state, then continue.

The general principle is:

```text
Long horizon
    +
early irreversible assumptions
    =
error amplification
```

This becomes especially important when designing planners.

A planner should generally establish:

* goals;
* major requirements;
* constraints;
* high-level decomposition;

without unnecessarily fixing every implementation detail hours before those details need to be decided.

---

# 3. The surprisingly important problem: self-evaluation

Anthropic argues that one of the largest weaknesses of long-running agents is not generation but **judgment**.

An agent may build:

```text
[Button: Delete]
```

and conclude that the delete feature is implemented because the button exists.

But perhaps:

* no backend handler exists;
* the API is broken;
* a state transition fails;
* the feature only works in one path;
* the UI is visually broken;
* the unit test passes while real use fails.

The builder has already invested effort into its implementation and tends to be excessively charitable toward its own output.

Anthropic observed this even when explicitly asking the same agent to review itself.

This leads to one of the central principles of the workshop:

> **Separate generation from evaluation.**

The important point is not merely that two calls are better than one.

The roles need meaningful separation:

```text
Generator context
    ↓
implements work
    ↓
artifacts
    ↓
Evaluator context
    ↓
independently judges work
```

The evaluator should preferably not inherit the builder's entire reasoning trajectory.

It sees the **result and evidence**, rather than becoming psychologically—or contextually—attached to how that result was produced.

---

# 4. Why an LLM evaluator can still work

A natural objection is:

> If an LLM builder is bad at judging its own work, why wouldn't another LLM simply rubber-stamp it?

Anthropic's observation is subtle.

Making a **builder simultaneously creative, productive and strongly self-critical** is difficult.

Making a dedicated critic skeptical is much easier.

This exploits an asymmetry:

```text
Ability to generate excellent output
        ≠
Ability to identify problems in output
```

Humans exhibit something similar: detecting weaknesses in a design, article or dish is easier than producing an excellent one from scratch.

A specialized evaluator can therefore provide useful adversarial pressure even when builder and evaluator use similar underlying models.

---

# 5. First-generation long-running harness

Anthropic's earlier architecture was designed around repeated fresh contexts.

It introduced an **initializer agent** followed by repeated **coding-agent sessions**.

## Initializer

The initializer transforms the vague user objective into persistent project state.

Typical artifacts included:

```text
feature_list.json
progress file
git repository
init.sh
initial implementation/environment
```

The feature list represented the definition of the complete product.

Critically:

```json
{
  "feature": "...",
  "passes": false
}
```

Everything begins as **failing**.

The agent must earn completion rather than assume it.

Anthropic found JSON useful because models were less likely to casually rewrite structured JSON than Markdown task lists.

---

# 6. The incremental worker loop

Each worker session roughly followed this lifecycle:

```text
START SESSION
      │
      ▼
Understand environment
      │
      ├─ pwd
      ├─ read progress
      ├─ inspect git history
      └─ inspect feature state
      │
      ▼
Restore application
      │
      └─ init.sh
      │
      ▼
Smoke-test existing system
      │
      ▼
Choose ONE incomplete feature
      │
      ▼
Implement
      │
      ▼
End-to-end verification
      │
      ▼
If verified:
  mark feature passing
  update progress
  git commit
      │
      ▼
Fresh context / next iteration
```

This architecture solves several problems simultaneously.

### Recoverability

Git provides known-good checkpoints.

### State continuity

The next agent doesn't need to reconstruct history from conversation logs.

### Bounded scope

Each execution has a tractable objective.

### Regression detection

Smoke tests ensure the previous worker didn't leave the project broken.

### Explicit completion

Features remain failing until verification occurs.

---

# 7. Filesystem state is a major architectural primitive

One recurring recommendation throughout the workshop is surprisingly mundane:

**Use the filesystem.**

Instead of trying to carry the entire state of a multi-hour task through model context, persist important state as artifacts.

Examples:

```text
BUILD_PLAN.md
PROGRESS.md
feature_list.json
test-results.json
contract.md
NEXT_FINDINGS.md
git commits
screenshots/
logs/
```

This creates two parallel systems:

```text
Ephemeral cognition
────────────────────
LLM context
reasoning
tool observations

Durable task state
──────────────────
filesystem
structured JSON
git history
evidence
contracts
```

The second one should be authoritative for long-term progress.

In the workshop's Q&A, Ash specifically recommends leaving explicit "breadcrumbs" in structured files so future agents—or humans—can reconstruct what happened.

---

# 8. Compaction versus fresh context

These are distinct strategies.

## Compaction

```text
context
context
context
context
   ↓
summarize
   ↓
continue same session
```

Advantages:

* cheap orchestration;
* continuity;
* fewer handoff mechanics.

Disadvantages:

* lossy;
* accumulated reasoning baggage remains;
* summaries can drift;
* context anxiety or stale assumptions may persist.

## Fresh-context reset

```text
Agent A
   ↓
structured handoff
   ↓
Agent B: clean context
```

Advantages:

* clean reasoning environment;
* removes accumulated distraction;
* good isolation.

Disadvantages:

* handoff must contain enough information;
* increased orchestration;
* extra latency/tokens;
* badly designed handoffs cause amnesia.

Anthropic does **not** present context resets as a universal architectural law.

Their earlier models needed resets substantially more. Later models could run coherent multi-hour sessions using compaction alone.

The lesson is therefore:

> Treat context-reset strategy as a response to model behavior, not as permanent architecture.

Measure what your actual model does.

---

# 9. Ralph loops and loop engineering

The workshop discusses the popular Ralph-loop pattern.

At its simplest:

```python
while not done:
    run_agent(prompt)
```

But Anthropic argues that the useful version is richer than the meme.

A more serious loop includes:

```text
plan
  ↓
select work
  ↓
fresh/managed context
  ↓
execute
  ↓
verify
  ↓
persist progress
  ↓
decide whether to continue
```

One appealing principle associated with these loops is essentially:

**predictable failure can be preferable to unpredictable success.**

A deterministic runtime should constrain and supervise the nondeterministic agent.

Claude Code implementations also use stop hooks: when the agent attempts to terminate, the harness can intercept termination, evaluate the completion condition, and continue if necessary.

This is an important conceptual shift.

The agent should not have unilateral control over:

```text
"I think I'm done."
```

The **runtime** determines whether the task is actually finished.

---

# 10. The more advanced architecture: Planner → Generator → Evaluator

Anthropic's newer experiments evolved toward three specialized roles.

```text
          USER GOAL
              │
              ▼
          ┌─────────┐
          │ Planner │
          └────┬────┘
               │
         high-level spec
               │
               ▼
      ┌─────────────────┐
      │    Generator    │
      └────────┬────────┘
               │
             work
               │
               ▼
      ┌─────────────────┐
      │    Evaluator    │
      └────────┬────────┘
               │
         PASS / critique
               │
         ┌─────┴─────┐
         ▼           ▼
       DONE       Generator
```

Each role receives its own context and responsibility.

Anthropic compares this loosely to familiar software teams:

```text
Planner    ≈ product/technical planning
Generator  ≈ implementing engineer
Evaluator  ≈ QA/reviewer
```

The important innovation is not pretending agents are humans.

It is **context and objective separation**.

---

# 11. Planner design: deliberately avoid overplanning

The planner produces a high-level product specification.

But Anthropic deliberately avoids having it define every technical detail.

Why?

Because a detailed five-hour plan contains many predictions about future implementation states.

An incorrect detail in:

```text
step 2
```

may corrupt:

```text
steps 3–20
```

before another agent has a chance to reconsider it.

Their planner therefore defines what the system should achieve while leaving lower-level implementation details to the generator/evaluator pair closer to execution time.

This suggests a useful planning hierarchy:

```text
Long-horizon plan
    ↓
goals / requirements / boundaries

Near-horizon contract
    ↓
exact implementation objective + verification

Execution
```

The closer a decision is to actual execution, the more detailed it can safely become.

---

# 12. Contract negotiation: perhaps the most important pattern

Before implementation begins, Anthropic lets the generator and evaluator **negotiate what "done" means**.

Suppose the generator proposes:

```text
I will implement feature X.

Verification:
- run test Y
```

The evaluator may answer:

```text
Insufficient.

You also need:
- edge case A
- persistence behavior B
- real browser interaction C
- failure behavior D
```

They exchange structured artifacts on disk until they agree.

Only then does implementation start.

The evaluator later grades against **that negotiated contract**, rather than vaguely interpreting the original one-line user request.

This creates a very useful transformation:

```text
USER INTENT
    ↓
product requirement
    ↓
implementation contract
    ↓
testable assertions
    ↓
execution
```

The planner therefore does not need to predict all implementation details.

The contract is created **just in time**.

---

# 13. Granularity matters

Anthropic found that vague evaluator criteria produce vague feedback.

For their retro-game example, a single sprint contained **27 contract criteria**.

That level of specificity was intentional.

Compare:

```text
BAD

"The level editor should work."
```

against:

```text
BETTER

- player can place tile
- placed tile persists
- delete removes selected tile
- collision state updates
- undo restores previous state
- saved project reloads correctly
```

A vague evaluator response:

```text
The editor needs improvement.
```

provides little actionable information.

A granular finding:

```text
Criterion 17 failed:
Delete updates the canvas but does not update persisted level state.
```

gives the next worker a precise target.

The principle is:

```text
Granular contract
      ↓
granular evidence
      ↓
granular critique
      ↓
targeted correction
```

---

# 14. Evaluators need real-world evidence

Code review alone is often insufficient.

The workshop's retro-game example illustrates this.

The solo implementation looked plausible:

* UI existed;
* entities rendered;
* score existed;
* controls were visible.

Yet the actual game didn't respond correctly to keyboard input.

The harnessed evaluator launched the application and interacted with it.

This caught failures that unit tests or superficial code inspection had missed.

The lesson is broader than browser testing.

**Evaluation should happen at the highest meaningful level of abstraction.**

For example:

```text
library
→ execute public API

CLI
→ run actual CLI commands

web app
→ use browser

API
→ perform real request flows

data pipeline
→ process real fixture end-to-end

agent
→ execute representative tasks
```

Testing implementation details is not the same as verifying product behavior.

---

# 15. Default-FAIL contracts

Anthropic's published harness primitives take the workshop's idea further.

Every requirement starts:

```json
"passes": false
```

More importantly, the harness can structurally restrict when an agent is allowed to change that state.

Their example tracks whether the agent has opened valid evidence—such as screenshots or logs—before allowing a requirement to become passing.

So instead of:

```text
Prompt:
"Please test carefully before marking complete."
```

the harness implements:

```text
No evidence
    ↓
cannot write PASS
```

This is a major harness-engineering principle:

> When something is important, prefer **mechanism** over instruction.

Prompts express policy.

Harness code can enforce policy.

---

# 16. The evaluator should have limited permissions

Anthropic's reference evaluator is deliberately prevented from editing the implementation.

Conceptually:

```text
Generator:
READ
WRITE
EDIT
EXECUTE

Evaluator:
READ
EXECUTE TESTS
OBSERVE
NO WRITE/EDIT
```

Why?

Because otherwise roles collapse:

```text
Evaluator finds bug
→ evaluator silently fixes bug
→ evaluator passes result
```

You lose independent assessment.

A strict boundary preserves useful adversarial pressure.

This is an important subagent-design principle:

**Different agent roles should not merely have different prompts. Their capabilities can also differ.**

---

# 17. Subjective quality can still be evaluated

Anthropic applies the generator/evaluator pattern to frontend design.

They use four broad rubric dimensions:

1. design quality;
2. originality;
3. craft;
4. functionality.

The interesting point is not those exact dimensions.

It is the idea that subjective criteria can often be partially operationalized.

Instead of:

```text
Does this look good?
```

define:

```text
Does the layout have coherent hierarchy?
Are component choices intentional?
Does the result rely on generic defaults?
Is spacing internally consistent?
Can the user understand the primary action?
```

Few-shot examples then calibrate the evaluator toward the desired standard.

Thus:

```text
subjective
≠
ungradable
```

If humans possess a sufficiently clear opinion about quality, part of harness design is forcing that opinion into an explicit rubric.

---

# 18. Generator–evaluator loops can escape local minima

A particularly interesting observation in the talk concerns repeated iteration.

A naive loop often behaves like:

```text
version 1
  ↓
patch
  ↓
patch
  ↓
patch
  ↓
patch
```

Eventually the system accumulates increasingly awkward fixes around a flawed foundation.

In Anthropic's adversarial harness, the evaluator can keep reporting that a major criterion is failing.

The generator may eventually conclude:

```text
This approach isn't recoverable.
```

and rebuild large sections—or start over entirely.

Anthropic observed agents doing this even after substantial previous investment.

This gives the system something similar to exploration beyond local hill-climbing.

A useful loop therefore needs to support more than:

```text
RETRY
```

It may need:

```text
PATCH
REPLAN
ROLLBACK
REIMPLEMENT
ABANDON APPROACH
```

---

# 19. State handoffs should be structured

A handoff between agents should not simply be:

```text
Here is a summary of what happened...
```

Important state can include:

```text
objective
completed work
current implementation state
remaining work
known bugs
decisions made
evidence collected
tests executed
failed approaches
next recommended action
```

Anthropic repeatedly favors structured files for this.

They additionally use Git as a second source of truth for what code actually changed.

A useful mental model is:

```text
PROGRESS.md
    = semantic handoff

git history
    = implementation handoff

contract/test state
    = completion handoff

evidence
    = verification handoff
```

No single artifact must explain the entire world.

---

# 20. Long-running harnesses need explicit termination semantics

A loop should not continue merely because the agent has not stopped.

Nor should it stop simply because the builder claims success.

The runtime needs termination conditions.

Anthropic's published examples suggest conditions such as:

```text
all criteria pass
OR no useful change occurred
OR budget exhausted
OR operator stop
```

They also expose:

```text
kill switch
manual steering file
iteration limits
```

as operator controls.

Conceptually:

```python
while True:
    result = run_worker(state)

    verdict = evaluate(result)

    if verdict.complete:
        break

    if budget.exhausted:
        break

    if no_progress_detected():
        break

    if operator_stop:
        break

    state = incorporate_feedback(state, verdict)
```

The **runtime**, rather than the worker, owns continuation.

---

# 21. Long-running agent architecture is a control problem

Although the workshop does not formally frame it in control-theory terms, its architecture can naturally be understood that way.

You have:

```text
desired state
     │
     ▼
  Planner
     │
     ▼
 Controller / harness
     │
     ▼
  Generator
     │
     ▼
 Environment
     │
     ▼
  Evidence
     │
     ▼
 Evaluator
     │
     └──────── feedback ─────────┐
                                │
                                ▼
                           next action
```

The generator acts on the environment.

The evaluator measures deviation from the desired state.

The harness uses that feedback to decide what should happen next.

Without evaluation:

```text
open-loop system
```

With independent evaluation:

```text
closed-loop system
```

Long-running reliability comes from closing that loop repeatedly.

---

# 22. Harness and model must co-evolve

Another major theme of the workshop is that there is no permanent optimal harness.

A harness exists partly to compensate for weaknesses of the current model.

Suppose Model A struggles with:

```text
context degradation
```

You introduce:

```text
context resets
```

Model B later handles long context much better.

Those resets may now cause:

* unnecessary latency;
* additional tokens;
* orchestration complexity;
* worse continuity.

So you remove them.

Anthropic followed the same process with sprint decomposition and evaluator frequency: some mechanisms that were critical for one model generation became unnecessary or could run less often with stronger models.

The principle is:

```text
Harness complexity should be earned.
```

Every harness component effectively asserts:

> "The model cannot reliably do X itself."

That assertion should periodically be retested.

---

# 23. Re-simplification should be experimental

Anthropic explicitly recommends removing components methodically.

Not:

```text
New model looks smarter.
Delete half the harness.
```

Instead:

```text
baseline
 ↓
remove component A
 ↓
evaluate
 ↓
keep/remove

then component B
 ↓
evaluate
```

This is essentially an ablation study on your harness.

For serious agent infrastructure, this means maintaining evaluations not just for prompts and models but for:

```text
model × prompt × tools × harness
```

The harness itself is part of the system under evaluation.

---

# 24. Model specialization can be economical

Anthropic also discusses assigning different models to different roles.

For example:

```text
strong reasoning model
→ planning

cheaper/faster model
→ implementation

specialized/faster model
→ evaluation
```

The correct choice depends on task and economics.

This should not be hardcoded from intuition.

Individual agent roles should have evaluations so that you can determine:

```text
model + prompt + role
→ actual performance
```

rather than assuming that the strongest model is required everywhere.

---

# 25. Subagents are valuable partly because of context isolation

One of the deeper implications of the workshop is that subagents are not merely a mechanism for parallel execution.

They provide **independent reasoning contexts**.

Compare:

```text
ONE AGENT

plan
build
rationalize build
evaluate own build
fix build
```

against:

```text
Planner context
     ↓
contract/state
     ↓
Builder context
     ↓
implementation/evidence
     ↓
Evaluator context
```

Isolation reduces contamination between roles.

The evaluator doesn't need to know every justification the generator made.

The planner does not need the entire execution trace.

The parent does not need every token generated by every child.

Only relevant state crosses boundaries.

That is one of the strongest architectural reasons for using subagents.

---

# 26. Multi-agent does not automatically mean hierarchical

Anthropic's discussion also mentions agent teams where subagents may communicate with one another instead of funneling every interaction through a central parent.

That allows architectures such as:

```text
         Orchestrator
        /     |      \
       /      |       \
Agent A ←→ Agent B ←→ Agent C
```

instead of:

```text
Agent A
   ↓
Parent
   ↓
Agent B
   ↓
Parent
   ↓
Agent C
```

This can reduce parent-context pollution and communication bottlenecks.

But the talk does not claim that agent teams should always be used. The broader principle remains: choose architecture based on the task and measure it.

---

# 27. Trace reading is the core harness-engineering skill

One of the most practical statements in the entire workshop concerns debugging.

Anthropic's engineers repeatedly say that the main development loop is:

```text
run agent
   ↓
read trace
   ↓
find divergence
   ↓
understand WHY model behaved that way
   ↓
modify prompt/tools/harness
   ↓
run again
```

Not simply:

```text
run 100 experiments
→ compare pass rate
```

Quantitative evaluation matters.

But when developing the harness, traces reveal the mechanism of failure.

They even recommend reading the complete trace rather than only a generated summary.

---

# 28. Agent debugging requires "model empathy"

This is a useful engineering concept from the Q&A.

Imagine controlling a browser while:

1. your eyes are closed;
2. every ten seconds someone lets you view one screenshot;
3. you must decide what to click;
4. your eyes close again.

Humans would make strange decisions in that environment.

An AI agent may be operating under similarly unnatural observational constraints.

When debugging, therefore, don't merely ask:

```text
Why was the model stupid?
```

Ask:

```text
What information was actually available?
What did the tool response look like?
What assumptions were reasonable from that perspective?
What relevant signal was missing?
What made the wrong action attractive?
```

Anthropic says this kind of close trace reading informed the development of their browser-use harnesses.

This is a central AI-engineering skill.

---

# 29. Harness development is itself a feedback loop

Anthropic also describes using agents to inspect traces.

Conceptually:

```text
Production agent traces
        ↓
trace-analysis agent
        ↓
candidate failure clusters
        ↓
human inspection
        ↓
prompt/tool/harness updates
```

But they still emphasize manual trace reading as the highest-fidelity debugging method.

Thus there are actually **two nested loops**:

```text
INNER LOOP

Generator
→ Evaluator
→ Generator


OUTER LOOP

Harness
→ production traces
→ engineer evaluation
→ improved harness
```

The agent learns within a task.

The harness engineer learns across tasks.

---

# 30. Evaluation should target recurring model weaknesses

An evaluator does not necessarily need to be project-specific.

Anthropic's goal was to identify general weaknesses that recur across outputs.

Examples could include:

```text
superficial verification
unfinished functionality
generic visual design
ignored edge cases
stub implementations
weak error handling
poor API boundaries
```

Those recurring weaknesses can become reusable rubrics or evaluator prompts.

Project-specific criteria can then be layered on top.

This suggests:

```text
Evaluator
├── generic quality rubric
├── domain rubric
├── repository/project rules
└── feature-specific contract
```

---

# 31. Humans should not automatically become permanent loop components

During Q&A, someone suggests periodically interrupting the harness for human sprint reviews.

Anthropic's answer is revealing.

A human checkpoint can absolutely be implemented.

But they prefer not to immediately turn every observed weakness into:

```text
agent fails here
→ add permanent human approval
```

Instead they ask whether the failure can be engineered out of the harness.

Their experimental workflow is closer to:

```text
run 10 autonomous attempts
      ↓
inspect failed runs
      ↓
improve harness
      ↓
repeat
      ↓
eventually trust unattended execution
```

Human intervention can remain available through hooks or steering mechanisms, but the research objective is to expand the portion of the task that can reliably execute without intervention.

---

# 32. Greenfield versus brownfield

Anthropic is explicit that the demonstrated architecture works particularly well for **greenfield application generation**.

Brownfield repositories introduce additional constraints:

* existing architecture;
* local conventions;
* backward compatibility;
* large test suites;
* hidden assumptions;
* production invariants;
* existing APIs;
* migration constraints.

The generic harness must therefore be adapted.

Anthropic suggests that the same principles remain useful, but the rubrics, tests and constraints must become project-aware. They also discuss automation around other brownfield SDLC stages such as monitoring → issue creation → implementation → PR review.

So:

```text
Pattern generalizes.
Implementation does not automatically generalize.
```

---

# 33. The five strongest workshop takeaways

Ash ends the main presentation with roughly five core lessons.

Rephrased technically:

### 1. Don't trust self-evaluation

Separate generator and evaluator.

### 2. Compaction isn't equivalent to coherence

Use structured state and clean contexts when needed.

### 3. Subjective quality can often be operationalized

Turn taste into rubrics and examples.

### 4. Structured handoffs matter

Persist state rather than expecting conversation context to carry a multi-hour task.

### 5. Read the traces

Harnesses should be derived from actual model failures, not theoretical expectations.

---

# 34. A concrete harness architecture derived from the workshop

The following is a synthesis of the ideas rather than an Anthropic-prescribed API.

```text
┌─────────────────────────────────────────┐
│               USER TASK                 │
└────────────────────┬────────────────────┘
                     │
                     ▼
             ┌───────────────┐
             │    PLANNER    │
             │ fresh context │
             └───────┬───────┘
                     │
               BUILD_PLAN
                     │
                     ▼
┌─────────────────────────────────────────┐
│           DURABLE TASK STATE            │
│                                         │
│ objective                               │
│ contracts                               │
│ progress                                │
│ completed work                          │
│ unresolved findings                     │
│ evidence                                │
│ checkpoints                             │
│ budget                                  │
└────────────────────┬────────────────────┘
                     │
                     ▼
             select next work
                     │
                     ▼
             ┌───────────────┐
             │   GENERATOR   │
             │ bounded task  │
             └───────┬───────┘
                     │
              implementation
                     │
                     ▼
                 evidence
                     │
                     ▼
             ┌───────────────┐
             │   EVALUATOR   │
             │ fresh context │
             │ read-only     │
             └───────┬───────┘
                     │
          ┌──────────┴───────────┐
          │                      │
        PASS                NEEDS_WORK
          │                      │
          ▼                      ▼
update contract          structured findings
          │                      │
          └──────────┬───────────┘
                     │
                     ▼
             LOOP CONTROLLER
                     │
         ┌───────────┼───────────┐
         │           │           │
      continue      done        stop
```

The most important architectural separation is:

```text
MODEL
→ proposes actions

HARNESS
→ controls execution lifecycle

STATE
→ records reality

EVIDENCE
→ demonstrates outcomes

EVALUATOR
→ judges progress

RUNTIME
→ decides continuation
```

---

# 35. Minimal long-running loop

A first implementation does not need a huge framework.

Conceptually:

```python
state = initialize_task(user_goal)

while not state.finished:

    work_item = select_next_work(state)

    contract = negotiate_contract(
        work_item=work_item,
        state=state,
    )

    result = run_generator(
        task=work_item,
        contract=contract,
        relevant_state=state,
    )

    verdict = run_evaluator(
        contract=contract,
        artifacts=result.artifacts,
        evidence=result.evidence,
    )

    state.record(result, verdict)

    if verdict.pass_:
        state.complete(work_item)
    else:
        state.add_findings(verdict.findings)

    if budget_exceeded(state):
        break

    if no_progress(state):
        break
```

Everything else should justify its existence by fixing an observed problem.

---

# 36. What NOT to build initially

The workshop strongly argues against premature harness complexity.

Avoid beginning with:

```text
20 specialized agents
complex supervisor graphs
multiple memory databases
deep planning hierarchies
automatic context reset everywhere
several evaluator layers
arbitrary reflection stages
```

unless traces show those components are necessary.

Instead begin closer to:

```text
Planner
Generator
Evaluator
Filesystem state
Explicit completion contract
Real verification
Loop controller
```

and evolve from evidence.

---

# 37. Anti-patterns

## Anti-pattern 1 — Model owns "done"

```text
Builder: "Looks good. Finished."
Harness: exits
```

Bad.

---

## Anti-pattern 2 — Conversation history is task state

```text
messages = everything_that_ever_happened
```

Eventually unreliable.

Persist canonical state separately.

---

## Anti-pattern 3 — Builder reviews itself

```text
build()
review_my_own_build()
```

Produces weak adversarial pressure.

---

## Anti-pattern 4 — Verification means tests happened

```text
pytest passes
→ product works
```

Not necessarily.

Use end-to-end evidence where appropriate.

---

## Anti-pattern 5 — Planning the entire future implementation

Detailed early mistakes compound.

Prefer high-level long-horizon planning + just-in-time contracts.

---

## Anti-pattern 6 — Permanent scaffolding

A harness designed around Model N may actively hurt Model N+1.

Re-evaluate.

---

## Anti-pattern 7 — Prompting instead of enforcing

```text
"Please don't mark tasks complete without evidence."
```

is weaker than:

```text
PASS state cannot be written without evidence.
```

---

## Anti-pattern 8 — Endless patching

Allow the loop to rollback or abandon a failed direction.

---

# 38. A practical state model

A serious harness could maintain something conceptually like:

```text
TaskState
├── objective
├── constraints
├── plan
├── work_items[]
│   ├── status
│   ├── contract
│   ├── attempts
│   ├── findings
│   └── evidence
├── decisions[]
├── checkpoints[]
├── unresolved_issues[]
├── progress_summary
├── budget
└── termination_state
```

Critically, this state should be authoritative independently of whichever model happens to be running.

A worker receives a **projection** of the state:

```text
task state
   ↓
context builder
   ↓
only relevant information
   ↓
worker context
```

rather than the full history.

---

# 39. The deeper lesson about subagents

The workshop suggests a better reason for creating subagents than simply:

> "Parallelism makes things faster."

Subagents give you:

### Context isolation

Workers don't inherit unrelated reasoning baggage.

### Objective specialization

One model builds; another attacks weaknesses.

### Capability restriction

Evaluators can be read-only.

### Independent judgment

The critic hasn't rationalized the implementation decisions.

### Context budgeting

The orchestrator doesn't need every worker's detailed trajectory.

### Fault containment

A subagent can fail without corrupting the whole parent context.

That is the architectural value of subagents in long-running systems.

---

# 40. The deepest lesson

The workshop ultimately changes the mental model from:

```text
How do I make the agent smart enough to work for six hours?
```

to:

```text
How do I design a system in which a probabilistic worker
can repeatedly make bounded progress toward a measurable
goal without losing state, fooling itself about completion,
or drifting away from the objective?
```

That is a harness-engineering problem.

The LLM is only one component.

The full system is:

```text
model
+ tools
+ environment
+ state
+ context construction
+ decomposition
+ evaluation
+ evidence
+ recovery
+ continuation logic
+ observability
```

Long-running capability emerges from the interaction between those components.

---

# 41. Study checklist

After studying this course, you should be able to answer:

### State

* What survives a context reset?
* What is authoritative?
* How does a new worker recover task state?

### Context

* What information does each agent actually need?
* When should context be compacted?
* When should it be reset?

### Planning

* What belongs in the long-horizon plan?
* What should remain undecided until execution?

### Contracts

* Who defines "done"?
* Are completion criteria independently testable?
* Are they granular enough to produce actionable failures?

### Evaluation

* Is the evaluator independent?
* Does it observe real behavior?
* Does it have a concrete rubric?
* Can it modify the implementation, and should it?

### Loop

* Who decides whether execution continues?
* What happens after failed evaluation?
* Can the system rollback or replan?
* What are the hard exit conditions?

### Observability

* Can you reconstruct why the model chose an action?
* Are complete traces available?
* Can failures be clustered across runs?

### Evolution

* Which harness components compensate for current model weaknesses?
* Which components can be removed when the model improves?

---

# 42. Compact mental model

Keep this model:

```text
                 INTENT
                   │
                   ▼
                PLAN
                   │
                   ▼
              CONTRACT
                   │
                   ▼
                BUILD
                   │
                   ▼
               OBSERVE
                   │
                   ▼
               EVALUATE
                   │
            ┌──────┴──────┐
            │             │
           PASS          FAIL
            │             │
            ▼             ▼
        persist        feedback
            │             │
            └─────► LOOP ◄┘
```

And underneath everything:

```text
DURABLE STATE
+
TRACEABILITY
+
EXPLICIT CONTROL
```

That is the core architecture behind the workshop.
