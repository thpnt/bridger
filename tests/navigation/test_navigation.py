"""Focused Layer 6 composition and repository navigation invariants."""

import asyncio
import json
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from openai._models import construct_type
from openai.types.responses import CompactedResponse
from pydantic import BaseModel, TypeAdapter, ValidationError

from bridger.contracts.enrichment import (
    EnrichmentGenerationSummary,
    EnrichmentRecord,
    FeatureGenerationSummary,
    GraphEnrichmentOverlay,
)
from bridger.contracts.files import FileIndexPath
from bridger.contracts.graph import GraphBuildResult, GraphConstructionConfig
from bridger.contracts.memory.core import SourceBinding
from bridger.contracts.memory.worker_cycle import (
    EvidenceKind,
    FileEvidenceLocator,
    GraphEntityEvidenceLocator,
    SourceRangeEvidenceLocator,
    SymbolEvidenceLocator,
)
from bridger.contracts.symbols import SymbolIndex, SymbolRecord, summarize_symbols
from bridger.graph.intelligence import build_graph_intelligence
from bridger.graph.lifecycle import (
    create_graph_snapshot,
    load_graph_snapshot_structural_state,
)
from bridger.llm.models import (
    LLMCompactionRequest,
    LLMMessage,
    LLMOperation,
    LLMPromptCacheConfig,
    LLMReasoningConfig,
    LLMRequest,
    LLMToolCall,
    LLMToolDefinition,
)
from bridger.llm.profiles import LLMProfile, RetryPolicy
from bridger.llm.providers.openai import OpenAILLMClient
from bridger.memory import build_graph_overview
from bridger.memory.runtime.worker_navigation_tools import (
    WORKER_REPOSITORY_TOOL_IDS,
    EvidenceCandidateRegistry,
    build_worker_navigation_tools,
)
from bridger.navigation import RepositoryNavigator, build_navigation_tools
from bridger.navigation.tools import NAVIGATION_TOOL_IDS
from bridger.repository.errors import SourceReadDeniedError
from bridger.repository.service import prepare_repository


@pytest.fixture(scope="module")
def layer6_state(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]]:
    tmp_path = tmp_path_factory.mktemp("layer6")
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Layer Six Test")
    (repository / "service.py").write_text(
        "class Service:\n"
        "    def run(self):\n"
        "        return helper()\n"
        "\n"
        "def helper():\n"
        "    return 'needle'\n"
        "\n"
        "def helper():\n"
        "    return 'other'\n",
        encoding="utf-8",
    )
    (repository / "README.md").write_text(
        "Repository navigation notes.\n", encoding="utf-8"
    )
    (repository / ".env").write_text("SECRET=needle\n", encoding="utf-8")
    _git(repository, "add", "-A")
    _git(repository, "commit", "-m", "layer six fixture")
    context, file_index = prepare_repository(repository)

    symbols = [
        SymbolRecord(
            symbol_id="symbol-service",
            name="Service",
            qualified_name="Service",
            kind="class",
            path="service.py",
            start_line=1,
            end_line=3,
            language="python",
        ),
        SymbolRecord(
            symbol_id="symbol-run",
            name="run",
            qualified_name="Service.run",
            kind="method",
            path="service.py",
            start_line=2,
            end_line=3,
            parent_symbol_id="symbol-service",
            language="python",
        ),
        SymbolRecord(
            symbol_id="symbol-helper-a",
            name="helper",
            qualified_name="helper",
            kind="function",
            path="service.py",
            start_line=5,
            end_line=6,
            language="python",
        ),
        SymbolRecord(
            symbol_id="symbol-helper-b",
            name="helper",
            qualified_name="helper",
            kind="function",
            path="service.py",
            start_line=8,
            end_line=9,
            language="python",
        ),
    ]
    symbol_index = SymbolIndex(
        schema_version="2",
        repository_id=context.repository_id,
        revision=context.revision,
        scope_path=context.scope_path,
        symbols=symbols,
        summary=summarize_symbols(symbols),
    )
    extraction: dict[str, Any] = {
        "nodes": [
            _node("file", "service.py", "service.py", "L1"),
            _node("service", "Service", "service.py", "L1"),
            _node("run", ".run()", "service.py", "L2"),
            _node("helper", "helper()", "service.py", None),
            _node("orphan", "External", "", None),
        ],
        "edges": [
            _edge("file", "service", "contains"),
            _edge("service", "run", "method"),
            _edge("run", "helper", "calls"),
            _edge("helper", "orphan", "calls"),
        ],
        "hyperedges": [
            {
                "id": "service-group",
                "label": "Service operations",
                "nodes": ["service", "run", "helper"],
                "relation": "groups",
            }
        ],
    }
    graph, diagnostics, structural = build_graph_intelligence(
        context,
        file_index,
        extraction,
        GraphConstructionConfig(),
    )
    graph_build = create_graph_snapshot(
        context,
        file_index,
        graph,
        diagnostics,
        structural,
        GraphConstructionConfig(),
        tmp_path / "graph",
    )
    restored_structural = load_graph_snapshot_structural_state(graph_build)
    return context, file_index, symbol_index, graph_build, restored_structural


def test_navigator_works_without_overlay_and_keeps_authorities_separate(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)
    community_id = min(structural["communities"])
    target_ref = {
        "community_id": community_id,
        "member_signature": structural["community_member_signatures"][community_id],
    }

    view = navigator.get_graph_entity("community", target_ref)

    assert view.enrichment == []
    assert (
        view.deterministic["deterministic_label"]
        == structural["community_labels"][community_id]
    )
    assert "name" not in view.deterministic


