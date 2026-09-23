"""Focused tests for canonical consumption result presentation."""

import pytest

from bridger.contracts.consumption import (
    BrainContext,
    Completeness,
    ConsumptionRevision,
    GraphCommunity,
    GraphEdge,
    GraphNode,
    ImpactGraph,
    ImpactNode,
    ImpactResolutionIssue,
    ImpactResult,
    ResolvedImpactRoot,
    UnderstandGraphContext,
    UnderstandResult,
)
from bridger.contracts.symbols import SymbolRecord
from bridger.presentation import render_intelligence_json, render_intelligence_markdown

REVISION = "a" * 40


def _revision() -> ConsumptionRevision:
    return ConsumptionRevision(
        repository_id="sonore",
        repository_revision=REVISION,
        graph_snapshot_id="gs_21fd",
        enrichment_overlay_id="ge_82ca",
    )


def _brain_context(**overrides: object) -> BrainContext:
    values: dict[str, object] = {
        "path": ".bridger/memory/business-logic/calls.md",
        "heading": "Incoming call lifecycle",
        "start_line": 42,
        "end_line": 67,
        "excerpt": "CallManager owns the transition.\n\n*Retry* **carefully**.",
        "semantic_owner": "business-logic",
    }
    values.update(overrides)
    return BrainContext(**values)  # type: ignore[arg-type]


def _understand(
    *,
    brain_context: list[BrainContext] | None = None,
    graph_context: UnderstandGraphContext | None = None,
    completeness: Completeness | None = None,
    warnings: list[str] | None = None,
) -> UnderstandResult:
    return UnderstandResult(
        query="incoming call",
        revision=_revision(),
        brain_context=brain_context or [],
        graph_context=graph_context or UnderstandGraphContext(),
        completeness=completeness or Completeness(),
        warnings=warnings or [],
    )


def _impact(
    *,
    roots: list[ResolvedImpactRoot] | None = None,
    graph: ImpactGraph | None = None,
    brain_enrichment: list[BrainContext] | None = None,
    completeness: Completeness | None = None,
    warnings: list[str] | None = None,
) -> ImpactResult:
    return ImpactResult(
        revision=_revision(),
        requested_symbols=["CallManager"],
        resolved_roots=roots or [],
        affected_graph=graph or ImpactGraph(),
        brain_enrichment=brain_enrichment or [],
        completeness=completeness or Completeness(),
        warnings=warnings or [],
    )


def _symbol(
    symbol_id: str,
    name: str,
    path: str,
    start_line: int,
    end_line: int,
    *,
    qualified_name: str | None = None,
    kind: str = "class",
) -> SymbolRecord:
    return SymbolRecord(
        symbol_id=symbol_id,
        name=name,
        qualified_name=qualified_name,
        kind=kind,  # type: ignore[arg-type]
        path=path,
        start_line=start_line,
        end_line=end_line,
    )


def test_json_returns_canonical_pydantic_dump() -> None:
    for result in (_understand(), _impact()):
        assert render_intelligence_json(result) == result.model_dump(mode="json")


