# Graphify Repository-Analysis Pipeline Mapping

**Repository:** `Graphify-Labs/graphify`  
**Branch analyzed:** `v8`  
**Revision analyzed:** `00efd6e7969837ae4a9f11d8d504dcd3b20b09df`  
**Document purpose:** Preserve the detailed architectural analysis of Graphify’s repository-processing pipeline, its data contracts, transformations, persistence model, cache design, and lifecycle boundaries for use in subsequent Bridger architecture tasks.

---

## 1. Scope and interpretation

This document maps Graphify as an analysis pipeline rather than as a collection of individual Python functions.

For each stage, it identifies:

- the input object, data model, or operational state;
- the transformation performed;
- the output object or contract;
- where the output is held or persisted;
- whether the stage is deterministic;
- the main downstream consumers.

The mapping distinguishes between:

1. **Canonical public artifacts**  
   Outputs intended to survive a run and be consumed by users or later tools.

2. **Operational persistent state**  
   Files that survive across runs to support caching, updates, portability, or bookkeeping.

3. **Transient orchestration artifacts**  
   Intermediate JSON files used by the host-agent workflow or incremental pipeline.

4. **In-memory state**  
   Python dictionaries, NetworkX graphs, strings, and collections that normally disappear when the process exits.

Graphify does not define most contracts as formal dataclasses or schema-generated models. Most stage boundaries are represented by Python dictionaries, lists of dictionaries, NetworkX graph objects, and JSON files. Therefore, the “contracts” below describe the effective runtime and serialized contracts rather than a strongly typed public API.

---

## 2. End-to-end pipeline

Graphify’s conceptual pipeline is:

```text
Repository or document corpus
        │
        ▼
1. Detect and classify files
        │
        ▼
2. Optionally transcribe or convert unsupported inputs
        │
        ▼
3. Extract structural and semantic entities
        │
        ▼
4. Merge and validate extraction records
        │
        ▼
5. Build the graph
        │
        ▼
6. Cluster and score graph communities
        │
        ▼
7. Analyze graph structure and anomalies
        │
        ▼
8. Generate community labels
        │
        ▼
9. Generate reports
        │
        ▼
10. Export graph artifacts
        │
        ▼
11. Persist run state, cache entries, and manifests
```

The simplified code-oriented form is:

```text
detect()
  → extract()
  → build_from_json()
  → cluster()
  → score_all()
  → analyze helpers
  → report.generate()
  → export functions
```

The current host-agent workflow introduces additional intermediate JSON files between those functions, but the underlying architectural stages remain the same.

---

## 3. Primary input / transformation / output mapping

| Stage | Input | Transformation | Output | Persistence |
|---|---|---|---|---|
| 0. Invocation and configuration | Repository root, CLI arguments, environment variables, output location, optional prompts and mode | Resolve root, output directory, extraction mode, feature flags, model settings, and runtime options | Effective run configuration and resolved paths | Primarily in memory; selected paths and environment details may be written to operational files |
| 1. Detection and classification | Repository root and ignore/security rules | Walk the corpus, classify files, exclude unsupported/noise paths, detect manifests and document types, count corpus statistics | `DetectionResult` dictionary | Usually serialized to `.graphify_detect.json`; selected state also contributes to `manifest.json` |
| 2. Optional transcription or conversion | Media, office documents, or files requiring preprocessing | Convert or transcribe content into text or supported document forms | Transcript/conversion sidecars and additional document paths | Persisted on disk; transcripts may be stored in `.graphify_transcripts.json` and converted files in output-managed directories |
| 3A. Structural extraction | Detected source-code files plus repository root and extraction configuration | Parse files with language-specific Tree-sitter extractors and derive code entities and relations | Per-file `ExtractionResult` fragments containing nodes, edges, hyperedges, raw calls, and language-specific intermediate facts | Returned in memory; per-file AST fragments persisted in the AST cache; workflow aggregates may be written to `.graphify_ast.json` |
| 3B. Semantic extraction | Detected document/media-derived text files, extraction prompt, mode, and model/host-agent execution | Use semantic extraction to identify concepts, entities, relationships, and supporting metadata from non-code content | Semantic `ExtractionResult` fragments | Returned in memory; per-file semantic fragments persisted in semantic cache; workflow aggregates may be written to `.graphify_semantic.json` or chunk files |
| 3C. Extraction merge | AST extraction fragments, semantic extraction fragments, cached fragments, and optional incremental fragments | Concatenate, normalize, reconcile, and combine extraction buckets | Combined `ExtractionResult` | In memory and commonly serialized to `.graphify_extract.json` |
| 4. Validation and graph construction | Combined `ExtractionResult` and optional root path | Validate required fields, normalize aliases and identifiers, reconcile duplicate representations, create graph nodes and edges | `networkx.Graph` or `networkx.DiGraph` | Primarily in memory; later exported to `graph.json` and optional graph formats |
| 5. Clustering and cohesion scoring | NetworkX graph and clustering options | Detect communities, optionally exclude hubs, split weak or oversized clusters, compute cohesion | `CommunityMap` and `CohesionMap` | In memory; community assignments are embedded into exported graph data; temporary analysis state may also be serialized |
| 6. Structural analysis | Graph, communities, and related metrics | Identify god nodes, surprising connections, suggested questions, structural anomalies, and other findings | `AnalysisBundle` composed of lists and dictionaries | In memory; may be written to `.graphify_analysis.json`; selected results appear in reports |
| 7. Diagnostics and health assessment | Detection result, graph, extraction metrics, and analysis metrics | Evaluate graph quality, extraction coverage, warnings, and operational health | Diagnostics and health summaries | Usually in memory and report content; selected metadata may enter manifest or logs |
| 8. Community labeling | Communities, graph context, and optional generated labels | Produce human-readable labels for graph communities, using deterministic or model-assisted mechanisms depending on configuration | `CommunityLabels` mapping | In memory; may be persisted in `.graphify_labels.json`; included in report and graph export |
| 9. Report generation | Graph, communities, cohesion, labels, analysis results, detection statistics, cost information, and root context | Render a human-readable Markdown description of the graph and findings | Markdown report string | Persisted as `GRAPH_REPORT.md` |
| 10. Export | Graph plus communities, labels, report context, and format options | Serialize graph and derived metadata to JSON, HTML, SVG, GraphML, Obsidian, Cypher, or related formats | `graph.json`, `graph.html`, and optional exports | Persisted as public output artifacts |
| 11. Finalization and operational persistence | Completed outputs, run metadata, caches, and previous manifest state | Write manifest, cache entries, state markers, cost data, and cleanup eligible temporary files | Durable public artifacts and operational state | Persisted on disk across runs |
| 12. Incremental update path | Previous `graph.json`, previous manifest, current repository, changed/deleted paths | Detect changes, extract changed files, merge with previous graph, remove deleted-file contributions, rebuild full extraction representation, rerun clustering and publication | Updated graph and artifacts | Uses temporary incremental files and then overwrites or republishes the normal durable outputs |

