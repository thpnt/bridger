---
name: bridger-graph
description: Use Bridger's repository graph to discover and traverse structural relationships in a codebase. Apply when determining what calls, depends on, connects to, surrounds, or belongs with a repository entity; tracing paths between components; exploring subsystem boundaries or graph communities; or following structural context returned by Bridger. Prefer graph-native exploration over broad repository searching when the missing information is relationship topology.
---

# Bridger Graph

Use Bridger's repository graph when the task requires discovering **structural relationships** in the codebase.

The graph complements Bridger's higher-level repository intelligence:

```text
understand
→ semantic repository orientation

graph tools
→ structural relationship discovery

impact
→ potential blast radius of changing exact symbols
```

Source code remains authoritative for exact implementation behavior.

## Available graph tools

Bridger exposes:

```text
query_graph
search_repository
get_graph_entity
get_graph_neighbors
get_graph_subgraph
get_graph_path
list_graph_communities
get_graph_community
```

These tools operate over the same repository revision and graph snapshot used by `understand` and `impact`.

## When to use graph-native exploration

Use the graph when the question is fundamentally about relationships.

Typical questions include:

```text
What calls this?

What does this depend on?

What depends on this?

How are A and B connected?

What components surround this service?

What belongs to this subsystem?

What crosses this subsystem boundary?

How does execution move from this component toward another one?

Which parts of the repository are structurally grouped together?
```

Prefer graph-native exploration over broad repository-wide searching when discovering these relationships.

Do not use graph tools merely because they are available.

For questions primarily about meaning, architecture, business rules, conventions, or how a subsystem works conceptually, prefer:

```text
understand(query)
```

For the blast radius of modifying already identified exact symbols, prefer:

```text
impact(symbols)
```

## Start from the right entry point

There are two primary ways to enter the graph.

### `query_graph` — conceptual discovery

Use `query_graph` when you know the relationship question but do not yet know the exact graph entities.

Examples:

```text
How does repository initialization connect to the memory runtime?

What is structurally involved around fleet reconciliation?

Where does request validation connect to persistence?
```

`query_graph` returns a bounded structural context including:

- seed node IDs;
- graph nodes;
- edges;
- communities;
- source locations when available;
- whether the result was truncated.

Use its returned node IDs as starting points for exact traversal.

Do not repeatedly issue broad `query_graph` calls once suitable graph entities have been identified. Continue through the graph instead.

### `search_repository` — resolve known entities

Use `search_repository` when you already know a name or concept and need its canonical repository identity.

Examples:

```text
FleetRuntimeStore
RepositoryNavigator
PersistenceManager
```

It can return:

```text
node
community
hyperedge
file
symbol
```

When performing graph navigation, prefer graph entity results such as nodes, communities, and hyperedges when appropriate.

If several candidates are returned, inspect them rather than guessing.

## Inspect exact entities

Use:

```text
get_graph_entity
```

after identifying an exact graph entity.

This is useful for inspecting:

- nodes;
- edges;
- hyperedges;
- communities;
- the graph entity itself.

The result distinguishes:

```text
deterministic
→ structural facts from the repository graph

enrichment
→ additional generated graph intelligence
```

Do not treat enrichment as stronger evidence than deterministic structure or source code.

For ordinary relationship traversal, a node ID returned by `query_graph` or `search_repository` can often be used directly with the traversal tools without calling `get_graph_entity` first.

Call it when the additional entity details or enrichment are useful.

## Follow direct relationships

Use:

```text
get_graph_neighbors
```

when you need the immediate topology around one known node.

Typical uses:

```text
Who calls this node?

What does this node call?

What is directly connected to this component?

Which immediate dependencies surround this node?
```

The tool supports direction:

```text
incoming
outgoing
both
```

Interpret direction relative to the graph edge direction.

Use:

```text
incoming
```

when interested in relationships entering the node.

Use:

```text
outgoing
```

when interested in relationships leaving the node.

Use:

```text
both
```

when exploring the local neighborhood without a directional constraint.

The tool also supports filtering by exact graph relations.

Do not guess relation names unnecessarily. If the relevant relation vocabulary is not yet known, inspect unfiltered graph results first and then narrow subsequent traversal if useful.

## Expand a local topology

Use:

```text
get_graph_subgraph
```

when one-hop neighbors are insufficient and you need a bounded multi-hop view around a known node.

Typical uses:

```text
Explore the subsystem around this service.

Show the structural neighborhood within two hops.

What components participate around this runtime component?
```

Control exploration using:

- depth;
- direction;
- relation filters;
- node bounds;
- edge bounds.

Prefer the smallest depth that answers the question.

Do not request a large subgraph when one-hop neighbors or a focused path can answer the question more precisely.

## Connect two known entities

Use:

```text
get_graph_path
```

when both endpoints are known and the question is how they connect.

Examples:

```text
How is HTTPHandler connected to PersistenceStore?

What structural chain connects initialization to fleet reconciliation?

Is component A connected to component B through this dependency direction?
```

Use exact graph node IDs obtained from prior graph discovery.

The tool supports:

