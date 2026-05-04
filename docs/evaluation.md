# Evaluation

This is a manual checklist for judging Bridger on a real repository or a fixture.

The goal is to decide whether the generated context and docs are actually useful to a developer or coding agent, not just whether they are complete.

## Run

```bash
bridger inspect
bridger inspect --graph
bridger init
bridger enrich-ticket "<rough ticket>"
```

If you are only evaluating the repo graph feature, `bridger enrich-ticket` is optional.

## What to check

### Repo context

- Did stack detection work?
- Are the detected commands correct?
- Are the important files the ones you would inspect first?
- Are the generated docs repo-specific, or generic?

### Graph-specific checks

- Did entrypoint detection make sense?
- Did import edges look correct?
- Were unresolved imports reported clearly?
- Did `bridger inspect --graph` highlight useful high fan-in and high fan-out files?
- Did the first 10 architecture-first files look like a good reading order?
- Were important source files included early?
- Did the graph-ordered context improve generated docs compared to heuristic file ordering?
- Did the graph stay stable across repeated runs?

### Ticket enrichment

- Is the enriched ticket better than the rough input?
- Are the acceptance criteria clearer?
- Are missing questions useful?
- Would you paste the handoff prompt into Claude Code or Codex?

### Hallucination review

- What was inferred without evidence?
- What looked overstated?
- Which repo facts were left ambiguous instead of guessed?

## Scoring

Rate each item from 1 to 5.

| Score | Meaning |
| --- | --- |
| 1 | Poor |
| 2 | Weak |
| 3 | Acceptable |
| 4 | Good |
| 5 | Excellent |

Track these dimensions:

- Repo-specificity
- File relevance
- Acceptance criteria quality
- Missing questions quality
- Agent handoff usefulness
- Hallucination control
- Graph fidelity
- Architecture-first usefulness
- Overall usefulness

## Notes

Write down the repo name, the commands you ran, and concrete examples of good or bad file ordering.

The main comparison is graph-backed context versus the older heuristic ordering.
