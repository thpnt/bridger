# Graphify Consolidated Component, Contract, and Code Map

**Purpose:** Selection baseline for Bridger's Graphify adoption strategy and canonical repository graph contract.  
**Graphify repository:** `Graphify-Labs/graphify`  
**Branch:** `v8`  
**Revision verified:** `00efd6e7969837ae4a9f11d8d504dcd3b20b09df`  
**Status:** Mapping only. No keep / adapt / replace / exclude decisions are made here.

## 1. Task alignment

This mapping supports the following task sequence:

1. **Define the Graphify adoption strategy** — identify relevant and excluded components; decide ownership, fork maintenance, and upstream synchronization.
2. **Design the canonical repository graph contract** — define node, edge, community, and hyperedge models; directionality, multiedges, identity, provenance, confidence, and deterministic/enrichment separation.
3. **Design the graph lifecycle and persistence model** — use the same map later to define builds, updates, invalidation, versioning, and incremental rebuilds.

The report therefore exposes Graphify as selectable **component units**, not only as an end-to-end product.

## 2. Verified Graphify pipeline

```text
Run configuration
    ↓
Corpus detection and classification
    ↓
Optional conversion / transcription
    ↓
┌───────────────────────────────┬──────────────────────────────┐
│ Deterministic extraction      │ Semantic extraction          │
│ per-file AST + resolution     │ docs / papers / images / AI  │
└───────────────────────────────┴──────────────────────────────┘
    ↓ combined ExtractionResult
Normalization + validation + identity reconciliation
    ↓
NetworkX Graph or DiGraph
    ↓
Communities + cohesion
    ↓
Structural analysis + diagnostics
    ↓
Deterministic or model-assisted labels
    ↓
Graph JSON + report + visual/export formats
    ↓
Query / MCP / feedback-memory consumers
```

Cross-cutting lifecycle state:

```text
AST cache + semantic cache + stat index + manifest
                         ↓
          incremental detection / tier-aware merge
                         ↓
              rebuild derived outputs
```

## 3. Object lineage

Graphify has a small number of actual typed internal models; most pipeline records are dictionaries with effective rather than formal schemas.

