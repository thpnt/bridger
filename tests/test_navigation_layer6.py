"""Focused Layer 6 composition and repository navigation invariants."""

import asyncio
import json
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from graph.intelligence import build_graph_intelligence
from graph.lifecycle import (
    create_graph_snapshot,
    load_graph_snapshot_structural_state,
)
from llm.models import LLMMessage, LLMOperation, LLMRequest, LLMToolCall
from llm.profiles import LLMProfile, RetryPolicy
from llm.providers.openai import OpenAILLMClient
from models.enrichment import (
    EnrichmentGenerationSummary,
    EnrichmentRecord,
    FeatureGenerationSummary,
    GraphEnrichmentOverlay,
)
from models.graph import GraphBuildResult, GraphConstructionConfig
from models.symbols import SymbolIndex, SymbolRecord, summarize_symbols
from navigation import RepositoryNavigator, build_navigation_tools
from repository.errors import SourceReadDeniedError
from repository.service import prepare_repository


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
        schema_version="1",
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
    assert path is not None
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
    assert [record.path for record in navigator.list_files(limit=2)] == [
        ".env",
        "README.md",
    ]
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

    assert [definition.name for definition in executor.definitions] == [
        "search_repository",
        "get_graph_entity",
        "get_graph_neighbors",
        "get_graph_path",
        "get_graph_subgraph",
        "get_graph_community",
        "get_graph_central_nodes",
        "graph_to_file",
        "graph_to_symbols",
        "file_to_graph",
        "symbol_to_graph",
        "list_files",
        "get_file_overview",
        "list_symbols",
        "search_symbols",
        "search_source_content",
        "read_symbol_excerpt",
        "read_file_ranges",
        "read_around_match",
    ]
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

    assert len(provider.requests[0]["tools"]) == 19
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


class _StructuredAnswer(BaseModel):
    answer: str


class _FakeResponses:
    def __init__(self, outcomes: list[Mapping[str, Any]]) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **payload: Any) -> Mapping[str, Any]:
        self.requests.append(payload)
        return self._outcomes.pop(0)


class _FakeOpenAI:
    def __init__(self, outcomes: list[Mapping[str, Any]]) -> None:
        self.responses = _FakeResponses(outcomes)

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self.responses.requests


def _openai_client(provider: _FakeOpenAI) -> OpenAILLMClient:
    return OpenAILLMClient(
        openai_client=provider,
        profile=LLMProfile(
            name="test",
            provider="openai",
            model="test-model",
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
