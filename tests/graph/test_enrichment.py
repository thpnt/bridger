"""Focused Layer 5 deterministic enrichment foundation invariants."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx  # type: ignore[import-untyped]
import pytest

from bridger.contracts.enrichment import (
    EnrichmentGenerationSummary,
    EnrichmentRecord,
    EnrichmentTargetReference,
    FailedEnrichmentBatch,
    FeatureGenerationSummary,
    GraphEnrichmentOverlay,
)
from bridger.contracts.files import (
    FileDisposition,
    FileIndex,
    FileRecord,
    summarize_files,
)
from bridger.contracts.graph import (
    GraphBuildResult,
    GraphConstructionConfig,
    GraphSnapshotManifest,
)
from bridger.contracts.repository import RepositoryContext
from bridger.graph.enrichment import (
    COMMUNITY_REPRESENTATIVE_LIMIT,
    InvalidGraphEnrichment,
    build_all_community_evidence,
    build_community_evidence,
    canonical_serialize_community_evidence,
    community_name_input_fingerprint,
    create_community_name_record,
    create_graph_enrichment,
    load_graph_enrichment,
    validate_graph_enrichment,
)
from bridger.graph.enrichment.fingerprint import _find_reusable_community_name
from bridger.graph.intelligence import build_graph_intelligence
from bridger.graph.lifecycle import (
    create_graph_snapshot,
    load_graph_snapshot_structural_state,
)


@pytest.fixture
def graph_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[GraphBuildResult, dict[str, object]]:
    graph = nx.DiGraph()
    for index in range(16):
        label = f"Service {index}"
        if index == 4:
            label = "Duplicate"
        elif index == 5:
            label = "duplicate"
        elif index == 6:
            label = "Control\x00  Label"
        graph.add_node(
            f"node-{index:02}",
            label=label,
            source_file=f"src/group-{index % 6}/module.py",
            metadata={
                "kind": "class" if index % 2 == 0 else "function",
                "parent_qualified_name": f"Owner{index % 5}",
            },
        )
    for index in range(1, 16):
        graph.add_edge("node-00", f"node-{index:02}", relation="calls")
        if index > 1:
            graph.add_edge(f"node-{index - 1:02}", f"node-{index:02}")

    signature = "a91b37e84cd88210"
    structural: dict[str, object] = {
        "communities": {4: list(graph.nodes)},
        "cohesion": {4: 0.5},
        "community_member_signatures": {4: signature},
        "community_labels": {4: "Service 0"},
        "god_nodes": [
            {"id": "node-00", "label": "Service 0", "degree": 15},
            {"id": "node-01", "label": "Service 1", "degree": 2},
        ],
        "surprising_connections": [],
        "suggested_questions": [],
    }
    snapshot_root = tmp_path / "graph" / "snapshots" / "snapshot-1"
    snapshot_root.mkdir(parents=True)
    (snapshot_root / "structural.json").write_text("unchanged\n", encoding="utf-8")
    manifest = GraphSnapshotManifest.model_construct(snapshot_id="snapshot-1")
    graph_build = GraphBuildResult.model_construct(
        operation_mode="loaded",
        graph=graph,
        manifest=manifest,
        diagnostics=None,
        snapshot_root=snapshot_root,
    )

    def load_state(_graph_build: GraphBuildResult) -> dict[str, object]:
        return structural

    monkeypatch.setattr(
        "bridger.graph.enrichment.evidence.load_graph_snapshot_structural_state",
        load_state,
    )
    monkeypatch.setattr(
        "bridger.graph.enrichment.validation.load_graph_snapshot_structural_state",
        load_state,
    )
    return graph_build, structural


def test_evidence_is_deterministic_bounded_diverse_and_separates_importance(
    graph_state: tuple[GraphBuildResult, dict[str, object]],
) -> None:
    graph_build, _ = graph_state

    first = build_community_evidence(graph_build, 4)
    second = build_community_evidence(graph_build, 4)
    representatives = first.important_representatives + first.other_representatives

    assert first == second
    assert [item.label for item in first.important_representatives] == [
        "Service 0",
        "Service 1",
    ]
    assert len(representatives) == COMMUNITY_REPRESENTATIVE_LIMIT
    assert len({item.label.casefold() for item in representatives}) == len(
        representatives
    )
    assert all(item.node_type in {"class", "function"} for item in representatives)
    assert all(
        item.source_path and not item.source_path.startswith("/")
        for item in representatives
    )
    assert any(item.label == "Control Label" for item in representatives)
    assert set(first.model_dump()) == {
        "community_id",
        "important_representatives",
        "other_representatives",
    }


def test_canonical_serialization_and_fingerprint_track_all_material_inputs(
    graph_state: tuple[GraphBuildResult, dict[str, object]],
) -> None:
    graph_build, _ = graph_state
    evidence = build_all_community_evidence(graph_build)[0]
    inputs = {
        "member_signature": "a91b37e84cd88210",
        "profile_version": "community-names-v1",
        "provider": "openai",
        "model": "gpt-test",
    }

    serialized = canonical_serialize_community_evidence(evidence)
    assert serialized == canonical_serialize_community_evidence(evidence.model_copy())
    baseline = community_name_input_fingerprint(evidence, **inputs)
    assert baseline == community_name_input_fingerprint(evidence, **inputs)

    changed_evidence = evidence.model_copy(deep=True)
    changed_evidence.other_representatives[0].source_path = "src/changed.py"
    mutations = [
        (changed_evidence, inputs),
        (evidence, {**inputs, "member_signature": "changed"}),
        (evidence, {**inputs, "profile_version": "v2"}),
        (evidence, {**inputs, "provider": "other"}),
        (evidence, {**inputs, "model": "other"}),
    ]
    assert all(
        community_name_input_fingerprint(candidate, **values) != baseline
        for candidate, values in mutations
    )


def test_record_construction_requires_signature_and_persists_exact_evidence(
    graph_state: tuple[GraphBuildResult, dict[str, object]],
) -> None:
    graph_build, _ = graph_state
    evidence = build_community_evidence(graph_build, 4)

    with pytest.raises(ValueError, match="member_signature"):
        create_community_name_record(
            evidence,
            member_signature="",
            name="Payments",
        )

    record = create_community_name_record(
        evidence,
        member_signature="a91b37e84cd88210",
        name="Payment Processing",
        enrichment_id="record-1",
    )
    assert record.target_ref == {
        "community_id": 4,
        "member_signature": "a91b37e84cd88210",
    }
    assert record.deterministic_features == {
        "important_representatives": [
            item.model_dump(mode="json", exclude_none=True)
            for item in evidence.important_representatives
        ],
        "other_representatives": [
            item.model_dump(mode="json", exclude_none=True)
            for item in evidence.other_representatives
        ],
    }


def test_validation_rejects_snapshot_signature_duplicate_and_evidence_drift(
    graph_state: tuple[GraphBuildResult, dict[str, object]],
) -> None:
    graph_build, _ = graph_state
    overlay = _complete_overlay(graph_build)
    validate_graph_enrichment(overlay, graph_build)

    mismatch = overlay.model_copy(update={"graph_snapshot_id": "other"})
    with pytest.raises(InvalidGraphEnrichment, match="snapshot binding"):
        validate_graph_enrichment(mismatch, graph_build)

    wrong_signature = overlay.model_copy(deep=True)
    assert isinstance(wrong_signature.records[0].target_ref, dict)
    wrong_signature.records[0].target_ref["member_signature"] = "wrong"
    with pytest.raises(InvalidGraphEnrichment, match="member_signature"):
        validate_graph_enrichment(wrong_signature, graph_build)

    duplicate = overlay.model_copy(deep=True)
    duplicate.records.append(
        duplicate.records[0].model_copy(update={"enrichment_id": "record-2"})
    )
    with pytest.raises(InvalidGraphEnrichment, match="duplicate community-name"):
        validate_graph_enrichment(duplicate, graph_build)

    drift = overlay.model_copy(deep=True)
    drift.records[0].deterministic_features["other_representatives"] = []
    with pytest.raises(InvalidGraphEnrichment, match="canonical evidence"):
        validate_graph_enrichment(drift, graph_build)


def test_validation_enforces_generation_summary_counts(
    graph_state: tuple[GraphBuildResult, dict[str, object]],
) -> None:
    graph_build, _ = graph_state
    overlay = _complete_overlay(graph_build)
    summary = overlay.generation_summary.features["community_names"]
    summary.generated_count = 0

    with pytest.raises(InvalidGraphEnrichment, match="schema is invalid"):
        validate_graph_enrichment(overlay, graph_build)

    partial = _partial_overlay(graph_build)
    validate_graph_enrichment(partial, graph_build)
    partial_summary = partial.generation_summary.features["community_names"]
    partial_summary.failed_target_count = 0
    with pytest.raises(InvalidGraphEnrichment):
        validate_graph_enrichment(partial, graph_build)


def test_overlay_persistence_round_trips_immutably_without_touching_layer4(
    tmp_path: Path,
) -> None:
    graph_build = _real_graph_build(tmp_path)
    structural = load_graph_snapshot_structural_state(graph_build)
    evidence = build_all_community_evidence(graph_build)
    records = [
        create_community_name_record(
            item,
            member_signature=structural["community_member_signatures"][
                item.community_id
            ],
            name=f"Community Name {item.community_id}",
            enrichment_id=f"record-{item.community_id}",
        )
        for item in evidence
    ]
    overlay = _overlay_with_records(graph_build, records)
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in graph_build.snapshot_root.iterdir()
        if path.is_file()
    }

    artifact = create_graph_enrichment(overlay, graph_build, tmp_path / ".bridger")
    assert artifact == (
        tmp_path
        / ".bridger"
        / "enrichment"
        / graph_build.manifest.snapshot_id
        / "overlay-1"
        / "graph-enrichment.json"
    )
    assert load_graph_enrichment(artifact, graph_build.manifest.snapshot_id) == overlay
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in graph_build.snapshot_root.iterdir()
        if path.is_file()
    }
    assert after == before

    with pytest.raises(InvalidGraphEnrichment, match="already exists"):
        create_graph_enrichment(overlay, graph_build, tmp_path / ".bridger")
    with pytest.raises(InvalidGraphEnrichment, match="expected graph snapshot"):
        load_graph_enrichment(artifact, "other")


def test_reuse_matches_fingerprint_not_community_id_alone(
    graph_state: tuple[GraphBuildResult, dict[str, object]],
) -> None:
    graph_build, _ = graph_state
    evidence = build_community_evidence(graph_build, 4)
    overlay = _complete_overlay(graph_build)

    assert (
        _find_reusable_community_name(
            [overlay],
            evidence,
            member_signature="a91b37e84cd88210",
            profile_version="community-names-v1",
            provider="openai",
            model="gpt-test",
        )
        == "Payment Processing"
    )
    assert (
        _find_reusable_community_name(
            [overlay],
            evidence,
            member_signature="different",
            profile_version="community-names-v1",
            provider="openai",
            model="gpt-test",
        )
        is None
    )


def _complete_overlay(graph_build: GraphBuildResult) -> GraphEnrichmentOverlay:
    evidence = build_community_evidence(graph_build, 4)
    record = create_community_name_record(
        evidence,
        member_signature="a91b37e84cd88210",
        name="Payment Processing",
        enrichment_id="record-1",
    )
    return GraphEnrichmentOverlay(
        schema_version="2",
        overlay_id="overlay-1",
        graph_snapshot_id="snapshot-1",
        generator_version="bridger-test",
        provider="openai",
        model="gpt-test",
        profile_version="community-names-v1",
        enabled_features=["community_names"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        generation_summary=EnrichmentGenerationSummary(
            features={
                "community_names": FeatureGenerationSummary(
                    status="complete",
                    target_count=1,
                    generated_count=1,
                    reused_count=0,
                    failed_target_count=0,
                    batch_count=1,
                    failed_batch_count=0,
                )
            }
        ),
        records=[record],
    )


def _partial_overlay(graph_build: GraphBuildResult) -> GraphEnrichmentOverlay:
    del graph_build
    target_ref: EnrichmentTargetReference = {
        "community_id": 4,
        "member_signature": "a91b37e84cd88210",
    }
    return GraphEnrichmentOverlay(
        schema_version="2",
        overlay_id="overlay-partial",
        graph_snapshot_id="snapshot-1",
        generator_version="bridger-test",
        provider="openai",
        model="gpt-test",
        profile_version="community-names-v1",
        enabled_features=["community_names"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        generation_summary=EnrichmentGenerationSummary(
            features={
                "community_names": FeatureGenerationSummary(
                    status="partial",
                    target_count=1,
                    generated_count=0,
                    reused_count=0,
                    failed_target_count=1,
                    batch_count=1,
                    failed_batch_count=1,
                    failed_batches=[
                        FailedEnrichmentBatch(
                            batch_id="batch-1",
                            target_refs=[target_ref],
                            attempts=3,
                            error_category="provider_error",
                        )
                    ],
                )
            }
        ),
        records=[],
    )


def _overlay_with_records(
    graph_build: GraphBuildResult,
    records: list[EnrichmentRecord],
) -> GraphEnrichmentOverlay:
    return GraphEnrichmentOverlay(
        schema_version="2",
        overlay_id="overlay-1",
        graph_snapshot_id=graph_build.manifest.snapshot_id,
        generator_version="bridger-test",
        provider="openai",
        model="gpt-test",
        profile_version="community-names-v1",
        enabled_features=["community_names"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        generation_summary=EnrichmentGenerationSummary(
            features={
                "community_names": FeatureGenerationSummary(
                    status="complete",
                    target_count=len(records),
                    generated_count=len(records),
                    reused_count=0,
                    failed_target_count=0,
                    batch_count=1 if records else 0,
                    failed_batch_count=0,
                )
            }
        ),
        records=records,
    )


def _real_graph_build(tmp_path: Path) -> GraphBuildResult:
    repository = tmp_path / "real-repository"
    repository.mkdir()
    records: list[FileRecord] = []
    nodes: list[dict[str, str]] = []
    for node_id in ("a", "b", "c"):
        source_path = f"{node_id}.py"
        (repository / source_path).write_text("pass\n", encoding="utf-8")
        records.append(
            FileRecord(
                path=source_path,
                git_object_id="a" * 40,
                size_bytes=5,
                content_type="source",
                language="python",
                disposition=FileDisposition(
                    read_mode="full",
                    processing_mode="extract",
                ),
            )
        )
        nodes.append(
            {
                "id": node_id,
                "label": node_id,
                "file_type": "code",
                "source_file": source_path,
                "source_location": "L1",
                "_origin": "ast",
            }
        )
    context = RepositoryContext(
        repository_id="layer-5-integration",
        root_path=repository,
        revision="b" * 40,
    )
    file_index = FileIndex(
        schema_version="1",
        repository_id=context.repository_id,
        revision=context.revision,
        scope_path=context.scope_path,
        files=records,
        summary=summarize_files(records),
    )
    extraction: dict[str, Any] = {
        "nodes": nodes,
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "_origin": "ast",
            },
            {
                "source": "b",
                "target": "c",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "b.py",
                "_origin": "ast",
            },
        ],
        "hyperedges": [],
    }
    config = GraphConstructionConfig()
    graph, diagnostics, structural = build_graph_intelligence(
        context,
        file_index,
        extraction,
        config,
    )
    return create_graph_snapshot(
        context,
        file_index,
        graph,
        diagnostics,
        structural,
        config,
        tmp_path / ".bridger" / "graph",
    )
