"""Derivation and atomic persistence of the model-driven init token audit."""

from pathlib import Path

from pydantic import ValidationError

from bridger.artifacts.writer import write_artifact
from bridger.contracts.enrichment import GraphEnrichmentOverlay
from bridger.contracts.memory.core import (
    ExecutionUsage,
    FleetRunState,
    MemoryFleetSpec,
    TargetTaskState,
)
from bridger.contracts.token_usage import TokenUsage, TokenUsageReport, TokenUsageTarget
from bridger.memory.persistence.durability import FleetRuntimeStore

_REPORT_FILE = "token-usage.json"


def build_token_usage_report(
    init_mode: str,
    fleet_spec: MemoryFleetSpec,
    store: FleetRuntimeStore,
    enrichment: GraphEnrichmentOverlay,
) -> TokenUsageReport:
    """Derive one report exclusively from persisted fleet and target state."""
    persisted_fleet = FleetRunState.model_validate_json(
        store.paths.fleet_state.read_bytes()
    )
    if persisted_fleet.fleet_run_id != fleet_spec.fleet_run_id:
        raise ValueError("persisted fleet state does not match fleet run")
    target_specs = store.load_target_specs()
    if persisted_fleet.target_task_ids != [
        target_spec.target_task_id for target_spec in target_specs
    ]:
        raise ValueError("persisted fleet target ordering is inconsistent")
    target_reports: list[TokenUsageTarget] = []
    for target_spec in target_specs:
        target_state = TargetTaskState.model_validate_json(
            store.paths.target_state(target_spec).read_bytes()
        )
        if (
            target_state.fleet_run_id != fleet_spec.fleet_run_id
            or target_state.target_task_id != target_spec.target_task_id
        ):
            raise ValueError("persisted target state does not match target spec")
        target_reports.append(
            TokenUsageTarget(
                target_task_id=target_spec.target_task_id,
                target_id=target_spec.target_id,
                usage=_from_execution_usage(target_state.usage),
            )
        )

    memory_total = _from_execution_usage(persisted_fleet.usage)
    target_total = TokenUsage()
    for target in target_reports:
        target_total = target_total.add(target.usage)
    fleet_only = _subtract_or_raise(memory_total, target_total)
    layer5_usage = enrichment.generation_summary.features["community_names"].usage
    return TokenUsageReport(
        init_mode=init_mode,
        fleet_run_id=fleet_spec.fleet_run_id,
        enrichment_overlay_id=enrichment.overlay_id,
        layer5_enrichment=layer5_usage,
        targets=target_reports,
        fleet_only_memory_overhead=fleet_only,
        memory_total=memory_total,
        init_total=layer5_usage.add(memory_total),
    )


def persist_token_usage_report(
    init_mode: str,
    fleet_spec: MemoryFleetSpec,
    store: FleetRuntimeStore,
    enrichment: GraphEnrichmentOverlay,
) -> Path:
    """Atomically write and round-trip the derived report beside fleet state."""
    report = build_token_usage_report(init_mode, fleet_spec, store, enrichment)
    destination = store.paths.run_root / _REPORT_FILE
    write_artifact(destination, report)
    try:
        persisted = TokenUsageReport.model_validate_json(destination.read_bytes())
    except (OSError, ValidationError) as error:
        raise ValueError("persisted token usage report is invalid") from error
    if persisted != report:
        raise ValueError("persisted token usage report did not round-trip")
    return destination


def load_token_usage_report(artifact: Path) -> TokenUsageReport:
    """Load one persisted init token audit."""
    try:
        return TokenUsageReport.model_validate_json(Path(artifact).read_bytes())
    except (OSError, ValidationError) as error:
        raise ValueError("token usage report is invalid") from error


def _from_execution_usage(usage: ExecutionUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        output_tokens=usage.output_tokens,
    )


def _subtract_or_raise(total: TokenUsage, target_total: TokenUsage) -> TokenUsage:
    """Derive fleet-only overhead and reject accounting drift."""
    try:
        return total.subtract(target_total)
    except ValueError as error:
        raise ValueError("fleet-only token usage overhead is negative") from error


__all__ = [
    "build_token_usage_report",
    "load_token_usage_report",
    "persist_token_usage_report",
]