| Object | Runtime shape | Producer | Main consumers | Persistence | Authority / caveat |
|---|---|---|---|---|---|
| `RunConfiguration` | Loose CLI/env/runtime values | `cli.py`, skills, entrypoints | Entire pipeline | Mostly memory; some marker/config files | Not a formal model |
| `DetectionResult` | `dict` | `detect.py` | Extraction, reporting, manifest/update logic | `.graphify_detect.json`; selected data in `manifest.json` | Filesystem corpus classification, not Git truth |
| `TranscriptRecord` / converted document | Files + loose metadata | `transcribe.py`, Google Workspace conversion | Semantic extraction | Transcript/conversion sidecars | Optional preprocessing output |
| `LanguageConfig` | Actual dataclass | `extractors/models.py`; instances largely configured from `extract.py` | Generic Tree-sitter engine | Memory | Reusable parser configuration contract |
| `_Symbol*Fact` records | Actual internal dataclasses | Extractor collection passes | Cross-file symbol resolution | Memory inside extraction | Internal contracts; underscore-prefixed and not public APIs |
| Per-file `ExtractionResult` | `dict` of buckets | Language extractor or semantic extractor | Cache, merge, build | Per-file AST/semantic cache JSON | Shared loose IR |
| Combined `ExtractionResult` | `dict` | Extraction/orchestration merge | `validate.py`, `build.py` | Usually `.graphify_extract.json` transiently | Contains deterministic and semantic records together |
| `NodeRecord` | `dict` | AST or semantic extractor | Graph builder, cache, exporters | Cache, transient extraction, `graph.json` | Required fields are minimal; many attributes optional |
| `EdgeRecord` | `dict` | AST/resolution or semantic extractor | Graph builder, analysis, query | Same as nodes | Typed relation plus confidence, but not a typed model |
| `HyperedgeRecord` | `dict` | Extractors | Build/export/query consumers | Extraction JSON; graph metadata; `graph.json` | Stored as graph-level metadata, not native NetworkX hyperedges |
| `RawCallRecord` | `dict` | AST extractors | Resolution passes | Cache and aggregate extraction | Intermediate only; not a published graph object |
| Auxiliary resolution facts | Dataclasses, tuples, maps, language-specific buckets | AST walkers | Repository-wide resolution passes | Mostly memory; some remain in cache fragments | Closely coupled to extractor implementation |
| Active graph | `nx.Graph` or `nx.DiGraph` | `build_from_json()` | Clustering, analysis, report, export, query | Memory | Default is not a multigraph |
| `CommunityMap` | `dict[int, list[str]]` | `cluster()` | Cohesion, labeling, report, export | Memory; embedded on nodes during export | Derived partition, not canonical entity meaning |
| `CohesionMap` | `dict[int, float]` | `score_all()` | Diagnostics/report | Memory/report | Derived metric |
| `AnalysisBundle` | Loose lists/dicts | `analyze.py` helpers | Report/visualization | Optional `.graphify_analysis.json`; report | Architectural name, not a class |
| Diagnostics | Loose lists/dicts | `diagnostics.py` and pipeline checks | CLI/report/publication guards | Logs/report/selected state | No single canonical diagnostics schema |
| `CommunityLabels` | `dict[int, str]` | deterministic hub labeling or model workflow | Report/export/query | `.graphify_labels.json`; exported fields | Can be deterministic or AI-produced |
| `GraphDocument` | NetworkX node-link JSON + Graphify fields | `export.to_json()` | Update, query, MCP, integrations | `graphify-out/graph.json` | Main machine-readable Graphify artifact |
| `GraphReport` | Markdown string | `report.generate()` | Humans/agent workflows | `GRAPH_REPORT.md` | Presentation, not graph authority |
| `Manifest` | `dict` | detection/finalization/update flow | Incremental comparison and rebuilds | `graphify-out/manifest.json` | Operational lifecycle baseline |
| AST cache entry | Per-file extraction JSON | `cache.save_cached()` | Later deterministic extraction | `cache/ast/v<version>/<hash>.json` | Extractor-version namespaced |
| Semantic cache entry | Per-file extraction JSON | Semantic extraction | Later semantic merge | `cache/semantic*/p<prompt-fp>/<hash>.json` | Prompt-fingerprinted; partial results normally rejected |
| Stat index | `dict[path, stat/hash data]` | `cache.py` | Detection/cache hashing | Memory + `cache/stat-index.json` | Fast path, not extraction truth |
| Query context/result | NetworkX graph, search index, selected subgraph/text | `serve.py`, `cli.py` | Human/agent queries | Usually memory; bounded textual output | Downstream retrieval object, not build contract |
| Learning overlay | Sidecar records | `reflect.py` / save-result workflow | Query display/reflection | Sidecar near graph | Episodic feedback; separate from graph facts |

## 4. Effective graph-record contracts

### 4.1 Node

```text
NodeRecord
├── id: str
├── label: str
├── file_type: code | document | paper | image | rationale | concept
├── source_file: str
├── source_location?: str
├── language?: str
├── _origin?: ast | semantic
└── extractor/semantic-specific attributes
```

Key behavior:

- Deterministic IDs are derived from the full repository-relative source path plus entity identity.
- Non-AST IDs are re-derived from `source_file` during build rather than trusted blindly.
- Legacy IDs are recognized and remapped where possible.
- Exact same-ID insertion is last-writer-wins at NetworkX insertion time.
- A later ghost-merge pass favors an AST-origin node over a non-AST node with the same normalized source file and label when the match is unambiguous.
- ID slug collisions and same-label ambiguity require explicit disambiguation logic; the current identity scheme is not yet a complete cross-revision identity contract.

### 4.2 Edge