- traversal direction;
- relation filters;
- maximum depth;
- bounded node exploration.

If the result contains no path:

```text
truncated = false
→ no path exists within the exhaustively searched requested topology

truncated = true
→ traversal bounds prevented an exhaustive conclusion
```

Do not interpret a truncated empty result as proof that no connection exists.

## Explore structural communities

Use:

```text
list_graph_communities
```

when you need repository-wide structural grouping or do not yet know which subsystem to investigate.

This is useful for questions such as:

```text
What major structural clusters exist?

Which subsystem appears relevant to this area?

How is the repository structurally partitioned?
```

Once a relevant community is identified, use:

```text
get_graph_community
```

to inspect:

- the community;
- member nodes;
- internal edges;
- cross-community edges;
- completeness of the returned materialization.

Cross-community edges are especially useful when investigating subsystem boundaries and integration points.

Do not enumerate every community by default when a focused node-based query already identifies the relevant area.

## Prefer traversal after discovery

Once an exact graph node is known, prefer traversing from it instead of repeatedly performing new searches.

Recommended pattern:

```text
conceptual relationship question
        ↓
query_graph
        │
        ├── identity unclear
        │       ↓
        │   search_repository
        │
        ▼
exact node
        ↓
get_graph_neighbors
or
get_graph_subgraph
or
get_graph_path
        ↓
follow returned topology
```

Use search to enter the graph.

Use traversal to navigate it.

## Move from graph to source

Graph exploration is a discovery mechanism, not a substitute for source inspection.

Graph nodes and edges may provide:

- source paths;
- source line ranges;
- edge evidence locations;
- symbol identifiers.

Once the relevant implementation area has been identified, use the coding agent's normal repository tools to inspect the actual source.

For example:

```text
graph traversal
    ↓
src/runtime/store.py:L40-L90
    ↓
read source directly
    ↓
reason from implementation
```

Do not keep traversing the graph when the remaining question requires implementation-level detail.

## Use `impact` for changes

Graph traversal and impact analysis answer different questions.

Graph tools answer:

```text
How are these things structurally related?
```

`impact` answers:

```text
What could be structurally affected if I change these exact symbols?
```

Once source inspection identifies the exact symbols likely to change, use `impact` when the modification has meaningful non-local structural risk.

Do not reproduce impact analysis manually through repeated neighbor or subgraph calls when `impact` is the correct operation.

## Respect graph completeness

Several graph tools return bounded results.

Always inspect:

```text
truncated
```

If `truncated` is true:

- treat the result as incomplete;
- do not infer that omitted relationships do not exist;
- narrow the question or traversal when possible;
- increase bounds only when additional topology is genuinely required;
- inspect source when graph expansion is no longer efficient.

Silence beyond a truncation boundary is not evidence of absence.

## Respect exact identities

Traversal tools operate on graph node IDs.

Prefer IDs returned directly by Bridger rather than reconstructing or guessing them.

When discovery returns multiple plausible entities:

1. inspect the candidates;
2. use their labels, source paths, types, or enrichment to disambiguate;
3. continue with the exact selected identity.

Do not arbitrarily choose between ambiguous entities.

## Keep exploration efficient

Choose the smallest operation that answers the structural question.

Prefer:

```text
get_graph_neighbors
```

over a large subgraph for one-hop questions.

Prefer:

```text
get_graph_path
```

over exploratory multi-hop expansion when both endpoints are already known.

Prefer:

```text
get_graph_subgraph
```

when the local topology itself is the object of investigation.

Prefer:

```text
get_graph_community
```

when investigating subsystem membership or boundaries.

Avoid issuing overlapping graph calls that reproduce context already returned by an earlier call.

## Recommended coding workflow

For a coding task involving structural discovery:

```text
1. Understand the task.

2. If semantic repository context is missing:
   use `understand`.

3. If the missing information is structural relationships:
   enter the graph with `query_graph` or `search_repository`.

4. Navigate using the smallest appropriate operation:
   - `get_graph_neighbors`
   - `get_graph_subgraph`
   - `get_graph_path`
   - community tools

5. Follow returned source locations into the actual repository.

6. Inspect the relevant implementation directly.

7. Identify the exact symbols that may change.

8. If the change has meaningful structural blast radius:
   use `impact`.

9. Implement and run the repository's normal validation.
```

This is a heuristic, not a mandatory sequence.

## Avoid unnecessary graph use

Skip graph-native exploration when:

- the exact implementation location is already known;
- the question is strictly local to one file or function;
- direct source inspection already answers the relationship question;
- the task is primarily semantic and `understand` is more appropriate;
- you already have sufficient graph context from an earlier call.

Do not turn every coding task into a graph traversal.

## Source authority

The repository graph represents structural knowledge derived from a pinned repository revision.

Use it to make discovery and relationship reasoning more efficient.

For exact behavior, implementation details, edge cases, and modifications, verify conclusions against:

- source code;
- tests;
- configuration;
- repository-native documentation when relevant.

The graph tells you where and how repository entities are structurally related.

The source tells you exactly what the software does.