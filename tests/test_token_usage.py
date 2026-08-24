"""Focused tests for the consolidated model-driven init token audit."""

from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest

from bridger.artifacts.writer import write_artifact
from bridger.contracts.enrichment import (
    EnrichmentGenerationSummary,
    FeatureGenerationSummary,
    GraphEnrichmentOverlay,
)
from bridger.contracts.memory.core import (
    ExecutionBudget,
    ExecutionUsage,
    FleetRunState,
    MemoryFleetSpec,
    SourceBinding,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.token_usage import TokenUsage
from bridger.memory.persistence.durability import FleetRuntimeStore
from bridger.repository_brain.token_usage import (
    build_token_usage_report,
    load_token_usage_report,
    persist_token_usage_report,
)


def test_report_uses_durable_target_and_fleet_usage_without_double_counting_cache(
    tmp_path: Path,
) -> None:
    spec = _fleet_spec(tmp_path, target_ids=["target-b", "target-a"])
    store = _write_durable_usage(
        spec,
        fleet_usage=ExecutionUsage(
            input_tokens=100,
            cached_input_tokens=30,
            cache_write_tokens=4,
            output_tokens=20,
        ),
        target_usages={
            "target-b": ExecutionUsage(
                input_tokens=60,
                cached_input_tokens=10,
                cache_write_tokens=1,
                output_tokens=9,
            ),
            "target-a": ExecutionUsage(
                input_tokens=25,
                cached_input_tokens=5,
                cache_write_tokens=2,
                output_tokens=6,
            ),
        },
    )
    enrichment = _enrichment(
        TokenUsage(input_tokens=12, cached_input_tokens=2, output_tokens=3)
    )

    report_path = persist_token_usage_report("test", spec, store, enrichment)
    report = load_token_usage_report(report_path)

    assert [target.target_id for target in report.targets] == ["target-b", "target-a"]
    assert report.fleet_only_memory_overhead == TokenUsage(
        input_tokens=15,
        cached_input_tokens=15,
        cache_write_tokens=1,
        output_tokens=5,
    )
    assert report.memory_total.input_tokens == 100
    assert report.memory_total.uncached_input_tokens == 70
    assert report.init_total.input_tokens == 112
    assert report.init_total.cached_input_tokens == 32
    assert report.init_total.uncached_input_tokens == 80
    assert report.init_total.output_tokens == 23
    raw = orjson.loads(report_path.read_bytes())
    assert "uncached_input_tokens" not in orjson.dumps(raw).decode()


def test_report_rejects_negative_fleet_only_overhead(tmp_path: Path) -> None:
    spec = _fleet_spec(tmp_path, target_ids=["target-a"])
    store = _write_durable_usage(
        spec,
        fleet_usage=ExecutionUsage(input_tokens=10),
        target_usages={"target-a": ExecutionUsage(input_tokens=11)},
    )

    with pytest.raises(ValueError, match="fleet-only token usage overhead is negative"):
        build_token_usage_report("full", spec, store, _enrichment(TokenUsage()))


def _fleet_spec(tmp_path: Path, *, target_ids: list[str]) -> MemoryFleetSpec:
    budget = ExecutionBudget(
        max_cycles=10,
        max_model_calls=10,
        max_tool_calls=10,
        max_repair_cycles=10,
    )
    return MemoryFleetSpec(
        fleet_run_id="fleet-audit",
        source=SourceBinding(
            repository_id="repository",
            repository_revision="revision",
            graph_snapshot_id="graph",
            enrichment_overlay_id="overlay",
        ),
        target_catalog_id="catalog",
        target_catalog_version="v1",
        target_ids=target_ids,
        runtime_profile_id="test-v1",
        default_worker_profile_id="worker",
        default_reviewer_profile_id="reviewer",
        default_permission_profile_id="permission",
        fleet_budget=budget,
        default_target_budget=budget,
        runtime_root=str(tmp_path / ".bridger" / "runtime"),
        output_root=str(tmp_path / ".bridger" / "memory"),
    )


def _write_durable_usage(
    spec: MemoryFleetSpec,
    *,
    fleet_usage: ExecutionUsage,
    target_usages: dict[str, ExecutionUsage],
) -> FleetRuntimeStore:
    store = FleetRuntimeStore(spec)
    store.paths.initialization_root.mkdir(parents=True, exist_ok=True)
    write_artifact(
        store.paths.fleet_state,
        FleetRunState(
            fleet_run_id=spec.fleet_run_id,
            target_task_ids=[f"task-{target_id}" for target_id in spec.target_ids],
            usage=fleet_usage,
        ),
    )
    for target_id in spec.target_ids:
        target_spec = TargetTaskSpec(
            target_task_id=f"task-{target_id}",
            fleet_run_id=spec.fleet_run_id,
            target_id=target_id,
            target_contract_version="v1",
            source=spec.source,
            worker_profile_id="worker",
            reviewer_profile_id="reviewer",
            permission_profile_id="permission",
            budget=spec.default_target_budget,
            target_workspace=str(Path(spec.output_root) / target_id),
        )
        write_artifact(store.paths.target_spec(target_id), target_spec)
        write_artifact(
            store.paths.target_state(target_spec),
            TargetTaskState(
                target_task_id=target_spec.target_task_id,
                fleet_run_id=spec.fleet_run_id,
                usage=target_usages[target_id],
            ),
        )
    return store


def _enrichment(usage: TokenUsage) -> GraphEnrichmentOverlay:
    return GraphEnrichmentOverlay(
        schema_version="2",
        overlay_id="overlay",
        graph_snapshot_id="graph",
        generator_version="bridger.layer5.v2",
        provider="openai",
        model="test-model",
        profile_version="test-v1",
        enabled_features=["community_names"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        generation_summary=EnrichmentGenerationSummary(
            features={
                "community_names": FeatureGenerationSummary(
                    status="complete",
                    target_count=0,
                    generated_count=0,
                    reused_count=0,
                    failed_target_count=0,
                    batch_count=0,
                    failed_batch_count=0,
                    usage=usage,
                )
            }
        ),
        records=[],
    )
