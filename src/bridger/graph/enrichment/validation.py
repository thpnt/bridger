"""Validation of Layer 5 overlays against deterministic graph snapshots."""

from pydantic import ValidationError

from bridger.contracts.enrichment import (
    EnrichmentTargetReference,
    FeatureGenerationSummary,
    GraphEnrichmentOverlay,
)
from bridger.contracts.graph import GraphBuildResult
from bridger.graph.enrichment.errors import InvalidGraphEnrichment
from bridger.graph.enrichment.evidence import (
    build_all_community_evidence,
    community_deterministic_features,
)
from bridger.graph.lifecycle import load_graph_snapshot_structural_state

ENRICHMENT_SCHEMA_VERSION = "2"
_V0_FEATURE = "community_names"


def validate_graph_enrichment(
    overlay: GraphEnrichmentOverlay,
    graph_build: GraphBuildResult,
) -> None:
    """Reject an overlay that is inconsistent with its deterministic snapshot."""
    try:
        validated = GraphEnrichmentOverlay.model_validate(
            overlay.model_dump(mode="python")
        )
    except (AttributeError, ValidationError, ValueError) as error:
        raise InvalidGraphEnrichment("overlay schema is invalid") from error

    if validated.schema_version != ENRICHMENT_SCHEMA_VERSION:
        raise InvalidGraphEnrichment("unsupported enrichment schema version")
    if validated.graph_snapshot_id != graph_build.manifest.snapshot_id:
        raise InvalidGraphEnrichment("overlay graph snapshot binding is invalid")
    if validated.enabled_features != [_V0_FEATURE]:
        raise InvalidGraphEnrichment("overlay enables an unsupported feature")
    if set(validated.generation_summary.features) != {_V0_FEATURE}:
        raise InvalidGraphEnrichment(
            "generation summary does not match enabled features"
        )

    structural = load_graph_snapshot_structural_state(graph_build)
    communities: dict[int, list[str]] = structural["communities"]
    signatures: dict[int, str] = structural["community_member_signatures"]
    evidence_by_id = {
        evidence.community_id: evidence
        for evidence in build_all_community_evidence(graph_build)
    }

    record_communities: set[int] = set()
    enrichment_ids: set[str] = set()
    for record in validated.records:
        if record.enrichment_id in enrichment_ids:
            raise InvalidGraphEnrichment("duplicate enrichment_id")
        enrichment_ids.add(record.enrichment_id)
        _validate_generic_target(record.target_type, record.target_ref, graph_build)
        if record.target_type != "community" or record.annotation_type != "name":
            raise InvalidGraphEnrichment(
                "overlay contains an unsupported V0 target or annotation type"
            )
        community_id, member_signature = _community_target(record.target_ref)
        _validate_community_identity(
            community_id,
            member_signature,
            communities,
            signatures,
        )
        if community_id in record_communities:
            raise InvalidGraphEnrichment("duplicate community-name annotation")
        record_communities.add(community_id)
        if not isinstance(record.value, str) or not record.value.strip():
            raise InvalidGraphEnrichment("community-name value is invalid")
        expected_features = community_deterministic_features(
            evidence_by_id[community_id]
        )
        if record.deterministic_features != expected_features:
            raise InvalidGraphEnrichment(
                "community deterministic_features do not match canonical evidence"
            )

    summary = validated.generation_summary.features[_V0_FEATURE]
    failed_communities = _validate_generation_summary(
        summary,
        communities,
        signatures,
        graph_build,
    )
    if record_communities & failed_communities:
        raise InvalidGraphEnrichment("failed targets also have community-name records")
    if record_communities | failed_communities != set(communities):
        raise InvalidGraphEnrichment("overlay coverage does not match communities")
    if summary.generated_count + summary.reused_count != len(validated.records):
        raise InvalidGraphEnrichment(
            "record count does not match generated and reused counts"
        )