---

## 4. Stage-by-stage architectural mapping

## 4.1 Stage 0 — Invocation and effective configuration

### Inputs

The run begins from a combination of:

- a repository or corpus root;
- CLI command and arguments;
- environment variables;
- output directory configuration;
- extraction mode;
- optional semantic extraction prompt;
- optional model or provider settings;
- export format flags;
- cache location;
- update, watch, or fresh-build mode.

The Python package exposes command entry points such as:

```text
graphify
graphify-mcp
```

### Transformation

The invocation layer:

1. resolves the root path;
2. resolves the output directory;
3. selects the pipeline mode;
4. determines whether AST extraction, semantic extraction, or both are active;
5. determines whether previous outputs and caches can be reused;
6. configures output and temporary artifact locations;
7. dispatches into the detection and extraction pipeline.

### Outputs

The effective output is not a single formal object. It is a set of runtime values:

```text
RunConfiguration
├── root
├── output directory
├── extraction mode
├── prompt or prompt file
├── cache root
├── export options
├── update/fresh mode
└── model and cost settings
```

### Persistence

Mostly in memory.

Some resolved state is also represented by operational files such as:

```text
.graphify_root
.graphify_python
```

These files are orchestration aids rather than canonical analysis contracts.

---

## 4.2 Stage 1 — Detection and file classification

### Inputs

```text
repository root
ignore rules
security rules
noise filters
file-extension and content classifiers
optional cache root
```

### Transformation

`detect()` scans the repository or corpus and classifies discovered files.

The transformation includes:

- traversing the corpus;
- classifying source code, documents, media, manifests, and unsupported files;
- applying ignore and safety rules;
- excluding generated or noisy paths;
- identifying documents that require conversion or transcription;
- computing file counts and corpus statistics;
- computing word counts for supported document types;
- preparing file groups for later extraction.

Detection is broader than a simple source-file inventory. It acts as the pipeline’s corpus partitioning stage.

### Output contract: `DetectionResult`

The result is a Python dictionary. At a high level:

```text
DetectionResult
├── root and path context
├── source-code file groups
├── document file groups
├── media or convertible file groups
├── manifests or project metadata
├── skipped, ignored, unsupported, or excluded files
├── language/type statistics
├── total file counts
├── total word or corpus-size metrics
└── warnings and detection metadata
```

The exact fields are implementation-defined and can evolve. Downstream stages rely primarily on its categorized path lists and aggregate statistics.

### Consumers

- AST extraction;
- semantic extraction;
- transcription/conversion;
- report generation;
- health diagnostics;
- manifest generation;
- incremental change detection.

### Persistence

Common transient representation:

```text
.graphify_detect.json
```

Durable persistence is indirect:

- selected detection state contributes to `manifest.json`;
- file hashes and word-count fast paths contribute to `cache/stat-index.json`.

### Determinism

Detection is intended to be deterministic for the same:

- corpus;
- filesystem-visible state;
- ignore/security policy;
- Graphify version;
- relevant configuration.

It may still depend on filesystem metadata and supported conversion tooling.

---

## 4.3 Stage 2 — Optional transcription and conversion

### Inputs

Files detected as:

- audio;
- video;
- office documents;
- documents requiring preprocessing;
- formats that cannot be directly handled by semantic extraction.

### Transformation

Depending on type and configuration, Graphify can:

- transcribe media;
- convert office documents into supported textual representations;
- emit new text or Markdown documents;
- append converted paths to the semantic extraction corpus.

This stage is optional and only applies to inputs requiring preprocessing.

### Output contracts

The main outputs are files rather than one central Python object:

```text
TranscriptRecord
├── original source path
├── generated transcript
├── generated transcript path
└── metadata

ConvertedDocument
├── original path
├── converted path
├── conversion type
└── conversion metadata
```

### Persistence

Durable or semi-durable sidecars can include:

```text
.graphify_transcripts.json
graphify-out/converted/...
```

The generated transcript or converted document becomes an input to semantic extraction.

### Determinism

Conversion may be deterministic for deterministic converters.

Transcription may not be deterministic when it relies on an external model or provider.

---

## 4.4 Stage 3A — Structural AST extraction

### Inputs

```text
detected source-code files
repository root
language-specific extractor registry
AST cache
extractor configuration
```

### Transformation

Graphify performs structural extraction through language-specific Tree-sitter-based extractors.

For each supported source file, the extractor derives:

- file-level entities;
- classes, functions, methods, modules, variables, and other symbols;
- declaration and containment relations;
- imports and dependency relations;
- calls and references where supported;
- language-specific intermediate records;
- hyperedges or raw-call structures where a binary edge is not yet sufficient.

The extraction is performed per file, which makes the result naturally cacheable.

### Output contract: per-file `ExtractionResult`

At a high level:

```text
ExtractionResult
├── nodes: list[NodeRecord]
├── edges: list[EdgeRecord]
├── hyperedges: list[HyperedgeRecord]
├── raw_calls: list[RawCallRecord]
├── language-specific auxiliary buckets
├── extraction status
└── optional partial/error metadata
```

Not every file or language produces every bucket.

### Node record

The effective node contract is a dictionary representing one graph entity.

