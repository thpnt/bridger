# Graphify Bridger Adoption

**Status:** Approved architecture decision document  
**Date:** 6 August 2026  
**Scope:** Graphify adoption strategy, canonical repository graph contract, graph lifecycle, persistence, versioning, and update model for Bridger V0.  
**Graphify baseline:** `Graphify-Labs/graphify`, branch `v8`, revision `00efd6e7969837ae4a9f11d8d504dcd3b20b09df`.

---

## 1. Purpose

This document consolidates the decisions from three connected design tasks:

1. **Define the Graphify adoption strategy** — decide which Graphify components Bridger keeps, adapts, defers, or excludes.
2. **Design the canonical repository graph contract** — define Bridger's authoritative graph representation and its interface around the adopted Graphify engine.
3. **Design the graph lifecycle and persistence model** — define how graphs are built, loaded, updated, invalidated, versioned, persisted, and exposed to downstream Bridger layers.

The primary constraint is to ship a qualitative V0 quickly. Graphify is therefore treated as a mature external graph engine embedded inside Bridger, not as a reference from which Bridger should unnecessarily reimplement extraction, resolution, graph construction, analysis, serialization, or incremental-update behavior.

---

## 2. Source basis

The decisions are based on:

- **Graphify Consolidated Component, Contract, and Code Map**;
- **Graphify Repository-Analysis Pipeline Mapping**;
- direct inspection of the Graphify `v8` codebase at the revision listed above;
- **Bridger — Product Vision and Core Engine Design**;
- **Bridger — Evaluation Framework and Layer Completion Gates**.

The consolidated Graphify mapping defines the component boundaries, code locations, object lineage, current internal contracts, persistence artifacts, coupling hotspots, and update behavior used in this document.

---

## 3. Executive decisions

1. **Graphify is the default deterministic graph implementation for Bridger V0.**
2. **The Graphify graph engine remains internally intact unless a concrete Bridger requirement or demonstrated reliability defect requires a targeted change.**
3. **Graphify's internal dictionary-based contracts, transformations, validation, caches, and NetworkX construction remain unchanged in V0.**
4. **Pydantic is introduced only for Bridger-owned interfaces and persisted Bridger contracts**, not throughout Graphify's internal extraction path.
5. **Bridger owns the application interface around Graphify**, including build requests, update requests, results, snapshot metadata, diagnostics aggregation, publication, and downstream access.
6. **`nx.DiGraph` is the Bridger default runtime graph.** Graphify's engine is configured accordingly; no graph-engine rewrite is required.
7. **Bridger V0 accepts Graphify's non-multigraph behavior.** No `MultiGraph` or `MultiDiGraph` migration is required unless later evaluation proves relation collapse materially harmful.
8. **The deterministic graph and AI enrichment are physically separate artifacts and authority layers.**
9. **The deterministic graph and enrichment overlay must be superposable at read time**, allowing AI agents and navigation tools to traverse structural graph facts while seeing AI names, scores, explanations, and classifications in the same logical view.
10. **Incremental updates are supported through explicit functions or methods.** Continuous watch mode is retained as upstream code but inactive and unqualified in Bridger V0.
11. **The final graph is both persisted and returned in memory.** Persisted artifacts support reuse without rebuilding; the in-memory graph supports immediate downstream enrichment and navigation.

---

## 4. Governing implementation principles

### 4.1 Preserve working internals

Graphify's internal pipeline remains based on dictionaries, lists, NetworkX objects, JSON artifacts, and its existing validation functions. Bridger does not migrate all internal records to Pydantic merely for stylistic consistency.

### 4.2 Type only Bridger-owned boundaries

Pydantic or equivalent typed models should be used for boundaries such as:

- `GraphBuildRequest`;
- `GraphUpdateRequest`;
- `GraphBuildResult`;
- `GraphSnapshotManifest`;
- Bridger diagnostics aggregation;
- enrichment overlay records;
- Repository Brain publication contracts.

### 4.3 Avoid mass internal renaming

User-facing commands, paths, artifact names, configuration, and public modules should follow Bridger conventions. Imported internal Graphify files and functions do not need to be mass-renamed during V0 because that would create a large low-value diff, increase regression risk, and make upstream synchronization harder.

### 4.4 Isolate the adopted engine

A suitable conceptual module boundary is:

```text
bridger/
└── graph/
    ├── application/          # Bridger-owned build/update/load/query services
    ├── contracts/            # Bridger-owned public and persisted contracts
    ├── engine/               # Adopted Graphify implementation
    ├── enrichment/           # Separate AI annotation overlay
    └── persistence/          # Snapshot loading, validation and publication
```

The exact folder names may change during implementation, but the ownership boundary should remain explicit.

---

# Part I — Graphify adoption strategy

## 5. Decision vocabulary

- **KEEP** — retain the Graphify component substantially as implemented.
- **ADAPT** — retain the capability and significant implementation, but change its Bridger-facing boundary, configuration, activation, or authority semantics.
- **DEFER / EXCLUDE FROM V0** — do not activate or qualify the component in the initial Bridger core engine. The design or code may remain available for later use.