def test_overlay_snapshot_mismatch_is_rejected(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, structural = layer6_state
    overlay = _overlay(graph_build, structural, snapshot_id="different-snapshot")

    with pytest.raises(ValueError, match="different graph snapshot"):
        RepositoryNavigator(
            context, file_index, symbol_index, graph_build, overlay=overlay
        )


def test_community_composition_and_search_require_exact_member_signature(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, structural = layer6_state
    valid_overlay = _overlay(graph_build, structural, name="AI Service Domain")
    valid = RepositoryNavigator(
        context, file_index, symbol_index, graph_build, overlay=valid_overlay
    )
    community_id = min(structural["communities"])
    target_ref = {
        "community_id": community_id,
        "member_signature": structural["community_member_signatures"][community_id],
    }

    composite = valid.get_graph_entity("community", target_ref)
    hits = valid.search_repository("AI Service Domain", kinds={"community"})

    assert [record.value for record in composite.enrichment] == ["AI Service Domain"]
    assert (
        composite.deterministic["deterministic_label"]
        == structural["community_labels"][community_id]
    )
    assert hits[0].ref == target_ref
    assert hits[0].label == "AI Service Domain"

    stale_overlay = valid_overlay.model_copy(deep=True)
    stale_overlay.records[0].target_ref["member_signature"] = "stale-signature"
    stale = RepositoryNavigator(
        context, file_index, symbol_index, graph_build, overlay=stale_overlay
    )
    assert stale.get_graph_entity("community", target_ref).enrichment == []
    assert (
        stale.search_repository("AI Service Domain", kinds={"community"}, min_score=80)
        == []
    )


def test_list_graph_communities_is_bounded_deterministic_and_composed(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, structural = layer6_state
    navigator = RepositoryNavigator(
        context,
        file_index,
        symbol_index,
        graph_build,
        overlay=_overlay(graph_build, structural, name="AI Service Domain"),
    )

    expected_ids = sorted(
        structural["communities"],
        key=lambda community_id: (
            -len(structural["communities"][community_id]),
            community_id,
        ),
    )
    first = navigator.list_graph_communities()
    second = navigator.list_graph_communities()

    assert [view.target_ref["community_id"] for view in first] == expected_ids
    assert [view.model_dump() for view in first] == [
        view.model_dump() for view in second
    ]
    assert all(view.target_type == "community" for view in first)
    assert all(view.deterministic["members"] == [] for view in first)
    assert all(
        view.deterministic["members_truncated"]
        == (view.deterministic["member_count"] > 0)
        for view in first
    )

    enriched = next(
        view
        for view in first
        if view.target_ref["community_id"] == min(structural["communities"])
    )
    assert [record.value for record in enriched.enrichment] == ["AI Service Domain"]
    assert len(navigator.list_graph_communities(limit=1)) == 1
    with pytest.raises(ValueError, match="limit must be between"):
        navigator.list_graph_communities(limit=0)

    stale_overlay = _overlay(graph_build, structural, name="AI Service Domain")
    stale_overlay.records[0].target_ref["member_signature"] = "stale-signature"
    stale = RepositoryNavigator(
        context,
        file_index,
        symbol_index,
        graph_build,
        overlay=stale_overlay,
    )
    stale_community = next(
        view
        for view in stale.list_graph_communities()
        if view.target_ref["community_id"] == min(structural["communities"])
    )
    assert stale_community.enrichment == []


def test_graph_symbol_mapping_preserves_zero_to_many_exact_matches(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)

    assert navigator.graph_to_symbols("file") == []
    assert [record.symbol_id for record in navigator.graph_to_symbols("service")] == [
        "symbol-service"
    ]
    assert [record.symbol_id for record in navigator.graph_to_symbols("helper")] == [
        "symbol-helper-a",
        "symbol-helper-b",
    ]
    assert navigator.symbol_to_graph("symbol-helper-a") == ["helper"]
    assert navigator.symbol_to_graph("symbol-helper-b") == ["helper"]
    assert navigator.symbol_to_graph("symbol-run") == ["run"]
    assert navigator.graph_to_symbols("orphan") == []


def test_traversal_and_search_results_are_bounded_and_supported(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)

    subgraph = navigator.get_graph_subgraph(
        "file", depth=4, direction="outgoing", max_nodes=3, max_edges=2
    )
    path = navigator.get_graph_path("file", "helper", direction="outgoing", max_depth=3)
    hits = navigator.search_repository("service", limit=100, min_score=0)

    assert len(subgraph.nodes) == 3
    assert len(subgraph.edges) == 2
    assert subgraph.truncated
    assert not path.truncated
    assert [view.target_ref for view in path.nodes] == [
        "file",
        "service",
        "run",
        "helper",
    ]
    assert {hit.kind for hit in hits} <= {
        "node",
        "community",
        "hyperedge",
        "file",
        "symbol",
    }


def test_graph_path_reports_exhaustive_and_incomplete_absence(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)

    exhaustive = navigator.get_graph_path("service", "file", direction="outgoing")
    depth_limited = navigator.get_graph_path(
        "file", "helper", direction="outgoing", max_depth=1
    )
    terminal_boundary = navigator.get_graph_path(
        "helper", "file", direction="outgoing", max_depth=1
    )
    node_limited = navigator.get_graph_path(
        "file", "orphan", direction="outgoing", max_nodes=2
    )

    assert exhaustive.nodes == []
    assert exhaustive.edges == []
    assert exhaustive.hyperedges == []
    assert not exhaustive.truncated
    assert depth_limited.nodes == []
    assert depth_limited.edges == []
    assert depth_limited.truncated
    assert terminal_boundary.nodes == []
    assert not terminal_boundary.truncated
    assert node_limited.nodes == []
    assert node_limited.truncated


def test_graph_subgraph_completeness_respects_depth_and_bounds(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)

    continuing = navigator.get_graph_subgraph("file", depth=1, direction="outgoing")
    terminal = navigator.get_graph_subgraph("orphan", depth=1, direction="outgoing")
    relation_limited = navigator.get_graph_subgraph(
        "file", depth=1, direction="outgoing", relations={"contains"}
    )
    direction_limited = navigator.get_graph_subgraph(
        "service", depth=1, direction="incoming"
    )
    edge_limited = navigator.get_graph_subgraph(
        "file", depth=4, direction="outgoing", max_edges=1
    )

    assert [view.target_ref for view in continuing.nodes] == ["file", "service"]
    assert continuing.truncated
    assert not terminal.truncated
    assert not relation_limited.truncated
    assert not direction_limited.truncated
    assert edge_limited.truncated


def test_source_search_and_reads_use_layer1_policy(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)

    matches = navigator.search_source_content("needle", context_lines=1)
    excerpt = navigator.read_symbol_excerpt("symbol-helper-a", context_lines=1)
    around = navigator.read_around_match("service.py", 6, context_lines=1)
    ranges = navigator.read_file_ranges("service.py", [(1, 2), (8, 9)])

    assert [(match.path, match.line_number) for match in matches] == [("service.py", 6)]
    assert "def helper" in excerpt.content
    assert around.start_line == 5
    assert around.end_line == 7
    assert [(result.start_line, result.end_line) for result in ranges] == [
        (1, 2),
        (8, 9),
    ]
    with pytest.raises(SourceReadDeniedError):
        navigator.read_file_ranges(".env", [(1, 1)])


def test_file_and_graph_navigation_reuse_canonical_records(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)

    file_record = navigator.graph_to_file("service")
    overview = navigator.get_file_overview("service.py")
    neighbors = navigator.get_graph_neighbors(
        "run", direction="outgoing", relations={"calls"}
    )
    community_id = min(structural["communities"])
    community = navigator.get_graph_community(community_id)

    assert file_record is file_index.files[-1]
    assert overview.file is file_record
    assert overview.symbol_ids == [
        "symbol-service",
        "symbol-run",
        "symbol-helper-a",
        "symbol-helper-b",
    ]
    assert navigator.file_to_graph("service.py") == [
        "file",
        "helper",
        "run",
        "service",
    ]
    listing = navigator.list_files(limit=2)
    assert [record.path for record in listing.files] == [
        ".env",
        "README.md",
    ]
    assert listing.truncated
    assert [record.symbol_id for record in navigator.list_symbols(path="service.py")]
    assert navigator.search_symbols("Service.run")[0].symbol_id == "symbol-run"
    assert [view.target_ref for view in neighbors.nodes] == ["run", "helper"]
    assert community.members
    assert isinstance(navigator.get_graph_central_nodes(), list)
    assert (
        navigator.get_graph_entity(
            "edge",
            {
                "source_node_id": "run",
                "target_node_id": "helper",
                "relation": "calls",
            },
        ).target_type
        == "edge"
    )
    assert (
        navigator.get_graph_entity("hyperedge", "service-group").deterministic[
            "member_count"
        ]
        == 3
    )
    assert navigator.get_graph_entity("graph", "graph").deterministic["node_count"] == 5


def test_navigation_tool_set_is_explicit_schema_derived_and_authority_bound(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    executor = build_navigation_tools(
        RepositoryNavigator(context, file_index, symbol_index, graph_build)
    )

    assert tuple(definition.name for definition in executor.definitions) == (
        NAVIGATION_TOOL_IDS
    )
    for definition in executor.definitions:
        assert definition.input_schema["type"] == "object"
        assert definition.input_schema["additionalProperties"] is False
        assert definition.description

    serialized_schemas = json.dumps(
        [definition.input_schema for definition in executor.definitions]
    )
    for internal_authority in (
        "repository_root",
        "repository_context",
        "file_index",
        "symbol_index",
        "graph_snapshot",
        "graph_build",
        "overlay",
    ):
        assert internal_authority not in serialized_schemas


def test_worker_navigation_surface_is_distinct_and_graph_node_is_composed(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)
    candidates = _evidence_candidates(context, graph_build)
    executor = build_worker_navigation_tools(navigator, candidates)

    result = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="inspect-service",
                name="inspect_graph_node",
                arguments={"node_id": "service"},
            )
        )
    )
    listing = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="list-service-files",
                name="list_files",
                arguments={"graph_node_id": "service", "limit": 1},
            )
        )
    )

    assert tuple(definition.name for definition in executor.definitions) == (
        WORKER_REPOSITORY_TOOL_IDS
    )
    assert set(NAVIGATION_TOOL_IDS) & set(WORKER_REPOSITORY_TOOL_IDS) == {"list_files"}
    assert result.error is None
    assert listing.output is not None
    assert listing.output["files"][0]["path"] == "service.py"
    assert not listing.output["truncated"]
    assert isinstance(result.output, dict)
    assert result.output["node"]["target_ref"] == "service"
    relationships = result.output["relationships"]
    assert {node["target_ref"] for node in relationships["neighboring_nodes"]} == {
        "file",
        "run",
    }
    assert result.output["source_bridges"]["files"][0]["path"] == "service.py"
    assert [
        symbol["symbol_id"] for symbol in result.output["source_bridges"]["symbols"]
    ] == ["symbol-service"]
    candidate = candidates.resolve(result.output["evidence_handle"])
    assert candidate.kind is EvidenceKind.GRAPH_ENTITY
    assert candidate.locator == GraphEntityEvidenceLocator(
        target_type="node",
        target_ref="service",
    )