```text
NodeRecord
├── id
├── label or name
├── type/kind
├── source_file
├── optional source location
├── optional language
├── optional semantic or structural attributes
└── optional provenance/confidence metadata
```

### Edge record

```text
EdgeRecord
├── source
├── target
├── type/relation
├── source_file
├── optional weight
├── optional confidence
└── optional provenance or location metadata
```

### Hyperedge record

Hyperedges represent a relation involving more than a simple source-target pair or an intermediate relation that must later be resolved.

```text
HyperedgeRecord
├── relation identity/type
├── participating nodes or endpoints
├── source_file
└── optional metadata
```

### Raw-call record

Raw calls are intermediate unresolved call facts used by later normalization or cross-file resolution.

```text
RawCallRecord
├── caller context
├── called name or target expression
├── source_file
├── language-specific context
└── resolution metadata
```

### Persistence

Per-file extraction fragments are stored in the custom AST cache:

```text
graphify-out/cache/ast/v<graphify-version>/<file-hash>.json
```

The host-agent workflow can also aggregate AST extraction into:

```text
.graphify_ast.json
```

### Determinism

The AST extraction branch is intended to be deterministic for the same:

- file content;
- repository-relative path;
- Graphify extractor version;
- extraction configuration.

This is the reason the cache is version-namespaced.

---

## 4.5 Stage 3B — Semantic extraction

### Inputs

```text
detected documents
transcripts
converted documents
semantic extraction prompt
semantic extraction mode
model or host-agent execution
semantic cache
```

### Transformation

The semantic branch extracts graph entities and relationships from unstructured or semi-structured text.

It may identify:

- concepts;
- people or organizations;
- systems and components;
- claims or topics;
- conceptual relationships;
- evidence-bearing references;
- document-level entities.

Depending on the run mode, semantic extraction can be executed by an external model, a host agent, or subagents.

### Output contract

The semantic branch emits the same broad extraction envelope as structural extraction:

```text
ExtractionResult
├── nodes
├── edges
├── hyperedges
├── optional partial marker
├── source-file provenance
└── semantic metadata
```

This shared shape allows structural and semantic extraction to be merged before graph construction.

### Persistence

Semantic cache entries are stored as JSON files under:

```text
graphify-out/cache/semantic/<hash>.json
graphify-out/cache/semantic/p<prompt-fingerprint>/<hash>.json
graphify-out/cache/semantic-deep/<hash>.json
graphify-out/cache/semantic-deep/p<prompt-fingerprint>/<hash>.json
```

Workflow aggregates and chunks may include:

```text
.graphify_semantic.json
.graphify_semantic_new.json
.graphify_chunk_<n>.json
.graphify_cached.json
.graphify_uncached.txt
```

### Determinism

This branch is not guaranteed to be deterministic because it may depend on:

- model behavior;
- model version;
- prompt;
- provider;
- sampling or reasoning behavior;
- host-agent execution.

Prompt fingerprinting reduces stale-cache reuse across prompt changes, but it does not make model generation deterministic.

---

## 4.6 Stage 3C — Extraction merge

### Inputs

The merge stage can receive:

- fresh AST extraction fragments;
- cached AST extraction fragments;
- fresh semantic fragments;
- cached semantic fragments;
- optional incremental extraction fragments;
- chunks created by host-agent execution.

### Transformation

The transformation combines the extraction buckets into one aggregate structure.

Typical operations include:

- concatenating nodes;
- concatenating edges;
- concatenating hyperedges;
- merging raw-call buckets;
- preserving provenance;
- normalizing source-file forms;
- consolidating partial or chunked output;
- preparing a single input for validation and graph building.

### Output contract: combined `ExtractionResult`

```text
CombinedExtractionResult
├── nodes
├── edges
├── hyperedges
├── raw_calls
├── auxiliary language buckets
├── partial/error metadata
└── provenance
```

### Persistence

Typical transient file:

```text
.graphify_extract.json
```

The object is also passed directly in memory to graph construction.

### Determinism

The merge operation itself can be deterministic.

Its result inherits any non-determinism from semantic extraction and any ordering behavior from fragment production.

---

## 4.7 Stage 4 — Validation and graph construction

### Inputs

```text
CombinedExtractionResult
repository root
directed/undirected graph option
normalization and compatibility rules
```

### Validation transformation

`validate_extraction()` evaluates whether extraction records contain required fields and supported values.

The effective schema includes requirements for:

- node identity;
- node label or type information;
- edge source;
- edge target;
- edge relation;
- supported confidence values where present.

Validation returns a list of errors rather than a typed validated object.

### Graph-building transformation

`build_from_json()` then:

1. accepts extraction dictionaries;
2. normalizes legacy aliases;
3. canonicalizes identifiers and paths;
4. reconciles duplicate AST and semantic representations;
5. creates a NetworkX graph;
6. adds node attributes;
7. adds edge attributes;
8. chooses `Graph` or `DiGraph` according to configuration.

### Output contract: NetworkX graph

```text
Graph
├── graph-level metadata
├── nodes
│   └── node attributes
└── edges
    └── edge attributes
```

The runtime type is:

```python
networkx.Graph
```

or:

```python
networkx.DiGraph
```

### Persistence

The NetworkX graph is initially in memory.

Its durable representation is later written as:

```text
graphify-out/graph.json
```

and optionally:

```text
.graphml
.svg
.cypher
Obsidian files
HTML visualization
```

### Determinism

Graph construction is intended to be deterministic given a fixed extraction result and fixed normalization code.

---

## 4.8 Stage 5 — Clustering and cohesion scoring

### Inputs

```text
NetworkX graph
resolution parameter
optional hub-exclusion percentile
community-size and cohesion rules
```

### Transformation

`cluster()` detects graph communities.

The current implementation can:

- use Leiden when available;
- fall back to Louvain;
- exclude high-degree hubs from clustering when configured;
- split oversized or weakly cohesive communities;
- produce deterministic hub labels or related metadata where supported.

`score_all()` calculates cohesion for communities.

### Output contracts

#### Community map

```text
CommunityMap = dict[int, list[str]]
```

Where:

- the key is a community identifier;
- the value is a list of graph node IDs.

