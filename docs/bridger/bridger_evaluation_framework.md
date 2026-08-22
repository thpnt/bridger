# Bridger — Evaluation Framework and Layer Completion Gates

**Status:** Foundational V0 evaluation document  
**Date:** 4 August 2026  
**Scope:** Core evaluation metrics, measurement procedures, layer completion gates, hard blockers, deferrable improvements, and final end-to-end qualification.

---

## 1. Purpose

This document defines how each architectural layer of Bridger is evaluated and when it is sufficiently complete to support construction of the next layer.

It complements, and does not redefine, the responsibilities, ownership boundaries, intended behavior, authority model, and V0 acceptance principles established in **Bridger — Product Vision and Core Engine Design**.

The framework focuses on the minimum evidence required to qualify the V0 core engine. It intentionally avoids exhaustive metric catalogs and implementation-specific requirements.

---

## 2. Global evaluation rule

A layer receives **GO** when:

1. all hard functional and boundary gates pass;
2. the required evaluation evidence is available;
3. performance and cost remain within the approved V0 budgets;
4. repeated runs satisfy the defined reproducibility standard;
5. remaining weaknesses are explicitly diagnosed and classified as deferrable.

Every evaluation run must identify:

- repository identity;
- repository revision;
- workspace scope;
- schema versions;
- generator and extractor versions;
- prompt and model versions where applicable;
- evaluation configuration.

Failure to establish this identity blocks qualification of every downstream layer.

---

## 3. Deterministic substrate

### 3.1 Core metrics

**Quality**

- Eligible Git-file representation rate.
- Valid symbol identity and source-range rate.
- Manifest and deterministic graph fact validity.
- Extraction failures explicitly diagnosed rather than silently omitted.

**Performance**

- Total build time, normalized by repository size.
- Peak memory usage, normalized by repository size.

**Cost**

- Compute cost per repository.
- Artifact storage size per repository.

**Reproducibility**

- Semantic equality of deterministic artifacts across repeated runs at the same repository revision and extractor version.

### 3.2 Quick measurement procedure

1. Run the deterministic substrate repeatedly on each reference repository.
2. Compare the file inventory against Git truth.
3. Validate schemas, identifiers, references, revisions, and checksums automatically.
4. Manually inspect a small representative sample of:
   - symbols;
   - source ranges;
   - manifests;
   - graph nodes and edges;
   - exclusions and diagnostics.

### 3.3 GO criteria

- All eligible files are represented or have an explicit exclusion or read-policy classification.
- Artifacts are valid, revisioned, checksummed, and mutually consistent.
- Stable identifiers and source ranges resolve correctly.
- Unsupported or failed extraction is visible through diagnostics.
- Deterministic artifacts contain no model-derived semantic interpretation.
- Repeated runs produce semantically equivalent deterministic results.
- Execution remains within the approved V0 resource budget.

### 3.4 Hard blockers

- Silent file or fact omissions.
- Invalid identifiers or source ranges.
- Incorrect or missing repository revision identity.
- Unreported extraction failures.
- AI-derived semantics stored as deterministic facts.
- Material instability across repeated runs.

### 3.5 Deferrable improvements

- Broader language coverage.
- Richer graph relations.
- Incremental rebuilding.
- Faster indexing.
- Advanced graph-quality analysis.

---

## 4. AI enrichment overlay

### 4.1 Core metrics

**Quality**

- Valid target-reference rate.
- Usefulness and correctness of labels on reviewed samples.
- Unsupported semantic assertion rate.

**Performance**

- Enrichment duration per repository.
- Enrichment duration per annotated graph entity.

**Cost**

- Model cost per repository.
- Model cost per accepted annotation.

**Reproducibility**

- Stability of core labels and classifications across repeated runs.
- Exact wording equality is not required.

### 4.2 Quick measurement procedure

1. Run enrichment several times over the same deterministic graph.
2. Validate target identifiers, revisions, provenance, statuses, and metadata automatically.
3. Have an expert review representative:
   - graph communities;
   - high-centrality nodes;
   - important classifications;
   - explanations and confidence levels.

### 4.3 GO criteria

- Enrichment remains physically and logically separate from deterministic artifacts.
- Every annotation targets an existing deterministic entity.
- Every annotation records required provenance and revision metadata.
- The deterministic graph is not mutated.
- Labels provide useful semantic orientation for downstream agents.
- Materially misleading or unsupported annotations remain within the accepted baseline.
- Repeated runs preserve the same broad repository interpretation.
- Latency and model cost remain within the approved V0 budget.

### 4.4 Hard blockers

- Mutation of deterministic artifacts.
- References to nonexistent graph entities.
- Missing provenance or revision metadata.
- Systematic semantic misclassification.
- Presentation of inferred annotations as deterministic truth.

### 4.5 Deferrable improvements

- Perfect naming consistency.
- Exhaustive entity annotation.
- Fully calibrated scoring models.
- Advanced anomaly detection.
- Optimized model allocation.

---

## 5. Memory-agent generation and maintenance

### 5.1 Core metrics

**Quality**

- Valid evidence-reference rate.
- Correctness of central behavioral claims.
- Assigned-scope coverage.
- Unsupported-certainty rate.
- Consistency between Markdown, metadata, and claim sidecars.

**Performance**

- Completion time per bounded knowledge task.
- Tool usage per bounded knowledge task.

**Cost**

- Model cost per completed task.
- Model cost per accepted knowledge bundle.

**Reproducibility**

- Agreement on core claims, workflows, evidence, and unknowns across repeated runs.

### 5.2 Quick measurement procedure