@pytest.mark.parametrize(
    "path",
    ["/src/foo.py", "./src/foo.py", "src//foo.py", "src/../foo.py", "src/foo.py/", "."],
)
def test_file_index_path_rejects_noncanonical_repository_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(FileIndexPath).validate_python(path)


def test_list_files_is_segment_aware_bounded_and_graph_related(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)

    prefix_listing = navigator.list_files(path_prefix="service")
    bounded_listing = navigator.list_files(limit=1)
    graph_listing = navigator.list_files(graph_node_id="service")

    assert not prefix_listing.files
    assert not prefix_listing.truncated
    assert [record.path for record in bounded_listing.files] == [".env"]
    assert bounded_listing.truncated
    assert [record.path for record in graph_listing.files] == ["service.py"]
    with pytest.raises(ValueError, match="mutually exclusive"):
        navigator.list_files(path_prefix="src", graph_node_id="service")
    with pytest.raises(ValueError, match="normalized repository-relative prefix"):
        navigator.list_files(path_prefix="./src")


def test_graph_file_bridges_canonicalize_absolute_repository_paths(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    graph = graph_build.graph.copy()
    graph.nodes["service"]["source_file"] = str(context.root_path / "service.py")
    navigator = RepositoryNavigator(
        context,
        file_index,
        symbol_index,
        graph_build.model_copy(update={"graph": graph}),
    )

    resolved = navigator.graph_to_file("service")

    assert resolved is not None
    assert resolved.path == "service.py"
    assert "service" in navigator.file_to_graph("service.py")
    assert [
        record.path for record in navigator.list_files(graph_node_id="service").files
    ] == ["service.py"]


def test_worker_path_mismatch_is_structured_and_never_substituted(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    executor = build_worker_navigation_tools(
        RepositoryNavigator(context, file_index, symbol_index, graph_build),
        _evidence_candidates(context, graph_build),
    )

    result = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="mismatch",
                name="inspect_file",
                arguments={"path": "servce.py"},
            )
        )
    )

    assert result.output is None
    assert result.error is not None
    assert (
        result.error.message == "Repository path is absent from the pinned FileIndex."
    )
    assert result.error.details == {
        "kind": "file_index_path_mismatch",
        "requested_path": "servce.py",
        "closest_valid_paths": ["service.py", ".env", "README.md"],
    }
    assert "details" in result.as_message().model_dump_json()