#### Cohesion map

```text
CohesionMap = dict[int, float]
```

Where:

- the key matches a community identifier;
- the value is a cohesion score.

### Important implementation detail

The current `cluster()` function returns a community mapping. It should not be modeled as primarily mutating the graph.

Community assignment is later incorporated into serialized graph artifacts by the export layer.

### Persistence

Primarily in memory.

Durable publication occurs when:

- community IDs are embedded in `graph.json`;
- communities are described in `GRAPH_REPORT.md`;
- labels are saved in `.graphify_labels.json`.

### Determinism

The clustering operation aims for stable output but can depend on:

- algorithm availability;
- graph ordering;
- algorithm implementation;
- resolution settings;
- random-state handling.

Bridger should not assume deterministic reproducibility without pinning these factors.

---

## 4.9 Stage 6 — Structural graph analysis

### Inputs

```text
graph
community assignments
cohesion scores
detection statistics
analysis configuration
```

### Transformation

Graphify runs analysis helpers that derive higher-level findings from graph topology.

Examples include:

- god-node detection;
- surprising connections;
- structural anomalies;
- cross-community links;
- suggested questions;
- potentially weak or overly centralized areas;
- graph-level summary metrics.

### Output contract: `AnalysisBundle`

`AnalysisBundle` is an architectural name for an assembled dictionary rather than a formal class.

```text
AnalysisBundle
├── god_nodes: list[dict]
├── surprising_connections: list[dict]
├── suggested_questions: list[dict or str]
├── structural metrics
├── warnings
└── optional diagnostics
```

### Persistence

Possible transient artifact:

```text
.graphify_analysis.json
```

Selected analysis is also rendered into:

```text
GRAPH_REPORT.md
```

and may influence:

```text
graph.html
```

### Determinism

Topological analysis is generally deterministic for a fixed graph and fixed thresholds.

Suggested questions or model-assisted interpretations may not be deterministic if generated semantically.

---

## 4.10 Stage 7 — Diagnostics and graph health

### Inputs

```text
DetectionResult
CombinedExtractionResult
Graph
CommunityMap
CohesionMap
AnalysisBundle
runtime warnings and costs
```

### Transformation

This stage assesses whether the produced graph is useful and internally plausible.

Potential checks include:

- extraction coverage;
- graph size;
- isolated nodes;
- missing relationships;
- community cohesion;
- centralization;
- skipped-file counts;
- unsupported files;
- partial semantic extraction;
- invalid records;
- operational warnings.

### Output contract

No single strong formal contract is exposed. The effective output is:

```text
Diagnostics
├── warnings
├── health metrics
├── extraction coverage
├── graph quality indicators
├── skipped/error summaries
└── publication cautions
```

### Persistence

Diagnostics are usually:

- held in memory;
- written into the Markdown report;
- included in logs;
- partially represented in the manifest or cost metadata.

A durable first-class diagnostics artifact is not clearly established as the canonical contract.

### Determinism

Diagnostic calculations are deterministic when based on deterministic inputs and fixed thresholds.

---

## 4.11 Stage 8 — Community labeling

### Inputs

```text
Graph
CommunityMap
node names and types
optional semantic context
label-generation settings
```

### Transformation

The labeler assigns human-readable descriptions to numeric community IDs.

A label can be generated from:

- prominent node names;
- hub nodes;
- recurring terms;
- semantic model output;
- deterministic heuristics.

### Output contract: `CommunityLabels`

```text
CommunityLabels = dict[int, str]
```

or a JSON-compatible equivalent where numeric keys are serialized as strings.

### Persistence

Possible operational artifact:

```text
.graphify_labels.json
```

Labels also appear in:

```text
graph.json
GRAPH_REPORT.md
graph.html
```

### Determinism

Heuristic labeling can be deterministic.

Model-generated labeling is not guaranteed to be deterministic.

---

## 4.12 Stage 9 — Markdown report generation

### Inputs

`report.generate()` receives a broad set of derived state:

```text
Graph
CommunityMap
CohesionMap
CommunityLabels
god-node analysis
surprising-connection analysis
DetectionResult
token/cost information
repository root
optional diagnostics
```

### Transformation

The report layer converts graph state into human-readable Markdown.

It can include:

- corpus overview;
- graph statistics;
- community descriptions;
- cohesion;
- god nodes;
- notable connections;
- suggested questions;
- warnings;
- cost information;
- analysis context.

### Output contract: report string

```text
GraphReport = Markdown string
```

### Persistence

Canonical report path:

```text
GRAPH_REPORT.md
```

This is a durable public artifact.

### Authority boundary

The report is a presentation artifact. It should not be treated as the authoritative graph data model.

The authoritative machine-readable graph is `graph.json`.

---

## 4.13 Stage 10 — Graph export and publication

### Inputs

```text
NetworkX graph
CommunityMap
CommunityLabels
analysis metadata
export options
output paths
```

### Transformation

The export layer serializes the graph into one or more target formats.

Supported output families include:

- node-link JSON;
- interactive HTML;
- SVG;
- GraphML;
- Obsidian-compatible files;
- Cypher;
- optional wiki-like outputs.

The JSON exporter uses node-link-style serialization and incorporates community information and selected metadata.

It also performs output safety checks such as shrink guards or backup handling.

### Main output contract: `GraphDocument`

The durable JSON contract can be modeled as:

```text
GraphDocument
├── graph metadata
├── nodes: list[SerializedNode]
├── links or edges: list[SerializedEdge]
├── community assignments
├── optional labels
└── optional derived metadata
```

The exact property names follow NetworkX node-link serialization and Graphify’s export additions.

### Canonical public artifacts

```text
graphify-out/graph.json
graphify-out/graph.html
GRAPH_REPORT.md
```

Optional exports can include:

```text
graphify-out/*.svg
graphify-out/*.graphml
graphify-out/*cypher*
graphify-out/obsidian/...
```

### Persistence

Durable on disk.

### Determinism

JSON and graph export can be deterministic if:

- graph ordering is stable;
- serialization ordering is stable;
- labels and semantic metadata are stable;
- the same Graphify version and settings are used.

