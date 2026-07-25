"""Deterministic runtime state for Context Plan repository discovery.

This module deliberately keeps mutable control state separate from the compact,
persisted ``ContextPlanRun`` artifact.  It is independent of LLM providers and
repository-tool implementations: callers provide shared tool requests, results,
and inspection deltas at the boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from pydantic import JsonValue

from bridger.artifacts import write_artifact
from bridger.deterministic.context_plan.evidence import EvidenceExtractor
from bridger.deterministic.context_plan.working_state import (
    WorkingStateMutationService,
)
from bridger.models.context_plan import (
    ContextPlanFinalizationRecord,
    ContextPlanFinalizationRequest,
    ContextPlanGraphQueryRecord,
    ContextPlanInspectedExcerpt,
    ContextPlanInspectedSymbol,
    ContextPlanRepository,
    ContextPlanRun,
    ContextPlanRunError,
    ContextPlanRunInspection,
    ContextPlanRunOutput,
    ContextPlanRunPhase,
    ContextPlanRunStatus,
    ContextPlanSearchRecord,
    ContextPlanValidationAttempt,
    ContextPlanValidationIssue,
    FinalizationContext,
    ToolBudgetCost,
    ToolCallRequest,
    ToolExecutionEvent,
    ToolExecutionEventType,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInspectionDelta,
)
from bridger.models.repository_path import RepositoryPath, validate_repository_path
from bridger.models.synthesis_manifest import SynthesisInputManifest

_COST_FIELDS = (
    "tool_calls",
    "file_reads",
    "excerpts",
    "searches",
    "symbol_queries",
    "graph_queries",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("runtime timestamps must be timezone-aware")
    return value


def _add_cost(left: ToolBudgetCost, right: ToolBudgetCost) -> ToolBudgetCost:
    return ToolBudgetCost(
        **{name: getattr(left, name) + getattr(right, name) for name in _COST_FIELDS}
    )


@dataclass(frozen=True)
class DiscoveryBudgetLimits:
    """Optional cumulative limits for one Context Plan run."""

    model_turns: int | None = None
    token_usage: int | None = None
    elapsed_seconds: int | None = None
    tool_calls: int | None = None
    file_reads: int | None = None
    excerpts: int | None = None
    searches: int | None = None
    symbol_queries: int | None = None
    graph_queries: int | None = None
    duplicate_call_threshold: int | None = None
    consecutive_no_progress_threshold: int | None = None

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class BudgetPreflightDecision:
    allowed: bool
    hard_budget_exhausted: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextPlanRunEvent:
    """In-memory lifecycle event with deliberately compact metadata."""

    event_type: str
    occurred_at: datetime
    metadata: dict[str, str | int | bool] = field(default_factory=dict)


class ToolCallFingerprinter:
    """Creates a stable digest from a tool name and canonical request arguments."""

    @staticmethod
    def fingerprint(request: ToolCallRequest) -> str:
        payload = {
            "arguments": ToolCallFingerprinter._normalize(request.arguments),
            "name": request.name,
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(serialized.encode()).hexdigest()

    @staticmethod
    def _normalize(value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            return {
                key: ToolCallFingerprinter._normalize(item)
                for key, item in sorted(value.items())
            }
        if isinstance(value, list):
            return [ToolCallFingerprinter._normalize(item) for item in value]
        if isinstance(value, str):
            # RepositoryPath is a constrained string at runtime. Revalidation
            # preserves its canonical form when a validated path is supplied;
            # ordinary strings remain ordinary tool arguments.
            try:
                return validate_repository_path(value)
            except ValueError:
                return value
        return value


class InspectionCoverageTracker:
    """Aggregates factual inspection only from explicit inspection deltas."""

    def __init__(self, safe_file_count: int) -> None:
        if safe_file_count < 0:
            raise ValueError("safe_file_count must be non-negative")
        self.safe_file_count = safe_file_count
        self.discovered_paths: set[RepositoryPath] = set()
        self.evidence_paths: set[RepositoryPath] = set()
        self.excerpts_read: set[tuple[RepositoryPath, int, int]] = set()
        self.symbols_inspected: set[tuple[str, RepositoryPath | None]] = set()
        self.searches_performed: dict[tuple[str, str], ContextPlanSearchRecord] = {}
        self.graph_paths_inspected: set[RepositoryPath] = set()
        self.manifests_inspected: set[RepositoryPath] = set()

    def apply(self, delta: ToolInspectionDelta) -> bool:
        """Apply one delta and return whether it added new factual inspection."""

        before = self._identity_set()
        self.discovered_paths.update(delta.discovered_paths)
        self.evidence_paths.update(delta.evidence_paths)
        self.excerpts_read.update(
            (item.path, item.line_start, item.line_end) for item in delta.excerpts_read
        )
        self.symbols_inspected.update(
            (item.identifier, item.path) for item in delta.symbols_inspected
        )
        for item in delta.searches_performed:
            self.searches_performed.setdefault((item.tool, item.query), item)
        self.graph_paths_inspected.update(delta.graph_paths_inspected)
        self.manifests_inspected.update(delta.manifests_inspected)
        return before != self._identity_set()

    def snapshot(self) -> ContextPlanRunInspection:
        inspected_files = sorted(
            self.evidence_paths
            | self.manifests_inspected
            | {path for path, _, _ in self.excerpts_read}
            | {path for _, path in self.symbols_inspected if path is not None}
        )
        graph_records = [
            ContextPlanGraphQueryRecord(
                tool="graph_inspection",
                subject=path,
                result_count=1,
            )
            for path in sorted(self.graph_paths_inspected)
        ]
        return ContextPlanRunInspection(
            safe_file_count=self.safe_file_count,
            inspected_file_count=len(inspected_files),
            remaining_file_count=max(self.safe_file_count - len(inspected_files), 0),
            inspected_files=inspected_files,
            inspected_excerpts=[
                ContextPlanInspectedExcerpt(
                    path=path,
                    line_start=line_start,
                    line_end=line_end,
                )
                for path, line_start, line_end in sorted(self.excerpts_read)
            ],
            inspected_symbols=[
                ContextPlanInspectedSymbol(identifier=identifier, path=path)
                for identifier, path in sorted(
                    self.symbols_inspected,
                    key=lambda item: (item[0], item[1] or ""),
                )
            ],
            search_records=sorted(
                self.searches_performed.values(),
                key=lambda item: (item.tool, item.query, item.result_count),
            ),
            graph_query_records=graph_records,
        )

    def _identity_set(self) -> set[tuple[str, object]]:
        return {
            *(("discovered", path) for path in self.discovered_paths),
            *(("evidence", path) for path in self.evidence_paths),
            *(("excerpt", item) for item in self.excerpts_read),
            *(("symbol", item) for item in self.symbols_inspected),
            *(("search", item) for item in self.searches_performed),
            *(("graph", path) for path in self.graph_paths_inspected),
            *(("manifest", path) for path in self.manifests_inspected),
        }


class DiscoveryBudgetPolicy:
    """Centralizes cumulative budget checks without executing tools."""

    def __init__(self, limits: DiscoveryBudgetLimits | None = None) -> None:
        self.limits = limits or DiscoveryBudgetLimits()

    def preflight_tool_call(
        self,
        state: ContextPlanRunState,
        estimated_cost: ToolBudgetCost,
        fingerprint: str,
        *,
        now: datetime | None = None,
    ) -> BudgetPreflightDecision:
        projected = _add_cost(state.consumed_cost, estimated_cost)
        reasons = self._cost_limit_reasons(projected)
        elapsed = state.elapsed_seconds(now)
        if (
            self.limits.elapsed_seconds is not None
            and elapsed >= self.limits.elapsed_seconds
        ):
            reasons.append("elapsed_seconds")
        duplicate_count = state.fingerprint_counts.get(fingerprint, 0)
        if (
            self.limits.duplicate_call_threshold is not None
            and duplicate_count >= self.limits.duplicate_call_threshold
        ):
            reasons.append("duplicate_call_threshold")
        return BudgetPreflightDecision(
            allowed=not reasons,
            hard_budget_exhausted=any(
                reason != "duplicate_call_threshold" for reason in reasons
            ),
            reasons=tuple(reasons),
        )

    def preflight_model_turn(
        self,
        state: ContextPlanRunState,
        *,
        reserved_turns: int = 0,
        now: datetime | None = None,
    ) -> BudgetPreflightDecision:
        if reserved_turns < 0:
            raise ValueError("reserved_turns must be non-negative")
        reasons: list[str] = []
        if (
            self.limits.model_turns is not None
            and state.model_turns + 1 + reserved_turns > self.limits.model_turns
        ):
            reasons.append("model_turns")
        if (
            self.limits.token_usage is not None
            and state.token_usage >= self.limits.token_usage
        ):
            reasons.append("token_usage")
        if (
            self.limits.elapsed_seconds is not None
            and state.elapsed_seconds(now) >= self.limits.elapsed_seconds
        ):
            reasons.append("elapsed_seconds")
        return BudgetPreflightDecision(
            allowed=not reasons,
            hard_budget_exhausted=bool(reasons),
            reasons=tuple(reasons),
        )

    def hard_budget_exhausted(
        self, state: ContextPlanRunState, *, now: datetime | None = None
    ) -> bool:
        if any(
            getattr(state.consumed_cost, name) >= limit
            for name in _COST_FIELDS
            if (limit := getattr(self.limits, name)) is not None
        ):
            return True
        if (
            self.limits.model_turns is not None
            and state.model_turns >= self.limits.model_turns
        ):
            return True
        if (
            self.limits.token_usage is not None
            and state.token_usage >= self.limits.token_usage
        ):
            return True
        return (
            self.limits.elapsed_seconds is not None
            and state.elapsed_seconds(now) >= self.limits.elapsed_seconds
        )

    def remaining_budget_summary(
        self, state: ContextPlanRunState, *, now: datetime | None = None
    ) -> dict[str, int | None]:
        summary: dict[str, int | None] = {}
        for name in _COST_FIELDS:
            limit = getattr(self.limits, name)
            used = getattr(state.consumed_cost, name)
            summary[name] = None if limit is None else max(limit - used, 0)
        summary["model_turns"] = self._remaining(
            self.limits.model_turns, state.model_turns
        )
        summary["token_usage"] = self._remaining(
            self.limits.token_usage, state.token_usage
        )
        summary["elapsed_seconds"] = self._remaining(
            self.limits.elapsed_seconds, state.elapsed_seconds(now)
        )
        return summary

    @staticmethod
    def _remaining(limit: int | None, used: int) -> int | None:
        return None if limit is None else max(limit - used, 0)

    def _cost_limit_reasons(self, cost: ToolBudgetCost) -> list[str]:
        return [
            name
            for name in _COST_FIELDS
            if (limit := getattr(self.limits, name)) is not None
            and getattr(cost, name) > limit
        ]


class ContextPlanRunState:
    """Mutable runtime state with an explicit persisted-artifact snapshot."""

    def __init__(
        self,
        *,
        run_id: str,
        repo: ContextPlanRepository,
        safe_file_count: int,
        model_profile: str | None = None,
        model_name: str | None = None,
        started_at: datetime | None = None,
    ) -> None:
        timestamp = _require_aware(started_at or _utc_now())
        self.run_id = run_id
        self.repo = repo
        self.model_profile = model_profile
        self.model_name = model_name
        self.started_at = timestamp
        self.updated_at = timestamp
        self.completed_at: datetime | None = None
        self.status = ContextPlanRunStatus.INITIALIZED
        self.phase = ContextPlanRunPhase.INITIALIZATION
        self.coverage = InspectionCoverageTracker(safe_file_count)
        self.model_turns = 0
        self.token_usage = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_input_tokens = 0
        self.reasoning_tokens = 0
        self.model_latency_ms = 0
        self.consumed_cost = ToolBudgetCost(tool_calls=0)
        self.fingerprint_counts: dict[str, int] = {}
        self._tool_requests: dict[str, ToolCallRequest] = {}
        self.consecutive_no_progress = 0
        self.finalization_requests: list[ContextPlanFinalizationRecord] = []
        self.validation_attempts: list[ContextPlanValidationAttempt] = []
        self.errors: list[ContextPlanRunError] = []
        self.events: list[ToolExecutionEvent | ContextPlanRunEvent] = []
        self.output: ContextPlanRunOutput | None = None
        self.working_state_service: WorkingStateMutationService | None = None
        self.working_state_path: RepositoryPath | None = None
        self.synthesis_input_manifest: SynthesisInputManifest | None = None
        self._evidence_extractor = EvidenceExtractor()
        self._last_working_mutation_sequence = 0
        self._record_runtime_event("run_started", timestamp)

    def configure_working_state(
        self,
        service: WorkingStateMutationService,
        path: RepositoryPath,
    ) -> None:
        self.working_state_service = service
        self.working_state_path = validate_repository_path(path)
        self._last_working_mutation_sequence = service.state.mutation_sequence

    def start(self, *, now: datetime | None = None) -> None:
        self.status = ContextPlanRunStatus.RUNNING
        self.phase = ContextPlanRunPhase.ORIENTATION
        self._touch(now)

    def set_phase(
        self, phase: ContextPlanRunPhase, *, now: datetime | None = None
    ) -> None:
        self.phase = phase
        self._touch(now)

    def elapsed_seconds(self, now: datetime | None = None) -> int:
        timestamp = _require_aware(now or _utc_now())
        return max(int((timestamp - self.started_at).total_seconds()), 0)

    def record_model_call_started(self, *, now: datetime | None = None) -> None:
        self._record_runtime_event("model_call_started", now)

    def record_model_call_completed(
        self,
        token_usage: int,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        latency_ms: int = 0,
        now: datetime | None = None,
    ) -> None:
        usage = {
            "token_usage": token_usage,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_input_tokens,
            "reasoning_tokens": reasoning_tokens,
            "latency_ms": latency_ms,
        }
        if any(value < 0 for value in usage.values()):
            raise ValueError("model usage and latency must be non-negative")
        self.model_turns += 1
        self.token_usage += token_usage
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_input_tokens += cached_input_tokens
        self.reasoning_tokens += reasoning_tokens
        self.model_latency_ms += latency_ms
        self._record_runtime_event("model_call_completed", now, **usage)

    def record_no_progress_turn(self, *, now: datetime | None = None) -> None:
        self.consecutive_no_progress += 1
        self._record_runtime_event("model_turn_no_progress", now)

    def record_tool_request(
        self,
        request: ToolCallRequest,
        estimated_cost: ToolBudgetCost,
        *,
        now: datetime | None = None,
    ) -> str:
        timestamp = self._touch(now)
        fingerprint = ToolCallFingerprinter.fingerprint(request)
        self.fingerprint_counts[fingerprint] = (
            self.fingerprint_counts.get(fingerprint, 0) + 1
        )
        self._tool_requests[request.call_id] = request
        self.events.append(
            ToolExecutionEvent(
                event_type=ToolExecutionEventType.TOOL_CALL_REQUESTED,
                call_id=request.call_id,
                tool_name=request.name,
                fingerprint=fingerprint,
                estimated_cost=estimated_cost,
                occurred_at=timestamp,
            )
        )
        return fingerprint

    def record_tool_result(
        self,
        result: ToolExecutionResult,
        fingerprint: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        timestamp = self._touch(now)
        self.consumed_cost = _add_cost(self.consumed_cost, result.actual_cost)
        progress = (
            result.status is ToolExecutionStatus.COMPLETED
            and self.coverage.apply(result.inspection_delta)
        )
        if (
            result.status is ToolExecutionStatus.COMPLETED
            and self.working_state_service is not None
        ):
            source_request = self._tool_requests.get(result.call_id)
            extracted = self._evidence_extractor.extract(
                result,
                starting_sequence=(
                    self.working_state_service.state.mutation_sequence
                ),
                source_arguments=(
                    source_request.arguments
                    if source_request is not None
                    else None
                ),
            )
            evidence_ids = self.working_state_service.apply_evidence(
                extracted,
                now=timestamp,
            )
            progress = progress or bool(evidence_ids)
            current_sequence = (
                self.working_state_service.state.mutation_sequence
            )
            progress = (
                progress
                or current_sequence > self._last_working_mutation_sequence
            )
            self._last_working_mutation_sequence = current_sequence
        self._tool_requests.pop(result.call_id, None)
        if progress:
            self.consecutive_no_progress = 0
        else:
            self.consecutive_no_progress += 1
        event_type = {
            ToolExecutionStatus.COMPLETED: ToolExecutionEventType.TOOL_CALL_COMPLETED,
            ToolExecutionStatus.REJECTED: ToolExecutionEventType.TOOL_CALL_REJECTED,
            ToolExecutionStatus.FAILED: ToolExecutionEventType.TOOL_CALL_FAILED,
        }[result.status]
        self.events.append(
            ToolExecutionEvent(
                event_type=event_type,
                call_id=result.call_id,
                tool_name=result.tool_name,
                fingerprint=fingerprint,
                estimated_cost=result.estimated_cost,
                actual_cost=result.actual_cost,
                inspection_delta=result.inspection_delta,
                issue_codes=[issue.code for issue in result.issues],
                truncated=result.truncated,
                occurred_at=timestamp,
            )
        )
        return progress

    def record_finalization_request(
        self, request: ContextPlanFinalizationRequest, *, now: datetime | None = None
    ) -> None:
        timestamp = self._touch(now)
        self.finalization_requests.append(
            ContextPlanFinalizationRecord(recorded_at=timestamp, request=request)
        )
        self._record_runtime_event("finalization_requested", timestamp)

    def record_finalization_rejected(self, *, now: datetime | None = None) -> None:
        self._record_runtime_event("finalization_rejected", now)

    def record_synthesis_started(self, *, now: datetime | None = None) -> None:
        self.phase = ContextPlanRunPhase.SYNTHESIS
        self._record_runtime_event("synthesis_started", now)

    def record_synthesis_manifest(
        self,
        manifest: SynthesisInputManifest,
        *,
        now: datetime | None = None,
    ) -> None:
        if manifest.run_id != self.run_id:
            raise ValueError("synthesis manifest run_id does not match run state")
        self.synthesis_input_manifest = manifest
        self._record_runtime_event(
            "synthesis_manifest_recorded",
            now,
            manifest_id=manifest.manifest_id,
        )

    def record_repair_started(self, *, now: datetime | None = None) -> None:
        self.phase = ContextPlanRunPhase.SYNTHESIS
        self._record_runtime_event("repair_started", now)

    def record_repair_completed(
        self, succeeded: bool, *, now: datetime | None = None
    ) -> None:
        self._record_runtime_event("repair_completed", now, succeeded=succeeded)

    def record_repair_budget_rejected(
        self,
        reasons: tuple[str, ...],
        *,
        now: datetime | None = None,
    ) -> None:
        self._record_runtime_event(
            "repair_budget_rejected",
            now,
            reasons=",".join(reasons),
        )

    def record_validation_attempt(
        self,
        succeeded: bool,
        issues: list[ContextPlanValidationIssue],
        *,
        now: datetime | None = None,
    ) -> None:
        timestamp = self._touch(now)
        self.phase = ContextPlanRunPhase.VALIDATION
        self.validation_attempts.append(
            ContextPlanValidationAttempt(
                attempted_at=timestamp,
                succeeded=succeeded,
                issues=issues,
            )
        )
        if not succeeded:
            self._record_runtime_event("validation_failed", timestamp)

    def record_artifact_written(
        self, output: ContextPlanRunOutput, *, now: datetime | None = None
    ) -> None:
        self.output = output
        self.phase = ContextPlanRunPhase.WRITING
        self._record_runtime_event("artifact_written", now)

    def record_error(self, message: str, *, now: datetime | None = None) -> None:
        timestamp = self._touch(now)
        self.errors.append(
            ContextPlanRunError(
                occurred_at=timestamp,
                phase=self.phase,
                message=message,
            )
        )

    def fail(self, message: str, *, now: datetime | None = None) -> None:
        timestamp = self._touch(now)
        self.status = ContextPlanRunStatus.FAILED
        self.completed_at = timestamp
        self.record_error(message, now=timestamp)
        self._record_runtime_event("run_failed", timestamp)

    def interrupt(
        self,
        message: str = "run interrupted",
        *,
        now: datetime | None = None,
    ) -> None:
        timestamp = self._touch(now)
        self.status = ContextPlanRunStatus.INTERRUPTED
        self.completed_at = timestamp
        self.errors.append(
            ContextPlanRunError(
                occurred_at=timestamp,
                phase=self.phase,
                message=message,
            )
        )

    def mark_budget_exhausted(self, *, now: datetime | None = None) -> None:
        self.status = ContextPlanRunStatus.BUDGET_EXHAUSTED
        self.completed_at = self._touch(now)

    def mark_stalled(self, *, now: datetime | None = None) -> None:
        self.status = ContextPlanRunStatus.STALLED
        self.completed_at = self._touch(now)

    def complete(self, *, now: datetime | None = None) -> None:
        timestamp = self._touch(now)
        self.status = ContextPlanRunStatus.COMPLETED
        self.phase = ContextPlanRunPhase.COMPLETED
        self.completed_at = timestamp
        self._record_runtime_event("run_completed", timestamp)

    def finalization_context(
        self, budget_policy: DiscoveryBudgetPolicy, *, now: datetime | None = None
    ) -> FinalizationContext:
        return FinalizationContext(
            run_status=self.status,
            stalled=(
                self.status is ContextPlanRunStatus.STALLED
                or self.is_stalled(budget_policy)
            ),
            hard_budget_exhausted=(
                self.status is ContextPlanRunStatus.BUDGET_EXHAUSTED
                or budget_policy.hard_budget_exhausted(self, now=now)
            ),
            evidence_paths=sorted(self.coverage.evidence_paths),
            finalization_request_count=len(self.finalization_requests),
        )

    def snapshot(self, *, now: datetime | None = None) -> ContextPlanRun:
        timestamp = self._touch(now)
        return ContextPlanRun(
            run_id=self.run_id,
            repo=self.repo,
            started_at=self.started_at,
            updated_at=timestamp,
            completed_at=self.completed_at,
            status=self.status,
            phase=self.phase,
            model_profile=self.model_profile,
            model_name=self.model_name,
            model_turns=self.model_turns,
            tool_call_count=self.consumed_cost.tool_calls,
            token_usage=self.token_usage,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cached_input_tokens=self.cached_input_tokens,
            reasoning_tokens=self.reasoning_tokens,
            model_latency_ms=self.model_latency_ms,
            inspection=self.coverage.snapshot(),
            finalization_requests=sorted(
                self.finalization_requests, key=lambda item: item.recorded_at
            ),
            validation_attempts=sorted(
                self.validation_attempts, key=lambda item: item.attempted_at
            ),
            errors=sorted(self.errors, key=lambda item: item.occurred_at),
            output=self.output,
            working_state_path=self.working_state_path,
            working_state_checksum=(
                self.working_state_service.store.checksum
                if self.working_state_service is not None
                else None
            ),
            working_state_summary=(
                self.working_state_service.state.summary()
                if self.working_state_service is not None
                else None
            ),
            synthesis_input_manifest=self.synthesis_input_manifest,
        )

    def is_stalled(self, policy: DiscoveryBudgetPolicy) -> bool:
        limit = policy.limits.consecutive_no_progress_threshold
        return limit is not None and self.consecutive_no_progress >= limit

    def _touch(self, now: datetime | None) -> datetime:
        timestamp = _require_aware(now or _utc_now())
        self.updated_at = timestamp
        return timestamp

    def _record_runtime_event(
        self,
        event_type: str,
        now: datetime | None,
        **metadata: str | int | bool,
    ) -> None:
        timestamp = self._touch(now)
        self.events.append(
            ContextPlanRunEvent(
                event_type=event_type,
                occurred_at=timestamp,
                metadata=metadata,
            )
        )


class ContextPlanRunRecorder:
    """Persists compact run snapshots atomically using the shared writer."""

    def __init__(self, destination: Path) -> None:
        self.destination = destination

    def persist(
        self, state: ContextPlanRunState, *, now: datetime | None = None
    ) -> ContextPlanRun:
        snapshot = state.snapshot(now=now)
        write_artifact(self.destination, snapshot)
        return snapshot