---

## 6. Component decision sheet

### A. Repository intake — C01–C03

| ID | Component and primary code | Decision | V0 activation | Input → transform → output | Bridger adaptation / exposed boundary | Tests and upstream policy | Rationale |
|---|---|---|---|---|---|---|---|
| **C01** | CLI and run dispatch — `graphify/cli.py`, `graphify/__main__.py`, `graphify/paths.py`, skill entrypoints | **ADAPT** | Active | User arguments, environment, repository path → resolve run configuration and dispatch stages → pipeline invocation | Bridger owns programmatic `build_repository_graph`, `update_repository_graph`, and load/query functions. The CLI is a thin wrapper. Preserve useful Graphify options and modes. Typer/Rich may be used if consistent with the wider Bridger CLI. | Import relevant configuration and dispatch tests. Add direct programmatic invocation tests. Selective upstream sync for useful options and bug fixes. | The graph is a final product in Graphify but an intermediate capability in Bridger. It must be callable by other Bridger workflows. |
| **C02** | Corpus discovery and classification — `graphify/detect.py`, `graphify/security.py`, `graphify/google_workspace.py` | **ADAPT** | Active | Repository root and policies → walk, classify, exclude, detect types, calculate corpus metrics → `DetectionResult`, manifest/stat data | Git-tracked inventory is authoritative. Graphify classification, sensitive-file handling, type detection, and corpus-health logic are retained. `.graphifyignore` becomes `.bridgerignore`. Tracked-but-excluded or unsupported files remain visible in diagnostics. Internal `DetectionResult` stays dictionary-based. | Retain detection, classification, security, and ignore tests. Add Git-truth and `.bridgerignore` tests. Selectively sync classification and security fixes while preserving Bridger inventory semantics. | Graphify's classifier is valuable, but raw filesystem enumeration does not satisfy Bridger's repository completeness and revision identity requirements. |
| **C03** | Media/document preprocessing — `graphify/transcribe.py`, Google Workspace conversion helpers | **DEFER / EXCLUDE FROM CORE V0** | Inactive | Audio, video, office or cloud documents → transcription/conversion → generated text and sidecars | Keep a future preprocessing extension point, but do not activate mixed-media conversion in the first deterministic graph pipeline. | No V0 qualification requirement. No routine upstream sync. Revisit when mixed-media Repository Brain ingestion is prioritized. | It adds provider configuration, dependencies, security concerns, and operational scope without being required for the first qualitative code graph. |

### B. Deterministic extraction — C04–C10

| ID | Component and primary code | Decision | V0 activation | Input → transform → output | Bridger adaptation / exposed boundary | Tests and upstream policy | Rationale |
|---|---|---|---|---|---|---|---|
| **C04** | Structural extraction facade and dispatch — `graphify/extract.py` | **KEEP WITH BOUNDARY ADAPTATION** | Active | Classified code/config paths, root, cache and extractor configuration → dispatch extractors, aggregate fragments, run repository-wide passes → per-file and combined `ExtractionResult` dictionaries | Preserve the internal dictionary flow. Do not migrate internal `ExtractionResult` records to Pydantic in V0. Expose the component only through Bridger's graph-build application service. | Retain extraction dispatch, aggregation, and repository-wide pass tests. Close sync while C04 remains coupled to extractors and resolvers. | C04 is a large compatibility and orchestration facade required by the working extractor stack. Rewriting it would create unnecessary risk. |
| **C05** | Generic Tree-sitter extractor kernel — `graphify/extractors/models.py`, `base.py`, `engine.py` | **KEEP** | Active | File bytes and `LanguageConfig` → parse AST, walk declarations/imports/calls/types → nodes, edges, raw facts | Keep behavior intact. Add Bridger diagnostics and integration around the kernel instead of changing its extraction semantics. | Import parser and language regression tests. Close upstream sync, especially correctness fixes. | This is a mature, high-value core capability. |
| **C06** | Language configuration layer — `LanguageConfig`, configuration and registry behavior split across `extractors/models.py` and `extract.py` | **KEEP** | Active | Grammar plus language rules → configure generic extraction → language-specific behavior | Retain the current dataclass and configuration path. A Bridger support registry may later describe status and coverage without replacing the engine configuration. | Retain language configuration and dispatch tests. Close sync with C04/C05. | Replacing a working dataclass or registry does not improve V0 quality. |
| **C07** | Cross-file and symbol resolution — shared resolution modules, resolver registry, language-specific resolvers | **KEEP** | Active | Per-file nodes, edges, symbol facts, aliases and repository layout → resolve imports, calls, inheritance, types, workspaces and references → augmented/repaired edges | Preserve the implementation. Bridger diagnostics must expose resolved, external, unresolved, ambiguous, ignored, and unsupported relations where available. | Import the full resolver regression suite for enabled languages. Highest-priority upstream sync area. | Cross-file resolution is essential and contains extensive accumulated language-specific hardening. |
| **C08** | Dedicated language extractors — `graphify/extractors/*.py` | **KEEP WITH SUPPORT TIERS** | Selected languages active | Source file and language-specific parser/configuration → extract structural facts → per-file extraction fragments | Retain available extractors, but classify language support as `supported`, `experimental`, or `disabled`. Only evaluated languages are promised by Bridger V0. | Import all tests for supported languages. Keep compatible regression tests for experimental languages. Close sync for supported languages; selective sync elsewhere. | Retaining source preserves future coverage without making Bridger guarantee every Graphify language immediately. |
| **C09** | Manifest, project and tool-config ingestion — `manifest_ingest.py`, `mcp_ingest.py`, `scip_ingest.py`, config extractors | **KEEP WITH SCOPED ACTIVATION** | Manifest/project ingestion active; SCIP/MCP optional | Manifests, project files, config or external indexes → extract declared packages, scripts, entrypoints and relations → deterministic nodes and edges | Activate manifests and project declarations in V0. Enable SCIP or MCP ingestion only when their node and relation types are accepted by the graph contract and needed by a Bridger workflow. | Retain manifest/project tests. Selectively synchronize by ingestion family. | Declared entrypoints and package boundaries are high-confidence facts. Other ingestion families are separable. |
| **C10** | Rationale and document quick-scan extraction — Markdown extractor, docstring/comment logic | **ADAPT AUTHORITY BOUNDARY** | Selectively active | Markdown, docstrings and marked comments → emit document/rationale records and relations → structural fragments | Deterministic existence, location, ownership, and containment can remain in the graph. Inferred intent, architecture meaning, or correctness belongs in AI enrichment or Repository Brain knowledge. | Retain extraction tests and add authority-layer checks. Selective sync. | Comments and docs are valuable evidence, but their semantic interpretation must not become deterministic truth. |