def _validate_generation_summary(
    summary: FeatureGenerationSummary,
    communities: dict[int, list[str]],
    signatures: dict[int, str],
    graph_build: GraphBuildResult,
) -> set[int]:
    if summary.target_count != len(communities):
        raise InvalidGraphEnrichment("summary target_count does not match communities")
    expected_batch_presence = summary.generated_count + summary.failed_target_count > 0
    if expected_batch_presence != (summary.batch_count > 0):
        raise InvalidGraphEnrichment("summary batch_count is inconsistent")

    batch_ids: set[str] = set()
    failed_communities: set[int] = set()
    for batch in summary.failed_batches:
        if batch.batch_id in batch_ids:
            raise InvalidGraphEnrichment("duplicate failed batch_id")
        batch_ids.add(batch.batch_id)
        for target_ref in batch.target_refs:
            _validate_generic_target("community", target_ref, graph_build)
            community_id, member_signature = _community_target(target_ref)
            _validate_community_identity(
                community_id,
                member_signature,
                communities,
                signatures,
            )
            if community_id in failed_communities:
                raise InvalidGraphEnrichment("duplicate failed community target")
            failed_communities.add(community_id)
    if len(failed_communities) != summary.failed_target_count:
        raise InvalidGraphEnrichment(
            "failed target references do not match failed_target_count"
        )
    return failed_communities


def _community_target(target_ref: EnrichmentTargetReference) -> tuple[int, str]:
    if not isinstance(target_ref, dict) or set(target_ref) != {
        "community_id",
        "member_signature",
    }:
        raise InvalidGraphEnrichment(
            "community target_ref requires community_id and member_signature"
        )
    community_id = target_ref["community_id"]
    member_signature = target_ref["member_signature"]
    if (
        isinstance(community_id, bool)
        or not isinstance(community_id, int)
        or not isinstance(member_signature, str)
        or not member_signature
    ):
        raise InvalidGraphEnrichment("community target_ref is invalid")
    return community_id, member_signature


def _validate_community_identity(
    community_id: int,
    member_signature: str,
    communities: dict[int, list[str]],
    signatures: dict[int, str],
) -> None:
    if community_id not in communities:
        raise InvalidGraphEnrichment("community target does not exist")
    if signatures[community_id] != member_signature:
        raise InvalidGraphEnrichment("community member_signature does not match")


def _validate_generic_target(
    target_type: str,
    target_ref: EnrichmentTargetReference,
    graph_build: GraphBuildResult,
) -> None:
    graph = graph_build.graph
    if target_type == "node":
        if not isinstance(target_ref, str) or target_ref not in graph:
            raise InvalidGraphEnrichment("node target does not exist")
        return
    if target_type == "edge":
        if not isinstance(target_ref, dict) or set(target_ref) != {
            "source_node_id",
            "target_node_id",
            "relation",
        }:
            raise InvalidGraphEnrichment("edge target_ref is invalid")
        source = target_ref["source_node_id"]
        target = target_ref["target_node_id"]
        relation = target_ref["relation"]
        if not all(isinstance(value, str) for value in (source, target, relation)):
            raise InvalidGraphEnrichment("edge target_ref is invalid")
        if not graph.has_edge(source, target):
            raise InvalidGraphEnrichment("edge target does not exist")
        if graph[source][target].get("relation") != relation:
            raise InvalidGraphEnrichment("edge target relation does not match")
        return
    if target_type == "hyperedge":
        hyperedge_ids = {
            hyperedge.get("id")
            for hyperedge in graph.graph.get("hyperedges", [])
            if isinstance(hyperedge, dict)
        }
        if not isinstance(target_ref, str) or target_ref not in hyperedge_ids:
            raise InvalidGraphEnrichment("hyperedge target does not exist")
        return
    if target_type == "community":
        _community_target(target_ref)
        return
    if target_type == "graph":
        if target_ref != "graph":
            raise InvalidGraphEnrichment("graph target_ref is invalid")
        return
    raise InvalidGraphEnrichment("unknown deterministic target type")


__all__ = ["ENRICHMENT_SCHEMA_VERSION", "validate_graph_enrichment"]