Interactive HTML may include generated presentation details but is still derived from the graph.

---

## 4.14 Stage 11 — Finalization and operational state

### Inputs

```text
published graph artifacts
run configuration
detection state
cache state
cost state
previous manifest
temporary files
```

### Transformation

Finalization:

- writes durable public artifacts;
- records a manifest;
- writes cost data;
- persists caches;
- records root/runtime markers;
- cleans transient files where appropriate;
- leaves reusable state for update runs.

### Durable public outputs

```text
graphify-out/graph.json
graphify-out/graph.html
GRAPH_REPORT.md
optional graph exports
```

### Durable operational outputs

```text
graphify-out/manifest.json
graphify-out/cost.json
graphify-out/cache/ast/...
graphify-out/cache/semantic/...
graphify-out/cache/semantic-deep/...
graphify-out/cache/stat-index.json
.graphify_labels.json
.graphify_root
.graphify_python
transcript/conversion sidecars
```

### Transient outputs

The default workflow may create and later remove files such as:

```text
.graphify_detect.json
.graphify_ast.json
.graphify_semantic.json
.graphify_semantic_new.json
.graphify_extract.json
.graphify_analysis.json
.graphify_chunk_*.json
.graphify_cached.json
.graphify_uncached.txt
.graphify_incremental.json
.graphify_old.json
```

The exact cleanup behavior depends on the workflow and mode.

---

## 5. Cache architecture

## 5.1 Overall design

Graphify uses a custom disk-backed cache implemented in `graphify/cache.py`.

It does not rely on a general-purpose caching library such as Redis, SQLite, `diskcache`, or `cachetools`.

The implementation uses Python standard-library mechanisms including:

- `json`;
- `hashlib`;
- `pathlib`;
- `os`;
- `tempfile`;
- `atexit`;
- process-local dictionaries and sets.

The cache has two layers:

1. **Extraction-result cache**  
   Per-file AST or semantic extraction results stored as JSON.

2. **Stat/hash index**  
   A small in-memory dictionary loaded from and flushed to a JSON file to avoid repeatedly reading unchanged files.

---

## 5.2 AST cache

### Persistence model

AST extraction results are persisted as files:

```text
graphify-out/cache/ast/v<extractor-version>/<hash>.json
```

They survive process termination and can be reused by later runs.

### Versioning model

AST results depend on extractor implementation.

Therefore, Graphify namespaces AST cache entries by installed Graphify package version:

```text
cache/ast/v0.9.32/
cache/ast/v0.9.33/
```

Old AST version directories are eligible for cleanup and are deliberately not treated as valid hits for the current extractor version.

### Cache key

The key is based on:

```text
SHA-256(file content + separator + repository-relative path)
```

The path component prevents identical file contents at different repository paths from incorrectly sharing one structural result.

For Markdown, frontmatter is excluded from the hashed body, so metadata-only frontmatter changes do not invalidate the cache.

### Cache value

The value is the per-file extraction dictionary:

```json
{
  "nodes": [],
  "edges": [],
  "hyperedges": [],
  "raw_calls": []
}
```

Additional language-specific fields may also be present.

### Cache lookup

Conceptual flow:

```text
compute file hash
    │
    ▼
resolve cache path
    │
    ├── file absent → miss
    ├── invalid JSON → miss
    ├── partial result not allowed → miss
    └── valid JSON → load and return extraction fragment
```

### Cache write

`save_cached()` conceptually:

1. verifies that the source path is a regular file;
2. deep-copies the extraction result;
3. rewrites `source_file` fields into portable repository-relative paths;
4. rewrites checkout-root-sensitive IDs and paths into a portable anchored form;
5. serializes the result as JSON;
6. writes to a temporary file;
7. atomically replaces the final cache entry.

Atomic replacement reduces the risk of publishing a partially written cache file.

### Portability

Cache entries are designed to survive:

- repository moves;
- different checkout directories;
- CI runners;
- shared caches.

On write, source paths are relativized.

On load, they are re-anchored to the current repository root so consumers receive the same absolute-path shape as a fresh extraction.

---

## 5.3 Semantic cache

### Persistence model

Semantic extraction results are also JSON files.

Unlike AST entries, they are not invalidated solely by Graphify package version because regenerating them can incur model cost.

### Namespaces

```text
cache/semantic/
cache/semantic-deep/
```

Prompt-specific entries can be placed under:

```text
p<prompt-fingerprint>/
```

Example:

```text
graphify-out/cache/semantic/pabc123/<hash>.json
```

### Prompt fingerprinting

Prompt fingerprinting prevents an extraction generated under one prompt from silently being treated as current under a different prompt.

Legacy un-fingerprinted entries may still be read in compatibility mode.

### Partial results

A semantic cache entry marked `partial` is normally treated as a cache miss.

This prevents a truncated model response from becoming permanently authoritative.

Partial entries may be explicitly loaded by checkpoint/merge logic to continue accumulating chunks.

### Pruning

Semantic cache directories are pruned by live content hashes rather than Graphify version.

This preserves reusable model-generated results while removing orphaned entries for deleted or changed files.

---

## 5.4 Stat index

### Runtime form

Graphify maintains a process-local dictionary:

```python
_stat_index: dict[str, dict]
```

It stores values such as:

```text
absolute path
→ size
→ mtime_ns
→ hashes keyed by path salt
→ optional word_count
```

### Persistent form

```text
graphify-out/cache/stat-index.json
```

### Purpose

The index avoids reopening and hashing every file on every run.

Lookup flow:

```text
file path
  ↓
stat(size, mtime_ns)
  ↓
compare against in-memory index
  ├── unchanged → reuse hash or word count
  └── changed/missing → read file, recompute, update index
```

### Lifecycle

```text
stat-index.json
    ↓ loaded on first use
in-memory _stat_index
    ↓ updated during run
atomically flushed at process exit
```

The flush process:

- prunes entries whose source file no longer exists;
- stores repository-internal paths in portable relative form;
- writes a temporary file;
- replaces the previous index atomically.

### Classification

The stat index is both:

- in-memory during a process;
- persistent across processes through JSON serialization.