def test_worker_community_composition_retains_exact_durable_identity(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)
    candidates = _evidence_candidates(context, graph_build)
    executor = build_worker_navigation_tools(navigator, candidates)
    community_id = min(structural["communities"])

    result = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="inspect-community",
                name="inspect_graph_community",
                arguments={"community_id": community_id},
            )
        )
    )

    assert result.error is None
    assert isinstance(result.output, dict)
    assert result.output["members"]
    assert "internal_relationships" in result.output
    assert "cross_community_relationships" in result.output
    candidate = candidates.resolve(result.output["evidence_handle"])
    assert candidate.kind is EvidenceKind.GRAPH_ENTITY
    assert candidate.locator == GraphEntityEvidenceLocator(
        target_type="community",
        target_ref={
            "community_id": community_id,
            "member_signature": structural["community_member_signatures"][community_id],
        },
    )


def test_worker_source_bridges_create_only_inspection_candidates(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)
    candidates = _evidence_candidates(context, graph_build)
    executor = build_worker_navigation_tools(navigator, candidates)

    orientation = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="orient",
                name="orient_repository",
                arguments={"query": "Service"},
            )
        )
    )
    file_result = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="file",
                name="inspect_file",
                arguments={"path": "service.py"},
            )
        )
    )
    symbol_result = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="symbol",
                name="inspect_symbol",
                arguments={"symbol_id": "symbol-run"},
            )
        )
    )
    source_search = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="search",
                name="find_source_text",
                arguments={"query": "needle"},
            )
        )
    )
    source_result = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="source",
                name="read_source_range",
                arguments={"path": "service.py", "start_line": 5, "end_line": 6},
            )
        )
    )

    assert isinstance(orientation.output, dict)
    assert "evidence_handle" not in orientation.output
    assert orientation.output["graph_nodes"]
    assert isinstance(source_search.output, list)
    assert all("evidence_handle" not in match for match in source_search.output)
    assert isinstance(file_result.output, dict)
    assert candidates.resolve(file_result.output["evidence_handle"]).locator == (
        FileEvidenceLocator(path="service.py")
    )
    assert isinstance(symbol_result.output, dict)
    assert candidates.resolve(symbol_result.output["evidence_handle"]).locator == (
        SymbolEvidenceLocator(symbol_id="symbol-run")
    )
    assert isinstance(source_result.output, dict)
    assert "content_digest" not in source_result.output
    source_candidate = candidates.resolve(source_result.output["evidence_handle"])
    expected_source = navigator.read_file_ranges("service.py", [(5, 6)])[0]
    assert source_candidate.locator == SourceRangeEvidenceLocator(
        path="service.py",
        start_line=5,
        end_line=6,
        content_digest=expected_source.content_digest,
    )


def test_worker_path_trace_uses_actual_edge_directions_without_evidence_handle(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)
    executor = build_worker_navigation_tools(
        navigator,
        _evidence_candidates(context, graph_build),
    )

    result = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="path",
                name="trace_graph_path",
                arguments={
                    "source_node_id": "helper",
                    "target_node_id": "service",
                },
            )
        )
    )

    assert result.error is None
    assert isinstance(result.output, dict)
    assert "evidence_handle" not in result.output
    assert {
        (
            edge["deterministic"]["source_node_id"],
            edge["deterministic"]["target_node_id"],
        )
        for edge in result.output["edges"]
    } == {("service", "run"), ("run", "helper")}