### C. Semantic extraction, caching, validation and graph construction — C11–C15

| ID | Component and primary code | Decision | V0 activation | Input → transform → output | Bridger adaptation / exposed boundary | Tests and upstream policy | Rationale |
|---|---|---|---|---|---|---|---|
| **C11** | Semantic/AI extraction — `graphify/llm.py`, `semantic_cleanup.py`, semantic extraction workflows | **EXCLUDE FROM THE DETERMINISTIC V0 ENGINE** | Inactive | Non-code corpus plus prompt/model → infer concepts and relationships → semantic `ExtractionResult` | Do not merge semantic extraction into the deterministic graph. Bridger's AI enrichment consumes the completed deterministic graph and writes a separate overlay. Individual provider or chunking utilities may be reused later. | No deterministic-engine qualification requirement. No regular upstream sync as a component. | Graphify merges semantic and structural records into one graph; Bridger requires physical and logical authority separation. |
| **C12** | Per-file caching and portability — `graphify/cache.py` | **KEEP WITH PATH/LIFECYCLE ADAPTATION** | Active | File content/path, extractor version and prompt fingerprint → hash, load/save, relativize/re-anchor, prune → AST/semantic caches and stat index | Adapt output paths and repository identity. Preserve AST cache portability, version namespacing, atomic replacement and stat-index behavior. Semantic cache remains inactive while C11 is disabled. | Retain hit/miss, portability, atomicity, pruning and invalidation tests. Close sync for correctness fixes. | Mature caching significantly reduces rebuild cost and already solves difficult portability issues. |
| **C13** | Schema validation — `graphify/validate.py` | **KEEP** | Active | Combined extraction dictionaries → validate Graphify-required fields/enums/endpoints → errors or accepted extraction | Keep Graphify validation unchanged while its internal dictionary contracts remain unchanged. Add separate Bridger validators only at Bridger-owned boundaries and publication gates. | Retain validation tests unchanged. Close sync with C04/C14 contract changes. | Replacing validation without replacing the internal contracts would create incompatibility with no V0 benefit. |
| **C14** | Normalization, identity repair and graph construction — `graphify/build.py`, `ids.py`, `paths.py` | **KEEP** | Active | Combined extraction → alias repair, path/ID normalization, duplicate/ghost reconciliation, edge filtering, NetworkX assembly → `nx.Graph` or `nx.DiGraph` | Adopt the engine as implemented. Configure `nx.DiGraph` as Bridger's default. Do not create a second graph engine. Make targeted changes only for demonstrated blockers. | Import normalization, identity, direction, deduplication, edge filtering, merge and graph-build regression tests. Close upstream sync. | The module contains extensive hardened logic. Reimplementing it would likely reintroduce solved defects. |
| **C15** | Entity deduplication — `graphify/dedup.py`, build-time exact/ghost deduplication | **KEEP** | Deterministic paths active | Node and edge records → exact identity reconciliation and supported rewiring → deduplicated graph inputs | Preserve deterministic deduplication. Semantic/fuzzy paths dependent on C11 remain inactive. Future probabilistic merges must be reversible overlays or proposals. | Retain deterministic deduplication tests. Close sync with C14. | Deduplication is part of the functioning Graphify pipeline and does not need replacement. |

### D. Derived structural intelligence — C16–C19

