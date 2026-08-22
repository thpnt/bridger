"""Focused Layer 5 generation, retry, reuse, and publication invariants."""

import asyncio
import hashlib
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar, cast

import networkx as nx  # type: ignore[import-untyped]
import orjson
import pytest
from pydantic import BaseModel

from bridger.contracts.enrichment import (
    CommunityEvidence,
    CommunityName,
    CommunityNameBatch,
    CommunityRepresentative,
    EnrichmentGenerationSummary,
    EnrichmentTargetReference,
    FailedEnrichmentBatch,
    FeatureGenerationSummary,
    GraphEnrichmentConfig,
    GraphEnrichmentOverlay,
)
from bridger.contracts.graph import GraphBuildResult, GraphSnapshotManifest
from bridger.graph.enrichment import (
    build_all_community_evidence,
    create_community_name_record,
    create_graph_enrichment,
    enrich_graph_snapshot,
    load_graph_enrichment,
    validate_graph_enrichment,
)
from bridger.graph.enrichment.naming import (
    InvalidCommunityNameBatch,
    validate_community_name_batch,
)
from bridger.graph.enrichment.service import _create_community_name_client
from bridger.llm.client import LLMClient
from bridger.llm.errors import LLMProviderError
from bridger.llm.models import LLMRequest, LLMResponse
from bridger.llm.profiles import LLMProfile

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)
Behavior = Callable[[tuple[int, ...], int], Awaitable[CommunityNameBatch]]


class FakeCommunityLLMClient:
    """Typed concurrent fake that records batch calls and active-call counts."""

    def __init__(self, behavior: Behavior) -> None:
        self._behavior = behavior
        self.requests: list[LLMRequest] = []
        self.output_types: list[type[BaseModel] | None] = []
        self.calls: Counter[tuple[int, ...]] = Counter()
        self.active_calls = 0
        self.max_active_calls = 0

    async def generate(
        self,
        request: LLMRequest,
        *,
        output_type: type[StructuredOutputT] | None = None,
    ) -> LLMResponse[StructuredOutputT]:
        community_ids = _request_community_ids(request)
        self.requests.append(request)
        self.output_types.append(output_type)
        self.calls[community_ids] += 1
        attempt = self.calls[community_ids]
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            batch = await self._behavior(community_ids, attempt)
        finally:
            self.active_calls -= 1
        response = LLMResponse[CommunityNameBatch](
            structured_output=batch,
            provider="dummy",
            model="dummy-model",
        )
        return cast(LLMResponse[StructuredOutputT], response)


def test_successful_generation_uses_evidence_only_and_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_build, structural = _graph_state(tmp_path, monkeypatch, community_count=3)

    async def succeed(
        community_ids: tuple[int, ...],
        _attempt: int,
    ) -> CommunityNameBatch:
        return _valid_batch(community_ids)

    client = FakeCommunityLLMClient(succeed)
    _use_client(monkeypatch, client)
    structural_path = graph_build.snapshot_root / "structural.json"
    before = hashlib.sha256(structural_path.read_bytes()).hexdigest()

    overlay = enrich_graph_snapshot(graph_build, _config())

    summary = overlay.generation_summary.features["community_names"]
    assert summary.status == "complete"
    assert summary.model_dump(exclude={"failed_batches"}) == {
        "status": "complete",
        "target_count": 3,
        "generated_count": 3,
        "reused_count": 0,
        "failed_target_count": 0,
        "batch_count": 1,
        "failed_batch_count": 0,
    }
    assert _record_community_ids(overlay) == [0, 1, 2]
    assert client.output_types == [CommunityNameBatch]
    request = client.requests[0]
    assert request.reasoning is None
    assert len(request.messages) == 2
    supplied = orjson.loads(request.messages[1].content or "")
    assert supplied == [
        item.model_dump(mode="json", exclude_none=True)
        for item in build_all_community_evidence(graph_build)
    ]
    assert all(
        set(item)
        == {
            "community_id",
            "important_representatives",
            "other_representatives",
        }
        for item in supplied
    )
    assert "cohesion" not in (request.messages[1].content or "")
    assert hashlib.sha256(structural_path.read_bytes()).hexdigest() == before
    artifact = _artifact_path(tmp_path, graph_build, overlay)
    assert load_graph_enrichment(artifact, graph_build.manifest.snapshot_id) == overlay
    validate_graph_enrichment(overlay, graph_build)
    assert structural["community_labels"] == {
        community_id: f"Node {community_id}" for community_id in range(3)
    }