def test_graph_overview_reuses_the_persisted_graph_snapshot(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    _context, _file_index, _symbol_index, graph_build, structural = layer6_state

    overview = build_graph_overview(graph_build)

    assert overview.graph_snapshot_id == graph_build.manifest.snapshot_id
    assert overview.node_count == graph_build.graph.number_of_nodes()
    assert overview.edge_count == graph_build.graph.number_of_edges()
    assert overview.community_count == len(structural["communities"])
    assert [node.node_id for node in overview.central_nodes] == [
        node["id"] for node in structural["god_nodes"][:10]
    ]
    assert len(overview.surprising_connections) <= 5
    assert len(overview.suggested_questions) <= 7


def test_navigation_tool_schemas_are_openai_strict_compatible(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    executor = build_navigation_tools(
        RepositoryNavigator(context, file_index, symbol_index, graph_build)
    )
    provider = _FakeOpenAI(
        [{"id": "response-1", "status": "completed", "output_text": "ok"}]
    )

    asyncio.run(
        _openai_client(provider).generate(
            LLMRequest(
                operation=LLMOperation.MEMORY_AGENT_WORKER,
                messages=[LLMMessage.user("Inspect the repository graph.")],
                tools=executor.definitions,
            )
        )
    )

    emitted_tools = provider.requests[0]["tools"]
    assert all(tool["strict"] is True for tool in emitted_tools)
    for tool in emitted_tools:
        _assert_no_empty_schema_nodes(tool["parameters"])

    graph_entity = next(
        tool for tool in emitted_tools if tool["name"] == "get_graph_entity"
    )
    target_ref = graph_entity["parameters"]["properties"]["target_ref"]
    assert target_ref["anyOf"]
    assert all(
        alternative.get("type") == "string" or "$ref" in alternative
        for alternative in target_ref["anyOf"]
    )


@pytest.mark.parametrize(
    ("target_type", "target_ref"),
    [
        ("node", "service"),
        ("hyperedge", "service-group"),
        ("graph", "graph"),
        (
            "edge",
            {"source_node_id": "run", "target_node_id": "helper", "relation": "calls"},
        ),
    ],
)
def test_get_graph_entity_tool_dispatches_supported_target_references(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
    target_type: str,
    target_ref: object,
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    executor = build_navigation_tools(
        RepositoryNavigator(context, file_index, symbol_index, graph_build)
    )

    result = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="call-graph-entity",
                name="get_graph_entity",
                arguments={"target_type": target_type, "target_ref": target_ref},
            )
        )
    )

    assert result.error is None
    assert result.output["target_type"] == target_type


def test_get_graph_entity_tool_dispatches_community_reference(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, structural = layer6_state
    executor = build_navigation_tools(
        RepositoryNavigator(context, file_index, symbol_index, graph_build)
    )
    community_id = min(structural["communities"])
    result = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="call-community",
                name="get_graph_entity",
                arguments={
                    "target_type": "community",
                    "target_ref": {
                        "community_id": community_id,
                        "member_signature": structural["community_member_signatures"][
                            community_id
                        ],
                    },
                },
            )
        )
    )

    assert result.error is None
    assert result.output["target_type"] == "community"


def test_tool_executor_validates_before_dispatch_and_returns_ordinary_errors(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    navigator = RepositoryNavigator(context, file_index, symbol_index, graph_build)
    executor = build_navigation_tools(navigator)
    handler_called = False

    def unexpected_handler(*_args: object, **_kwargs: object) -> object:
        nonlocal handler_called
        handler_called = True
        return []

    monkeypatch.setattr(navigator, "search_repository", unexpected_handler)
    invalid = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="call-invalid",
                name="search_repository",
                arguments={"query": "service", "limit": 501},
            )
        )
    )
    unknown = asyncio.run(
        executor.execute(
            LLMToolCall(id="call-unknown", name="not_registered", arguments={})
        )
    )
    denied = asyncio.run(
        executor.execute(
            LLMToolCall(
                id="call-denied",
                name="read_file_ranges",
                arguments={
                    "path": ".env",
                    "ranges": [{"start_line": 1, "end_line": 1}],
                },
            )
        )
    )

    assert not handler_called
    assert invalid.error is not None
    assert invalid.error.code == "invalid_arguments"
    assert unknown.error is not None
    assert unknown.error.code == "unknown_tool"
    assert denied.error is not None
    assert denied.error.code == "tool_execution_error"
    assert "denied" in denied.error.message
    assert denied.as_message().tool_failed
    assert "details" not in denied.as_message().model_dump_json()


def test_llm_client_tool_call_to_navigation_result_integration(
    layer6_state: tuple[Any, Any, SymbolIndex, GraphBuildResult, dict[str, Any]],
) -> None:
    context, file_index, symbol_index, graph_build, _structural = layer6_state
    executor = build_navigation_tools(
        RepositoryNavigator(context, file_index, symbol_index, graph_build)
    )
    provider = _FakeOpenAI(
        [
            {
                "id": "response-1",
                "status": "completed",
                "model": "test-model",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call-search",
                        "name": "search_repository",
                        "arguments": json.dumps(
                            {
                                "query": "Service",
                                "kinds": ["node"],
                                "limit": 1,
                                "min_score": 0,
                            }
                        ),
                    }
                ],
            }
        ]
    )
    client = _openai_client(provider)
    request = LLMRequest(
        operation=LLMOperation.REPO_DISCOVERY,
        messages=[LLMMessage.user("Locate the Service graph node.")],
        tools=executor.definitions,
    )

    response = asyncio.run(client.generate(request, output_type=_StructuredAnswer))
    result = asyncio.run(executor.execute(response.tool_calls[0]))

    assert len(provider.requests[0]["tools"]) == 20
    assert provider.requests[0]["tools"][0]["name"] == "search_repository"
    assert response.tool_calls[0].id == "call-search"
    assert response.structured_output is None
    assert result.call_id == "call-search"
    assert result.error is None
    assert isinstance(result.output, list)
    assert result.output[0]["kind"] == "node"
    assert result.output[0]["ref"] == "service"