| ID | Component and primary code | Decision | V0 activation | Input → transform → output | Bridger adaptation / exposed boundary | Tests and upstream policy | Rationale |
|---|---|---|---|---|---|---|---|
| **C16** | Community detection and cohesion — `graphify/cluster.py` | **KEEP** | Active | Graph plus clustering configuration → Leiden/Louvain, hub handling, splitting, reindexing and cohesion scoring → communities, cohesion, member signatures | Preserve the implementation. Record algorithm, version, parameters, projection and relevant seeds/configuration in snapshot metadata. Select one stable default configuration for V0. | Retain clustering, stable reindexing, hub exclusion, splitting and cohesion tests. Close sync for correctness. | Communities are important for navigation and enrichment, and Graphify already provides the needed implementation. |
| **C17** | Structural analysis — `graphify/analyze.py` | **KEEP** | Active | Graph and communities → god nodes, surprising connections, suggested questions and topology analysis → derived analysis lists/dictionaries | Preserve the full component. Store and present its outputs as derived structural analysis rather than extracted repository facts. | Retain god-node, noise-filtering, cross-file, cross-community and suggested-question tests. Close sync while graph semantics remain aligned. | Its heuristics and noise filters are specifically hardened for Graphify's graph model; this coupling is beneficial. |
| **C18** | Diagnostics and health checks — `graphify/diagnostics.py` plus distributed build/export/watch checks | **KEEP WITH BRIDGER AGGREGATION** | Active | Detection, extraction, graph and previous outputs → identify failures, shrinkage, dangling/collapsed/suspicious output → warnings and health signals | Keep all internal checks. Add a typed Bridger diagnostics artifact aggregating stage, code, severity, message, affected entities, recoverability, and publication-blocking status. | Retain existing diagnostics tests and add aggregation/publication-gate tests. Close sync for internal checks; Bridger owns the external diagnostics contract. | Diagnostics are required for trust, but Graphify does not expose one consolidated durable contract. |
| **C19** | Community labeling — deterministic hub labels and model-assisted labeling | **ADAPT INTO TWO AUTHORITY PATHS** | Deterministic active; AI path later | Communities and graph context → deterministic or model-generated names → label data | Deterministic labels remain part of derived deterministic outputs. AI names are stored only in the enrichment overlay. Both may be visible in a composite read view with provenance. | Retain deterministic label tests. AI label evaluation belongs to the enrichment layer. | A single shared label field would hide whether a label was algorithmic or model-generated. |

### E. Publication, lifecycle and consumers — C20–C25

| ID | Component and primary code | Decision | V0 activation | Input → transform → output | Bridger adaptation / exposed boundary | Tests and upstream policy | Rationale |
|---|---|---|---|---|---|---|---|
| **C20** | Graph serialization and external exports — `graphify/export.py`, `graphify/exporters/*` | **KEEP** | JSON active; optional formats as needed | Graph, communities, labels and metadata → node-link JSON and optional visual/database formats → graph JSON, HTML, GraphML, SVG, Obsidian, Cypher | Adopt Graphify's JSON graph shape as the default Bridger V0 deterministic graph artifact. Rename paths only where useful. Add Bridger snapshot metadata or a wrapping manifest without replacing the exporter. Preserve atomic writes, backups and shrink guards. | Retain JSON round-trip, direction, hyperedge, community, atomic-write, backup and shrink-guard tests. Close sync for JSON/safety; selectively sync optional exporters. | Existing serialization is mature and is an acceptable Bridger V0 graph contract unless evaluation reveals an actual incompatibility. |
| **C21** | Human-readable report — `graphify/report.py` | **KEEP** | Active | Graph and derived analysis → render overview, metrics, communities and warnings → Markdown report | Reframe and place the report under Bridger's graph artifact namespace. It remains a presentation and review artifact, not Repository Brain knowledge authority. | Retain report section and generation tests. Selective sync. | It provides inexpensive auditability and debugging value. |
| **C22** | Incremental update and watch runtime — `graphify/watch.py`, `build_merge`, manifest/update logic | **KEEP; WATCH OPTIONAL** | Incremental update active; continuous watch inactive by default | Previous graph/manifest plus changed/deleted files → re-extract affected files, remove prior contributions, merge, recompute derived outputs, republish | Expose explicit Bridger `full_build` and `incremental_build` functions. Retain Graphify's update algorithms, locks, pending-change handling and publication safety. Keep watch/Git-hook code available but outside V0 activation and qualification. | Retain changed/deleted-file, merge, pruning, locking, queue and atomic publication tests. Watch-specific qualification may be deferred. Close sync for incremental correctness; selective sync for watcher behavior. | Incremental updates are core to a living repository. A long-running filesystem watcher is useful but not necessary to ship V0. |
| **C23** | Query and context retrieval — `graphify/serve.py`, query commands in `cli.py` | **KEEP WITH APPLICATION BOUNDARY** | Active for internal navigation | Persisted graph plus query/traversal parameters → lexical/trigram ranking, paths, neighborhoods and token budgeting → bounded results/context | Reuse Graphify's search and traversal. Expose it through a Bridger query/navigation service that can read the deterministic graph and enrichment overlay together. Structured results are preferred at the Bridger boundary; text is a formatter. | Retain search, path, neighborhood, affected-node, ranking and budget tests. Selective-to-close sync. | Memory agents and later consumers require bounded graph navigation, and Graphify already provides useful primitives. |
| **C24** | MCP and agent adapters — MCP entrypoint, generated skills/templates | **DEFER / EXCLUDE FROM CORE V0** | Inactive | Graph/query runtime → expose Graphify-specific commands and workflows → MCP responses and skills | Treat as design reference. Later build a Bridger-owned MCP interface over the Bridger navigation and Repository Brain retrieval layers. | No V0 tests beyond C23 query behavior. No routine sync. | Existing adapters encode Graphify-specific paths and product semantics that Bridger will replace. |
| **C25** | Feedback/query memory — `graphify/reflect.py`, save-result workflows | **DEFER / EXCLUDE FROM V0** | Inactive | Query results, corrections and cited nodes → score useful/dead-end sources → learning sidecar | Retain the architectural pattern of a separate experiential overlay, but defer implementation until Bridger's memory and maintenance contracts are designed. | No V0 qualification requirement. No regular sync; revisit corroboration and decay logic later. | It is outside deterministic graph construction and overlaps with Bridger's future Repository Brain maintenance architecture. |