def test_mixed_reuse_generates_only_unmatched_target_and_materializes_new_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_build, structural = _graph_state(tmp_path, monkeypatch, community_count=2)
    previous = _partial_previous_overlay(graph_build, structural)
    create_graph_enrichment(previous, graph_build, tmp_path / ".bridger")
    previous_artifact = _artifact_path(tmp_path, graph_build, previous)
    previous_digest = hashlib.sha256(previous_artifact.read_bytes()).hexdigest()

    async def succeed(
        community_ids: tuple[int, ...],
        _attempt: int,
    ) -> CommunityNameBatch:
        return _valid_batch(community_ids)

    client = FakeCommunityLLMClient(succeed)
    _use_client(monkeypatch, client)

    overlay = enrich_graph_snapshot(graph_build, _config())

    assert list(client.calls) == [(1,)]
    summary = overlay.generation_summary.features["community_names"]
    assert summary.generated_count == 1
    assert summary.reused_count == 1
    assert summary.failed_target_count == 0
    assert overlay.overlay_id != previous.overlay_id
    assert overlay.records[0].value == "Existing Domain Name"
    assert overlay.records[0].enrichment_id != previous.records[0].enrichment_id
    assert hashlib.sha256(previous_artifact.read_bytes()).hexdigest() == previous_digest

    monkeypatch.setattr(
        "bridger.graph.enrichment.service._create_community_name_client",
        lambda _config: pytest.fail("all compatible names should be reused"),
    )
    all_reused = enrich_graph_snapshot(graph_build, _config())
    reused_summary = all_reused.generation_summary.features["community_names"]
    assert reused_summary.generated_count == 0
    assert reused_summary.reused_count == 2
    assert all_reused.overlay_id != overlay.overlay_id
    assert {record.enrichment_id for record in all_reused.records}.isdisjoint(
        {record.enrichment_id for record in overlay.records}
    )

    changed_client = FakeCommunityLLMClient(succeed)
    _use_client(monkeypatch, changed_client)
    changed = enrich_graph_snapshot(
        graph_build,
        _config(profile_version="community-names-v2"),
    )
    assert list(changed_client.calls) == [(0, 1)]
    assert changed.generation_summary.features["community_names"].reused_count == 0


@pytest.mark.parametrize(
    "response",
    [
        CommunityNameBatch(communities=[]),
        CommunityNameBatch(
            communities=[
                CommunityName(community_id=1, name="Valid Domain"),
                CommunityName(community_id=1, name="Duplicate Domain"),
            ]
        ),
        CommunityNameBatch(
            communities=[CommunityName(community_id=99, name="Unknown Domain")]
        ),
        CommunityNameBatch(communities=[CommunityName(community_id=1, name="Single")]),
        CommunityNameBatch(
            communities=[
                CommunityName(
                    community_id=1,
                    name="One Two Three Four Five Six",
                )
            ]
        ),
        CommunityNameBatch.model_construct(
            communities=[CommunityName.model_construct(community_id=1, name="")]
        ),
    ],
)
def test_invalid_structured_batch_is_atomic(response: CommunityNameBatch) -> None:
    evidence = (
        CommunityEvidence(
            community_id=1,
            other_representatives=[CommunityRepresentative(label="Service")],
        ),
    )

    with pytest.raises(InvalidCommunityNameBatch):
        validate_community_name_batch(response, evidence)