def test_llm_client_keeps_text_and_structured_output_behavior() -> None:
    provider = _FakeOpenAI(
        [
            {
                "status": "completed",
                "model": "test-model",
                "output_text": "ordinary response",
                "output": [],
            },
            {
                "status": "completed",
                "model": "test-model",
                "output_text": '{"answer":"structured response"}',
                "output": [],
            },
        ]
    )
    client = _openai_client(provider)
    request = LLMRequest(
        operation=LLMOperation.REPO_DISCOVERY,
        messages=[LLMMessage.user("Respond once.")],
    )

    ordinary = asyncio.run(client.generate(request))
    structured = asyncio.run(client.generate(request, output_type=_StructuredAnswer))

    assert ordinary.text == "ordinary response"
    assert structured.structured_output == _StructuredAnswer(
        answer="structured response"
    )
    assert "tools" not in provider.requests[0]
    assert provider.requests[1]["text"]["format"]["type"] == "json_schema"


def test_openai_continuation_exact_instructions_storage_and_compaction_mapping() -> (
    None
):
    provider = _FakeOpenAI(
        [
            {
                "id": "response-b",
                "status": "completed",
                "model": "test-model",
                "output_text": "continued",
                "output": [],
            },
            {
                "id": "response-c",
                "status": "completed",
                "model": "test-model",
                "output_text": "seeded",
                "output": [],
            },
        ],
        compaction_outcomes=[
            {
                "object": "response.compaction",
                "output": [
                    {
                        "type": "compaction",
                        "encrypted_content": "opaque-provider-state",
                    }
                ],
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 30,
                    "total_tokens": 230,
                },
            }
        ],
    )
    client = _openai_client(provider)
    continued_request = LLMRequest(
        operation=LLMOperation.MEMORY_AGENT_WORKER,
        messages=[
            LLMMessage.tool_result_message(
                tool_call_id="call-a",
                tool_name="search_repository",
                result={"matches": []},
            )
        ],
        instructions="exact control context",
        continuation_ref="response-a",
        store=True,
        reasoning=LLMReasoningConfig(effort="xhigh", context="all_turns"),
    )

    continued = asyncio.run(client.generate(continued_request))
    compacted = asyncio.run(
        client.compact(
            LLMCompactionRequest(
                operation=LLMOperation.MEMORY_AGENT_WORKER,
                messages=continued_request.messages,
                instructions="latest exact control context",
                continuation_ref=continued.response_id or "",
            )
        )
    )
    seeded = asyncio.run(
        client.generate(
            LLMRequest(
                operation=LLMOperation.MEMORY_AGENT_WORKER,
                messages=[LLMMessage.user("exact recent replay")],
                instructions="post-compaction exact control context",
                compacted_context=compacted.context,
                store=True,
            )
        )
    )

    continued_payload = provider.requests[0]
    assert continued_payload["instructions"] == "exact control context"
    assert continued_payload["previous_response_id"] == "response-a"
    assert continued_payload["store"] is True
    assert continued_payload["reasoning"] == {
        "effort": "xhigh",
        "context": "all_turns",
    }
    assert [item["type"] for item in continued_payload["input"]] == [
        "function_call_output"
    ]
    assert provider.compaction_requests[0] == {
        "model": "test-model",
        "input": continued_payload["input"],
        "instructions": "latest exact control context",
        "previous_response_id": "response-b",
    }
    assert compacted.context.provider == "openai"
    assert compacted.usage.input_tokens == 200
    seeded_payload = provider.requests[1]
    assert "previous_response_id" not in seeded_payload
    assert seeded_payload["input"][0]["type"] == "compaction"
    assert seeded_payload["input"][1] == {
        "role": "user",
        "content": "exact recent replay",
    }
    assert seeded.response_id == "response-c"