---

## 7. Fork ownership and upstream synchronization

### 7.1 Close synchronization

Regularly review upstream bug fixes and regression tests for:

```text
C04  Structural extraction facade
C05  Generic Tree-sitter kernel
C06  Language configuration
C07  Cross-file and symbol resolution
C08  Enabled language extractors
C12  Caching and portability
C13  Existing validation
C14  Graph construction and normalization
C15  Deduplication
C16  Communities and cohesion
C17  Structural analysis
C20  JSON serialization and safety
C22  Incremental-update correctness
```

### 7.2 Selective synchronization

Review and import only relevant fixes for:

```text
C01  CLI behavior
C02  Classification and security
C09  Individual ingestion families
C10  Document/rationale extraction
C18  Internal diagnostics
C19  Deterministic labeling
C21  Report generation
C23  Query and traversal
```

### 7.3 No active synchronization in V0

```text
C03  Media preprocessing
C11  Graphify semantic extraction
C24  Graphify MCP/skills
C25  Graphify feedback memory
```

---

# Part II — Canonical repository graph contract

## 8. Architectural boundary

Bridger treats Graphify as an internal, independent deterministic graph engine behind a Bridger-owned interface.

```text
Bridger GraphBuildRequest
        ↓
Graphify deterministic engine
        ↓
NetworkX DiGraph + Graphify artifacts
        ↓
Bridger GraphBuildResult + GraphSnapshotManifest
```

The internal extraction dictionaries and Graphify validation are implementation details. The persisted graph artifact and Bridger snapshot metadata form the externally supported V0 contract.

---

## 9. Bridger input contracts

### 9.1 `GraphBuildRequest`

A typed Bridger request should contain at least:

```text
repository_root
repository_revision
workspace_scope
build_mode: full
exclusion_rules
use_bridger_ignore
inventory_policy: git_tracked
runtime_graph_type: directed
cache_policy
output_root
build_configuration
```

Semantic extraction and model-assisted labeling are disabled in the deterministic build.

### 9.2 `GraphUpdateRequest`

```text
repository_root
previous_snapshot_id
previous_manifest_path
previous_graph_path
new_repository_revision
workspace_scope
changed_paths
deleted_paths
cache_policy
output_root
build_configuration
```

An update request is accepted only when the previous snapshot is compatible with the current graph contract, engine, scope, and inventory policy.

---

## 10. Bridger output contracts

### 10.1 `GraphBuildResult`

```text
snapshot_id
repository_revision
workspace_scope
build_mode: full | incremental | loaded
graph                       # in-memory NetworkX DiGraph
graph_artifact_path
manifest_path
analysis_path
labels_path
report_path
diagnostics_path
cache_statistics
changed_paths
deleted_paths
status
```

The returned in-memory graph and persisted graph artifact must represent the same successfully published snapshot.

### 10.2 `GraphSnapshotManifest`

```text
snapshot_id
repository_identity
repository_revision
workspace_scope
bridger_graph_contract_version
graphify_engine_version
extractor_version_or_fingerprint
inventory_policy_version
build_configuration_fingerprint
artifact paths and checksums
creation_timestamp
build_mode
parent_snapshot_id?
validation_status
diagnostics_summary
```

The manifest is the Bridger lifecycle and compatibility authority. It does not replace Graphify's internal manifest where the update engine relies on it; both may coexist, with the Bridger manifest referencing internal Graphify lifecycle artifacts.

---

## 11. Canonical runtime graph

### 11.1 Graph type

Bridger V0 uses:

```python
networkx.DiGraph
```

Direction is important for imports, calls, containment, inheritance, implementation, references, configuration links, and declared dependencies.

Community detection may derive an undirected projection internally without changing the canonical runtime graph.

### 11.2 No multigraph migration in V0

Bridger does not modify Graphify to emit `MultiDiGraph`.

Consequences are accepted and documented:

- Graphify's existing deduplication and overwrite/collapse behavior remains authoritative for V0.
- Multiple conceptual relations between the same source and target may not survive as independent native edge objects.
- A multigraph migration is considered only if evaluation shows material loss for repository navigation, enrichment, impact analysis, or memory generation.

---

## 12. Effective entity models

These are documented versions of Graphify's effective existing contracts. They are not an instruction to rewrite the engine using new classes.

### 12.1 Node

```text
Node
├── id: str
├── label: str
├── file_type: code | document | paper | image | rationale | concept
├── source_file: str
├── source_location?: str
├── language?: str
├── _origin?: ast | semantic
└── extractor-specific attributes
```

For Bridger's deterministic graph, semantic-origin records are disabled. `_origin` remains useful for compatibility and provenance.

### 12.2 Edge

```text
Edge
├── source: node id
├── target: node id
├── relation: str
├── confidence: EXTRACTED | INFERRED | AMBIGUOUS
├── source_file: str
├── source_location?: str
├── weight?: float
├── confidence_score?: float
├── _origin?: ast | semantic
└── relation-specific attributes
```

### 12.3 Hyperedge

```text
Hyperedge
├── id
├── relation/type
├── nodes: list[node id]
├── source_file
└── optional provenance/confidence metadata
```

Hyperedges remain graph-level metadata rather than native NetworkX edges. They are serializable and addressable but do not automatically participate in ordinary edge traversal or clustering.

### 12.4 Community

Graphify communities remain derived structures:

```text
Community
├── community_id
├── member_node_ids
├── cohesion_score
├── member_signature
├── deterministic_label?
└── clustering metadata supplied through snapshot/run context
```

Community identity is snapshot-relative. Community labels may be deterministic or AI-generated, but the two label sources remain distinct.

---

## 13. Stable identity policy

### 13.1 Node identity

Graphify IDs are derived from repository-relative source paths and entity identity.

V0 guarantees are deliberately limited:

```text
unchanged repository-relative path + unchanged extracted entity identity
    → expected stable node ID

moved/renamed file or renamed entity
    → old entity removed, new entity created
```

No general cross-revision rename/move reconciliation system is introduced in V0.

### 13.2 Edge identity for Bridger overlays

Graphify does not expose a universal first-class edge ID. Bridger therefore defines a snapshot-scoped `EdgeRef` at the interface/publication layer without changing the engine:

```text
EdgeRef
├── snapshot_id
├── source_node_id
├── target_node_id
├── relation
└── deterministic hash or opaque derived identifier
```

Because V0 uses a simple `DiGraph`, this reference identifies the final surviving serialized relation between the node pair.

### 13.3 Hyperedge identity

Use Graphify's existing hyperedge `id`, scoped by the graph snapshot.

### 13.4 Community identity

Use:

```text
snapshot_id + community_id + member_signature
```

The member signature protects against treating a reused or remapped numeric community ID as the same semantic grouping when its membership changed materially.

---

## 14. Provenance and confidence

### 14.1 Deterministic provenance

The graph retains Graphify fields such as:

- `source_file`;
- `source_location`;
- `_origin`;
- graph/build revision metadata;
- relation-specific extraction context;
- optional weights and confidence scores.

### 14.2 Structural confidence

Graphify's edge confidence values remain:

```text
EXTRACTED
INFERRED
AMBIGUOUS
```

These are categorical extraction/resolution states, not calibrated probabilities.

### 14.3 AI confidence

AI-generated confidence belongs only to the enrichment overlay. It must never overwrite Graphify's structural confidence.

---

## 15. Deterministic graph and AI enrichment overlay

### 15.1 Physical separation

```text
graph.json
    deterministic Graphify-derived graph
    deterministic communities and structural analysis

graph-enrichment.json
    AI names, scores, classifications, explanations and uncertainty
```

### 15.2 Enrichment target types

The overlay may target:

- nodes through `node_id`;
- edges through `EdgeRef`;
- hyperedges through `hyperedge_id`;
- communities through `community_id` plus `member_signature`;
- the whole graph through `snapshot_id`.

### 15.3 Enrichment record

```text
EnrichmentRecord
├── enrichment_id
├── graph_snapshot_id
├── target_type
├── target_ref
├── annotation_type
├── value / label / score / explanation
├── confidence
├── deterministic features used
├── model/provider metadata
├── prompt/policy version
├── generation timestamp
├── status: active | stale | superseded | rejected
└── optional reviewer/validation metadata
```

### 15.4 Superposable composite graph view

The deterministic graph and enrichment overlay must be navigable together without merging their authorities.

Bridger should expose a logical read model such as:

```text
CompositeGraphView
├── deterministic_graph
├── enrichment_overlay
├── snapshot_manifest
└── layer-aware query/navigation operations
```

Rules:

1. The deterministic graph remains unchanged and independently loadable.
2. Enrichment is joined at read time using stable target references.
3. A caller can request:
   - deterministic only;
   - enrichment only;
   - composite view.