1. Assign predefined repository-understanding tasks.
2. Validate schemas, evidence references, repository revisions, and claim links automatically.
3. Compare results with expert-reviewed expectations.
4. Repeat selected tasks to measure conclusion and evidence stability.
5. Review at least one complete knowledge bundle per reference repository.

### 5.3 GO criteria

- Agents can navigate from the enriched graph to implementation-level source evidence.
- Substantive claims are traceable to valid evidence at the correct repository revision.
- Central workflows are explained correctly within the assigned task scope.
- Unknowns, contradictions, and insufficient evidence are preserved explicitly.
- Knowledge bundles are internally consistent.
- Durable state, budgets, completion decisions, and publication authority remain harness-controlled.
- A bounded task can resume from durable task-level state or a checkpoint.
- Agents do not mutate deterministic or enrichment artifacts.

### 5.4 Hard blockers

- Unsupported central claims.
- Invalid, fabricated, or stale evidence.
- Inconsistent knowledge bundles.
- Hidden contradictions or false certainty.
- Inability to complete bounded knowledge tasks.
- Transcript-only execution state.
- Mutation of upstream deterministic or enrichment artifacts.

### 5.5 Deferrable improvements

- Complete PR-driven maintenance.
- Sophisticated multi-agent scheduling.
- Arbitrary mid-turn recovery.
- Optimized context selection.
- Advanced contradiction-repair strategies.

---

## 6. Repository Brain publication

### 6.1 Core metrics

**Quality**

- Manifest completeness.
- Checksum and revision consistency.
- Knowledge-bundle integrity.
- Successful validation rate.

**Performance**

- Publication time per snapshot.

**Cost**

- Snapshot storage overhead.

**Reproducibility**

- Identical validated component inputs produce the same composite manifest and snapshot identity.

### 6.2 Quick measurement procedure

1. Assemble snapshots from validated components.
2. Run schema and cross-artifact validation.
3. Inject mismatched, stale, incomplete, or missing components.
4. Verify that publication is rejected.
5. Verify that no partial or mixed snapshot becomes visible to consumers.

### 6.3 GO criteria

- All published components belong to the declared repository revision.
- Artifact versions and checksums resolve correctly.
- Markdown, metadata, and claim sidecars are consistent.
- Validation completes before publication.
- Publication is atomic.
- Consumers cannot observe mixed, incomplete, or partially updated snapshots.

### 6.4 Hard blockers

- Mixed repository revisions.
- Missing required components or checksums.
- Orphaned claims.
- Inconsistent knowledge bundles.
- Non-atomic publication.
- Publication despite failed validation.

### 6.5 Deferrable improvements

- Remote storage.
- Snapshot-retention policy.
- Incremental publication.
- Advanced caching.
- Historical comparison interfaces.

---

## 7. Retrieval and product-consumption layer

### 7.1 Core metrics

**Quality**

- Relevant-context precision.
- Required-context recall.
- Provenance completeness.
- Usefulness of `bridger prompt` and `bridger ticket` outputs.

**Performance**

- Retrieval latency.
- Returned context size.

**Cost**

- Retrieval and generation cost per request.

**Reproducibility**

- Stable core context selection for the same Repository Brain snapshot, task, and retrieval configuration.

### 7.2 Quick measurement procedure

1. Define a small representative set of coding and product tasks.
2. Compare retrieved context with expert-selected relevant evidence.
3. Review generated `bridger prompt` and `bridger ticket` outputs.
4. Repeat identical requests against the same snapshot and configuration.
5. Verify budget compliance and evidence expansion behavior.

### 7.3 GO criteria

- Retrieval returns targeted context rather than concatenating the entire Repository Brain.
- Returned context distinguishes:
  - deterministic facts;
  - AI enrichment;
  - knowledge claims;
  - uncertainty and contradictions.
- Evidence, revision, freshness, and warning information are available.
- Context budgets are respected.
- The interface is read-only and provider-neutral.
- `bridger prompt` and `bridger ticket` produce technically useful outputs grounded in the Repository Brain.
- External consumers can retrieve and expand relevant context through a stable interface.

### 7.4 Hard blockers

- Whole-Brain context dumping.
- Missing provenance.
- Stale or mixed-revision context.
- Mutation through the consumer interface.
- Hidden uncertainty.
- Dependence on one provider-specific internal format.

### 7.5 Deferrable improvements

- Optimal retrieval ranking.
- Polished product UX.
- Broader MCP functionality.
- Personalized retrieval.
- Organization-level or cross-repository querying.

---

## 8. Final end-to-end qualification

Final qualification is cumulative rather than a separate evaluation framework.

The V0 core engine receives **GO** when:

1. every architectural layer has passed its own completion gate;
2. one integrated run confirms that the qualified layers compose correctly;
3. each layer consumes only the contracts exposed by the preceding layer;
4. authority and mutation boundaries remain intact;
5. repository revision identity is preserved end to end;
6. a valid Repository Brain snapshot is published atomically;
7. the published Repository Brain is consumed successfully through the retrieval layer and initial product surfaces.

End-to-end qualification does not replace layer-level evaluation. It confirms that independently qualified layers integrate without violating their contracts.

---

## 9. Decision outcomes

### GO

All hard gates pass. Remaining issues are documented and deferrable. The next layer may be built on top of the qualified layer.

### NO-GO

At least one hard blocker remains, required evidence is missing, or the layer cannot reliably satisfy its core V0 responsibility.

A separate **conditional GO** status is intentionally excluded from the core framework. Any issue serious enough to make progression conditional should either be resolved or explicitly reclassified as a non-blocking deferred improvement before progression.