```text
EdgeRecord
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

Key behavior:

- Legacy aliases are repaired (`type → relation`, `from/to → source/target`).
- Dangling external/stdlib targets are tolerated and omitted during graph assembly.
- Cross-language phantom imports/references and inferred calls are filtered conservatively.
- In the default undirected graph, the true source and target are stored temporarily as `_src` / `_tgt` and restored in JSON export.
- Exact parallel edges are commonly collapsed by simple Graph/DiGraph storage or by `(source, target, relation)` deduplication.

### 4.3 Hyperedge

```text
HyperedgeRecord
├── id
├── relation/type
├── nodes: list[node id]
├── source_file
└── optional provenance/confidence metadata
```

Aliases such as `members` and `node_ids` are normalized to `nodes`. Hyperedges are attached to `G.graph["hyperedges"]` and serialized separately; they do not participate as first-class NetworkX edges in ordinary traversal or clustering.

### 4.4 Community

Graphify does not produce a formal community entity model.

```text
CommunityMap: dict[community_id, list[node_id]]
CohesionMap: dict[community_id, float]
CommunityLabels: dict[community_id, str]
Member signatures: dict[community_id, hash]
```

Community IDs are deterministically reindexed for a fixed grouping, and update flows can remap new communities to previous IDs by overlap. Community meaning remains derived and labels may be AI-generated.

## 5. Component-to-code map

The following rows are the units on which an adoption decision can be made.

| ID | Component / features | Primary code | Input | Transform | Output / persistence | Coupling and selection notes |
|---|---|---|---|---|---|---|
| C01 | CLI and run dispatch | `graphify/cli.py`, `graphify/__main__.py`, `graphify/skill.md`, `graphify/paths.py` | User args, env, repo path | Resolve modes, paths, options; orchestrate stages | Runtime config; temporary workflow files | Product-specific shell around the library; separable from extraction logic |
| C02 | Corpus discovery and classification | `graphify/detect.py`, `graphify/security.py`, `graphify/google_workspace.py` | Filesystem root, ignore/security rules | Walk, classify, count, exclude, detect changes | `DetectionResult`, manifest/stat data | Broad and mature corpus classifier; inventory semantics do not match Bridger's Git-aware contract |
| C03 | Media/document preprocessing | `graphify/transcribe.py`, Google Workspace conversion helpers | Audio/video/office/cloud docs | Convert/transcribe to supported text | Sidecars and generated text paths | Optional mixed-media feature; separable from code graph core |
| C04 | Structural extraction facade and dispatch | `graphify/extract.py` | Detected code/config paths, root, cache | Dispatch extractors, stamp origin, aggregate results, run repository-wide passes | Per-file and combined `ExtractionResult` | Still a large compatibility facade and orchestration center, not a thin module |
| C05 | Generic Tree-sitter extractor kernel | `graphify/extractors/models.py`, `base.py`, `engine.py` | File bytes + `LanguageConfig` | Parse AST; walk declarations, calls, imports, types; emit file/symbol facts | Nodes, edges, raw facts | Strong reusable kernel, but config-driven languages remain coupled to `extract.py` during the ongoing migration |
| C06 | Language configuration layer | `LanguageConfig` in `extractors/models.py`; configurations and dispatch largely in `extract.py` | Grammar module and per-language rules | Parameterize generic AST walker | Configured extraction behavior | Actual dataclass; useful boundary, but current registry/config ownership is split |
| C07 | Cross-file and symbol resolution | `extractors/resolution.py`, `resolver_registry.py`, `symbol_resolution.py`, `ruby_resolution.py`, `pascal_resolution.py`, language modules such as `extractors/csharp.py` | Per-file nodes/edges + symbol facts + repo layout | Resolve imports, exports, calls, inheritance, types, aliases, workspaces | Rewritten/augmented extraction edges | High-value but high-maintenance; many language-specific heuristics and shared state |
| C08 | Dedicated language extractors | `graphify/extractors/*.py` | One language/config file | Language-specific parsing and facts | Per-file extraction fragments | Selectable per language; migrated and non-migrated extractors have different coupling levels |
| C09 | Manifest, project, and tool-config ingestion | `manifest_ingest.py`, `mcp_ingest.py`, `scip_ingest.py`, relevant config extractors | Manifest/config/index files | Extract declared packages, scripts, entrypoints, MCP/SCIP relations | Nodes/edges | Deterministic declared facts; separable by input family |
| C10 | Rationale and document quick-scan extraction | `extractors/markdown.py`, rationale/comment logic in generic/language extractors | Markdown, docstrings, marked comments | Emit document/rationale nodes and relations | Structural extraction fragments | Bridges source mechanics and design intent; must be authority-classified explicitly |
| C11 | Semantic/AI extraction | `graphify/llm.py`, `semantic_cleanup.py`, skill extraction specifications | Non-code corpus, prompt, provider/model | Chunk, infer concepts/relations, normalize output | Semantic `ExtractionResult`; semantic cache | Non-deterministic producer; currently shares the same loose IR and final graph |
| C12 | Per-file caching and portability | `graphify/cache.py` | File content/path, prompt, extractor version | Hash, load/save, relativize/re-anchor, atomic replace | AST cache, semantic cache, stat index | Strong independent infrastructure; cache invalidation differs by producer tier |
| C13 | Schema validation | `graphify/validate.py` | Combined extraction dict | Validate minimal required fields/enums/endpoints | Error list or exception | Useful validation gate, but intentionally permissive and too weak to be Bridger's canonical schema |
| C14 | Normalization, identity repair, graph construction | `graphify/build.py`, `ids.py`, `paths.py` | Combined extraction + root + directed flag | Alias repair, ID coercion/rekey, ghost merge, edge filtering, NetworkX construction | `nx.Graph` / `nx.DiGraph` | Central high-value module; also contains compatibility and lifecycle logic, so adoption cannot be treated as a trivial serializer |
| C15 | Entity deduplication | `graphify/dedup.py`, build-time exact/ghost dedup | Node/edge lists, optional communities | Exact-ID and fuzzy label/entity merge, edge rewiring | Deduplicated nodes/edges | Code nodes are protected from fuzzy label merging; semantic dedup is a distinct optional decision |
| C16 | Community detection and cohesion | `graphify/cluster.py` | Graph + resolution/hub options | Leiden or Louvain, isolate handling, hub exclusion, community splitting, stable reindexing | `CommunityMap`, `CohesionMap`, member signatures | Derived analysis; converts directed graph to undirected projection internally |
| C17 | Structural analysis | `graphify/analyze.py` | Graph + communities | God nodes, surprising links, suggested questions, topology heuristics | Analysis lists/dicts | Useful derived features; heuristics depend on Graphify's node/edge semantics |
| C18 | Diagnostics and health checks | `graphify/diagnostics.py`, checks spread across build/export/watch | Detection, extraction, graph, previous output | Detect missing/dangling/collapsed/shrunk/suspicious output | Warnings/health summaries | Important behavior but not consolidated behind one typed diagnostics contract |
| C19 | Community labeling | `cluster.label_communities_by_hub`, model-assisted skill/LLM path | Communities + graph context | Deterministic hub name or AI naming | `CommunityLabels` | Deterministic and AI modes must be separated in Bridger ownership |
| C20 | Graph serialization and external exports | `graphify/export.py`, `graphify/exporters/base.py`, `html.py`, `graphdb.py` | Graph, communities, labels | Node-link JSON; HTML/GraphML/SVG/Obsidian/Cypher; Neo4j/FalkorDB push | `graph.json`, visual/export artifacts | JSON writer includes safety guards, atomic write, communities, hyperedges, commit metadata |
| C21 | Human-readable report | `graphify/report.py` | Graph and derived analysis | Render Markdown | `GRAPH_REPORT.md` | Presentation only; not a canonical graph contract |
| C22 | Incremental update and watch runtime | `graphify/watch.py`, `build.build_merge`, detection manifest logic, `cache.py` | Previous graph/manifest + changed/deleted files | Detect, re-extract, producer-tier replace, prune deletes, preserve unchanged data, rebuild derivatives | Republished graph/report/manifest | Strong lifecycle pattern; mixed with Graphify-specific markers, locks, hooks, and output layout |
| C23 | Query and context retrieval | `graphify/serve.py`, query commands in `cli.py` | `graph.json` + user query | Lexical/trigram candidate generation, deterministic scoring, BFS/DFS/path/neighborhood traversal, token budgeting | Bounded graph context text | Downstream consumer of the graph; largely separable from graph production |
| C24 | MCP and agent adapters | `serve.py`, MCP entrypoint, generated `skills/*`, `skill-*.md` | Graph/query runtime | Expose query functions and workflows to agents | MCP responses / skill workflows | Product/adaptor layer; generated skill files should not be treated as core graph code |
| C25 | Feedback/query memory | `graphify/reflect.py`, save-result/reflect workflows | Query results, corrections, cited nodes | Store learning/dead-end/preference overlays | Sidecar learning overlay | Episodic knowledge; intentionally separate from graph facts and should remain so |

## 6. Extractor package decomposition

The extraction code is mid-migration. `graphify/extractors/MIGRATION.md` explicitly preserves `extract.py` as a compatibility facade while modules move out.

### 6.1 Shared extraction core

```text
graphify/extract.py                 dispatch, configs, aggregation, global passes
graphify/extractors/models.py       LanguageConfig + symbol-resolution fact models
graphify/extractors/base.py         shared low-level helpers
graphify/extractors/engine.py       generic AST walking and relation extraction
graphify/extractors/resolution.py   shared cross-file resolution
graphify/resolver_registry.py       pluggable resolver registration/execution
```

### 6.2 Language-specific support modules

Current extractor family includes modules for:

```text
apex, bash, blade, csharp, dart, dm, elixir, fortran, go,
json_config, julia, markdown, objc, pascal, pascal_forms,
powershell, razor, rust, sln, sql, terraform, verilog, zig
```

Config-driven languages still substantially depend on the shared generic core and `extract.py`, including Python, JS/TS and framework script blocks, Java/JVM languages, C/C++, Ruby, C#, Kotlin, Scala, PHP, Lua, Swift, Groovy, Vue, Svelte, Astro, and XAML.

**Selection implication:** choosing “the extractors” is not one binary decision. The practical units are:

1. generic kernel;
2. language configuration/registry;
3. cross-file resolution framework;
4. individual bespoke extractors;
5. individual language-resolution extensions;
6. facade/orchestration compatibility layer.

## 7. Dataflow by stage and persistence

| Stage | Input contract | Output contract | In-memory | Transient disk | Durable disk |
|---|---|---|---:|---:|---:|
| Detect | Root + policies | `DetectionResult` | Yes | `.graphify_detect.json` | `manifest.json`, stat index subset |
| Preprocess | Media/office inputs | Generated text/records | Yes | Workflow-specific | Transcript/conversion sidecars |
| AST extract | Code path + root + cache/config | Per-file `ExtractionResult` | Yes | `.graphify_ast.json` aggregate | AST cache entry |
| Semantic extract | Document path + prompt/model | Per-file semantic `ExtractionResult` | Yes | chunks / `.graphify_semantic*.json` | Semantic cache entry |
| Merge | Fresh/cached fragments | Combined `ExtractionResult` | Yes | `.graphify_extract.json` | No canonical merged IR artifact |
| Validate/build | Combined extraction | Graph/DiGraph | Yes | No | Later `graph.json` |
| Cluster | Graph | communities/cohesion | Yes | Optional analysis state | Embedded community fields/labels |
| Analyze | Graph + communities | analysis/diagnostics | Yes | `.graphify_analysis.json` optional | Report content |
| Label | Graph + communities | label map | Yes | No | `.graphify_labels.json`, exports |
| Publish | Graph + derivatives | graph/report/visuals | Yes | Atomic temp files | `graph.json`, report, HTML, exports |
| Query | `graph.json` | selected bounded context | Yes | No | Optional query-memory overlay |
| Update | Previous graph/manifest + changes | New full artifact set | Yes | incremental/old/new fragment files | Replaces published outputs and state |

## 8. Graphify features and their producing components

| Feature | Producing components | Graph dependency |
|---|---|---|
| File, symbol, import, call, type, inheritance, implementation, reference graph | C04–C10 | Core graph facts |
| JS/TS aliases, workspaces, exports/re-exports | C05–C09 | Cross-file resolution |
| Python nested `src/` package repair | C04/C07/C14 | Identity/edge resolution |
| Receiver-aware member call resolution | C05/C07 + language modules | Inferred/extracted call edges |
| Rationale/docstring/comment nodes | C10 | Structural/derived content nodes |
| Semantic concepts and similarity relations | C11 | Semantic tier merged into graph |
| AST/semantic duplicate reconciliation | C14/C15 | Build normalization |
| Communities and cohesion | C16 | Derived from graph topology |
| God nodes and surprising connections | C17 | Derived from graph + communities |
| Community names | C19 | Derived label layer |
| JSON/HTML/GraphML/SVG/Obsidian/Cypher/graph DB export | C20 | Publication/adapters |
| Query, path, explain, affected, god-node commands | C23 | Read-side graph traversal |
| MCP access and multi-project LRU contexts | C23/C24 | Query service |
| Producer-tier incremental replacement | C12/C22 | Lifecycle |
| Query-result corrections and preferred/dead-end sources | C25 | Separate learning overlay |

## 9. Contract facts that directly constrain Bridger Task 2

These are current Graphify behaviors, not recommendations:

| Concern | Graphify as implemented |
|---|---|
| Canonical runtime graph | `nx.Graph` by default; optional `nx.DiGraph` |
| Multiedges | Builder does not produce `MultiGraph`; parallel edges can collapse. Helpers tolerate externally supplied multigraphs |
| Direction | Native in `DiGraph`; otherwise side-channel `_src/_tgt` restored at export |
| Node identity | Path-derived slug + entity; code-side semantic rekey; legacy aliases and collision repair |
| Cross-revision identity | No complete stable entity continuity contract; community overlap remapping exists |
| Provenance | `source_file`, `source_location`, `_origin`, relation confidence; inconsistent optional metadata across producers |
| Confidence | Edge enum `EXTRACTED/INFERRED/AMBIGUOUS`; optional numeric score; no unified node/community confidence model |
| Hyperedges | Loose records stored in graph metadata, outside ordinary traversal |
| Communities | Derived mapping; exported as node attributes; labels may be deterministic or AI |
| Deterministic vs AI data | Producer tiers exist and incremental merge respects them, but both tiers are merged into one published graph |
| Validation | Minimal dictionary validation plus extensive build-time repair/warnings |
| Schema/version metadata | Partial and operational; not a Bridger-grade versioned graph schema |

## 10. Coupling hotspots

These boundaries matter when deciding whether to reuse files directly, fork them, or extract smaller libraries.

1. **`extract.py` remains a large compatibility facade.** Generic configs, dispatch, repository-wide passes, and re-exports coexist. Copying only `extractors/` will not reproduce the pipeline.
2. **`build.py` is more than graph assembly.** It owns schema repair, legacy compatibility, identity migration, AST/semantic reconciliation, edge filtering, direction preservation, and incremental merge support.
3. **Resolution is distributed.** Shared logic lives in `extractors/resolution.py`, while language modules and separate resolver modules carry special cases.
4. **Diagnostics are distributed.** Health and safety checks appear in detection, build, export, watch, and dedicated diagnostics code.
5. **Semantic and deterministic producers share the extraction envelope.** `_origin` and tier-aware merge preserve producer identity, but the final graph still combines them.
6. **Graph analysis assumes Graphify's noise model.** God-node and surprising-connection logic filters file nodes, concepts, builtins, JSON keys, language-family pollution, and other Graphify-specific artifacts.
7. **Publication is coupled to lifecycle safety.** `export.py` handles backups, shrink protection, community embedding, direction restoration, commit stamping, hyperedges, and atomic writes.
8. **Generated skills are adapters, not source-of-truth implementation.** The code and shared skill templates should be distinguished from generated per-host copies.

## 11. Decision worksheet for the next tasks

Use one row per component ID from Section 5.

| Component ID | Decision: keep / adapt / replace / exclude | Bridger owner | Upstream code retained? | Contract boundary to expose | Tests to retain/import | Upstream sync policy | Rationale |
|---|---|---|---|---|---|---|---|
| `Cxx` |  |  |  |  |  |  |  |

For Task 2, use one row per graph object:

| Object | Bridger canonical model? | Graphify source fields retained | Fields added/changed | Deterministic or overlay layer | Identity/version policy | Migration adapter required |
|---|---|---|---|---|---|---|
| Node |  |  |  |  |  |  |
| Edge |  |  |  |  |  |  |
| Hyperedge |  |  |  |  |  |  |
| Community |  |  |  |  |  |  |
| Graph artifact |  |  |  |  |  |  |

## 12. Selection baseline

The component map reduces Graphify to five independent decision domains:

```text
A. Repository intake
   C01–C03

B. Deterministic fact extraction
   C04–C10

C. Shared graph contract and construction
   C12–C15

D. Derived structural intelligence
   C16–C19

E. Publication, lifecycle, and consumers
   C20–C25
```

The highest-coupling boundary is **C04–C07 + C14**: extraction dispatch, generic parsing, cross-file resolution, and graph construction have evolved together and share identity/resolution assumptions. Any selective adoption strategy must explicitly define adapters between these modules rather than assuming their current loose dictionaries are stable public APIs.

---

## Verification basis

- Existing Graphify pipeline/data-contract analysis supplied for this work.
- Existing repository-discovery analysis supplied in the request.
- Direct GitHub verification against the `v8` default branch at revision `00efd6e7969837ae4a9f11d8d504dcd3b20b09df`.
- Key code inspected: `detect.py`, `extract.py`, `extractors/models.py`, `extractors/MIGRATION.md`, `build.py`, `validate.py`, `cache.py`, `cluster.py`, `analyze.py`, `export.py`, `watch.py`, `serve.py`, and relevant extractor/search results.