4. Composite node, edge, hyperedge, and community results expose both deterministic attributes and enrichment annotations.
5. Every returned field retains layer provenance.
6. Enrichment cannot introduce or remove deterministic edges in the base graph.
7. Navigation can rank or filter using enrichment scores while traversing deterministic topology.
8. AI agents can inspect deterministic neighborhoods and AI labels/scores in one tool response.
9. An overlay may be composed only with the graph snapshot it targets, unless an explicit compatibility/rebase step validates all references.

Conceptually:

```text
Deterministic node/edge/community
            +
matching enrichment records
            ↓
Layer-aware composite entity view
```

This superposition model is crucial for later graph-navigation tools used by memory agents and Repository Brain generation.

---

# Part III — Graph lifecycle and persistence

## 16. Lifecycle states

A graph snapshot may be:

```text
building
validating
published
loaded
superseded
invalid
corrupt
```

Only an atomically published and validated snapshot may be consumed as the current deterministic graph.

---

## 17. Full build lifecycle

```text
1. Resolve repository identity, revision and workspace scope
2. Build Git-tracked Bridger inventory
3. Apply Bridger exclusions and Graphify classification/security checks
4. Run Graphify structural extraction
5. Run repository-wide resolution
6. Validate Graphify internal extraction records
7. Build the NetworkX DiGraph
8. Compute communities and cohesion
9. Run structural analysis and diagnostics
10. Serialize Graphify graph and derived artifacts
11. Write Bridger snapshot manifest and checksums
12. Validate cross-artifact consistency
13. Atomically publish the snapshot
14. Return the in-memory graph and artifact references
```

Graphify semantic extraction and model-assisted labeling are disabled during this lifecycle.

---

## 18. Loading without rebuilding

Bridger may load the persisted graph instead of rebuilding when all of the following match:

- repository identity;
- repository revision;
- workspace scope;
- Bridger graph-contract compatibility;
- Graphify engine/extractor compatibility;
- inventory and exclusion policy;
- build-configuration fingerprint;
- required artifact presence;
- artifact checksums;
- successful prior validation status.

The load path reconstructs the NetworkX graph using Graphify's supported persisted graph format and returns a `GraphBuildResult` with `build_mode = loaded`.

---

## 19. Explicit incremental update lifecycle

Continuous watch mode is not active in Bridger V0. Updates are triggered through a function or method interface.

```text
1. Receive previous snapshot and new repository revision
2. Verify snapshot compatibility
3. Resolve changed, new and deleted Git-tracked paths
4. Re-extract changed/new files
5. Remove graph contributions from changed/deleted files
6. Preserve compatible unchanged extraction data
7. Merge new extraction fragments using Graphify's update logic
8. Rebuild/normalize the complete graph
9. Recompute communities, analysis, labels and diagnostics
10. Serialize a new complete graph artifact set
11. Write a new Bridger snapshot manifest referencing the parent snapshot
12. Validate and atomically publish
13. Return the new graph in memory
```

Incremental update is an optimization. The published output is still a complete graph snapshot.

---

## 20. Invalidation and rebuild policy

### 20.1 No rebuild required

Load the existing snapshot when:

- repository revision is unchanged;
- workspace scope is unchanged;
- engine, extractor, schema, inventory policy and build configuration remain compatible;
- persisted artifacts and checksums are valid.

### 20.2 Incremental update allowed

Use incremental update when:

- repository revision changed;
- exact changed/new/deleted paths are known;
- previous graph and lifecycle artifacts are valid;
- workspace scope is unchanged;
- inventory policy and global extraction configuration are unchanged;
- schema and engine versions remain incrementally compatible.

### 20.3 Full rebuild required

Run a full build when:

- there is no valid previous graph;
- graph, manifest, cache baseline or required derived artifact is missing/corrupt;
- the Bridger graph-contract major version changes;
- the Graphify engine/extractor change is incompatible;
- repository workspace scope changes;
- inventory or exclusion semantics materially change;
- global extractor configuration changes;
- the incremental update fails validation;
- shrink or consistency guards reject the update;
- path normalization or identity policy changes;
- previous graph provenance is incomplete or unreliable.

---

## 21. Stable identity during updates

1. Unchanged files and unchanged extracted entities should preserve Graphify node IDs.
2. Changed files are re-extracted and replace their prior producer contributions.
3. Deleted files remove their graph contributions.
4. File moves and symbol renames are represented as deletion plus creation in V0.
5. Community IDs may be overlap-remapped by Graphify, but community continuity is validated using member signatures.
6. Enrichment annotations targeting removed or changed entities become stale until revalidated or regenerated.
7. No AI process may rewrite deterministic entity IDs to preserve semantic continuity.

---

## 22. Persistence layout

The exact internal filenames may remain close to Graphify to reduce unnecessary modifications. The conceptual Bridger layout is:

```text
.bridger/
└── graph/
    ├── snapshots/
    │   └── <snapshot-id>/
    │       ├── graph.json
    │       ├── graphify-manifest.json
    │       ├── snapshot-manifest.json
    │       ├── analysis.json
    │       ├── deterministic-labels.json
    │       ├── diagnostics.json
    │       ├── GRAPH_REPORT.md
    │       └── enrichment/
    │           └── graph-enrichment.json
    ├── cache/
    │   ├── ast/
    │   ├── semantic/          # inactive while C11 is disabled
    │   └── stat-index.json
    └── current                # pointer/reference to the published snapshot
```