It is not the extraction-result cache itself. It accelerates cache-key and corpus-statistics computation.

---

## 5.5 Cache contract summary

| Cache component | Key | Value | Storage | Invalidation |
|---|---|---|---|---|
| AST extraction cache | SHA-256 of content plus repository-relative path | Per-file structural `ExtractionResult` | JSON files under `cache/ast/v<version>/` | File hash change or Graphify extractor-version change |
| Semantic cache | Content/path-derived hash plus optional prompt namespace | Per-file semantic `ExtractionResult` | JSON files under `cache/semantic*` | File hash change, prompt namespace change, partial-entry rules, or liveness pruning |
| Stat/hash index | Source path with per-root salt handling | Size, `mtime_ns`, hashes, optional word count | In-memory dict plus `cache/stat-index.json` | Stat change, missing file, or explicit cleanup |
| Process-local memoization | Function-specific keys | Cleaned directories, prompt fingerprints, dirty flags | Memory only | Process exit |

---

## 6. Contract catalog

## 6.1 `DetectionResult`

**Role:** Corpus inventory and classification contract.

```text
DetectionResult
├── categorized source paths
├── categorized document paths
├── media/conversion candidates
├── manifests
├── skipped and unsupported paths
├── language/type counts
├── corpus size metrics
├── root context
└── warnings
```

**Producer:** detection stage.  
**Consumers:** extraction, reporting, diagnostics, manifest/update logic.  
**Typical persistence:** `.graphify_detect.json`, with selected durable data in `manifest.json`.

---

## 6.2 `ExtractionResult`

**Role:** Shared intermediate representation for graph facts.

```text
ExtractionResult
├── nodes
├── edges
├── hyperedges
├── raw_calls
├── auxiliary language facts
├── provenance
├── partial marker
└── errors/status
```

**Producers:** AST extractors and semantic extractors.  
**Consumers:** merge, validation, graph build, incremental update.  
**Persistence:** per-file cache JSON and transient aggregate JSON.

---

## 6.3 `NodeRecord`

**Role:** One entity that can become a graph node.

```text
NodeRecord
├── id
├── label/name
├── type/kind
├── source_file
├── optional location
├── optional language
├── optional attributes
└── optional provenance/confidence
```

**Producer:** extraction.  
**Consumer:** graph builder.  
**Persistence:** extraction cache, combined extraction, graph export.

---

## 6.4 `EdgeRecord`

**Role:** One binary relationship.

```text
EdgeRecord
├── source node ID
├── target node ID
├── relation type
├── source_file
├── optional weight
├── optional confidence
└── optional provenance
```

**Producer:** extraction.  
**Consumer:** graph builder.  
**Persistence:** extraction cache, combined extraction, graph export.

---

## 6.5 `HyperedgeRecord`

**Role:** A relation not yet reducible to one simple source-target pair or involving multiple participants.

**Producer:** language or semantic extractors.  
**Consumer:** normalization/resolution and graph build.  
**Persistence:** extraction cache and aggregate extraction.

---

## 6.6 `RawCallRecord`

**Role:** Unresolved or partially resolved call information.

**Producer:** language-specific AST extraction.  
**Consumer:** cross-file resolution and graph normalization.  
**Persistence:** extraction cache and aggregate extraction.

---

## 6.7 NetworkX graph

**Role:** Central in-memory graph representation.

```text
Graph
├── node IDs and attributes
├── edge endpoints and attributes
└── graph metadata
```

**Producer:** `build_from_json()`.  
**Consumers:** clustering, analysis, labeling, reporting, export, query tools.  
**Persistence:** serialized into `graph.json` and optional graph formats.

---

## 6.8 `CommunityMap`

```python
dict[int, list[str]]
```

**Role:** Maps each community ID to its node IDs.  
**Producer:** `cluster()`.  
**Consumers:** cohesion scoring, labeling, reporting, export.  
**Persistence:** embedded in exports and labels; primarily in memory.

---

## 6.9 `CohesionMap`

```python
dict[int, float]
```

**Role:** Community quality/cohesion score.  
**Producer:** `score_all()`.  
**Consumers:** reporting and diagnostics.  
**Persistence:** primarily report and transient state.

---

## 6.10 `AnalysisBundle`

**Role:** Aggregated structural findings.

```text
AnalysisBundle
├── god nodes
├── surprising connections
├── suggested questions
├── structural summaries
└── warnings
```

**Producer:** analysis helpers.  
**Consumers:** report and visualization.  
**Persistence:** transient `.graphify_analysis.json` and durable report content.

---

## 6.11 `CommunityLabels`

```python
dict[int, str]
```

**Role:** Human-readable names for communities.  
**Producer:** labeler.  
**Consumers:** report, JSON export, HTML.  
**Persistence:** `.graphify_labels.json` and published outputs.

---

## 6.12 `GraphDocument`

**Role:** Canonical machine-readable graph artifact.

```text
GraphDocument
├── graph metadata
├── serialized nodes
├── serialized links/edges
├── community attributes
└── optional labels and analysis metadata
```

**Producer:** JSON exporter.  
**Consumers:** update mode, query tools, visualizations, external integrations.  
**Persistence:** `graphify-out/graph.json`.

---

## 6.13 `GraphReport`

**Role:** Human-readable Markdown analysis.

**Producer:** `report.generate()`.  
**Consumers:** users, reviewers, later documentation workflows.  
**Persistence:** `GRAPH_REPORT.md`.

---

## 6.14 `Manifest`

**Role:** Durable run and corpus state used for lifecycle and update behavior.

At a high level:

```text
Manifest
├── file inventory or fingerprints
├── run metadata
├── root/path context
├── output state
├── version information
└── update comparison data
```

**Producer:** finalization/detection lifecycle.  
**Consumers:** incremental detection and update workflows.  
**Persistence:** `graphify-out/manifest.json`.

---

## 7. Persistence matrix

## 7.1 Durable public artifacts