def test_retry_success_isolated_batches_ordering_and_concurrency_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_build, _ = _graph_state(tmp_path, monkeypatch, community_count=205)

    async def retry_middle(
        community_ids: tuple[int, ...],
        attempt: int,
    ) -> CommunityNameBatch:
        first_id = community_ids[0]
        if first_id == 100 and attempt == 1:
            return CommunityNameBatch(
                communities=[
                    CommunityName(
                        community_id=community_id,
                        name=f"Community {community_id} Domain",
                    )
                    for community_id in community_ids[:-1]
                ]
            )
        await asyncio.sleep({0: 0.03, 100: 0.01, 200: 0.001}[first_id])
        return _valid_batch(community_ids)

    client = FakeCommunityLLMClient(retry_middle)
    _use_client(monkeypatch, client)

    overlay = enrich_graph_snapshot(
        graph_build,
        _config(max_concurrency=2),
    )

    assert client.calls[tuple(range(100))] == 1
    assert client.calls[tuple(range(100, 200))] == 2
    assert client.calls[tuple(range(200, 205))] == 1
    assert client.max_active_calls <= 2
    assert _record_community_ids(overlay) == list(range(205))
    summary = overlay.generation_summary.features["community_names"]
    assert summary.status == "complete"
    assert summary.batch_count == 3
    assert summary.failed_batch_count == 0


def test_retry_exhaustion_is_partial_and_does_not_cancel_siblings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_build, _ = _graph_state(tmp_path, monkeypatch, community_count=201)

    async def fail_middle(
        community_ids: tuple[int, ...],
        _attempt: int,
    ) -> CommunityNameBatch:
        if community_ids[0] == 100:
            raise LLMProviderError("unavailable", retryable=True)
        await asyncio.sleep(0.002)
        return _valid_batch(community_ids)

    client = FakeCommunityLLMClient(fail_middle)
    _use_client(monkeypatch, client)

    overlay = enrich_graph_snapshot(
        graph_build,
        _config(max_concurrency=3),
    )

    failed_key = tuple(range(100, 200))
    assert client.calls[tuple(range(100))] == 1
    assert client.calls[failed_key] == 3
    assert client.calls[(200,)] == 1
    assert _record_community_ids(overlay) == [*range(100), 200]
    summary = overlay.generation_summary.features["community_names"]
    assert summary.status == "partial"
    assert summary.generated_count == 101
    assert summary.failed_target_count == 100
    assert summary.failed_batch_count == 1
    assert summary.failed_batches[0].batch_id == "community-names-0001"
    assert summary.failed_batches[0].attempts == 3
    assert summary.failed_batches[0].error_category == "provider_error"
    assert len(summary.failed_batches[0].target_refs) == 100
    artifact = _artifact_path(tmp_path, graph_build, overlay)
    assert load_graph_enrichment(artifact, graph_build.manifest.snapshot_id) == overlay
    validate_graph_enrichment(overlay, graph_build)


def test_layer5_client_disables_internal_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[LLMProfile] = []
    sentinel = cast(LLMClient, object())

    def capture(profile: LLMProfile) -> LLMClient:
        captured.append(profile)
        return sentinel

    monkeypatch.setattr(
        "bridger.graph.enrichment.service.create_llm_client_from_profile",
        capture,
    )

    assert _create_community_name_client(_config()) is sentinel
    assert captured[0].retry_policy.max_attempts == 1