A flatter layout may be used initially if Graphify's implementation strongly prefers it. The required architectural separation is:

- deterministic graph artifacts;
- Graphify operational state and caches;
- Bridger snapshot metadata;
- AI enrichment overlay;
- transient run files.

---

## 23. Persisted artifacts

Persist at minimum:

- final `graph.json`;
- Graphify lifecycle manifest required for updates;
- Bridger `GraphSnapshotManifest`;
- repository revision and workspace scope;
- engine, extractor, contract and inventory-policy versions;
- build-configuration fingerprint;
- checksums;
- communities, cohesion and structural analysis required for reload/navigation;
- deterministic community labels;
- diagnostics;
- human-readable graph report;
- AST cache and stat index;
- AI enrichment overlay as a separate artifact.

Transient combined extraction and chunk files remain implementation details and are not part of Bridger's public graph contract.

---

## 24. In-memory handoff

A successful full build, incremental update, or load returns the graph in memory in addition to persisted paths.

Primary downstream uses include:

- AI community naming;
- node, edge, community and god-node scoring;
- structural navigation tools;
- Repository Brain memory-agent tasks;
- retrieval and impact analysis;
- diagnostic and evaluation workflows.

The in-memory graph is not a separate authority. It is the runtime representation of the published deterministic snapshot.

---

## 25. Enrichment lifecycle

### 25.1 Initial enrichment

```text
Published deterministic graph snapshot
        ↓
AI enrichment pass
        ↓
Validate target references and metadata
        ↓
Publish graph-enrichment.json for that snapshot
        ↓
Expose deterministic, enrichment, or composite graph views
```

### 25.2 After graph update

When a new deterministic snapshot is published:

1. the previous overlay remains associated with the previous snapshot;
2. annotations targeting removed entities are stale for the new snapshot;
3. annotations targeting apparently unchanged entities may be copied only through an explicit validated rebase process;
4. affected annotations are regenerated or revalidated;
5. the deterministic graph can be consumed before enrichment completes;
6. composite navigation for the new snapshot uses only compatible active annotations.

### 25.3 Rollback

Because enrichment is a sidecar, it can be rejected, superseded, regenerated, or rolled back without changing the deterministic graph.

---

## 26. Versioning and compatibility

### 26.1 Required versions

Each snapshot records:

```text
bridger_graph_contract_version
graphify_engine_version
extractor/cache version or fingerprint
inventory_policy_version
build_configuration_fingerprint
enrichment_schema_version
```

### 26.2 Compatibility policy

- **Major graph-contract change:** persisted snapshot is incompatible; full rebuild required.
- **Minor additive change:** old graph remains readable; absent fields use defined defaults or adapters.
- **Patch change:** no schema or compatibility impact.
- **Incompatible Graphify extractor change:** affected caches and graph artifacts are rebuilt according to Graphify invalidation rules.
- **Enrichment schema change:** does not invalidate the deterministic graph; only the overlay requires migration or regeneration.

### 26.3 Snapshot immutability

Published snapshots are immutable. Full and incremental builds create a new snapshot and atomically move the current pointer only after validation succeeds.

---

## 27. Concurrency and publication safety

1. Only one full or incremental writer may operate on the same repository scope at a time.
2. Graphify locking and pending-change mechanisms may be retained even though continuous watch is disabled.
3. Consumers continue reading the previous published snapshot while a new one is building.
4. Graph artifacts, manifest, diagnostics and checksums are validated before publication.
5. A failed build or update never replaces the current valid snapshot.
6. Shrink guards and consistency checks remain active.

---

## 28. V0 non-goals

Bridger V0 does not require:

- replacing Graphify's internal dictionaries with Pydantic;
- implementing a new graph construction engine;
- migrating to `MultiDiGraph`;
- general cross-revision rename/move identity reconciliation;
- enabling Graphify semantic extraction;
- running a continuous filesystem watcher;
- importing Graphify's MCP and generated agent skills;
- importing Graphify's feedback/query memory system;
- graph-database persistence as the canonical store.

---

## 29. Final architecture

```text
Git-aware Bridger repository inventory
        ↓
Graphify classification and deterministic extraction
        ↓
Graphify cross-file resolution and validation
        ↓
Graphify NetworkX DiGraph construction
        ↓
Graphify communities, analysis and diagnostics
        ↓
Graphify JSON serialization and incremental lifecycle state
        ↓
Bridger GraphSnapshotManifest and atomic publication
        ↓
Separate Bridger AI enrichment overlay
        ↓
Layer-aware CompositeGraphView
        ↓
AI graph navigation, memory agents and Repository Brain generation
```

This architecture preserves Graphify's working engine, minimizes initial implementation risk, protects deterministic authority, supports explicit incremental updates, avoids unnecessary rebuilds, and gives downstream AI systems a unified navigable view over deterministic topology and AI interpretation.