| Artifact | Purpose | Canonical status |
|---|---|---|
| `graphify-out/graph.json` | Machine-readable graph | Primary canonical graph artifact |
| `GRAPH_REPORT.md` | Human-readable findings | Canonical presentation artifact |
| `graphify-out/graph.html` | Interactive visualization | Published visualization |
| Optional SVG | Static graph visualization | Optional |
| Optional GraphML | Interchange with graph tools | Optional |
| Optional Cypher | Graph-database import | Optional |
| Optional Obsidian output | Knowledge-base navigation | Optional |

---

## 7.2 Durable operational artifacts

| Artifact | Purpose |
|---|---|
| `graphify-out/manifest.json` | Run and file-state lifecycle data |
| `graphify-out/cost.json` | Model/token cost bookkeeping |
| `graphify-out/cache/ast/...` | Versioned structural extraction results |
| `graphify-out/cache/semantic/...` | Semantic extraction results |
| `graphify-out/cache/semantic-deep/...` | Deep-mode semantic extraction |
| `graphify-out/cache/stat-index.json` | Hash and word-count fast path |
| `.graphify_labels.json` | Community-label persistence |
| `.graphify_root` | Root/orchestration marker |
| `.graphify_python` | Python/runtime orchestration marker |
| `.graphify_transcripts.json` | Transcription mapping/state |
| Converted document directories | Reusable preprocessing outputs |

---

## 7.3 Transient orchestration artifacts

| Artifact | Role |
|---|---|
| `.graphify_detect.json` | Serialized detection result |
| `.graphify_ast.json` | Aggregated AST extraction |
| `.graphify_semantic.json` | Aggregated semantic extraction |
| `.graphify_semantic_new.json` | Newly generated semantic fragments |
| `.graphify_extract.json` | Combined extraction input to graph build |
| `.graphify_analysis.json` | Intermediate analysis bundle |
| `.graphify_chunk_*.json` | Chunked semantic/subagent output |
| `.graphify_cached.json` | Cached semantic fragments selected for merge |
| `.graphify_uncached.txt` | Files requiring semantic extraction |
| `.graphify_incremental.json` | Incremental detection result |
| `.graphify_old.json` | Previous graph or extraction state for update |

These files support orchestration. They should not automatically be treated as product-level public contracts.

---

## 7.4 In-memory-only state

| State | Runtime form |
|---|---|
| Effective run configuration | Python values/dictionaries |
| Active graph | `networkx.Graph` or `networkx.DiGraph` |
| Community assignments | `dict[int, list[str]]` |
| Cohesion scores | `dict[int, float]` |
| Analysis lists | Python lists and dictionaries |
| Markdown report before write | Python string |
| Diagnostics | Dictionaries/lists |
| Stat index during execution | Process-local dictionary |
| Cache cleanup and fingerprint memoization | Process-local sets/dictionaries |

---

## 8. Incremental update pipeline

The update pipeline is not merely “rerun everything.” It reuses the previous published graph and manifest.

## 8.1 Inputs

```text
current repository
previous manifest
previous graph.json
current detection state
changed paths
deleted paths
cache
```

## 8.2 Transformation sequence

```text
Current repository + previous manifest
        │
        ▼
detect_incremental()
        │
        ▼
IncrementalDetectionResult
        │
        ├── changed files
        ├── new files
        └── deleted files
        │
        ▼
Extract changed/new files
        │
        ▼
Changed ExtractionResult
        │
        ▼
build_merge(previous graph, changed extraction, deleted files)
        │
        ▼
Merged graph
        │
        ▼
Re-materialize or reconstruct full extraction/graph state
        │
        ▼
Re-cluster, re-analyze, re-label, re-report, re-export
```

## 8.3 Intermediate artifacts

Typical files:

```text
.graphify_incremental.json
.graphify_old.json
.graphify_semantic_new.json
.graphify_extract.json
```

## 8.4 Outputs

The normal public artifacts are republished:

```text
graphify-out/graph.json
graphify-out/graph.html
GRAPH_REPORT.md
manifest.json
```

## 8.5 Architectural implication

The previous `graph.json` and manifest jointly serve as the update baseline.

This makes their schema stability, path portability, version metadata, and deletion semantics important.

---

## 9. Determinism boundaries

## 9.1 Intended deterministic components

The following can be deterministic for fixed inputs and versions:

- file detection and classification;
- source hashing;
- AST extraction;
- extraction merge;
- validation;
- ID normalization;
- graph construction;
- structural graph analysis;
- JSON serialization, subject to ordering;
- report rendering from fixed inputs.

## 9.2 Potentially non-deterministic components

- semantic extraction;
- model-generated community labels;
- transcription through model services;
- model-generated suggested questions;
- clustering if algorithm, random state, library version, or node ordering varies.

## 9.3 Cache impact

Caching can make repeated runs appear stable even when the original producer was non-deterministic.

That does not make the generating process deterministic. It only replays a previously persisted result.

---

## 10. Ownership and authority boundaries

## 10.1 Source of truth by concern

| Concern | Effective source of truth |
|---|---|
| Corpus classification during a run | `DetectionResult` |
| Per-file extracted facts | AST/semantic cache entry or fresh `ExtractionResult` |
| Active graph during processing | NetworkX graph |
| Durable graph | `graphify-out/graph.json` |
| Human-readable interpretation | `GRAPH_REPORT.md` |
| Community names | `CommunityLabels` / `.graphify_labels.json` |
| Incremental baseline | `manifest.json` plus previous `graph.json` |
| Cache-key fast path | `cache/stat-index.json` plus current filesystem stat |
| Cost bookkeeping | `cost.json` |

## 10.2 Non-authoritative artifacts

The following should not be treated as the canonical product model:

- host-agent chunk files;
- temporary merged extraction files;
- report prose;
- HTML visualization;
- Python runtime markers;
- cost ledger;
- transcript orchestration state.

They may be useful, but they are supporting artifacts.

---

## 11. Implications for Bridger

This section records the architectural implications derived from the mapping. It is not a claim that Graphify already satisfies Bridger’s product contract.

## 11.1 Strong reuse candidates

Potentially reusable or adaptable:

