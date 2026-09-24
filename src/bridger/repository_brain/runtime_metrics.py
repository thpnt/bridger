"""Derive and persist one invocation's runtime measurements."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

import orjson
from pydantic import ValidationError

from bridger.artifacts.writer import write_artifact
from bridger.contracts.memory.persistence import TaskEvent
from bridger.contracts.runtime_metrics import (
    BatchMetrics,
    BatchStep,
    CycleMetrics,
    RuntimeMetricsReport,
    TargetMetrics,
)
from bridger.runtime_timing import RuntimeMetricsCollector


def _ms(start: str, end: str) -> float:
    return max(
        0,
        (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        * 1000,
    )


def _wall_breakdown(
    started_at: str,
    total_ms: float,
    windows: list[tuple[int, str, float]],
) -> list[float]:
    """Count overlapping waits once for the wall-clock CLI summary."""
    edges: list[tuple[float, int, int]] = []
    for category, start_at, duration in windows:
        start = min(total_ms, _ms(started_at, start_at))
        end = min(total_ms, start + duration)
        if end > start:
            edges.extend(((start, category, 1), (end, category, -1)))
    edges.sort()
    active = [0, 0, 0, 0]
    totals = [0.0, 0.0, 0.0, 0.0]
    previous = 0.0
    for position, category, delta in edges:
        for index, count in enumerate(active):
            if count:
                totals[index] += position - previous
                break
        active[category] += delta
        previous = position
    return totals


def _events(bridger_root: Path, metrics: RuntimeMetricsCollector) -> list[TaskEvent]:
    if metrics.fleet_run_id is None or metrics.reused:
        return []
    path = bridger_root / "runtime" / metrics.fleet_run_id / "events.jsonl"
    if not path.exists():
        return []
    start = datetime.fromisoformat(metrics.started_at)
    events = []
    with path.open("rb") as stream:
        for line in stream:
            try:
                record = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get("event_type") not in {
                "cycle_finished",
                "finalization_requested",
                "target_accepted",
            }:
                continue
            try:
                event = TaskEvent.model_validate(record)
            except ValidationError:
                continue
            if datetime.fromisoformat(event.timestamp) >= start:
                events.append(event)
    return events


def build_runtime_metrics_report(
    metrics: RuntimeMetricsCollector,
    *,
    bridger_root: Path,
    mode: str,
    fresh: bool,
    model: str | None,
    reasoning_effort: str,
    model_profile: str,
    status: str,
) -> RuntimeMetricsReport:
    """Summarize stopwatch spans and this invocation's existing TaskEvents."""
    with metrics.lock:
        spans = list(metrics.spans)
        calls = list(metrics.model_calls)
        tools = list(metrics.tool_calls)
        backoffs = list(metrics.backoffs)
    events = _events(bridger_root, metrics)
    finished_at = metrics.utc_now().isoformat()
    total_ms = max(0, (metrics.clock_ns() - metrics.started_ns) / 1_000_000)
    by_name = defaultdict(list)
    for span in spans:
        by_name[span.name].append(span)

    event_by_target: dict[str, list[TaskEvent]] = defaultdict(list)
    cycle_ids: dict[tuple[str, int], str] = {}
    for event in events:
        if event.target_task_id is not None:
            event_by_target[event.target_task_id].append(event)
            if event.event_type == "cycle_finished":
                number = event.payload.get("cycle_number")
                cycle_id = event.payload.get("cycle_id")
                if isinstance(number, int) and isinstance(cycle_id, str):
                    cycle_ids[(event.target_task_id, number)] = cycle_id

    steps = by_name["target_step"]
    target_task_ids = set(metrics.target_ids) | {
        s.target_task_id for s in steps if s.target_task_id
    }
    targets = []
    for task_id in sorted(target_task_ids):
        target_spans = [s for s in spans if s.target_task_id == task_id]
        target_steps = [s for s in steps if s.target_task_id == task_id]
        target_events = event_by_target[task_id]
        first_start = min((s.started_at for s in target_steps), default=None)
        accepted_at = next(
            (
                e.timestamp
                for e in reversed(target_events)
                if e.event_type == "target_accepted"
            ),
            None,
        )
        finalization_at = next(
            (
                e.timestamp
                for e in target_events
                if e.event_type == "finalization_requested"
            ),
            None,
        )
        cycle_reports = []
        for span in target_spans:
            if span.name != "worker_cycle":
                continue
            cycle_id = cycle_ids.get((task_id, span.cycle_number or 0))
            hydration = sum(
                s.duration_ms
                for s in target_spans
                if s.name == "context_hydration" and s.cycle_number == span.cycle_number
            )
            hydration_mode = next(
                (
                    s.mode
                    for s in target_spans
                    if s.name == "context_hydration"
                    and s.cycle_number == span.cycle_number
                ),
                None,
            )
            model_wait = (
                sum(
                    c.duration_ms
                    for c in calls
                    if c.target_task_id == task_id and c.cycle_id == cycle_id
                )
                if cycle_id
                else 0
            )
            tool_wait = (
                sum(
                    t.duration_ms
                    for t in tools
                    if t.target_task_id == task_id and t.cycle_id == cycle_id
                )
                if cycle_id
                else 0
            )
            retry = (
                sum(
                    ms
                    for target, cycle, _start, ms in backoffs
                    if target == task_id and cycle == cycle_id
                )
                if cycle_id
                else 0
            )
            cycle_reports.append(
                CycleMetrics(
                    cycle_number=span.cycle_number or 0,
                    cycle_id=cycle_id,
                    duration_ms=span.duration_ms,
                    outcome=span.outcome or span.status,
                    mode=hydration_mode,
                    repair=bool(span.repair),
                    context_hydration_ms=hydration,
                    model_wait_ms=model_wait,
                    tool_wait_ms=tool_wait,
                    retry_backoff_ms=retry,
                    other_harness_ms=max(
                        0, span.duration_ms - model_wait - tool_wait - retry
                    ),
                )
            )
        validation = [s for s in target_spans if s.name == "target_validation"]
        review = [s for s in target_spans if s.name == "target_review"]
        targets.append(
            TargetMetrics(
                target_task_id=task_id,
                target_id=metrics.target_ids.get(task_id, task_id),
                first_execution_started_at=first_start,
                accepted_at=accepted_at,
                elapsed_ms=_ms(first_start, accepted_at)
                if first_start and accepted_at
                else None,
                active_step_ms=sum(s.duration_ms for s in target_steps),
                cycles=cycle_reports,
                repair_cycles=sum(c.repair for c in cycle_reports),
                hydration_ms=sum(c.context_hydration_ms for c in cycle_reports),
                worker_cycle_ms=sum(c.duration_ms for c in cycle_reports),
                model_wait_ms=sum(
                    c.duration_ms for c in calls if c.target_task_id == task_id
                ),
                retry_backoff_ms=sum(
                    duration
                    for target, _cycle, _start, duration in backoffs
                    if target == task_id
                ),
                tool_wait_ms=sum(
                    t.duration_ms for t in tools if t.target_task_id == task_id
                ),
                validation_attempts=len(validation),
                validation_time_ms=sum(s.duration_ms for s in validation),
                review_attempts=len(review),
                review_time_ms=sum(s.duration_ms for s in review),
                time_to_first_finalization_ms=_ms(first_start, finalization_at)
                if first_start and finalization_at
                else None,
                time_to_acceptance_ms=_ms(first_start, accepted_at)
                if first_start and accepted_at
                else None,
                repair_penalty_ms=_ms(finalization_at, accepted_at)
                if finalization_at and accepted_at
                else None,
            )
        )

    batches = []
    critical_steps = []
    critical_targets = []
    for index, batch in enumerate(by_name["target_batch"], start=1):
        contained = [s for s in steps if batch.started_at <= s.started_at <= s.ended_at]
        ranked = sorted(contained, key=lambda s: s.duration_ms, reverse=True)
        if ranked:
            critical_steps.append(f"batch-{index}:{ranked[0].target_task_id}")
            if ranked[0].target_task_id is not None:
                critical_targets.append(ranked[0].target_task_id)
        batches.append(
            BatchMetrics(
                batch_id=f"batch-{index}",
                started_at=batch.started_at,
                duration_ms=batch.duration_ms,
                target_steps=[
                    BatchStep(
                        target_task_id=s.target_task_id or "",
                        duration_ms=s.duration_ms,
                        outcome=s.outcome or s.status,
                        barrier_wait_ms=max(0, batch.duration_ms - s.duration_ms),
                    )
                    for s in contained
                ],
                slowest_target=ranked[0].target_task_id if ranked else None,
                straggler_extension_ms=(ranked[0].duration_ms - ranked[1].duration_ms)
                if len(ranked) > 1
                else 0,
            )
        )
    fleet_wall = sum(s.duration_ms for s in by_name["memory_fleet"])
    target_work = sum(s.duration_ms for s in steps)
    model_wait = sum(c.duration_ms for c in calls)
    retry_wait = sum(item[3] for item in backoffs)
    tool_wait = sum(t.duration_ms for t in tools)
    validation_review = sum(
        s.duration_ms
        for s in spans
        if s.name
        in {
            "target_validation",
            "target_review",
            "fleet_validation",
            "fleet_reconciliation",
        }
    )
    wall_model, wall_tool, wall_review, wall_retry = _wall_breakdown(
        metrics.started_at,
        total_ms,
        [(0, call.started_at, call.duration_ms) for call in calls]
        + [(1, tool.started_at, tool.duration_ms) for tool in tools]
        + [
            (2, span.started_at, span.duration_ms)
            for span in spans
            if span.name
            in {
                "target_validation",
                "target_review",
                "fleet_validation",
                "fleet_reconciliation",
            }
        ]
        + [(3, start_at, duration) for _target, _cycle, start_at, duration in backoffs],
    )
    tool_by_name: dict[str, dict[str, float]] = {}
    for name in sorted({t.tool for t in tools}):
        durations = [t.duration_ms for t in tools if t.tool == name]
        tool_by_name[name] = {
            "calls": len(durations),
            "total_duration_ms": sum(durations),
            "average_duration_ms": sum(durations) / len(durations),
            "max_duration_ms": max(durations),
        }
    model_by_role = {
        role: {
            "calls": sum(c.role == role for c in calls),
            "total_duration_ms": sum(c.duration_ms for c in calls if c.role == role),
        }
        for role in sorted({c.role for c in calls})
    }
    fleet_validation = sum(s.duration_ms for s in by_name["fleet_validation"])
    fleet_reconciliation = sum(s.duration_ms for s in by_name["fleet_reconciliation"])
    publication = sum(s.duration_ms for s in by_name["brain_publication"])
    publication += sum(s.duration_ms for s in by_name["token_report_persistence"])
    critical_path = (
        sum(max((s.duration_ms for s in b.target_steps), default=0) for b in batches)
        + fleet_validation
        + fleet_reconciliation
        + publication
    )
    if fleet_validation:
        critical_steps.append("fleet_validation")
    if fleet_reconciliation:
        critical_steps.append("fleet_reconciliation")
    if publication:
        critical_steps.append("fleet_publication")
    return RuntimeMetricsReport(
        init_run_id=metrics.init_run_id,
        fleet_run_id=metrics.fleet_run_id,
        repository_id=metrics.repository_id,
        repository_revision=metrics.revision,
        mode=mode,
        fresh=fresh,
        reused=metrics.reused,
        resumed=metrics.resumed,
        model=model,
        reasoning_effort=reasoning_effort,
        model_profile=model_profile,
        started_at=metrics.started_at,
        finished_at=finished_at,
        status=status,
        failed_stage=metrics.failed_stage if status == "failed" else None,
        total_duration_ms=total_ms,
        deterministic_total_ms=sum(
            s.duration_ms
            for s in spans
            if s.name
            in {"prepare_repository", "extract_facts", "build_graph", "publish_graph"}
        ),
        model_driven_total_ms=sum(
            s.duration_ms
            for s in spans
            if s.name in {"model_enrichment", "memory_fleet"}
        ),
        stages=[
            s
            for s in spans
            if s.name
            in {
                "prepare_repository",
                "extract_facts",
                "build_graph",
                "publish_graph",
                "model_enrichment",
                "memory_fleet",
                "brain_publication",
                "brain_index",
            }
        ],
        targets=targets,
        model_calls=calls,
        model_provider_wait_ms=model_wait,
        retry_backoff_ms=retry_wait,
        total_model_wait_ms=model_wait + retry_wait,
        model_wall_ms=wall_model,
        retry_backoff_wall_ms=wall_retry,
        model_by_role=model_by_role,
        tool_calls=tools,
        total_tool_wait_ms=tool_wait,
        tool_wall_ms=wall_tool,
        tool_by_name=tool_by_name,
        batches=batches,
        configured_concurrency=metrics.configured_concurrency,
        fleet_wall_time_ms=fleet_wall,
        total_target_work_ms=target_work,
        average_active_targets=target_work / fleet_wall if fleet_wall else 0,
        effective_parallel_speedup=target_work / fleet_wall if fleet_wall else 0,
        concurrency_utilization=(
            target_work / (fleet_wall * metrics.configured_concurrency)
        )
        if fleet_wall and metrics.configured_concurrency
        else 0,
        total_barrier_wait_ms=sum(
            s.barrier_wait_ms for b in batches for s in b.target_steps
        ),
        fleet_validation_ms=fleet_validation,
        fleet_reconciliation_ms=fleet_reconciliation,
        checkpoint_ms=sum(s.duration_ms for s in by_name["checkpoint"]),
        token_report_persistence_ms=sum(
            s.duration_ms for s in by_name["token_report_persistence"]
        ),
        brain_publication_ms=sum(s.duration_ms for s in by_name["brain_publication"]),
        brain_index_ms=sum(s.duration_ms for s in by_name["brain_index"]),
        validation_and_review_ms=validation_review,
        validation_review_wall_ms=wall_review,
        critical_path_ms=critical_path,
        critical_path_steps=critical_steps,
        critical_path_target_ids=list(dict.fromkeys(critical_targets)),
        other_harness_ms=max(
            0, total_ms - wall_model - wall_tool - wall_review - wall_retry
        ),
    )


def persist_runtime_metrics_report(
    report: RuntimeMetricsReport, bridger_root: Path
) -> Path:
    destination = (
        bridger_root
        / "runtime"
        / "metrics"
        / report.init_run_id
        / "runtime-metrics.json"
    )
    write_artifact(destination, report)
    return destination


def load_runtime_metrics_report(path: Path) -> RuntimeMetricsReport:
    return RuntimeMetricsReport.model_validate_json(path.read_bytes())
