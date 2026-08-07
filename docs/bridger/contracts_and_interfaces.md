## Segmentation  
```
0. Shared contract foundations
        ↓
1. Repository source and intake
        ↓
2. Deterministic extraction and indexing
        ↓
3. Graph construction and structural intelligence
        ↓
4. Graph lifecycle and persistence
        ↓
5. AI enrichment overlay
        ↓
6. Composite graph access and repository navigation
        ↓
7. Memory-agent orchestration and runtime
        ↓
8. Evidence-backed knowledge bundles
        ↓
9. Repository Brain assembly and publication
        ↓
10. Retrieval and external access
        ↓
11. Product consumers

```
This expands the six conceptual architecture layers into smaller design units that have coherent ownership and contract boundaries.  
  
  
# Layer 1 — Repository Source and Intake  
**Status: Locked for V0**  
## Responsibility  
Produce a complete, revision-bound inventory of the repository’s Git-tracked files and provide controlled access to their contents.  
```
Local Git repository
        ↓
Resolve exact repository revision
        ↓
Enumerate Git-tracked files
        ↓
Classify file access and processing policy
        ↓
RepositoryContext + FileIndex

```
This layer does not parse manifests, symbols, imports or ASTs, and does not construct the graph.  
Git-tracked inventory is authoritative. Graphify consumes this inventory through a private adapter and cannot independently redefine repository membership.  
  
## Contracts  
```
RepositoryContext

```
Identifies the exact repository state being processed.  
```
RepositoryContext
├── repository_id
├── root_path
├── revision
├── branch?
└── scope_path = "."

```
* repository_id: stable logical repository identifier.  
* root_path: local runtime checkout path.  
* revision: exact Git commit SHA; authoritative source identity.  
* branch: optional informational branch name.  
* scope_path: repository-relative analysis root; "." means the full repository.  
  
```
FileDisposition

```
Defines how Bridger may access and process one tracked file.  
```
FileDisposition
├── read_mode
├── processing_mode
└── reason?

```
read_mode:  
```
full
bounded
denied

```
processing_mode:  
```
extract
metadata_only
skip

```
Example reasons:  
```
sensitive_file
unsupported_type
generated_file
bridger_internal
file_too_large
excluded_by_policy

```
Reading policy and extraction policy remain separate because a file may be readable without being eligible for deterministic extraction.  
  
```
FileRecord

```
Represents one scoped Git-tracked file.  
```
FileRecord
├── path
├── git_object_id
├── size_bytes
├── content_type
├── language?
└── disposition: FileDisposition

```
* path: normalized repository-relative path.  
* git_object_id: Git blob identifier or equivalent content digest.  
* content_type: coarse classification such as source, documentation, configuration, binary or unknown.  
* language: optional detected language.  
* disposition: authoritative access and processing policy.  
  
```
FileIndex

```
Canonical Layer 1 artifact containing every scoped Git-tracked file.  
```
FileIndex
├── schema_version
├── repository_id
├── revision
├── scope_path
├── files: list[FileRecord]
└── summary

```
Summary fields:  
```
total_tracked
extractable
metadata_only
skipped
fully_readable
bounded_readable
read_denied

```
The index remains complete. Authorized or extractable views are derived through filtering rather than persisted as separate indexes.  
  
```
SourceReadRequest

```
Requests a bounded read of one indexed repository file.  
```
SourceReadRequest
├── path
├── start_line?
├── end_line?
└── max_bytes?

```
The request does not grant access. The corresponding FileDisposition remains authoritative.  
  
```
SourceReadResult

```
Returns policy-compliant source content.  
```
SourceReadResult
├── path
├── revision
├── content
├── start_line
├── end_line
├── content_digest
├── encoding
└── truncated

```
The result is revision-bound and suitable for later evidence references.  
  
```
FileChangeSet

```
Describes file-level changes between two repository revisions.  
```
FileChangeSet
├── base_revision
├── target_revision
├── added_paths
├── modified_paths
└── deleted_paths

```
Rename detection is not required in V0; a rename may appear as one deletion and one addition.  
  
## Interfaces  

| Interface | Visibility | Input | Output | Responsibility |
| ---------------------------- | ------------------------------ | -------------------------------------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------- |
| prepare_repository | Internal application interface | root_path, optional revision, optional scope_path | RepositoryContext, FileIndex | Coordinates repository resolution and file-index construction. |
| resolve_repository | Internal | Repository path, revision and scope | RepositoryContext | Verifies the Git repository, resolves the exact commit and normalizes scope. |
| build_file_index | Internal | RepositoryContext, Bridger intake configuration | FileIndex | Enumerates tracked files, gathers metadata and assigns dispositions. |
| read_file | Stable internal read interface | RepositoryContext, FileIndex, SourceReadRequest | SourceReadResult | Validates the path and range, applies FileDisposition, and returns bounded revision-bound content. |
| compare_revisions | Internal lifecycle interface | Repository context, base revision, target revision | FileChangeSet | Computes added, modified and deleted tracked paths using Git. |
| adapt_file_index_to_graphify | Private adapter | RepositoryContext, FileIndex | Graphify internal detection structure | Translates Bridger’s authoritative inventory into Graphify’s expected private format. |
  