- per-file extraction architecture;
- structural `NodeRecord`, `EdgeRecord`, and `HyperedgeRecord` concepts;
- content-addressed cache entries;
- AST cache version namespacing;
- portable path serialization;
- atomic JSON writes;
- NetworkX graph construction;
- graph export mechanics;
- community clustering;
- cohesion and structural-analysis helpers;
- incremental merge concepts.

## 11.2 Components that require a Bridger-owned wrapper or contract

### Detection

Graphify detection is a corpus classifier.

Bridger requires stronger repository identity and lifecycle semantics, including likely:

- Git-tracked inventory;
- repository revision;
- tracked/untracked policy;
- submodule handling;
- deterministic repository-relative paths;
- explicit exclusion reasoning;
- checksums and schema versions.

### Extraction records

Graphify’s dictionary contracts are flexible.

Bridger should consider formalizing:

- schema version;
- stable IDs;
- exact source ranges;
- declaration/body distinction;
- extraction status;
- evidence provenance;
- confidence semantics;
- deterministic ordering.

### Graph document

`graph.json` should be wrapped or replaced by a Bridger-owned graph artifact that defines:

- schema version;
- producer version;
- repository revision;
- deterministic ordering;
- checksum;
- node and edge invariants;
- compatibility policy;
- diagnostics linkage.

### Communities and analysis

Community output and structural analysis should remain derived artifacts rather than silently mutating the canonical deterministic substrate.

### Manifest and update lifecycle

Bridger should own:

- revision identity;
- cache compatibility;
- invalidation rules;
- migration behavior;
- failure recovery;
- deletion semantics;
- reproducibility metadata.

## 11.3 Components that should not become Bridger canonical contracts

- `.graphify_chunk_*.json`;
- host-agent temporary extraction files;
- `.graphify_python`;
- installation helpers;
- cost bookkeeping as graph authority;
- Markdown report prose as graph authority;
- temporary cache-selection lists;
- Graphify-specific orchestration filenames.

## 11.4 Recommended separation

A Bridger integration should preserve three layers:

```text
1. Deterministic repository substrate
   ├── Git-aware inventory
   ├── stable symbol facts
   ├── stable graph facts
   ├── diagnostics
   └── revision/checksum metadata

2. Derived structural analysis
   ├── communities
   ├── cohesion
   ├── centrality
   └── anomaly analysis

3. Non-deterministic enrichment
   ├── semantic document extraction
   ├── model-generated labels
   ├── suggested questions
   └── narrative report
```

Graphify currently allows these concerns to converge into the published graph and report. Bridger should make their authority boundaries explicit.

---

## 12. Known contract weaknesses and analysis cautions

1. **Most contracts are dictionaries, not typed public schemas.**  
   Field-level compatibility must be verified directly against implementation before binding Bridger to them.

2. **The architecture documentation can simplify current behavior.**  
   Current implementation should take precedence when documentation and code differ.

3. **Clustering output is a mapping, not primarily a graph mutation.**  
   Export later embeds community assignments.

4. **`AnalysisBundle` is an analytical name, not a formal runtime class.**

5. **Temporary JSON files are workflow contracts, not necessarily stable library APIs.**

6. **Semantic extraction and model-generated labels must not be classified as deterministic substrate.**

7. **Cache replay can conceal non-determinism.**  
   A cache hit reproduces a prior answer; it does not prove that regeneration would produce the same answer.

8. **Versioning differs by cache type.**  
   AST cache is package-version namespaced. Semantic cache is prompt-fingerprinted and content-liveness-pruned rather than package-version-invalidated.

9. **Path portability is actively handled.**  
   Cached source paths and root-sensitive IDs are rewritten on write and re-anchored on load.

10. **The stat index is hybrid.**  
    It is in memory during the run and persisted as JSON at process exit.

---

## 13. Source map

The analysis is grounded in the following repository areas at the revision stated at the top of this document:

| Repository path | Role in this analysis |
|---|---|
| `ARCHITECTURE.md` | Conceptual pipeline and module responsibilities |
| `README.md` | User-visible outputs and primary execution model |
| `graphify/skill.md` | Current host-agent orchestration and temporary artifact lifecycle |
| `graphify/detect.py` | Detection, classification, manifest, and stat-index use |
| `graphify/extract.py` | Structural extraction and extraction assembly |
| `graphify/cache.py` | AST cache, semantic cache, stat index, portability, and atomic writes |
| `graphify/validate.py` | Extraction validation rules |
| `graphify/build.py` | Extraction-to-NetworkX graph construction |
| `graphify/cluster.py` | Community detection and cohesion |
| `graphify/analyze.py` | Structural analysis helpers |
| `graphify/report.py` | Markdown report generation |
| `graphify/export.py` | JSON, HTML, SVG, GraphML, Obsidian, and Cypher exports |
| `graphify/update.md` | Incremental detection and merge flow |
| `graphify/transcribe.md` | Optional media transcription |
| `tests/test_cache.py` | Cache round-trip, invalidation, frontmatter hashing, and portability behavior |
| `pyproject.toml` | Package versioning, dependencies, and command entry points |

---

## 14. Working architectural model

For subsequent tasks, Graphify should be understood as the following system:

```text
Graphify
├── Corpus discovery
│   └── DetectionResult
├── Extraction
│   ├── Deterministic AST extraction
│   └── Non-deterministic semantic extraction
├── Shared intermediate representation
│   └── ExtractionResult
├── Graph construction
│   └── NetworkX Graph/DiGraph
├── Derived graph intelligence
│   ├── CommunityMap
│   ├── CohesionMap
│   ├── AnalysisBundle
│   └── CommunityLabels
├── Publication
│   ├── graph.json
│   ├── GRAPH_REPORT.md
│   ├── graph.html
│   └── optional graph formats
└── Lifecycle support
    ├── manifest.json
    ├── versioned AST cache
    ├── semantic cache
    ├── stat-index.json
    └── incremental update artifacts
```

The key architectural boundary for Bridger is:

> Graphify’s strongest reusable core is the per-file extraction, graph-building, cache, and graph-analysis machinery. Bridger must own the repository contract, stable schemas, revision identity, validation, diagnostics, deterministic ordering, and the separation between canonical deterministic facts and non-deterministic enrichment.