def test_openai_compacted_response_round_trips_to_a_valid_continuation_request() -> (
    None
):
    worker_instructions = "Bridger worker control instructions"
    raw_compacted_response = {
        "id": "compact-response",
        "created_at": 1,
        "object": "response.compaction",
        "output": [
            {
                "id": "msg-prior-developer-1",
                "type": "message",
                "status": "completed",
                "role": "developer",
                "phase": "commentary",
                "content": [
                    {"type": "input_text", "text": "prior target context"},
                    {"type": "input_text", "text": "prior obligation context"},
                    {"type": "input_text", "text": "prior tool rules"},
                ],
            },
            {
                "id": "msg-prior-developer-2",
                "type": "message",
                "status": "completed",
                "role": "developer",
                "phase": "final_answer",
                "content": [
                    {"type": "input_text", "text": "prior repair context"},
                    {"type": "input_text", "text": "prior focus context"},
                    {"type": "input_text", "text": "prior yield rule"},
                    {
                        "type": "input_text",
                        "text": "prior finalization rule",
                    },
                ],
            },
            {
                "id": "cmp-opaque",
                "type": "compaction",
                "encrypted_content": "opaque-encrypted-context",
                "created_by": "response-a",
            },
        ],
        "usage": {
            "input_tokens": 200,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 30,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 230,
        },
    }
    compacted_response = construct_type(
        value=raw_compacted_response,
        type_=CompactedResponse,
    )
    assert isinstance(compacted_response, CompactedResponse)
    assert [type(item).__name__ for item in compacted_response.output] == [
        "ResponseOutputMessage",
        "ResponseOutputMessage",
        "ResponseCompactionItem",
    ]
    provider = _FakeOpenAI(
        [
            {
                "id": "response-after-compaction",
                "status": "completed",
                "model": "gpt-5.6",
                "output_text": "continued",
                "output": [],
            }
        ],
        compaction_outcomes=[compacted_response],
    )
    client = _openai_client(provider, model="gpt-5.6")
    prompt_cache = LLMPromptCacheConfig(
        key="worker-cache-key",
        instruction_breakpoints=(7,),
    )
    tool = LLMToolDefinition(
        name="search_repository",
        description="Search the repository.",
        input_schema={"type": "object", "properties": {}},
    )
    compacted = asyncio.run(
        client.compact(
            LLMCompactionRequest(
                operation=LLMOperation.MEMORY_AGENT_WORKER,
                messages=[LLMMessage.user("compaction request input")],
                instructions=worker_instructions,
                continuation_ref="response-before-compaction",
            )
        )
    )
    request = LLMRequest(
        operation=LLMOperation.MEMORY_AGENT_WORKER,
        messages=[
            LLMMessage.tool_result_message(
                tool_call_id="call-after-compaction",
                tool_name="search_repository",
                result={"matches": ["src/bridger/llm/providers/openai.py"]},
            )
        ],
        instructions=worker_instructions,
        compacted_context=compacted.context,
        store=True,
        prompt_cache=prompt_cache,
        tools=[tool],
        tool_choice="required",
        reasoning=LLMReasoningConfig(effort="high", context="all_turns"),
        max_output_tokens=321,
        timeout_seconds=12,
        metadata={"workflow_id": "workflow-1", "run_id": "run-1", "ignored": "x"},
    )

    asyncio.run(client.generate(request))

    assert compacted.context.payload == [
        {
            "type": "message",
            "role": "developer",
            "content": [
                {"type": "input_text", "text": "prior target context"},
                {"type": "input_text", "text": "prior obligation context"},
                {"type": "input_text", "text": "prior tool rules"},
            ],
        },
        {
            "type": "message",
            "role": "developer",
            "content": [
                {"type": "input_text", "text": "prior repair context"},
                {"type": "input_text", "text": "prior focus context"},
                {"type": "input_text", "text": "prior yield rule"},
                {"type": "input_text", "text": "prior finalization rule"},
            ],
        },
        {
            "type": "compaction",
            "encrypted_content": "opaque-encrypted-context",
            "id": "cmp-opaque",
        },
    ]
    payload = provider.requests[0]
    assert payload["input"] == [
        {
            "type": "message",
            "role": "developer",
            "content": [
                {
                    "type": "input_text",
                    "text": worker_instructions[:7],
                    "prompt_cache_breakpoint": {"mode": "explicit"},
                },
                {"type": "input_text", "text": worker_instructions[7:]},
            ],
        },
        *compacted.context.payload,
        {
            "type": "function_call_output",
            "call_id": "call-after-compaction",
            "output": json.dumps(
                {
                    "ok": True,
                    "tool_name": "search_repository",
                    "result": {"matches": ["src/bridger/llm/providers/openai.py"]},
                }
            ),
        },
    ]
    assert "previous_response_id" not in payload
    assert "instructions" not in payload
    assert payload["model"] == "gpt-5.6"
    assert payload["store"] is True
    assert payload["tools"] == [
        {
            "type": "function",
            "name": "search_repository",
            "description": "Search the repository.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]
    assert payload["tool_choice"] == "required"
    assert payload["reasoning"] == {"effort": "high", "context": "all_turns"}
    assert payload["metadata"] == {"workflow_id": "workflow-1", "run_id": "run-1"}
    assert payload["max_output_tokens"] == 321
    assert payload["timeout"] == 12
    assert payload["prompt_cache_key"] == "worker-cache-key"
    assert payload["prompt_cache_options"] == {"mode": "explicit"}


def test_openai_explicit_prompt_cache_mapping_and_usage_are_semantic_noops() -> None:
    provider = _FakeOpenAI(
        [
            {
                "id": "cold",
                "status": "completed",
                "model": "test-model",
                "output_text": "same result",
                "output": [],
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 5,
                    "total_tokens": 125,
                    "input_tokens_details": {
                        "cached_tokens": 0,
                        "cache_write_tokens": 100,
                    },
                },
            },
            {
                "id": "hit",
                "status": "completed",
                "model": "test-model",
                "output_text": "same result",
                "output": [],
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 5,
                    "total_tokens": 125,
                    "input_tokens_details": {
                        "cached_tokens": 100,
                        "cache_write_tokens": 0,
                    },
                },
            },
        ]
    )
    client = _openai_client(provider, model="gpt-5.6-test")
    request = LLMRequest(
        operation=LLMOperation.MEMORY_AGENT_WORKER,
        instructions="global-target-cycle-dynamic",
        prompt_cache=LLMPromptCacheConfig(
            key="a" * 64,
            instruction_breakpoints=(6, 13, 19),
        ),
        tools=[
            LLMToolDefinition(
                name="lookup",
                description="Look up one value.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "zeta": {"type": "string"},
                        "alpha": {"type": "string"},
                    },
                },
            )
        ],
    )

    cold = asyncio.run(client.generate(request))
    hit = asyncio.run(client.generate(request))

    assert cold.text == hit.text == "same result"
    assert cold.usage.cached_input_tokens == 0
    assert cold.usage.cache_write_tokens == 100
    assert hit.usage.cached_input_tokens == 100
    assert hit.usage.cache_write_tokens == 0
    payload = provider.requests[0]
    assert "instructions" not in payload
    assert payload["prompt_cache_key"] == "a" * 64
    assert payload["prompt_cache_options"] == {"mode": "explicit"}
    instruction = payload["input"][0]
    assert instruction["role"] == "developer"
    assert [part["text"] for part in instruction["content"]] == [
        "global",
        "-target",
        "-cycle",
        "-dynamic",
    ]
    assert all(
        part["prompt_cache_breakpoint"] == {"mode": "explicit"}
        for part in instruction["content"][:3]
    )
    assert "prompt_cache_breakpoint" not in instruction["content"][3]
    parameters = payload["tools"][0]["parameters"]
    assert list(parameters) == sorted(parameters)
    assert list(parameters["properties"]) == ["alpha", "zeta"]