def test_understand_renders_brain_graph_coordinates_and_warnings_exactly() -> None:
    result = _understand(
        brain_context=[_brain_context()],
        graph_context=UnderstandGraphContext(
            seed_node_ids=["class:CallManager"],
            nodes=[
                GraphNode(
                    node_id="class:CallManager",
                    label="CallManager",
                    symbol_ids=["symbol_92", "symbol_93"],
                    source_path="src/calls/manager.py",
                    source_start_line=21,
                    source_end_line=146,
                    community_id=4,
                ),
                GraphNode(
                    node_id="CallSession",
                    label="CallSession",
                    source_path="src/calls/session.py",
                    source_start_line=48,
                    source_end_line=48,
                ),
            ],
            edges=[
                GraphEdge(
                    source_node_id="CallSession",
                    target_node_id="class:CallManager",
                    relation="calls",
                    evidence="callback binding",
                    evidence_path="src/calls/session.py",
                    evidence_start_line=48,
                    evidence_end_line=48,
                )
            ],
            communities=[GraphCommunity(community_id=4, label="Call lifecycle")],
        ),
        warnings=["dense Brain retrieval unavailable; BM25 fallback used."],
    )

    assert render_intelligence_markdown(result) == (
        "# UNDERSTAND\n"
        f"State: sonore@{REVISION} | graph=gs_21fd | overlay=ge_82ca\n"
        "Complete: brain=yes | graph=yes\n"
        "Warning: dense Brain retrieval unavailable; BM25 fallback used.\n"
        "\n"
        "## Brain\n"
        "\n"
        "`.bridger/memory/business-logic/calls.md:L42-L67` | Incoming call lifecycle | business-logic\n"
        "> CallManager owns the transition.\n"
        ">\n"
        "> *Retry* **carefully**.\n"
        "\n"
        "## Graph\n"
        "\n"
        "Seeds: N1\n"
        "\n"
        "Nodes:\n"
        "N1 CallManager | src/calls/manager.py:L21-L146 | id=class:CallManager | "
        "sym=symbol_92,symbol_93 | C4\n"
        "N2 CallSession | src/calls/session.py:L48\n"
        "\n"
        "Edges:\n"
        "N2 -calls-> N1 @ src/calls/session.py:L48 | callback binding\n"
        "\n"
        "Communities: C4=Call lifecycle\n"
    )


def test_understand_empty_substrates_and_truncation_are_explicit() -> None:
    result = _understand(
        completeness=Completeness(brain_truncated=True, graph_truncated=True)
    )

    assert render_intelligence_markdown(result) == (
        "# UNDERSTAND\n"
        f"State: sonore@{REVISION} | graph=gs_21fd | overlay=ge_82ca\n"
        "Complete: brain=no | graph=no\n"
        "Note: truncated sections may omit relevant results.\n"
        "\n"
        "## Brain\n"
        "\n"
        "No matches.\n"
        "\n"
        "## Graph\n"
        "\n"
        "No matches.\n"
    )


def test_node_without_optional_coordinates_and_community_omits_them() -> None:
    result = _understand(
        graph_context=UnderstandGraphContext(
            nodes=[
                GraphNode(node_id="same", label="same", source_path="src/only.py"),
                GraphNode(node_id="without-source", label="without-source"),
            ]
        )
    )
    rendered = render_intelligence_markdown(result)
    assert "N1 same | src/only.py\n" in rendered
    assert "N2 without-source\n" in rendered
    assert "id=same" not in rendered
    assert "Communities:" not in rendered


def test_impact_renders_roots_depth_important_nodes_and_empty_brain() -> None:
    graph = ImpactGraph(
        nodes=[
            ImpactNode(
                node_id="id-a",
                label="CallManager",
                symbol_ids=["symbol_92"],
                source_path="src/calls/manager.py",
                source_start_line=21,
                source_end_line=146,
                community_id=4,
                depth=0,
            ),
            ImpactNode(
                node_id="id-b",
                label="Webhook",
                source_path="src/http/webhook.py",
                source_start_line=51,
                source_end_line=51,
                community_id=2,
                depth=1,
            ),
        ],
        edges=[
            GraphEdge(
                source_node_id="id-b",
                target_node_id="id-a",
                relation="calls",
                evidence_path="src/http/webhook.py",
                evidence_start_line=51,
                evidence_end_line=51,
            )
        ],
        communities=[
            GraphCommunity(community_id=2, label="HTTP integrations"),
            GraphCommunity(community_id=4, label="Call lifecycle"),
        ],
        important_node_ids=["id-b"],
    )
    result = _impact(
        roots=[
            ResolvedImpactRoot(selector="CallManager", graph_node_ids=["id-a"]),
            ResolvedImpactRoot(selector="Webhook", graph_node_ids=["id-b"]),
        ],
        graph=graph,
        completeness=Completeness(graph_truncated=True),
    )

    assert render_intelligence_markdown(result) == (
        "# IMPACT\n"
        "Potential structural impact; not guaranteed semantic breakage.\n"
        f"State: sonore@{REVISION} | graph=gs_21fd | overlay=ge_82ca\n"
        "Complete: brain=yes | graph=no\n"
        "Note: truncated sections may omit relevant results.\n"
        "\n"
        "Roots:\n"
        "CallManager -> N1\n"
        "Webhook -> N2\n"
        "\n"
        "## Affected graph\n"
        "\n"
        "Nodes:\n"
        "N1 [d0] CallManager | src/calls/manager.py:L21-L146 | id=id-a | sym=symbol_92 | C4\n"
        "N2 [d1] Webhook | src/http/webhook.py:L51 | id=id-b | C2\n"
        "\n"
        "Edges:\n"
        "N2 -calls-> N1 @ src/http/webhook.py:L51\n"
        "\n"
        "Important: N2\n"
        "\n"
        "Communities: C2=HTTP integrations | C4=Call lifecycle\n"
        "\n"
        "## Brain enrichment\n"
        "\n"
        "No lexical matches.\n"
    )