def _graph_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    community_count: int,
) -> tuple[GraphBuildResult, dict[str, object]]:
    graph = nx.DiGraph()
    communities: dict[int, list[str]] = {}
    signatures: dict[int, str] = {}
    labels: dict[int, str] = {}
    for community_id in range(community_count):
        node_id = f"node-{community_id:04d}"
        graph.add_node(
            node_id,
            label=f"Node {community_id}",
            source_file=f"src/domain-{community_id}/service.py",
            metadata={"kind": "class"},
        )
        communities[community_id] = [node_id]
        signatures[community_id] = hashlib.sha256(node_id.encode()).hexdigest()[:16]
        labels[community_id] = f"Node {community_id}"
    structural: dict[str, object] = {
        "communities": communities,
        "cohesion": {community_id: 0.0 for community_id in communities},
        "community_member_signatures": signatures,
        "community_labels": labels,
        "god_nodes": [],
        "surprising_connections": [],
        "suggested_questions": [],
    }
    snapshot_root = tmp_path / ".bridger" / "graph" / "snapshots" / "snapshot-execution"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    (snapshot_root / "structural.json").write_text(
        "deterministic-layer-4\n",
        encoding="utf-8",
    )
    graph_build = GraphBuildResult.model_construct(
        operation_mode="loaded",
        graph=graph,
        manifest=GraphSnapshotManifest.model_construct(
            snapshot_id="snapshot-execution"
        ),
        diagnostics=None,
        snapshot_root=snapshot_root,
    )

    def load_state(_graph_build: GraphBuildResult) -> dict[str, object]:
        return structural

    for target in (
        "bridger.graph.enrichment.evidence.load_graph_snapshot_structural_state",
        "bridger.graph.enrichment.validation.load_graph_snapshot_structural_state",
        "bridger.graph.enrichment.service.load_graph_snapshot_structural_state",
    ):
        monkeypatch.setattr(target, load_state)
    return graph_build, structural


def _config(
    *,
    profile_version: str = "community-names-v1",
    max_concurrency: int = 4,
) -> GraphEnrichmentConfig:
    return GraphEnrichmentConfig(
        provider="openai",
        model="gpt-test",
        profile_version=profile_version,
        max_concurrency=max_concurrency,
    )


def _valid_batch(community_ids: tuple[int, ...]) -> CommunityNameBatch:
    return CommunityNameBatch(
        communities=[
            CommunityName(
                community_id=community_id,
                name=f"Community {community_id} Domain",
            )
            for community_id in community_ids
        ]
    )


def _request_community_ids(request: LLMRequest) -> tuple[int, ...]:
    payload = orjson.loads(request.messages[-1].content or "")
    return tuple(item["community_id"] for item in payload)


def _use_client(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeCommunityLLMClient,
) -> None:
    monkeypatch.setattr(
        "bridger.graph.enrichment.service._create_community_name_client",
        lambda _config: client,
    )


def _record_community_ids(overlay: GraphEnrichmentOverlay) -> list[int]:
    return [
        cast(int, cast(dict[str, object], record.target_ref)["community_id"])
        for record in overlay.records
    ]


def _artifact_path(
    tmp_path: Path,
    graph_build: GraphBuildResult,
    overlay: GraphEnrichmentOverlay,
) -> Path:
    return (
        tmp_path
        / ".bridger"
        / "enrichment"
        / graph_build.manifest.snapshot_id
        / overlay.overlay_id
        / "graph-enrichment.json"
    )


def _partial_previous_overlay(
    graph_build: GraphBuildResult,
    structural: dict[str, object],
) -> GraphEnrichmentOverlay:
    evidence = build_all_community_evidence(graph_build)
    signatures = cast(dict[int, str], structural["community_member_signatures"])
    record = create_community_name_record(
        evidence[0],
        member_signature=signatures[0],
        name="Existing Domain Name",
        enrichment_id="previous-record",
    )
    failed_ref: EnrichmentTargetReference = {
        "community_id": 1,
        "member_signature": signatures[1],
    }
    return GraphEnrichmentOverlay(
        schema_version="1",
        overlay_id="previous-overlay",
        graph_snapshot_id=graph_build.manifest.snapshot_id,
        generator_version="bridger.layer5.v1",
        provider="openai",
        model="gpt-test",
        profile_version="community-names-v1",
        enabled_features=["community_names"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        generation_summary=EnrichmentGenerationSummary(
            features={
                "community_names": FeatureGenerationSummary(
                    status="partial",
                    target_count=2,
                    generated_count=1,
                    reused_count=0,
                    failed_target_count=1,
                    batch_count=1,
                    failed_batch_count=1,
                    failed_batches=[
                        FailedEnrichmentBatch(
                            batch_id="previous-failed-batch",
                            target_refs=[failed_ref],
                            attempts=3,
                            error_category="provider_error",
                        )
                    ],
                )
            }
        ),
        records=[record],
    )