def test_openai_unsupported_model_ignores_cache_intent_without_changing_request() -> (
    None
):
    provider = _FakeOpenAI(
        [
            {
                "id": "uncached",
                "status": "completed",
                "model": "test-model",
                "output_text": "same result",
                "output": [],
            }
        ]
    )
    client = _openai_client(provider)
    request = LLMRequest(
        operation=LLMOperation.MEMORY_AGENT_WORKER,
        instructions="exact control context",
        prompt_cache=LLMPromptCacheConfig(
            key="b" * 64,
            instruction_breakpoints=(5,),
        ),
    )

    response = asyncio.run(client.generate(request))

    assert response.text == "same result"
    assert provider.requests[0]["instructions"] == request.instructions
    assert provider.requests[0]["input"] == []
    assert "prompt_cache_key" not in provider.requests[0]
    assert "prompt_cache_options" not in provider.requests[0]


class _StructuredAnswer(BaseModel):
    answer: str


def _evidence_candidates(
    context: Any,
    graph_build: GraphBuildResult,
) -> EvidenceCandidateRegistry:
    return EvidenceCandidateRegistry(
        "task-1",
        SourceBinding(
            repository_id=context.repository_id,
            repository_revision=context.revision,
            graph_snapshot_id=graph_build.manifest.snapshot_id,
        ),
    )


class _FakeResponses:
    def __init__(
        self,
        outcomes: list[Mapping[str, Any]],
        compaction_outcomes: list[Mapping[str, Any]],
    ) -> None:
        self._outcomes = list(outcomes)
        self._compaction_outcomes = list(compaction_outcomes)
        self.requests: list[dict[str, Any]] = []
        self.compaction_requests: list[dict[str, Any]] = []

    async def create(self, **payload: Any) -> Mapping[str, Any]:
        self.requests.append(payload)
        return self._outcomes.pop(0)

    async def compact(self, **payload: Any) -> Mapping[str, Any]:
        self.compaction_requests.append(payload)
        return self._compaction_outcomes.pop(0)


class _FakeOpenAI:
    def __init__(
        self,
        outcomes: list[Mapping[str, Any]],
        *,
        compaction_outcomes: list[Mapping[str, Any]] | None = None,
    ) -> None:
        self.responses = _FakeResponses(outcomes, compaction_outcomes or [])

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self.responses.requests

    @property
    def compaction_requests(self) -> list[dict[str, Any]]:
        return self.responses.compaction_requests


def _openai_client(
    provider: _FakeOpenAI,
    *,
    model: str = "test-model",
) -> OpenAILLMClient:
    return OpenAILLMClient(
        openai_client=provider,
        profile=LLMProfile(
            name="test",
            provider="openai",
            model=model,
            retry_policy=RetryPolicy(max_attempts=1),
        ),
    )


def _overlay(
    graph_build: GraphBuildResult,
    structural: dict[str, Any],
    *,
    snapshot_id: str | None = None,
    name: str = "AI Community",
) -> GraphEnrichmentOverlay:
    community_id = min(structural["communities"])
    record = EnrichmentRecord(
        enrichment_id="enrichment-community",
        target_type="community",
        target_ref={
            "community_id": community_id,
            "member_signature": structural["community_member_signatures"][community_id],
        },
        annotation_type="name",
        value=name,
        deterministic_features={},
    )
    community_count = len(structural["communities"])
    return GraphEnrichmentOverlay(
        schema_version="1",
        overlay_id="overlay-layer6",
        graph_snapshot_id=snapshot_id or graph_build.manifest.snapshot_id,
        generator_version="test",
        provider="test",
        model="test",
        profile_version="test",
        enabled_features=["community_names"],
        created_at=datetime.now(UTC),
        generation_summary=EnrichmentGenerationSummary(
            features={
                "community_names": FeatureGenerationSummary(
                    status="complete",
                    target_count=community_count,
                    generated_count=community_count,
                    reused_count=0,
                    failed_target_count=0,
                    batch_count=1,
                    failed_batch_count=0,
                )
            }
        ),
        records=[record],
    )


def _assert_no_empty_schema_nodes(value: object) -> None:
    _assert_schema_node(value, is_schema_node=True)


def _assert_schema_node(value: object, *, is_schema_node: bool) -> None:
    if isinstance(value, dict):
        if is_schema_node:
            assert value, "OpenAI schema contains an unconstrained empty object"
        for key, child in value.items():
            _assert_schema_node(
                child,
                is_schema_node=key not in {"properties", "$defs"},
            )
    elif isinstance(value, list):
        for child in value:
            _assert_schema_node(child, is_schema_node=True)


def _node(
    node_id: str,
    label: str,
    source_file: str,
    source_location: str | None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "file_type": "code",
        "source_file": source_file,
        "source_location": source_location,
        "_origin": "ast",
    }


def _edge(source: str, target: str, relation: str) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": "EXTRACTED",
        "source_file": "service.py",
        "_origin": "ast",
    }


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()