## Locked rules  
1. Bridger V0 supports Git repositories only.  
2. Git-tracked files define repository membership; untracked files are excluded.  
3. Every scoped tracked file appears exactly once in the FileIndex.  
4. Tracked but inaccessible, unsupported or excluded files remain visible with an explicit disposition.  
5. .bridger/** is indexed if tracked but uses processing_mode = skip and reason = bridger_internal.  
6. Repository-relative paths are normalized and deterministically ordered.  
7. File access must go through read_file; callers do not read repository paths directly.  
8. The caller cannot override a file’s disposition through SourceReadRequest.  
9. Graphify receives only files selected from the FileIndex; it may classify them further but cannot add repository members.  
10. Layer 1 performs no semantic, symbol, manifest-content or graph interpretation.  
11. The exact Git commit SHA, rather than the branch name, identifies the analyzed source state.  
12. Publishable snapshots must be based on a commit-pinned source state. Dirty tracked content is outside V0.  
The repository and exact revision remain the ultimate authority for all downstream deterministic and AI-derived artifacts.  
   
# Layer 2 — Deterministic Extraction and Indexing  
**Status: Locked for V0**  
## Responsibility  
Transform Layer 1’s authorized files into deterministic extraction facts for graph construction, while producing Bridger’s durable symbol index and an explicit extraction completeness report.  
```
RepositoryContext + FileIndex
              ↓
Select authorized extractable files
              ↓
Graphify AST extraction and cross-file resolution
              ↓
├─ private Graphify extraction data → Layer 3
├─ SymbolIndex
└─ ExtractionReport

```
Graphify’s dictionaries, caches, per-file fragments and resolution records remain private implementation contracts.  
  
## Contracts  
```
SymbolRecord

```
Represents one source-backed declaration.  
```
SymbolRecord
├── symbol_id
├── name
├── qualified_name?
├── kind
├── path
├── start_line
├── end_line
├── parent_symbol_id?
└── signature?

```
* symbol_id: stable declaration identifier while path and declaration identity remain unchanged.  
* name: local source name.  
* qualified_name: namespace- or parent-qualified name when available.  
* kind: controlled declaration kind such as class, interface, function, method, constructor, property, enum, type alias, namespace, module or variable.  
* path: normalized repository-relative path.  
* start_line, end_line: exact inclusive declaration range.  
* parent_symbol_id: containing declaration when applicable.  
* signature: optional bounded declaration signature without the complete body.  
A SymbolRecord represents a real source declaration. It does not represent files, imports, calls, unresolved stubs, graph communities or semantic concepts.  
  
```
SymbolIndex

```
Canonical deterministic index of source declarations for one repository revision.  
```
SymbolIndex
├── schema_version
├── repository_id
├── revision
├── scope_path
├── symbols: list[SymbolRecord]
└── summary

```
Summary fields:  
```
total_symbols
files_with_symbols
symbols_by_kind

```
Rules:  
* every symbol path must exist in the Layer 1 FileIndex;  
* symbols may originate only from files with processing_mode = extract;  
* ranges must resolve inside the corresponding file;  
* symbols are deterministically ordered;  
* file metadata and access policy remain owned by FileIndex.  
  
```
ExtractionReport

```
Records deterministic extraction completeness.  
```
ExtractionReport
├── repository_id
├── revision
├── attempted_files
├── successful_files
├── failed_files
└── produced_symbols

```
Each failed-file record contains:  
```
path
error

```
A successfully parsed file containing no declarations is not considered a failure.  
Files marked metadata_only or skip are not extraction failures; their status remains represented in the Layer 1 FileIndex.  
  
## Interfaces  

| Interface | Visibility | Input | Output | Responsibility |
| ---------------------------- | --------------------------------- | ------------------------------------------------------ | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| extract_repository_facts | Internal application interface | RepositoryContext, FileIndex, extraction configuration | SymbolIndex, ExtractionReport, private Graphify extraction data | Coordinates file selection, structural extraction, cross-file resolution, symbol-index generation and failure collection. |
| adapt_file_index_to_graphify | Private adapter | RepositoryContext, FileIndex | Ordered list[Path] | Selects authorized extractable files and resolves their repository-relative paths into safe runtime paths. |
| run_graphify_extraction | Private Graphify engine interface | Ordered paths, repository root, cache configuration | Private Graphify extraction dictionary and symbol emissions | Runs per-file AST extraction, cache reuse and repository-wide resolution. |
| build_symbol_index | Internal deterministic interface | Private Graphify symbol emissions, RepositoryContext | SymbolIndex | Converts Graphify’s loose symbol records into Bridger’s stable typed symbol contract. |
  
## Locked rules and notes  
1. Graphify does not currently publish a complete dedicated SymbolIndex. Its internal symbol-resolution facts are temporary and insufficient as Bridger’s persisted symbol contract.  
2. The SymbolIndex is generated from the existing Graphify AST pass; Bridger does not run a second parser.  
3. Graphify’s private extraction result is extended with a symbols bucket containing exact declaration ranges and symbol metadata.  
4. Graphify’s existing nodes and edges remain the private handoff to Layer 3.  
5. Graphify detect() and collect_files() are bypassed. Layer 1’s FileIndex remains the sole authority for repository membership.  
6. The adapter passes a file only when:  
```
processing_mode == extract
AND
read_mode == full

```
7. Graphify may read selected files directly internally in V0. General-purpose and agent-facing reads still use Layer 1’s SourceReadRequest interface.  
8. Graphify cannot add paths absent from the FileIndex.  
9. Graphify’s internal dictionaries, AST caches and resolution dataclasses are not converted to Bridger models.  
10. Symbol identity is distinct from graph-node identity. Graph construction may merge entities that remain separate source declarations.  
11. Cross-revision rename and move reconciliation is outside V0.  
12. Manifest declarations and other deterministic Graphify facts remain in the private graph extraction data; no separate ManifestIndex is introduced.  
13. Symbol search and symbol excerpt retrieval are not part of this layer; they belong to Layer 6.  
14. AI semantic extraction is excluded from this layer.  
Graphify’s public extraction path accepts explicit file paths and returns node/edge dictionaries, allowing Bridger to supply its own authoritative file selection without reproducing Graphify’s native detection stage.  
  
  
# 3 — Graph construction and structural intelligence  
## Responsibility  
Delegate deterministic graph construction and structural analysis to the isolated Graphify engine.  
Layer 3 transforms Graphify’s private resolved extraction output into:  
* the canonical runtime directed graph;  
* private Graphify community and structural-analysis results;  
* typed Bridger diagnostics.  
Persistence, loading, incremental updates, snapshot identity and publication belong to Layer 4.  
## Contracts  
```
GraphConstructionConfig

```
Controls deterministic graph construction and structural-analysis behavior.  
Main attributes:  
* community algorithm;  
* community resolution;  
* optional hub-exclusion percentile;  
* limits for god nodes, surprising connections and suggested questions.  
Fixed V0 policies:  
* runtime graph type: nx.DiGraph;  
* deterministic deduplication enabled;  
* semantic extraction disabled;  
* model-assisted labels disabled;  
* selected algorithms and parameters must be explicit and fingerprintable.  
```
RepositoryGraph

```
The canonical runtime deterministic graph.  
Runtime type:  
```

networkx.DiGraph


```
Graphify owns its internal:  
* node records and attributes;  
* edge records and attributes;  
* hyperedges stored in graph metadata;  
* identity normalization;  
* deduplication and endpoint resolution.  
The graph is treated as immutable after Layer 3 completes.  
```
GraphDiagnostics

```
Records graph-construction quality, information loss and publication blockers.  
Main content:  
* input and output node, edge and hyperedge counts;  
* invalid or dropped records;  
* dangling endpoints;  
* possible same-endpoint edge collapse;  
* isolated-node and community metrics;  
* FileIndex consistency failures;  
* severity and publication-blocking status.  
## Interfaces  
```
build_graph_intelligence

```
Primary Layer 3 entrypoint.  
**Input:**  
* RepositoryContext;  
* FileIndex;  
* private Graphify extraction result;  
* GraphConstructionConfig.  
**Output:**  
* RepositoryGraph;  
* GraphDiagnostics;  
* private Graphify derived runtime state.  
Coordinates graph construction, communities, structural analysis and validation.  
```
construct_repository_graph

```
Invokes Graphify’s retained graph builder with:  
```

directed = true
deduplication = true
semantic records absent


```
Returns the RepositoryGraph and private diagnostic observations.  
```
compute_community_structure

```
Runs Graphify’s existing:  
* community clustering;  
* cohesion calculation;  
* community member signatures;  
* deterministic hub-based labels.  
Returns Graphify-native private dictionaries. No Bridger CommunityStructure or CommunityRecord contract is introduced.  
```
analyze_graph_structure

```
Runs Graphify’s existing structural analysis:  
* god nodes;  
* surprising connections;  
* suggested questions.  
Returns Graphify-native private lists and dictionaries. No Bridger StructuralAnalysis contract is introduced.  
```
validate_graph_intelligence

```
Validates:  
* graph type and revision identity;  
* deterministic-only content;  
* graph paths against FileIndex;  
* node and edge validity;  
* hyperedge members;  
* possible edge collapse;  
* complete community coverage;  
* structural-analysis references.  
Returns GraphDiagnostics.  
## Locked rules and notes  
* Graphify’s extraction dictionary already exists as a private loose internal structure. Bridger does not implement a GraphifyExtractionData model.  
* Graphify’s nodes, edges, hyperedges, communities, cohesion maps, labels and structural-analysis dictionaries remain private and are not converted into Bridger domain models.  
* The canonical runtime graph is networkx.DiGraph.  
* MultiDiGraph is excluded from V0. Potential parallel-relation loss must be measured through diagnostics.  
* Community and structural-analysis outputs are deterministic derived intelligence, not direct repository facts.  
* Deterministic community labels remain inside the deterministic layer. AI-generated labels belong exclusively to Layer 5.  
* Hyperedges remain graph metadata and require explicit hyperedge-aware access.  
* Layer 3 must retain the private Graphify derived state until Layer 4 persists enough information to reconstruct:  
    * the directed graph;  
    * community membership;  
    * deterministic labels;  
    * community signatures;  
    * required structural-analysis outputs.  
* The NetworkX graph provides sufficient data for later graph traversal, querying and node/edge enrichment. Community navigation and enrichment additionally require the retained or persisted community metadata.  
* Graph-to-source and graph-to-symbol navigation will combine the RepositoryGraph, Layer 1 FileIndex and Layer 2 SymbolIndex.  
* Layer 3 does not serialize or publish artifacts. Graph lifecycle and persistence remain Layer 4 responsibilities.  
  
##   
# Locked Layer 4 — Graph lifecycle and persistence  
## Contracts  
```
ArtifactReference

```
Identifies one persisted artifact within a graph snapshot.  
```
path
sha256
size_bytes
GraphSnapshotManifest

```
Canonical lifecycle and compatibility record for one immutable graph snapshot.  
```
schema_version
snapshot_id

repository_id
revision
scope_path
file_index_digest

graph_contract_version
graphify_engine_version
extractor_fingerprint
inventory_policy_version
build_configuration_fingerprint

build_mode: full | incremental
parent_snapshot_id?

artifacts: map[str, ArtifactReference]

created_at
validation_status
diagnostics_summary

```
Required artifacts:  
```
graph.json
structural.json
diagnostics.json
graphify-manifest.json
GRAPH_REPORT.md
snapshot-manifest.json
GraphBuildResult

```
Common runtime result for build, update and load operations.  
```
operation_mode: full | incremental | loaded
graph: RepositoryGraph
manifest: GraphSnapshotManifest
diagnostics: GraphDiagnostics
snapshot_root

```
No GraphBuildRequest, GraphUpdateRequest or persisted lifecycle-state model is introduced.  
  
## Interfaces  
```
create_graph_snapshot

```
Publishes a full deterministic snapshot.  
**Input:**  
* RepositoryContext  
* FileIndex  
* RepositoryGraph  
* GraphDiagnostics  
* private Graphify derived state  
* GraphConstructionConfig  
* output root  
**Output:**  
* GraphBuildResult  
Process:  
1. Reject publication-blocking diagnostics.  
2. Serialize all artifacts into a staging directory.  
3. Generate checksums and the snapshot manifest.  
4. Validate the complete snapshot.  
5. Atomically publish it.  
6. Atomically update the current pointer.  
  
```
load_graph_snapshot

```
Loads an explicit snapshot or the current snapshot.  
**Input:**  
* graph storage root  
* optional snapshot_id  
**Output:**  
* GraphBuildResult  
It verifies the manifest, required artifacts, checksums, compatibility, graph direction, revision and scope before returning the runtime graph.  
It does not silently repair or rebuild invalid snapshots.  
  
```
update_graph_snapshot

```
Creates a new immutable snapshot through Graphify’s incremental update machinery.  
**Input:**  
* previous GraphSnapshotManifest  
* target RepositoryContext  
* target FileIndex  
* FileChangeSet  
* extraction configuration  
* GraphConstructionConfig  
* output root  
**Output:**  
* GraphBuildResult  
It re-extracts added and modified files, removes deleted or replaced contributions, recomputes derived graph intelligence and publishes a complete new snapshot.  
When compatibility or validation fails, it raises FullRebuildRequired.  
  
```
validate_graph_snapshot

```
Validates a staged or persisted snapshot.  
Checks include:  
* manifest schema;  
* required artifacts;  
* checksums and sizes;  
* repository identity, revision and scope;  
* graph and extractor compatibility;  
* inventory and configuration fingerprints;  
* graph reconstruction;  
* diagnostics and structural consistency;  
* absence of publication-blocking issues.  
  
## Locked rules and notes  
* GraphSnapshotManifest is Bridger’s lifecycle authority.  
* Graphify’s own manifest remains private operational state.  
* graph.json is the canonical persisted deterministic graph.  
* structural.json stores Graphify-native communities, cohesion, signatures, deterministic labels and structural-analysis outputs.  
* diagnostics.json stores GraphDiagnostics.  
* Snapshots are immutable after publication.  
* Every incremental update creates a new complete snapshot.  
* Only one writer may publish for a repository scope at a time.  
* Builds occur in a staging directory and become visible only after complete validation.  
* The previous current snapshot remains available when a build fails.  
* Readers must never observe a partially written or mixed snapshot.  
* Compatibility requires exact fingerprint matching in V0.  
* Any incompatible engine, extractor, graph contract, inventory policy, scope or build configuration requires a full rebuild.  
* Incremental update is an optimization; its final result must be semantically equivalent to a full build.  
* Shared AST and stat caches remain mutable operational state outside snapshots.  
* Cache contents are not canonical and may be deleted and rebuilt.  
* AI enrichment never modifies deterministic graph snapshots.  
* Continuous watch mode, Git hooks and pending-change queues are excluded from V0.  
* Retention limits, remote storage, migration adapters and historical graph-diff APIs are deferred.  
* The graph current pointer identifies the default deterministic graph snapshot, not the final Repository Brain artifact.  
  
##   
## 5 — AI enrichment overlay  
## Responsibility  
Layer 5 is entirely **Bridger-owned**.  
It consumes a published deterministic graph snapshot from Layer 4 and produces a separate immutable AI enrichment overlay.  
Graphify is not involved in Layer 5 execution.  
Layer 5 may add semantic interpretation such as:  
* community naming;  
* high-centrality / god-node labeling;  
* semantic categories;  
* importance explanations;  
* anomaly annotations;  
* entity, edge, or community scores once their metrics are formally defined.  
It must never mutate deterministic graph topology, structural confidence, or canonical graph facts.  
  
## Contracts  
```
GraphEnrichmentConfig

```
Configuration for one enrichment pass.  
```

provider
model
profile_version
enabled_features
max_concurrency


```
## Notes  
* profile_version versions the complete Bridger-owned enrichment prompt/policy bundle.  
* Model execution goes through Bridger's model runtime, not Graphify's provider configuration.  
* enabled_features allows enrichment capabilities to be activated independently.  
Initial feature set:  
```

community_names
high_centrality_labels


```
Future features can include:  
```

entity_scores
edge_scores
community_scores
importance_explanations
anomaly_annotations
semantic_categories


```
The exact score semantics remain deferred until their metrics are formally designed.  
  
```
EnrichmentRecord

```
Represents **one AI-generated annotation over one deterministic graph target**.  
```

enrichment_id
target_type
target_ref
annotation_type
value
confidence?
deterministic_features

target_type

```
Defines what deterministic graph entity the record annotates.  
Supported V0 target types:  
```

node
edge
hyperedge
community
graph


```
No separate NodeRef, EdgeRef, CommunityRef, etc. contracts are introduced.  
  
```
target_ref

```
Its shape depends on target_type.  
**Node**  
```

target_type = node

target_ref = node_id


```
The node ID must exist in the targeted RepositoryGraph.  
Example:  
```

{
  "target_type": "node",
  "target_ref": "src/payment/service.py::PaymentService"
}


```
  
**Edge**  
```

target_type = edge

target_ref = {
    source_node_id,
    target_node_id,
    relation
}


```
All three are required because Layer 3 uses nx.DiGraph and relation is part of the logical edge identity.  
Example:  
```

{
  "target_type": "edge",
  "target_ref": {
    "source_node_id": "PaymentService",
    "target_node_id": "StripeClient",
    "relation": "calls"
  }
}


```
The enclosing overlay already carries the graph snapshot identity, so snapshot_id is not duplicated inside the edge reference.  
  
**Hyperedge**  
```

target_type = hyperedge

target_ref = hyperedge_id


```
The ID must resolve against the hyperedges stored in graph metadata.  
Example:  
```

{
  "target_type": "hyperedge",
  "target_ref": "payment_flow_12"
}


```
  
**Community**  
```

target_type = community

target_ref = {
    community_id,
    member_signature
}


```
Both values are required.  
community_id alone is insufficient because community IDs are snapshot-relative and clustering may produce different memberships after graph changes.  
member_signature therefore binds the enrichment to the exact deterministic member set.  
Example:  
```

{
  "target_type": "community",
  "target_ref": {
    "community_id": 4,
    "member_signature": "a91b37e84cd88210"
  }
}


```
This follows the community-signature mechanism already retained from Graphify.  
  
**Whole graph**  
```

target_type = graph

target_ref = "graph"


```
The graph snapshot itself is identified by the enclosing GraphEnrichmentOverlay.graph_snapshot_id.  
This avoids repeating repository ID, revision, scope, or snapshot identity inside the record.  
  
```
annotation_type

```
Identifies the semantic meaning of the annotation.  
Examples:  
```

name
semantic_label
semantic_category
importance_explanation
anomaly
score:<metric_id>


```
This remains intentionally generic.  
Examples:  
```

name
score:architectural_importance
score:change_risk
semantic_category


```
The goal is to avoid separate schemas for community names, node classifications, scores, explanations, etc.  
  
```
value

```
Contains the actual AI-generated enrichment value.  
Examples:  
```

"Payment Processing"


"Core orchestration component"


0.87


{
  "category": "persistence_boundary",
  "explanation": "..."
}


```
Its exact shape depends on annotation_type.  
  
```
confidence

```
Optional AI confidence.  
It is explicitly distinct from Graphify's deterministic edge confidence such as:  
```

EXTRACTED
INFERRED
AMBIGUOUS


```
AI confidence must never overwrite or reinterpret structural confidence.  
  
```
deterministic_features

```
Records the deterministic graph evidence used by the model.  
Example:  
```

{
  "degree": 47,
  "community_size": 83,
  "cohesion": 0.31,
  "representative_nodes": [
    "PaymentService",
    "InvoiceRepository"
  ],
  "dominant_relations": [
    "calls",
    "imports"
  ]
}


```
Purpose:  
```

deterministic graph facts
        ↓
AI interpretation
        ↓
auditable EnrichmentRecord


```
This field provides the explicit trace between deterministic structure and model interpretation.  
It should contain bounded graph-derived features, not arbitrary repository source.  
  
```
GraphEnrichmentOverlay

```
Represents one immutable enrichment pass over exactly one deterministic graph snapshot.  
```

schema_version
overlay_id

graph_snapshot_id

generator_version
provider
model
profile_version
enabled_features

created_at

records: list[EnrichmentRecord]


```
## Notes  
* graph_snapshot_id is the authoritative binding to Layer 4.  
* Repository ID, revision and scope are not duplicated because they are available through the corresponding GraphSnapshotManifest.  
* Model/provider/profile metadata is overlay-level in V0 because one enrichment pass uses one configuration.  
* AI provenance therefore does not need to be repeated in every EnrichmentRecord.  
* A second enrichment pass over the same graph creates another immutable overlay_id.  
  
## Interfaces  
```
enrich_graph_snapshot

```
Primary Layer 4 → Layer 5 interface.  
```

enrich_graph_snapshot(
    graph_build: GraphBuildResult,
    config: GraphEnrichmentConfig,
)
    -> GraphEnrichmentOverlay


```
Conceptual flow:  
```

GraphBuildResult
        ↓
load graph + structural state
        ↓
select targets
        ↓
derive bounded deterministic features
        ↓
Bridger model inference
        ↓
parse EnrichmentRecord[]
        ↓
validate targets and evidence
        ↓
persist immutable overlay


```
## Important execution rule  
The model receives bounded graph-derived context.  
For example, community naming may use:  
```

community_id
member_signature
community size
cohesion
representative nodes
high-degree nodes
source-file distribution
important internal relations
cross-community relations


```
A high-centrality-node annotation may use:  
```

node attributes
degree
incoming/outgoing relations
community
neighbor summaries
structural-analysis signals


```
Layer 5 is therefore graph interpretation, not repository-wide source analysis.  
  
```
validate_graph_enrichment

```
Validates an overlay against its deterministic graph snapshot.  
```

validate_graph_enrichment(
    overlay,
    graph_build
) -> None


```
Validation includes:  
```

node
→ node exists

edge
→ source + target + relation exist

hyperedge
→ hyperedge exists

community
→ community exists
→ member_signature matches

graph
→ graph_snapshot_id matches


```
It also validates:  
* schema correctness;  
* confidence bounds;  
* supported annotation types;  
* uniqueness of (target, annotation_type) where required;  
* consistency of declared deterministic features;  
* absence of unknown deterministic targets.  
A failed validation means the overlay is not published.  
  
```
load_graph_enrichment

```
Loads an existing enrichment overlay for downstream use.  
```

load_graph_enrichment(
    artifact,
    expected_graph_snapshot_id
) -> GraphEnrichmentOverlay


```
The overlay must match the requested deterministic graph snapshot.  
Layer 6 later performs read-time composition:  
```

RepositoryGraph
+
GraphEnrichmentOverlay
=
enriched navigation view


```
Layer 5 itself does not mutate or materialize a new canonical graph.  
  
## Persistence  
One self-contained artifact per enrichment run:  
```

.bridger/
└── enrichment/
    └── <graph-snapshot-id>/
        └── <overlay-id>/
            └── graph-enrichment.json


```
No separate EnrichmentManifest is introduced.  
GraphEnrichmentOverlay already contains the required identity and generation metadata.  
The Repository Brain publication layer later decides which graph snapshot and which enrichment overlay belong together.  
  
## Locked rules and notes  
* Layer 5 is entirely Bridger-owned.  
* Graphify stops at deterministic graph construction, structural analysis, and persistence.  
* Bridger reimplements AI community naming rather than using Graphify's LLM label pipeline.  
* The same Bridger enrichment machinery extends to god-node labels, semantic categories, explanations, anomalies, and future scores.  
* AI enrichment is always physically separate from deterministic graph artifacts.  
* Enrichment must never create, delete, or rewrite deterministic nodes, edges, hyperedges, communities, or confidence values.  
* EnrichmentRecord is the single generic annotation contract for V0.  
* target_type determines how target_ref is interpreted.  
* target_ref never repeats graph_snapshot_id; the enclosing overlay already provides snapshot scope.  
* Node targets use stable Graphify node IDs.  
* Edge targets use (source_node_id, target_node_id, relation) within the targeted graph snapshot.  
* Hyperedge targets use the deterministic hyperedge ID.  
* Community targets require both community_id and member_signature.  
* Whole-graph enrichment uses target_ref = "graph".  
* Community IDs are not stable enough by themselves to support enrichment reuse.  
* AI confidence is separate from deterministic structural confidence.  
* deterministic_features records the bounded deterministic evidence used to generate each annotation.  
* Layer 5 consumes graph-derived structural context, not unrestricted repository contents.  
* The exact semantics of future scores remain deferred.  
* One enrichment pass uses one model/provider/profile configuration in V0.  
* Overlay lifecycle is immutable: rerunning enrichment creates a new overlay_id.  
* No per-record active/stale/superseded/rejected lifecycle field is introduced in V0.  
* Staleness is determined by graph-snapshot mismatch.  
* Supersession is determined by whichever overlay a later Repository Brain snapshot selects.  
* Rejected or invalid overlays are simply not published.  
* Layer 6 owns composition of deterministic graph plus enrichment for navigation and querying.  
  
##   
## 6 — Composite graph access and repository navigation  
## Responsibility  
Layer 6 provides the **unified read surface used by agents** across:  
```

RepositoryContext
FileIndex
SymbolIndex
RepositoryGraph
GraphSnapshotManifest / structural state
GraphEnrichmentOverlay
source contents


```
It is a **shared runtime capability**, not a new authority and not a persisted interpretation layer.  
Conceptually:  
```

Layers 1–5
   │
   ├── repository / FileIndex
   ├── SymbolIndex
   ├── deterministic graph
   └── AI enrichment overlay
   │
   ▼
RepositoryNavigator
   │
   ▼
search → inspect → traverse → locate → read evidence


```
No composite graph artifact is created.  
  
## Contracts  
```
CompositeEntityView

```
Read-time representation of one graph entity together with any matching AI enrichment.  
```

target_type
target_ref

deterministic
enrichment: list[EnrichmentRecord]


```
Supported targets reuse the Layer 5 identity rules.  
## Node  
```

target_type = node
target_ref = node_id


```
## Edge  
```

target_type = edge

target_ref = {
    source_node_id,
    target_node_id,
    relation
}


```
## Hyperedge  
```

target_type = hyperedge
target_ref = hyperedge_id


```
## Community  
```

target_type = community

target_ref = {
    community_id,
    member_signature
}


```
## Whole graph  
```

target_type = graph
target_ref = "graph"


```
## Important notes  
deterministic and enrichment remain explicitly separate.  
```

CompositeEntityView
├── deterministic
│   └── canonical graph facts
│
└── enrichment
    └── derived EnrichmentRecord[]


```
Layer 6 never copies AI-generated values into deterministic graph attributes.  
The view is runtime-only and is not persisted.  
  
```
RepositorySearchHit

```
Lightweight result returned by structured repository search.  
```

kind
ref
label
source_path?
score?


```
Supported V0 kinds:  
```

node
community
hyperedge
file
symbol

ref

```
Reuses the existing identity of the underlying entity:  
```

node
→ node_id

community
→ { community_id, member_signature }

hyperedge
→ hyperedge_id

file
→ repository-relative path

symbol
→ symbol_id


```
## Rationale  
search_repository() searches heterogeneous structures. Returning full graph entities, FileRecords or SymbolRecords directly would produce unnecessarily large results.  
RepositorySearchHit is only a bounded discovery result:  
```

search
   ↓
RepositorySearchHit
   ↓
explicit inspection / traversal / source read


```
It is runtime-only and never becomes an authoritative repository object.  
## Edges are excluded from generic V0 search  
Edges remain fully navigable through traversal but are not general search-entry entities.  
The reasoning is:  
* most edge searchable text is already represented by its source node, target node and relation;  
* generic relations such as calls or imports would create large noisy result sets;  
* agents usually discover relationships after locating an entity.  
Typical flow:  
```

search "PaymentService"
        ↓
PaymentService
        ↓
outgoing relations
        ↓
PaymentService --calls--> StripeClient


```
This can be revisited if future edge enrichment creates rich edge semantics that are useful as direct search targets.  
  
## Primary runtime interface  
```
RepositoryNavigator

```
Unified Layer 6 read interface.  
It operates over existing immutable Layer 1–5 data rather than owning copies.  
Conceptually initialized from:  
```

RepositoryContext
FileIndex
SymbolIndex
GraphBuildResult
optional GraphEnrichmentOverlay


```
No additional RepositoryNavigationContext contract is introduced in V0.  
The navigator remains functional when no enrichment overlay exists.  
  
## Interfaces and capabilities  
## 1. search_repository  
Structured repository orientation search.  
Searches the indexed/read-time representation of:  
* graph node labels;  
* community labels;  
* AI enrichment names/categories where available;  
* hyperedge metadata;  
* file paths;  
* symbol names;  
* qualified symbol names.  
```

search_repository(query, filters?, limit?)
    -> RepositorySearchHit[]


```
This is **not source-text search**.  
Its purpose is to locate repository entities that an agent can inspect or navigate from.  
Example:  
```

"authentication"
    ↓
Community: Authentication & Sessions
Node: AuthMiddleware
Symbol: validate_session
File: src/auth/middleware.py


```
V0 should use simple deterministic lexical/fuzzy search. No embedding index or vector database is required.  
AI enrichment may improve matching/ranking, but every returned hit must resolve to an existing deterministic graph/file/symbol entity.  
  
## 2. get_graph_entity  
Inspect one graph entity through the composite view.  
```

get_graph_entity(target_type, target_ref)
    -> CompositeEntityView


```
Supports:  
* node;  
* edge;  
* hyperedge;  
* community;  
* whole graph.  
This is the standard agent-facing way to retrieve deterministic graph information plus matching enrichment while preserving provenance.  
  
## Graph traversal capabilities  
Layer 6 must provide bounded traversal for:  
```

neighbors
incoming relations
outgoing relations
relation filtering

shortest paths

bounded neighborhoods / subgraphs

community members

cross-community connections

central / god nodes

hyperedge membership


```
Suggested interfaces:  
```

get_graph_neighbors
get_graph_path
get_graph_subgraph
get_graph_community
get_graph_central_nodes


```
Exact tool signatures can be designed separately.  
All traversal is bounded by explicit limits such as:  
```

depth
max_nodes
max_edges
relation filters
direction


```
Agents should not receive an unrestricted full-graph dump by default.  
  
## Graph ↔ repository navigation  
```
graph_to_file

graph_to_file(node_id)
    -> FileRecord?


```
Uses deterministic source_file information from the graph and resolves it through the authoritative FileIndex.  
No duplicate file representation is introduced.  
  
```
graph_to_symbols

graph_to_symbols(node_id)
    -> SymbolRecord[]


```
Attempts deterministic mapping from a graph node to indexed symbols.  
Potential matching evidence includes:  
1. exact source location/span when available;  
2. source file + qualified name;  
3. source file + symbol name;  
4. compatible deterministic source-location information.  
There is no assumption that:  
```

one graph node == one symbol


```
The result may contain zero, one or multiple symbols.  
No AI or fuzzy semantic inference is used to manufacture mappings.  
  
```
file_to_graph

file_to_graph(path)
    -> graph node refs[]


```
Returns all graph nodes deterministically associated with that source file.  
A single source file may naturally contribute many graph entities.  
  
```
symbol_to_graph

symbol_to_graph(symbol_id)
    -> graph node refs[]


```
The mapping cardinality is explicitly:  
```

SymbolRecord → 0..N graph nodes


```
Layer 6 never forces uniqueness.  
If multiple graph entities can be deterministically associated with the symbol, all are returned.  
If no deterministic association can be established, the result is empty.  
## Matching rule  
Use progressively available deterministic evidence:  
```

exact source span/location
        ↓
source_file + qualified name
        ↓
source_file + symbol name/type
        ↓
other exact structural metadata


```
No candidate-confidence subsystem is introduced.  
No semantic/fuzzy matching is performed here.  
If the agent wants to investigate an unresolved correspondence, it can use repository search and graph traversal itself.  
  
## File and symbol navigation  
Layer 6 exposes navigation over the existing Layer 1 and Layer 2 authorities.  
Required capabilities include:  
```

list_files
get_file_overview

list_symbols
search_symbols
read_symbol_excerpt


```
These do not redefine FileRecord, FileIndex, SymbolRecord or SymbolIndex.  
Layer 6 delegates to those underlying components.  
  
## Source evidence access  
```
search_source_content

```
New Layer 6 interface for bounded source-text search.  
The previous Bridger search_with_context interface is discarded as part of the redesign.  
search_source_content must be implemented against the new Layers 1–2 contracts and access rules.  
Conceptually:  
```

search_source_content(
    query / regex,
    path filters?,
    context lines?,
    limits?
)


```
It searches actual readable repository contents and returns bounded, line-addressable matches with surrounding context.  
Search must respect:  
* canonical FileIndex membership;  
* FileDisposition;  
* Git-tracked scope;  
* read restrictions;  
* explicit result limits;  
* deterministic repository-relative paths.  
  
## Difference from search_repository  
They search different spaces.  
```
search_repository

```
Structured orientation:  
```

graph
communities
enrichment
symbols
file paths


```
Returns:  
```

RepositorySearchHit[]

search_source_content

```
Actual repository text:  
```

source code
configuration
documentation
comments
string literals
etc.


```
Returns bounded source evidence.  
Typical agent flow:  
```

search_repository
       ↓
identify architecture/entity
       ↓
graph traversal
       ↓
file / symbol resolution
       ↓
search_source_content
or bounded direct read
       ↓
source evidence


```
  
## Bounded evidence-read capabilities  
Layer 6 must additionally expose:  
```

read_symbol_excerpt
read_file_ranges
read_around_match


```
These reads remain governed by Layer 1/2 authority.  
They must be:  
* bounded;  
* line-addressable;  
* exact-source based;  
* disposition-aware;  
* restricted to the repository scope.  
  
## Proposed agent navigation tool surface  
Without locking exact signatures yet:  
```

Composite / search
------------------
search_repository
get_graph_entity

Graph traversal
---------------
get_graph_neighbors
get_graph_path
get_graph_subgraph
get_graph_community
get_graph_central_nodes

Graph ↔ repository
------------------
graph_to_file
graph_to_symbols
file_to_graph
symbol_to_graph

Repository navigation
---------------------
list_files
get_file_overview
list_symbols
search_symbols

Source evidence
---------------
search_source_content
read_symbol_excerpt
read_file_ranges
read_around_match


```
The tools are different views over one RepositoryNavigator capability rather than independent data authorities.  
  
## Locked rules and notes  
* Layer 6 is a **shared read capability**, not a repository authority.  
* Layer 6 persists no canonical repository data.  
* No composite-graph.json or equivalent artifact exists.  
* RepositoryGraph remains immutable.  
* GraphEnrichmentOverlay remains immutable.  
* Graph and enrichment are composed only at read time.  
* Deterministic facts and AI enrichment always remain distinguishable.  
* Layer 6 must work without an enrichment overlay.  
* An enrichment overlay targeting a different graph snapshot must be rejected.  
* RepositorySearchHit is a lightweight runtime search envelope, not a domain authority.  
* Generic V0 repository search includes nodes, communities, hyperedges, files and symbols.  
* Edges are excluded from generic V0 search and reached through graph traversal.  
* Search enrichment can improve discoverability but cannot create new navigation entities.  
* search_repository searches structured repository entities.  
* search_source_content searches actual repository contents.  
* The old Bridger search_with_context interface is discarded and must not constrain the new implementation.  
* search_source_content must be reimplemented against the newly locked FileIndex, FileDisposition and source-read contracts.  
* File navigation remains grounded in Layer 1's authoritative FileIndex.  
* Symbol navigation remains grounded in Layer 2's authoritative SymbolIndex.  
* Graph nodes and SymbolRecords are distinct concepts.  
* No 1:1 graph↔symbol relationship is assumed.  
* graph_to_symbols and symbol_to_graph may return zero, one or many mappings.  
* Only deterministic mappings are returned.  
* Layer 6 does not introduce fuzzy/AI inference to resolve graph↔symbol ambiguity.  
* Ambiguous or unsupported mappings are not guessed.  
* Graph traversal is bounded by default.  
* Source search and evidence reads are bounded by default.  
* Agents should move from structural orientation toward exact source evidence rather than receiving repository-wide context dumps.  
* Higher-level repository interpretation remains the responsibility of consuming agents.  
The final Layer 6 flow is therefore:  
```

structured search
      ↓
graph inspection / traversal
      ↓
file + symbol navigation
      ↓
source search / bounded reads
      ↓
grounded evidence

```
  
  
# TO BE DEFINED - SUGGESTIONS ONLY FOR NOW, NOT LOCKED VERSION  
##   
## 7. Memory-agent orchestration and runtime  
Replaces the old Context Plan-centred runtime:  
```
BrainGenerationRun
MemoryTaskSpec
AgentTaskState
TaskCheckpoint
TaskEvent
ExecutionBudget
TaskCompletionRequest
TaskResult

```
Interfaces:  
```
create_memory_run()
assign_memory_task()
checkpoint_task()
resume_task()
request_task_completion()
validate_task_result()

```
This layer owns orchestration, budgets, resumability, retries, model execution and completion decisions.  
##   
## 8. Evidence-backed knowledge bundles  
Defines what memory agents produce:  
```
KnowledgeDocument
KnowledgeMetadata
ClaimRecord
EvidenceReference
CoverageSummary
ContradictionRecord
KnowledgeValidationReport

```
Logical bundle:  
```
<memory-id>.md
<memory-id>.meta.json
<memory-id>.claims.json

```
These are durable artifacts, not runtime state.  
##   
## 9. Repository Brain assembly and publication  
Defines the final product snapshot:  
```
RepositoryBrainBuildRequest
RepositoryBrainManifest
RepositoryBrainSnapshot
ComponentReference
PublicationValidationReport

```
Interfaces:  
```
assemble_repository_brain()
validate_repository_brain()
publish_repository_brain()
load_repository_brain()

```
This layer ensures revision consistency, checksums, required components and atomic publication.  
##   
## 10. Retrieval and external access  
Defines the provider-neutral read interface:  
```
RetrievalRequest
RetrievalContextPackage
KnowledgeCatalogEntry
EvidenceExpansionRequest
RetrievalWarning

```
Surfaces:  
```
Python/application API
CLI
MCP resources and tools
future HTTP API

```
All interfaces are read-only and progressively disclose evidence.  
##   
## 11. Product consumers  
Downstream adapters:  
```
BridgerPromptRequest / Result
BridgerTicketRequest / Result

```
They consume retrieval contracts but cannot mutate canonical Repository Brain artifacts.  
## Template for each layer  
For every segment, we should produce the same decision set:  
```
1. Responsibility and explicit exclusions
2. Authority and ownership
3. Runtime data models
4. Persisted data models
5. Input and output contracts
6. Operations and interface signatures
7. Public / internal / private classification
8. Lifecycle and state transitions
9. Validation, diagnostics and errors
10. Versioning and compatibility
11. Existing models to retain, adapt or remove

```
The correct starting point is **Layer 0: shared contract foundations**, followed immediately by **Layer 1: repository source and intake**.  
