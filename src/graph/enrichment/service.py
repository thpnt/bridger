"""End-to-end Layer 5 V0 enrichment orchestration."""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from graph.enrichment.errors import InvalidGraphEnrichment
from graph.enrichment.evidence import build_all_community_evidence
from graph.enrichment.execution import (
    CommunityNameBatchRequest,
    CommunityNameBatchResult,
    build_community_name_batches,
    execute_community_name_batches,
)
from graph.enrichment.fingerprint import (
    _index_reusable_community_names,
    community_name_input_fingerprint,
)
from graph.enrichment.persistence import (
    create_graph_enrichment,
    load_graph_enrichment,
)
from graph.enrichment.records import create_community_name_record
from graph.enrichment.validation import (
    ENRICHMENT_SCHEMA_VERSION,
    validate_graph_enrichment,
)
from graph.lifecycle import load_graph_snapshot_structural_state
from llm.client import LLMClient
from llm.factory import create_llm_client_from_profile
from llm.profiles import LLMProfile, RetryPolicy
from models.enrichment import (
    CommunityEvidence,
    EnrichmentGenerationSummary,
    EnrichmentRecord,
    FailedEnrichmentBatch,
    FeatureGenerationSummary,
    GraphEnrichmentConfig,
    GraphEnrichmentOverlay,
)
from models.graph import GraphBuildResult

LAYER5_GENERATOR_VERSION = "bridger.layer5.v1"
_FEATURE_ID = "community_names"


def enrich_graph_snapshot(
    graph_build: GraphBuildResult,
    config: GraphEnrichmentConfig,
) -> GraphEnrichmentOverlay:
    """Generate, validate, and publish one V0 enrichment overlay."""
    validated_config = GraphEnrichmentConfig.model_validate(
        config.model_dump(mode="python")
    )
    bridger_root = _resolve_bridger_root(graph_build)
    structural = load_graph_snapshot_structural_state(graph_build)
    signatures: dict[int, str] = structural["community_member_signatures"]
    evidence = build_all_community_evidence(graph_build)

    reusable_names = _index_reusable_community_names(
        _discover_previous_overlays(bridger_root)
    )
    reused: dict[int, str] = {}
    generation_targets: list[CommunityEvidence] = []
    for item in evidence:
        fingerprint = community_name_input_fingerprint(
            item,
            member_signature=signatures[item.community_id],
            profile_version=validated_config.profile_version,
            provider=validated_config.provider,
            model=validated_config.model,
        )
        reusable_name = reusable_names.get(fingerprint)
        if reusable_name is None:
            generation_targets.append(item)
        else:
            reused[item.community_id] = reusable_name

    batches = build_community_name_batches(generation_targets)
    batch_results: list[CommunityNameBatchResult] = []
    if batches:
        client = _create_community_name_client(validated_config)
        batch_results = _run_batch_execution(
            client,
            batches,
            profile_version=validated_config.profile_version,
            max_concurrency=validated_config.max_concurrency,
        )

    generated = _generated_names(batch_results)
    records = _build_records(
        evidence,
        signatures=signatures,
        reused=reused,
        generated=generated,
    )
    failed_batches = _failed_batches(batch_results, signatures)
    failed_target_count = sum(len(batch.target_refs) for batch in failed_batches)
    summary = FeatureGenerationSummary(
        status="partial" if failed_target_count else "complete",
        target_count=len(evidence),
        generated_count=len(generated),
        reused_count=len(reused),
        failed_target_count=failed_target_count,
        batch_count=len(batches),
        failed_batch_count=len(failed_batches),
        failed_batches=failed_batches,
    )
    overlay = GraphEnrichmentOverlay(
        schema_version=ENRICHMENT_SCHEMA_VERSION,
        overlay_id=f"overlay-{uuid.uuid4().hex}",
        graph_snapshot_id=graph_build.manifest.snapshot_id,
        generator_version=LAYER5_GENERATOR_VERSION,
        provider=validated_config.provider,
        model=validated_config.model,
        profile_version=validated_config.profile_version,
        enabled_features=list(validated_config.enabled_features),
        created_at=datetime.now(UTC),
        generation_summary=EnrichmentGenerationSummary(features={_FEATURE_ID: summary}),
        records=records,
    )
    validate_graph_enrichment(overlay, graph_build)
    create_graph_enrichment(overlay, graph_build, bridger_root)
    return overlay


def _create_community_name_client(config: GraphEnrichmentConfig) -> LLMClient:
    profile = LLMProfile(
        name=f"layer5-{config.profile_version}",
        provider=config.provider,
        model=config.model,
        retry_policy=RetryPolicy(max_attempts=1),
    )
    return create_llm_client_from_profile(profile)


def _run_batch_execution(
    client: LLMClient,
    batches: list[CommunityNameBatchRequest],
    *,
    profile_version: str,
    max_concurrency: int,
) -> list[CommunityNameBatchResult]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            execute_community_name_batches(
                client,
                batches,
                profile_version=profile_version,
                max_concurrency=max_concurrency,
            )
        )
    raise RuntimeError("enrich_graph_snapshot cannot run inside an active event loop")


def _generated_names(results: list[CommunityNameBatchResult]) -> dict[int, str]:
    generated: dict[int, str] = {}
    for result in results:
        if result.names is not None:
            generated.update(result.names)
    return generated


def _build_records(
    evidence: list[CommunityEvidence],
    *,
    signatures: dict[int, str],
    reused: dict[int, str],
    generated: dict[int, str],
) -> list[EnrichmentRecord]:
    records: list[EnrichmentRecord] = []
    for item in evidence:
        name = reused.get(item.community_id, generated.get(item.community_id))
        if name is None:
            continue
        records.append(
            create_community_name_record(
                item,
                member_signature=signatures[item.community_id],
                name=name,
            )
        )
    return records


def _failed_batches(
    results: list[CommunityNameBatchResult],
    signatures: dict[int, str],
) -> list[FailedEnrichmentBatch]:
    failed: list[FailedEnrichmentBatch] = []
    for result in results:
        if result.names is not None:
            continue
        if result.error_category is None:
            raise RuntimeError("failed community-name batch has no error category")
        failed.append(
            FailedEnrichmentBatch(
                batch_id=result.batch.batch_id,
                target_refs=[
                    {
                        "community_id": item.community_id,
                        "member_signature": signatures[item.community_id],
                    }
                    for item in result.batch.evidence
                ],
                attempts=result.attempts,
                error_category=result.error_category,
            )
        )
    return failed


def _discover_previous_overlays(
    bridger_root: Path,
) -> list[GraphEnrichmentOverlay]:
    enrichment_root = bridger_root / "enrichment"
    overlays: list[GraphEnrichmentOverlay] = []
    for artifact in sorted(enrichment_root.glob("*/*/graph-enrichment.json")):
        graph_snapshot_id = artifact.parent.parent.name
        try:
            overlay = load_graph_enrichment(artifact, graph_snapshot_id)
        except InvalidGraphEnrichment:
            continue
        overlays.append(overlay)
    return overlays


def _resolve_bridger_root(graph_build: GraphBuildResult) -> Path:
    snapshot_root = graph_build.snapshot_root
    if (
        snapshot_root.parent.name != "snapshots"
        or snapshot_root.parent.parent.name != "graph"
    ):
        raise InvalidGraphEnrichment(
            "graph snapshot is not under the locked .bridger/graph layout"
        )
    return snapshot_root.parent.parent.parent


__all__ = ["LAYER5_GENERATOR_VERSION", "enrich_graph_snapshot"]