def test_impact_multi_node_root_and_brain_enrichment() -> None:
    graph = ImpactGraph(
        nodes=[
            ImpactNode(node_id="id-a", label="A", depth=0),
            ImpactNode(node_id="id-b", label="B", depth=0),
        ]
    )
    result = _impact(
        roots=[
            ResolvedImpactRoot(selector="SomeSymbol", graph_node_ids=["id-a", "id-b"])
        ],
        graph=graph,
        brain_enrichment=[_brain_context()],
    )
    rendered = render_intelligence_markdown(result)
    assert "SomeSymbol -> N1 N2" in rendered
    assert "## Affected graph" in rendered
    assert "## Brain enrichment" in rendered
    assert rendered.index("## Affected graph") < rendered.index("## Brain enrichment")
    assert "No lexical matches." not in rendered


@pytest.mark.parametrize(
    ("reason", "candidates", "expected_issue"),
    [
        ("not_found", [], "MissingThing | not_found"),
        ("not_in_graph", [], "SomeSymbol | not_in_graph"),
        (
            "ambiguous",
            [
                _symbol(
                    "symbol_a1",
                    "CallManager",
                    "src/api/calls.py",
                    12,
                    80,
                    qualified_name="api.CallManager",
                ),
                _symbol(
                    "symbol_b7",
                    "CallManager",
                    "src/worker/calls.py",
                    9,
                    67,
                    qualified_name="worker.CallManager",
                ),
            ],
            "  symbol_a1 | api.CallManager | class | src/api/calls.py:L12-L80\n"
            "  symbol_b7 | worker.CallManager | class | src/worker/calls.py:L9-L67",
        ),
    ],
)
def test_impact_resolution_failures_do_not_render_traversal(
    reason: str,
    candidates: list[SymbolRecord],
    expected_issue: str,
) -> None:
    selector = "MissingThing" if reason == "not_found" else "SomeSymbol"
    result = ImpactResult(
        revision=_revision(),
        requested_symbols=[selector],
        resolution_issues=[
            ImpactResolutionIssue(
                selector=selector,
                reason=reason,  # type: ignore[arg-type]
                candidates=candidates,
            )
        ],
        completeness=Completeness(),
    )

    rendered = render_intelligence_markdown(result)
    candidate_lines = "".join(
        f"  {candidate.symbol_id} | {candidate.qualified_name or candidate.name} | "
        f"{candidate.kind} | {candidate.path}:L{candidate.start_line}-L{candidate.end_line}\n"
        for candidate in candidates
    )
    assert rendered == (
        "# IMPACT\n"
        "Potential structural impact; not guaranteed semantic breakage.\n"
        f"State: sonore@{REVISION} | graph=gs_21fd | overlay=ge_82ca\n"
        "\n"
        "Resolution failed; traversal not executed.\n"
        "\n"
        "Issues:\n"
        f"{selector} | {reason}\n"
        f"{candidate_lines}"
    )
    if not candidates:
        assert expected_issue in rendered
    assert "Complete:" not in rendered
    assert "Roots:" not in rendered
    assert "Affected graph" not in rendered
    assert "Brain enrichment" not in rendered
