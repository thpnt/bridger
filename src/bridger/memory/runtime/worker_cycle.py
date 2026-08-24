"""Stage 4 bounded worker model/tool execution loop."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

import orjson

from bridger.contracts.memory.core import (
    ExecutionBudget,
    ExecutionUsage,
    FleetRunState,
    MemoryFleetSpec,
    TargetCompletionState,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
    budgeted_input_tokens,
)
from bridger.contracts.memory.hydration import (
    WorkerContext,
    WorkerContextMode,
    WorkerProfile,
)
from bridger.contracts.memory.worker_cycle import EvidenceReference, OpenQuestion
from bridger.llm.client import LLMClient
from bridger.llm.errors import LLMError
from bridger.llm.models import (
    LLMCompactedContext,
    LLMCompactionRequest,
    LLMCompactionResult,
    LLMMessage,
    LLMOperation,
    LLMPromptCacheConfig,
    LLMReasoningConfig,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    LLMToolError,
    LLMToolResult,
    LLMUsage,
)
from bridger.memory.errors import WorkerCycleInvocationError, WorkerCyclePreflightError
from bridger.memory.persistence.durability import FleetRuntimeStore
from bridger.memory.runtime.context_window import ContextWindowManager
from bridger.memory.runtime.hydration import serialize_worker_context_sections
from bridger.memory.runtime.provider_recovery import run_provider_with_retry
from bridger.memory.runtime.trace import (
    bounded_error_message,
    focus_payload,
    model_error_trace_payload,
    model_request_trace_context,
    model_response_trace_payload,
    project_tool_arguments,
    provider_usage_payload,
    summarize_tool_result,
)
from bridger.memory.runtime.worker_tools import (
    FINALIZATION_TOOL_ID,
    YIELD_CYCLE_TOOL_ID,
    WorkerToolRuntime,
)

DEFAULT_TOOL_CONTEXT_SOFT_TOKENS = 16_000
DEFAULT_TOOL_RESULT_MAX_BYTES = 32 * 1024
DEFAULT_ACTIVE_CONTEXT_SOFT_LIMIT_TOKENS = 128_000
DEFAULT_COMPACTION_TRIGGER_RATIO = 0.75
COMPACTION_INGRESS_SAFETY_TOKENS = 256
PROTECTED_TOOL_BATCHES = 3
MAX_MALFORMED_ARGUMENT_CORRECTION_TURNS = 3
_MALFORMED_ARGUMENT_CORRECTION_LIMIT_MESSAGE = (
    "malformed tool arguments exceeded the correction limit"
)
_CONTROL_TOOL_IDS = {FINALIZATION_TOOL_ID, YIELD_CYCLE_TOOL_ID}


class WorkerCycleOutcome(StrEnum):
    """Small non-persisted Stage 4 handoff result."""

    FINALIZATION_REQUESTED = "finalization-requested"
    CYCLE_YIELDED = "cycle-yielded"
    TARGET_BUDGET_EXHAUSTED = "target-budget-exhausted"
    FLEET_BUDGET_STOP = "fleet-budget-stop"
    EXECUTION_INTERRUPTED = "execution-interrupted"


@dataclass(frozen=True, slots=True)
class WorkerInterruption:
    """Persistable diagnostic summary for an interrupted worker trajectory."""

    category: str
    operation: str
    message: str
    retryable: bool


class _BudgetScope(StrEnum):
    TARGET = "target"
    FLEET = "fleet"


class _BudgetStop(RuntimeError):
    def __init__(self, scope: _BudgetScope) -> None:
        super().__init__(f"{scope.value} budget prevents the next action")
        self.scope = scope


class _ContextCapacityStop(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerRuntimeLimits:
    """Runtime-owned Stage 4 context and tool-output tuning."""

    tool_context_soft_tokens: int = DEFAULT_TOOL_CONTEXT_SOFT_TOKENS
    tool_result_max_bytes: int = DEFAULT_TOOL_RESULT_MAX_BYTES
    active_context_soft_limit_tokens: int = DEFAULT_ACTIVE_CONTEXT_SOFT_LIMIT_TOKENS
    compaction_trigger_ratio: float = DEFAULT_COMPACTION_TRIGGER_RATIO

    def __post_init__(self) -> None:
        if (
            self.tool_context_soft_tokens < 1
            or self.tool_result_max_bytes < 1
            or self.active_context_soft_limit_tokens < 1
        ):
            raise ValueError("worker runtime limits must be positive")
        if not 0 < self.compaction_trigger_ratio < 1:
            raise ValueError("compaction_trigger_ratio must be between zero and one")


@dataclass(slots=True)
class _ModelReservation:
    input_tokens: int
    output_tokens: int
    active: bool = True
    attempt_id: str | None = None
    target_spec: TargetTaskSpec | None = None
    target_state: TargetTaskState | None = None
    fleet_state: FleetRunState | None = None
    trace_context: dict[str, object] | None = None


@dataclass(slots=True)
class _ToolReservation:
    remaining: int
    active: bool = True


class FleetExecutionCoordinator:
    """Concurrency-safe in-flight coordination for one fleet's hard budgets."""

    def __init__(self, persistence: FleetRuntimeStore | None = None) -> None:
        self._lock = asyncio.Lock()
        self._persistence = persistence
        self._fleet_state: FleetRunState | None = None
        self._reserved_input_tokens = 0
        self._reserved_output_tokens = 0
        self._reserved_tool_calls = 0
        self._durable_holds_loaded = False

    def bind_persistence(
        self,
        persistence: FleetRuntimeStore,
        fleet_state: FleetRunState,
    ) -> None:
        """Bind one shared durable fleet authority before worker execution."""
        if self._persistence is not None and self._persistence is not persistence:
            raise ValueError("coordinator is already bound to another fleet store")
        if self._fleet_state is not None and self._fleet_state is not fleet_state:
            raise ValueError("coordinator is already bound to another fleet state")
        self._persistence = persistence
        self._fleet_state = fleet_state
        if not self._durable_holds_loaded:
            reservations = persistence.provider_reservations()
            self._reserved_input_tokens += sum(
                item.input_token_reservation for item in reservations
            )
            self._reserved_output_tokens += sum(
                item.output_token_reservation for item in reservations
            )
            self._durable_holds_loaded = True

    async def start_cycle_and_reserve_first_model_call(
        self,
        fleet_budget: ExecutionBudget,
        fleet_usage: ExecutionUsage,
        target_budget: ExecutionBudget,
        target_state: TargetTaskState,
        *,
        repair: bool,
        input_tokens: int,
        requested_output_tokens: int,
        trace_context: Mapping[str, object] | None = None,
    ) -> _ModelReservation:
        """Preflight the first action before atomically entering WORKING."""
        target_usage = target_state.usage
        if target_usage.model_calls >= target_budget.max_model_calls:
            raise _BudgetStop(_BudgetScope.TARGET)
        if target_budget.max_input_tokens is not None and (
            budgeted_input_tokens(target_usage) + input_tokens
            > target_budget.max_input_tokens
        ):
            raise _BudgetStop(_BudgetScope.TARGET)
        target_output = _remaining_optional(
            target_budget.max_output_tokens,
            target_usage.output_tokens,
        )
        if target_output is not None:
            requested_output_tokens = min(requested_output_tokens, target_output)
        if requested_output_tokens < 1:
            raise _BudgetStop(_BudgetScope.TARGET)

        async with self._lock:
            _require_cycle_capacity(
                target_budget, target_usage, repair, _BudgetScope.TARGET
            )
            _require_cycle_capacity(
                fleet_budget, fleet_usage, repair, _BudgetScope.FLEET
            )
            if fleet_usage.model_calls >= fleet_budget.max_model_calls:
                raise _BudgetStop(_BudgetScope.FLEET)
            if fleet_budget.max_input_tokens is not None and (
                budgeted_input_tokens(fleet_usage)
                + self._reserved_input_tokens
                + input_tokens
                > fleet_budget.max_input_tokens
            ):
                raise _BudgetStop(_BudgetScope.FLEET)
            fleet_output = _remaining_optional(
                fleet_budget.max_output_tokens,
                fleet_usage.output_tokens + self._reserved_output_tokens,
            )
            if fleet_output is not None:
                requested_output_tokens = min(requested_output_tokens, fleet_output)
            if requested_output_tokens < 1:
                raise _BudgetStop(_BudgetScope.FLEET)

            attempt_id: str | None = None
            target_spec: TargetTaskSpec | None = None
            if self._persistence is None:
                target_state.phase = TargetPhase.WORKING
                _apply_usage_delta(target_usage, fleet_usage, cycles=1, model_calls=1)
                if repair:
                    _apply_usage_delta(target_usage, fleet_usage, repair_cycles=1)
            else:
                fleet_state = self._require_bound_fleet_state(fleet_usage)
                target_spec = self._target_spec(target_state.target_task_id)
                attempt_id = self._persistence.prepare_provider_attempt(
                    fleet_state,
                    target_spec,
                    target_state,
                    input_tokens=input_tokens,
                    output_tokens=requested_output_tokens,
                    cycle_start=True,
                    repair=repair,
                    trace_context=trace_context,
                )
            self._reserved_input_tokens += input_tokens
            self._reserved_output_tokens += requested_output_tokens
            return _ModelReservation(
                input_tokens,
                requested_output_tokens,
                attempt_id=attempt_id,
                target_spec=target_spec,
                target_state=target_state if target_spec is not None else None,
                fleet_state=(self._fleet_state if target_spec is not None else None),
                trace_context=dict(trace_context or {}),
            )

    async def reserve_model_call(
        self,
        fleet_budget: ExecutionBudget,
        fleet_usage: ExecutionUsage,
        target_budget: ExecutionBudget,
        target_usage: ExecutionUsage,
        *,
        input_tokens: int,
        requested_output_tokens: int,
        target_state: TargetTaskState | None = None,
        target_spec: TargetTaskSpec | None = None,
        trace_context: Mapping[str, object] | None = None,
    ) -> _ModelReservation:
        """Reserve exact input and maximum output, then charge the call attempt."""
        if target_usage.model_calls >= target_budget.max_model_calls:
            raise _BudgetStop(_BudgetScope.TARGET)
        if target_budget.max_input_tokens is not None and (
            budgeted_input_tokens(target_usage) + input_tokens
            > target_budget.max_input_tokens
        ):
            raise _BudgetStop(_BudgetScope.TARGET)
        target_output = _remaining_optional(
            target_budget.max_output_tokens,
            target_usage.output_tokens,
        )
        if target_output is not None:
            requested_output_tokens = min(requested_output_tokens, target_output)
        if requested_output_tokens < 1:
            raise _BudgetStop(_BudgetScope.TARGET)

        async with self._lock:
            if fleet_usage.model_calls >= fleet_budget.max_model_calls:
                raise _BudgetStop(_BudgetScope.FLEET)
            if fleet_budget.max_input_tokens is not None and (
                budgeted_input_tokens(fleet_usage)
                + self._reserved_input_tokens
                + input_tokens
                > fleet_budget.max_input_tokens
            ):
                raise _BudgetStop(_BudgetScope.FLEET)
            fleet_output = _remaining_optional(
                fleet_budget.max_output_tokens,
                fleet_usage.output_tokens + self._reserved_output_tokens,
            )
            if fleet_output is not None:
                requested_output_tokens = min(requested_output_tokens, fleet_output)
            if requested_output_tokens < 1:
                raise _BudgetStop(_BudgetScope.FLEET)
            attempt_id: str | None = None
            if self._persistence is None:
                _apply_usage_delta(target_usage, fleet_usage, model_calls=1)
            else:
                if target_state is None or target_spec is None:
                    raise ValueError(
                        "durable model reservation requires target authorities"
                    )
                fleet_state = self._require_bound_fleet_state(fleet_usage)
                attempt_id = self._persistence.prepare_provider_attempt(
                    fleet_state,
                    target_spec,
                    target_state,
                    input_tokens=input_tokens,
                    output_tokens=requested_output_tokens,
                    cycle_start=False,
                    trace_context=trace_context,
                )
            self._reserved_input_tokens += input_tokens
            self._reserved_output_tokens += requested_output_tokens
            return _ModelReservation(
                input_tokens,
                requested_output_tokens,
                attempt_id=attempt_id,
                target_spec=target_spec,
                target_state=target_state,
                fleet_state=self._fleet_state,
                trace_context=dict(trace_context or {}),
            )

    async def reserve_fleet_model_call(
        self,
        fleet_budget: ExecutionBudget,
        fleet_state: FleetRunState,
        *,
        input_tokens: int,
        requested_output_tokens: int,
        trace_context: Mapping[str, object] | None = None,
    ) -> _ModelReservation:
        """Reserve and charge one fleet-only model invocation."""
        async with self._lock:
            usage = fleet_state.usage
            if usage.model_calls >= fleet_budget.max_model_calls:
                raise _BudgetStop(_BudgetScope.FLEET)
            if fleet_budget.max_input_tokens is not None and (
                budgeted_input_tokens(usage)
                + self._reserved_input_tokens
                + input_tokens
                > fleet_budget.max_input_tokens
            ):
                raise _BudgetStop(_BudgetScope.FLEET)
            fleet_output = _remaining_optional(
                fleet_budget.max_output_tokens,
                usage.output_tokens + self._reserved_output_tokens,
            )
            if fleet_output is not None:
                requested_output_tokens = min(requested_output_tokens, fleet_output)
            if requested_output_tokens < 1:
                raise _BudgetStop(_BudgetScope.FLEET)
            attempt_id: str | None = None
            if self._persistence is None:
                usage.model_calls += 1
            else:
                bound = self._require_bound_fleet_state(usage)
                attempt_id = self._persistence.prepare_fleet_provider_attempt(
                    bound,
                    input_tokens=input_tokens,
                    output_tokens=requested_output_tokens,
                    trace_context=trace_context,
                )
            self._reserved_input_tokens += input_tokens
            self._reserved_output_tokens += requested_output_tokens
            return _ModelReservation(
                input_tokens,
                requested_output_tokens,
                attempt_id=attempt_id,
                fleet_state=self._fleet_state,
                trace_context=dict(trace_context or {}),
            )

    async def mark_model_invoked(self, reservation: _ModelReservation) -> None:
        """Persist the provider invocation boundary before network dispatch."""
        if self._persistence is not None and reservation.attempt_id is not None:
            self._persistence.mark_provider_invoked(reservation.attempt_id)

    async def finish_model_call(
        self,
        reservation: _ModelReservation,
        target_usage: ExecutionUsage,
        fleet_usage: ExecutionUsage,
        usage: LLMUsage | None,
        trace_payload: Mapping[str, object] | None = None,
        failed: bool | None = None,
    ) -> None:
        """Charge reported tokens and release the unused in-flight allowance."""
        async with self._lock:
            if not reservation.active:
                return
            reservation.active = False
            self._reserved_input_tokens -= reservation.input_tokens
            self._reserved_output_tokens -= reservation.output_tokens
            if self._persistence is not None and reservation.attempt_id is not None:
                if (
                    reservation.target_spec is None
                    or reservation.target_state is None
                    or reservation.fleet_state is None
                ):
                    raise RuntimeError("durable model reservation lost authorities")
                self._persistence.settle_provider_attempt(
                    reservation.fleet_state,
                    reservation.target_spec,
                    reservation.target_state,
                    reservation.attempt_id,
                    input_tokens=(usage.input_tokens or 0) if usage else 0,
                    cached_input_tokens=(
                        (usage.cached_input_tokens or 0) if usage else 0
                    ),
                    cache_write_tokens=(usage.cache_write_tokens or 0) if usage else 0,
                    output_tokens=(usage.output_tokens or 0) if usage else 0,
                    failed=usage is None if failed is None else failed,
                    trace_payload=trace_payload,
                )
            elif usage is not None:
                _apply_usage_delta(
                    target_usage,
                    fleet_usage,
                    input_tokens=usage.input_tokens or 0,
                    cached_input_tokens=usage.cached_input_tokens or 0,
                    cache_write_tokens=usage.cache_write_tokens or 0,
                    output_tokens=usage.output_tokens or 0,
                )

    async def finish_fleet_model_call(
        self,
        reservation: _ModelReservation,
        fleet_state: FleetRunState,
        usage: LLMUsage | None,
        trace_payload: Mapping[str, object] | None = None,
        failed: bool | None = None,
    ) -> None:
        """Settle a fleet-only model invocation and release its allowance."""
        async with self._lock:
            if not reservation.active:
                return
            reservation.active = False
            self._reserved_input_tokens -= reservation.input_tokens
            self._reserved_output_tokens -= reservation.output_tokens
            if self._persistence is not None and reservation.attempt_id is not None:
                if reservation.fleet_state is None:
                    raise RuntimeError("durable fleet reservation lost authority")
                self._persistence.settle_fleet_provider_attempt(
                    reservation.fleet_state,
                    reservation.attempt_id,
                    input_tokens=(usage.input_tokens or 0) if usage else 0,
                    cached_input_tokens=(
                        (usage.cached_input_tokens or 0) if usage else 0
                    ),
                    cache_write_tokens=(usage.cache_write_tokens or 0) if usage else 0,
                    output_tokens=(usage.output_tokens or 0) if usage else 0,
                    failed=usage is None if failed is None else failed,
                    trace_payload=trace_payload,
                )
            elif usage is not None:
                fleet_state.usage.input_tokens += usage.input_tokens or 0
                fleet_state.usage.cached_input_tokens += usage.cached_input_tokens or 0
                fleet_state.usage.cache_write_tokens += usage.cache_write_tokens or 0
                fleet_state.usage.output_tokens += usage.output_tokens or 0

    async def charge_additional_fleet_model_attempts(
        self,
        fleet_state: FleetRunState,
        attempts: int,
    ) -> None:
        """Charge fleet-only retries performed inside one logical request."""
        if attempts < 0:
            raise ValueError("additional provider attempts cannot be negative")
        async with self._lock:
            if (
                fleet_state.usage.model_calls + attempts
                > self._fleet_budget().max_model_calls
            ):
                raise _BudgetStop(_BudgetScope.FLEET)
            if self._persistence is None:
                fleet_state.usage.model_calls += attempts
            else:
                self._persistence.apply_fleet_usage_delta(
                    fleet_state,
                    {"model_calls": attempts},
                )

    async def charge_fleet_reported_tokens(
        self,
        fleet_state: FleetRunState,
        usage: LLMUsage,
    ) -> None:
        """Charge tokens from a definitive fleet-review retry failure."""
        delta = {
            "input_tokens": usage.input_tokens or 0,
            "cached_input_tokens": usage.cached_input_tokens or 0,
            "cache_write_tokens": usage.cache_write_tokens or 0,
            "output_tokens": usage.output_tokens or 0,
        }
        async with self._lock:
            if self._persistence is None:
                fleet_state.usage.input_tokens += delta["input_tokens"]
                fleet_state.usage.cached_input_tokens += delta["cached_input_tokens"]
                fleet_state.usage.cache_write_tokens += delta["cache_write_tokens"]
                fleet_state.usage.output_tokens += delta["output_tokens"]
            else:
                self._persistence.apply_fleet_usage_delta(
                    fleet_state,
                    delta,
                    allow_budget_overage=True,
                )

    async def charge_additional_model_attempts(
        self,
        target_usage: ExecutionUsage,
        fleet_usage: ExecutionUsage,
        attempts: int,
        *,
        target_state: TargetTaskState | None = None,
        target_spec: TargetTaskSpec | None = None,
    ) -> None:
        """Charge provider retries already performed inside an existing client."""
        if attempts < 0:
            raise ValueError("additional provider attempts cannot be negative")
        async with self._lock:
            if (
                target_spec is not None
                and target_usage.model_calls + attempts
                > target_spec.budget.max_model_calls
            ):
                raise _BudgetStop(_BudgetScope.TARGET)
            if (
                self._persistence is not None
                and fleet_usage.model_calls + attempts
                > self._persistence.fleet_spec.fleet_budget.max_model_calls
            ):
                raise _BudgetStop(_BudgetScope.FLEET)
            if self._persistence is None:
                _apply_usage_delta(
                    target_usage,
                    fleet_usage,
                    model_calls=attempts,
                )
            else:
                if target_state is None or target_spec is None:
                    raise ValueError("durable retry charge requires target authorities")
                self._persistence.apply_usage_delta(
                    self._require_bound_fleet_state(fleet_usage),
                    target_spec,
                    target_state,
                    {"model_calls": attempts},
                )

    def record_retry(
        self,
        target_task_id: str | None,
        attempt: int,
        delay_seconds: float,
    ) -> None:
        """Append compact provider retry scheduling metadata."""
        if self._persistence is None:
            return
        self._persistence.append_event(
            "retry_scheduled",
            {"attempt": attempt, "delay_seconds": delay_seconds},
            target_task_id=target_task_id,
        )

    def record_retry_attempt_boundary(
        self,
        target_task_id: str | None,
        logical_attempt_id: str,
        provider_attempt: int,
        *,
        failed: bool,
        usage: LLMUsage | None = None,
        error: BaseException | None = None,
    ) -> None:
        """Trace one physical retry boundary within a logical model request."""
        if self._persistence is None:
            return
        payload: dict[str, object] = {
            "attempt_id": logical_attempt_id,
            "provider_attempt": provider_attempt,
        }
        try:
            payload.update(
                self._persistence.load_provider_reservation(
                    logical_attempt_id
                ).trace_context
            )
        except (FileNotFoundError, ValueError):
            pass
        if usage is not None:
            payload["provider_usage"] = provider_usage_payload(usage)
        if error is not None:
            payload.update(model_error_trace_payload(error))
        self._persistence.append_event(
            "model_attempt_failed" if failed else "model_attempt_started",
            payload,
            target_task_id=target_task_id,
            operation_id=logical_attempt_id,
        )

    async def charge_reported_tokens(
        self,
        target_state: TargetTaskState,
        fleet_state: FleetRunState,
        usage: LLMUsage,
    ) -> None:
        """Charge tokens reported by a definitive intermediate retry failure."""
        delta = {
            "input_tokens": usage.input_tokens or 0,
            "cached_input_tokens": usage.cached_input_tokens or 0,
            "cache_write_tokens": usage.cache_write_tokens or 0,
            "output_tokens": usage.output_tokens or 0,
        }
        async with self._lock:
            if self._persistence is None:
                _apply_usage_delta(target_state.usage, fleet_state.usage, **delta)
                return
            target_spec = self._target_spec(target_state.target_task_id)
            self._persistence.apply_usage_delta(
                fleet_state,
                target_spec,
                target_state,
                delta,
                allow_budget_overage=True,
            )

    async def reserve_tool_batch(
        self,
        fleet_budget: ExecutionBudget,
        fleet_usage: ExecutionUsage,
        target_budget: ExecutionBudget,
        target_usage: ExecutionUsage,
        size: int,
    ) -> _ToolReservation:
        """Reserve a complete operational batch before any call dispatches."""
        if target_usage.tool_calls + size > target_budget.max_tool_calls:
            raise _BudgetStop(_BudgetScope.TARGET)
        async with self._lock:
            if (
                fleet_usage.tool_calls + self._reserved_tool_calls + size
                > fleet_budget.max_tool_calls
            ):
                raise _BudgetStop(_BudgetScope.FLEET)
            self._reserved_tool_calls += size
            return _ToolReservation(size)

    async def begin_tool_dispatch(
        self,
        reservation: _ToolReservation,
        target_usage: ExecutionUsage,
        fleet_usage: ExecutionUsage,
        *,
        target_state: TargetTaskState | None = None,
        target_spec: TargetTaskSpec | None = None,
        tool: str = "operational",
        trace_payload: Mapping[str, object] | None = None,
    ) -> None:
        """Charge one attempted operational dispatch from a reserved batch."""
        async with self._lock:
            if not reservation.active or reservation.remaining < 1:
                raise RuntimeError("tool dispatch does not have a live reservation")
            reservation.remaining -= 1
            self._reserved_tool_calls -= 1
            if self._persistence is None:
                _apply_usage_delta(target_usage, fleet_usage, tool_calls=1)
            else:
                if target_state is None or target_spec is None:
                    raise ValueError(
                        "durable tool dispatch requires target authorities"
                    )
                self._persistence.apply_usage_delta(
                    self._require_bound_fleet_state(fleet_usage),
                    target_spec,
                    target_state,
                    {"tool_calls": 1},
                    event_type="tool_dispatch_started",
                    payload={"tool": tool, **dict(trace_payload or {})},
                )

    async def release_tool_batch(self, reservation: _ToolReservation) -> None:
        """Release any operational calls not attempted after an interruption."""
        async with self._lock:
            if not reservation.active:
                return
            reservation.active = False
            self._reserved_tool_calls -= reservation.remaining
            reservation.remaining = 0

    async def yield_cycle(
        self,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
    ) -> None:
        """End one bounded cycle and return the admitted target to SCHEDULED."""
        async with self._lock:
            if target_state.phase is not TargetPhase.WORKING:
                raise RuntimeError("yield_cycle requires a WORKING target")
            target_state.phase = TargetPhase.SCHEDULED
            if self._persistence is not None:
                self._persistence.persist_target_state(
                    target_spec,
                    target_state,
                    event_type="phase_transition",
                    payload={
                        "from_phase": TargetPhase.WORKING.value,
                        "to_phase": TargetPhase.SCHEDULED.value,
                        "reason": YIELD_CYCLE_TOOL_ID,
                    },
                )

    def record_tool_result(
        self,
        target_task_id: str,
        tool: str,
        *,
        failed: bool,
        error_code: str | None = None,
        trace_payload: Mapping[str, object] | None = None,
    ) -> None:
        """Append compact tool completion metadata when persistence is active."""
        if self._persistence is None:
            return
        payload: dict[str, object] = {
            "tool": tool,
            "status": "error" if failed else "ok",
        }
        if error_code is not None:
            payload["error_code"] = error_code
        if trace_payload is not None:
            payload.update(trace_payload)
        self._persistence.append_event(
            "tool_dispatch_rejected" if failed else "tool_dispatch_completed",
            payload,
            target_task_id=target_task_id,
        )

    def record_cycle_finished(
        self,
        target_task_id: str,
        *,
        cycle_id: str,
        cycle_number: int,
        outcome: WorkerCycleOutcome,
        focus: Mapping[str, object],
        usage_delta: Mapping[str, int],
        completion_changes: list[Mapping[str, object]],
    ) -> None:
        """Append the diagnostic boundary for one normally returned worker cycle."""
        if self._persistence is None:
            return
        self._persistence.append_event(
            "cycle_finished",
            {
                "cycle_id": cycle_id,
                "cycle_number": cycle_number,
                "outcome": outcome.value,
                "focus": dict(focus),
                "usage_delta": dict(usage_delta),
                "completion_changes": [dict(item) for item in completion_changes],
            },
            target_task_id=target_task_id,
            operation_id=cycle_id,
        )

    def record_compaction_started(
        self,
        target_task_id: str,
        *,
        projected_context_tokens: int,
        active_context_soft_limit_tokens: int,
        model_context_window_tokens: int,
        trace_payload: Mapping[str, object] | None = None,
    ) -> None:
        """Append compact context-pressure metadata before compaction dispatch."""
        if self._persistence is None:
            return
        self._persistence.append_event(
            "compaction_started",
            {
                "projected_context_tokens": projected_context_tokens,
                "active_context_soft_limit_tokens": active_context_soft_limit_tokens,
                "model_context_window_tokens": model_context_window_tokens,
                **dict(trace_payload or {}),
            },
            target_task_id=target_task_id,
        )

    def record_compaction_completed(
        self,
        target_task_id: str,
        *,
        projected_context_tokens: int,
        active_context_soft_limit_tokens: int,
        model_context_window_tokens: int,
        trace_payload: Mapping[str, object] | None = None,
    ) -> None:
        """Append compact context-pressure metadata after successful compaction."""
        if self._persistence is None:
            return
        self._persistence.append_event(
            "compaction_completed",
            {
                "projected_context_tokens": projected_context_tokens,
                "active_context_soft_limit_tokens": active_context_soft_limit_tokens,
                "model_context_window_tokens": model_context_window_tokens,
                **dict(trace_payload or {}),
            },
            target_task_id=target_task_id,
        )

    def _require_bound_fleet_state(
        self,
        fleet_usage: ExecutionUsage,
    ) -> FleetRunState:
        if self._fleet_state is None or self._fleet_state.usage is not fleet_usage:
            raise ValueError("durable coordinator fleet state is not bound")
        return self._fleet_state

    def _fleet_budget(self) -> ExecutionBudget:
        if self._persistence is None:
            raise RuntimeError("fleet retry budget requires persistence")
        return self._persistence.fleet_spec.fleet_budget

    def _target_spec(self, target_task_id: str) -> TargetTaskSpec:
        if self._persistence is None:
            raise RuntimeError("durable target lookup requires persistence")
        matches = [
            spec
            for spec in self._persistence.load_target_specs()
            if spec.target_task_id == target_task_id
        ]
        if len(matches) != 1:
            raise ValueError("target task spec does not resolve uniquely")
        return matches[0]


@dataclass(slots=True)
class _ToolBatch:
    calls: list[LLMToolCall]
    results: list[LLMToolResult]
    placeholder: bool = False

    def messages(self) -> list[LLMMessage]:
        return [
            LLMMessage.assistant_tool_calls(self.calls),
            *(result.as_message() for result in self.results),
        ]

    def keys(self) -> tuple[bytes, ...]:
        return tuple(
            orjson.dumps(
                {"name": call.name, "arguments": call.arguments},
                option=orjson.OPT_SORT_KEYS,
            )
            for call in self.calls
        )


class _RecentToolWorkingSet:
    def __init__(
        self,
        manager: ContextWindowManager,
        *,
        soft_tokens: int,
    ) -> None:
        self._manager = manager
        self._soft_tokens = soft_tokens
        self._batches: list[_ToolBatch] = []

    def add(self, batch: _ToolBatch) -> None:
        self._batches.append(batch)
        self._trim_soft_limit()

    def messages(self) -> list[LLMMessage]:
        return [message for batch in self._batches for message in batch.messages()]

    def protected_messages(self) -> list[LLMMessage]:
        """Return exact copies of only the protected most-recent tool batches."""
        return [
            message
            for batch in self._batches[-PROTECTED_TOOL_BATCHES:]
            for message in batch.messages()
        ]

    def evict_one_for_context_pressure(self) -> bool:
        evictable_count = len(self._batches) - PROTECTED_TOOL_BATCHES
        if evictable_count <= 0:
            return False
        duplicate_index = self._duplicate_index(evictable_count)
        candidates = range(evictable_count)
        if duplicate_index is not None:
            index = duplicate_index
        else:
            unplaceholdered = [
                index for index in candidates if not self._batches[index].placeholder
            ]
            index = max(
                unplaceholdered,
                key=lambda value: self._batch_tokens(self._batches[value]),
                default=0,
            )
        batch = self._batches[index]
        if not batch.placeholder:
            self._batches[index] = _placeholder_batch(batch)
        else:
            self._batches.pop(index)
        return True

    def _trim_soft_limit(self) -> None:
        while self._tokens() > self._soft_tokens:
            if not self.evict_one_for_context_pressure():
                return

    def _tokens(self) -> int:
        return sum(self._batch_tokens(batch) for batch in self._batches)

    def _batch_tokens(self, batch: _ToolBatch) -> int:
        return self._manager.count_text(_serialize_messages(batch.messages()))

    def _duplicate_index(self, evictable_count: int) -> int | None:
        for index in range(evictable_count):
            keys = self._batches[index].keys()
            newer_keys = {
                key for batch in self._batches[index + 1 :] for key in batch.keys()
            }
            if any(key in newer_keys for key in keys):
                return index
        return None


class WorkerRunner:
    """Execute one hydrated worker cycle under runtime-owned controls."""

    def __init__(
        self,
        *,
        fleet_spec: MemoryFleetSpec,
        fleet_state: FleetRunState,
        target_spec: TargetTaskSpec,
        target_state: TargetTaskState,
        completion_state: TargetCompletionState,
        context: WorkerContext,
        worker_profile: WorkerProfile,
        context_window_manager: ContextWindowManager,
        llm_client: LLMClient,
        tools: WorkerToolRuntime,
        evidence: dict[str, EvidenceReference],
        questions: dict[str, OpenQuestion],
        coordinator: FleetExecutionCoordinator,
        limits: WorkerRuntimeLimits | None = None,
    ) -> None:
        self._fleet_spec = fleet_spec
        self._fleet_state = fleet_state
        self._target_spec = target_spec
        self._target_state = target_state
        self._completion_state = completion_state
        self._context = context
        self._profile = worker_profile
        self._manager = context_window_manager
        self._client = llm_client
        self._tools = tools
        self._evidence = evidence
        self._questions = questions
        self._coordinator = coordinator
        self._last_runtime_error: Exception | None = None
        self._last_interruption: WorkerInterruption | None = None
        self._limits = limits or WorkerRuntimeLimits()
        self._canonical_sections = serialize_worker_context_sections(context)
        self._canonical_base = "".join(self._canonical_sections)
        self._tool_definitions = self._tools.definitions
        self._prompt_cache_key = _worker_prompt_cache_key(
            context,
            target_spec,
            self._tool_definitions,
        )
        self._base_completion = {
            item.obligation_id: (
                item.status,
                item.resolution_note,
                item.evidence_refs,
            )
            for item in context.completion_obligations
        }
        self._base_artifacts = context.candidate_artifacts
        self._base_summary = context.working_summary
        self._base_questions = tuple(
            item.question_id for item in context.open_questions
        )
        self._base_evidence = set(target_state.evidence_refs)
        self._working_set = _RecentToolWorkingSet(
            context_window_manager,
            soft_tokens=self._limits.tool_context_soft_tokens,
        )
        self._continuation_ref: str | None = None
        self._compacted_context: LLMCompactedContext | None = None
        self._pending_messages: list[LLMMessage] = []
        self._latest_usage = LLMUsage()
        self._malformed_argument_correction_turns = 0
        self._cycle_id: str | None = None
        self._cycle_number = 0
        self._cycle_turn = 0
        self._cycle_entry_usage = target_state.usage.model_copy(deep=True)

    @property
    def last_runtime_error(self) -> Exception | None:
        """Return the transient failure that ended the current trajectory."""
        return self._last_runtime_error

    @property
    def last_interruption(self) -> WorkerInterruption | None:
        """Return the diagnostic reason for the current interrupted trajectory."""
        return self._last_interruption

    async def run(self) -> WorkerCycleOutcome:
        """Execute one cycle and discard every provider-local trajectory on exit."""
        self._last_runtime_error = None
        self._last_interruption = None
        self._malformed_argument_correction_turns = 0
        self._cycle_id = f"cycle-{uuid4().hex}"
        self._cycle_number = self._target_state.usage.cycles + 1
        self._cycle_turn = 0
        self._cycle_entry_usage = self._target_state.usage.model_copy(deep=True)
        outcome: WorkerCycleOutcome | None = None
        try:
            outcome = await self._run_cycle()
            return outcome
        finally:
            if outcome is not None and self._cycle_id is not None:
                try:
                    self._coordinator.record_cycle_finished(
                        self._target_spec.target_task_id,
                        cycle_id=self._cycle_id,
                        cycle_number=self._cycle_number,
                        outcome=outcome,
                        focus=focus_payload(self._context.cycle_focus),
                        usage_delta=_usage_delta(
                            self._cycle_entry_usage,
                            self._target_state.usage,
                        ),
                        completion_changes=_completion_changes(
                            self._base_completion,
                            self._completion_state,
                        ),
                    )
                except Exception:
                    pass
            self._tools.clear_transient_state()
            self._continuation_ref = None
            self._compacted_context = None
            self._pending_messages = []
            self._latest_usage = LLMUsage()

    async def _run_cycle(self) -> WorkerCycleOutcome:
        """Preflight, charge, and execute one multi-turn hydrated worker cycle."""
        try:
            request, input_tokens, output_tokens = self._preflight()
        except _BudgetStop as stop:
            return self._outcome_for_budget_stop(stop.scope)
        except _ContextCapacityStop as error:
            return self._interrupt(
                category="context-capacity",
                operation="context-build",
                message=str(error),
            )
        repair = self._context.mode is WorkerContextMode.REPAIR
        self._cycle_turn = 1
        trace_context = self._request_trace_context(
            request,
            input_tokens,
            cycle_turn=self._cycle_turn,
        )
        try:
            model_reservation = (
                await self._coordinator.start_cycle_and_reserve_first_model_call(
                    self._fleet_spec.fleet_budget,
                    self._fleet_state.usage,
                    self._target_spec.budget,
                    self._target_state,
                    repair=repair,
                    input_tokens=input_tokens,
                    requested_output_tokens=output_tokens,
                    trace_context=trace_context,
                )
            )
        except _BudgetStop as stop:
            return self._outcome_for_budget_stop(stop.scope)
        while self._target_state.phase is TargetPhase.WORKING:
            reservation = model_reservation
            request = request.model_copy(
                update={"max_output_tokens": reservation.output_tokens}
            )

            response: LLMResponse | None = None
            durable_retry_loop = False
            try:
                await self._coordinator.mark_model_invoked(reservation)
                if reservation.attempt_id is None:
                    response = await self._client.generate(request)
                else:
                    durable_retry_loop = True
                    response = await self._generate_with_retries(
                        request,
                        reservation.attempt_id,
                    )
            except _BudgetStop as stop:
                await self._coordinator.finish_model_call(
                    reservation,
                    self._target_state.usage,
                    self._fleet_state.usage,
                    None,
                )
                return self._outcome_for_budget_stop(stop.scope)
            except Exception as error:
                failed_usage = getattr(error, "usage", None)
                await self._coordinator.finish_model_call(
                    reservation,
                    self._target_state.usage,
                    self._fleet_state.usage,
                    failed_usage if isinstance(failed_usage, LLMUsage) else None,
                    trace_payload=model_error_trace_payload(error),
                    failed=True,
                )
                attempt_count = getattr(error, "attempt_count", 1)
                if (
                    not durable_retry_loop
                    and isinstance(attempt_count, int)
                    and attempt_count > 1
                ):
                    await self._coordinator.charge_additional_model_attempts(
                        self._target_state.usage,
                        self._fleet_state.usage,
                        attempt_count - 1,
                        target_state=self._target_state,
                        target_spec=self._target_spec,
                    )
                return self._interrupt_from_error("model-invocation", error)
            await self._coordinator.finish_model_call(
                reservation,
                self._target_state.usage,
                self._fleet_state.usage,
                response.usage,
                trace_payload=model_response_trace_payload(response),
            )
            if response.retry_count and not durable_retry_loop:
                await self._coordinator.charge_additional_model_attempts(
                    self._target_state.usage,
                    self._fleet_state.usage,
                    response.retry_count,
                    target_state=self._target_state,
                    target_spec=self._target_spec,
                )
            self._latest_usage = response.usage
            self._continuation_ref = response.response_id
            if (
                request.compacted_context is not None
                and response.response_id is not None
            ):
                self._compacted_context = None

            calls = response.tool_calls
            if not calls:
                return self._interrupt(
                    category="runtime",
                    operation="worker-protocol",
                    message="model response contained no tool calls",
                )
            malformed_calls = [call for call in calls if call.has_malformed_arguments]
            if malformed_calls:
                self._malformed_argument_correction_turns += 1
                if (
                    self._malformed_argument_correction_turns
                    > MAX_MALFORMED_ARGUMENT_CORRECTION_TURNS
                ):
                    for call in malformed_calls:
                        self._coordinator.record_tool_result(
                            self._target_spec.target_task_id,
                            call.name,
                            failed=True,
                            error_code="malformed_arguments",
                            trace_payload={
                                "call_id": call.id,
                                "parent_attempt_id": reservation.attempt_id,
                                "cycle_id": self._cycle_id,
                                **project_tool_arguments(call),
                            },
                        )
                    return self._interrupt(
                        category="runtime",
                        operation="tool-arguments",
                        message=_MALFORMED_ARGUMENT_CORRECTION_LIMIT_MESSAGE,
                    )
            if self._is_valid_finalization(calls):
                return WorkerCycleOutcome.FINALIZATION_REQUESTED
            if self._is_valid_yield(calls):
                try:
                    await self._coordinator.yield_cycle(
                        self._target_spec,
                        self._target_state,
                    )
                except Exception as error:
                    return self._interrupt_from_error("cycle-yield", error)
                return WorkerCycleOutcome.CYCLE_YIELDED

            operational = [
                call
                for call in calls
                if (
                    call.name not in _CONTROL_TOOL_IDS
                    and not call.has_malformed_arguments
                )
            ]
            tool_reservation: _ToolReservation | None = None
            if operational:
                try:
                    tool_reservation = await self._coordinator.reserve_tool_batch(
                        self._fleet_spec.fleet_budget,
                        self._fleet_state.usage,
                        self._target_spec.budget,
                        self._target_state.usage,
                        len(operational),
                    )
                except _BudgetStop as stop:
                    return self._outcome_for_budget_stop(stop.scope)

            results: list[LLMToolResult] = []
            raw_results: list[LLMToolResult] = []
            try:
                for call in calls:
                    if call.has_malformed_arguments:
                        result = _malformed_arguments_result(call)
                        raw_results.append(result)
                        results.append(result)
                        continue
                    if call.name in _CONTROL_TOOL_IDS:
                        result = _control_protocol_error(call, calls)
                        raw_results.append(result)
                        results.append(result)
                        continue
                    if tool_reservation is None:
                        raise RuntimeError("operational call lacks batch reservation")
                    await self._coordinator.begin_tool_dispatch(
                        tool_reservation,
                        self._target_state.usage,
                        self._fleet_state.usage,
                        target_state=self._target_state,
                        target_spec=self._target_spec,
                        tool=call.name,
                        trace_payload={
                            "call_id": call.id,
                            "parent_attempt_id": reservation.attempt_id,
                            "cycle_id": self._cycle_id,
                            **project_tool_arguments(call),
                        },
                    )
                    result = await self._tools.execute_operational(call)
                    delivered = _bound_tool_result(
                        result,
                        maximum_bytes=self._limits.tool_result_max_bytes,
                    )
                    raw_results.append(result)
                    results.append(delivered)
            except Exception as error:
                if tool_reservation is not None:
                    await self._coordinator.release_tool_batch(tool_reservation)
                return self._interrupt_from_error("tool-dispatch", error)
            if tool_reservation is not None:
                await self._coordinator.release_tool_batch(tool_reservation)
            try:
                results = self._bound_pending_tool_results(results)
            except _ContextCapacityStop as error:
                return self._interrupt(
                    category="context-capacity",
                    operation="compaction",
                    message=str(error),
                )
            for call, raw_result, delivered_result in zip(
                calls,
                raw_results,
                results,
                strict=True,
            ):
                result_trace: dict[str, object] = {
                    "call_id": call.id,
                    "parent_attempt_id": reservation.attempt_id,
                    "cycle_id": self._cycle_id,
                    "result": summarize_tool_result(
                        raw_result,
                        delivered_result,
                        self._manager.count_text,
                    ),
                }
                if raw_result.error is not None:
                    result_trace.update(bounded_error_message(raw_result.error.message))
                self._coordinator.record_tool_result(
                    self._target_spec.target_task_id,
                    call.name,
                    failed=raw_result.error is not None,
                    error_code=(
                        raw_result.error.code if raw_result.error is not None else None
                    ),
                    trace_payload={
                        **project_tool_arguments(call),
                        **result_trace,
                    },
                )
            self._working_set.add(_ToolBatch(calls=list(calls), results=results))
            self._pending_messages = [result.as_message() for result in results]

            try:
                await self._compact_if_needed()
            except _BudgetStop as stop:
                return self._outcome_for_budget_stop(stop.scope)
            except _ContextCapacityStop as error:
                return self._interrupt(
                    category="context-capacity",
                    operation="compaction",
                    message=str(error),
                )
            except Exception as error:
                return self._interrupt_from_error("compaction", error)
            try:
                request, input_tokens, output_tokens = self._next_request()
            except _BudgetStop as stop:
                return self._outcome_for_budget_stop(stop.scope)
            except _ContextCapacityStop as error:
                return self._interrupt(
                    category="context-capacity",
                    operation="context-build",
                    message=str(error),
                )
            except Exception as error:
                return self._interrupt_from_error("context-build", error)
            self._cycle_turn += 1
            try:
                model_reservation = await self._coordinator.reserve_model_call(
                    self._fleet_spec.fleet_budget,
                    self._fleet_state.usage,
                    self._target_spec.budget,
                    self._target_state.usage,
                    input_tokens=input_tokens,
                    requested_output_tokens=output_tokens,
                    target_state=self._target_state,
                    target_spec=self._target_spec,
                    trace_context=self._request_trace_context(
                        request,
                        input_tokens,
                        cycle_turn=self._cycle_turn,
                    ),
                )
            except _BudgetStop as stop:
                return self._outcome_for_budget_stop(stop.scope)
            except Exception as error:
                return self._interrupt_from_error("model-reservation", error)

        return self._interrupt(
            category="runtime",
            operation="worker-cycle",
            message=(
                "worker exited active trajectory without a terminal control outcome"
            ),
        )

    def _interrupt(
        self,
        *,
        category: str,
        operation: str,
        message: str,
        retryable: bool = True,
        error: Exception | None = None,
    ) -> WorkerCycleOutcome:
        self._last_runtime_error = error
        self._last_interruption = WorkerInterruption(
            category=category,
            operation=operation,
            message=message,
            retryable=retryable,
        )
        return WorkerCycleOutcome.EXECUTION_INTERRUPTED

    def _interrupt_from_error(
        self,
        operation: str,
        error: Exception,
    ) -> WorkerCycleOutcome:
        if isinstance(error, LLMError):
            return self._interrupt(
                category="provider",
                operation=operation,
                message=error.safe_message,
                retryable=error.retryable,
                error=error,
            )
        return self._interrupt(
            category="runtime",
            operation=operation,
            message=str(error),
            error=error,
        )

    async def _generate_with_retries(
        self,
        request: LLMRequest,
        logical_attempt_id: str,
    ) -> LLMResponse:
        async def operation() -> LLMResponse:
            generate_once = getattr(self._client, "generate_once", None)
            if callable(generate_once):
                return await generate_once(request)
            return await self._client.generate(request)

        async def before_attempt(attempt: int) -> None:
            if attempt == 1:
                return
            await self._coordinator.charge_additional_model_attempts(
                self._target_state.usage,
                self._fleet_state.usage,
                1,
                target_state=self._target_state,
                target_spec=self._target_spec,
            )
            self._coordinator.record_retry_attempt_boundary(
                self._target_spec.target_task_id,
                logical_attempt_id,
                attempt,
                failed=False,
            )

        async def on_retry(
            next_attempt: int,
            delay_seconds: float,
            error: LLMError,
        ) -> None:
            self._coordinator.record_retry_attempt_boundary(
                self._target_spec.target_task_id,
                logical_attempt_id,
                next_attempt - 1,
                failed=True,
                usage=(error.usage if isinstance(error.usage, LLMUsage) else None),
                error=error,
            )
            failed_usage = getattr(error, "usage", None)
            if isinstance(failed_usage, LLMUsage):
                await self._coordinator.charge_reported_tokens(
                    self._target_state,
                    self._fleet_state,
                    failed_usage,
                )
            self._coordinator.record_retry(
                self._target_spec.target_task_id,
                next_attempt,
                delay_seconds,
            )

        return await run_provider_with_retry(
            operation,
            before_attempt=before_attempt,
            on_retry=on_retry,
        )

    def _preflight(self) -> tuple[LLMRequest, int, int]:
        self._validate_invocation()
        request, input_tokens, output_tokens = self._build_request(initial=True)
        _require_cycle_capacity(
            self._target_spec.budget,
            self._target_state.usage,
            self._context.mode is WorkerContextMode.REPAIR,
            _BudgetScope.TARGET,
        )
        _require_cycle_capacity(
            self._fleet_spec.fleet_budget,
            self._fleet_state.usage,
            self._context.mode is WorkerContextMode.REPAIR,
            _BudgetScope.FLEET,
        )
        self._require_execution_headroom(input_tokens, output_tokens)
        return request, input_tokens, output_tokens

    def _next_request(self) -> tuple[LLMRequest, int, int]:
        request, input_tokens, output_tokens = self._build_request(initial=False)
        self._require_execution_headroom(input_tokens, output_tokens)
        return request, input_tokens, output_tokens

    def _request_trace_context(
        self,
        request: LLMRequest | LLMCompactionRequest,
        input_tokens: int,
        *,
        cycle_turn: int,
        call_kind: str = "generate",
    ) -> dict[str, object]:
        """Build bounded request diagnostics from existing serialized context."""
        initial = (
            isinstance(request, LLMRequest)
            and request.continuation_ref is None
            and request.compacted_context is None
            and not request.messages
        )
        overlay_tokens = 0
        if not initial:
            overlay_tokens = self._manager.count_text(self._execution_overlay())
        return model_request_trace_context(
            request,
            local_request_input_tokens=input_tokens,
            count_tokens=self._manager.count_text,
            canonical_base_tokens=self._manager.count_text(self._canonical_base),
            execution_overlay_tokens=overlay_tokens,
            pending_tool_result_tokens=(
                self._manager.count_text(_serialize_messages(self._pending_messages))
                if self._pending_messages
                else 0
            ),
            cycle_id=self._cycle_id,
            cycle_turn=cycle_turn,
            call_kind=call_kind,
        )

    def _build_request(self, *, initial: bool) -> tuple[LLMRequest, int, int]:
        while True:
            messages = self._request_messages(initial=initial)
            instructions = self._exact_control_context(initial=initial)
            request = LLMRequest(
                operation=LLMOperation.MEMORY_AGENT_WORKER,
                profile=self._profile.profile_id,
                messages=messages,
                instructions=instructions,
                continuation_ref=None if initial else self._continuation_ref,
                store=True,
                compacted_context=None if initial else self._compacted_context,
                prompt_cache=LLMPromptCacheConfig(
                    key=self._prompt_cache_key,
                    instruction_breakpoints=_instruction_breakpoints(
                        self._canonical_sections
                    ),
                ),
                tools=list(self._tool_definitions),
                tool_choice="required",
                max_output_tokens=max(1, self._profile.reserved_response_tokens),
                reasoning=(
                    LLMReasoningConfig(
                        effort=self._profile.reasoning_effort,
                        context=self._profile.reasoning_context,
                    )
                    if self._profile.reasoning_effort is not None
                    else None
                ),
                metadata={
                    "run_id": self._fleet_spec.fleet_run_id,
                    "workflow_id": self._target_spec.target_task_id,
                },
            )
            serialized = _serialize_request(request)
            canonical_ingress_tokens = self._manager.count_text(
                _serialize_canonical_ingress(request)
            )
            input_tokens = self._manager.count_text(serialized)
            output_tokens = self._maximum_output_tokens(input_tokens)
            diagnostics = self._manager.inspect_request(
                serialized,
                reserved_response_tokens=output_tokens,
            )
            if (
                canonical_ingress_tokens <= self._profile.provider_input_hard_cap_tokens
                and diagnostics.within_context_limit
            ):
                return (
                    request.model_copy(update={"max_output_tokens": output_tokens}),
                    diagnostics.current_request_input_tokens,
                    output_tokens,
                )
            if canonical_ingress_tokens > self._profile.provider_input_hard_cap_tokens:
                raise WorkerCyclePreflightError(
                    "minimum valid canonical worker ingress exceeds the "
                    "provider-input hard cap"
                )
            if initial or not self._working_set.evict_one_for_context_pressure():
                raise _ContextCapacityStop("minimum valid worker request cannot fit")

    def _request_messages(self, *, initial: bool) -> list[LLMMessage]:
        if initial:
            return []
        if self._compacted_context is not None:
            return self._working_set.protected_messages()
        if self._continuation_ref is not None:
            return list(self._pending_messages)
        return self._working_set.messages()

    def _exact_control_context(self, *, initial: bool) -> str:
        if initial:
            return self._canonical_base
        return f"{self._canonical_base}\n\n{self._execution_overlay()}\n"

    async def _compact_if_needed(self) -> None:
        continuation_ref = self._continuation_ref
        latest_input = self._latest_usage.input_tokens
        latest_output = self._latest_usage.output_tokens
        if continuation_ref is None or latest_input is None or latest_output is None:
            return
        pending_tokens = self._manager.count_text(
            _serialize_messages(self._pending_messages)
        )
        projected_context = (
            latest_input
            + latest_output
            + pending_tokens
            + self._profile.reserved_response_tokens
        )
        trigger = int(
            self._limits.active_context_soft_limit_tokens
            * self._limits.compaction_trigger_ratio
        )
        if projected_context <= trigger:
            return

        instructions = self._exact_control_context(initial=False)
        compaction_request = LLMCompactionRequest(
            operation=LLMOperation.MEMORY_AGENT_WORKER,
            profile=self._profile.profile_id,
            messages=list(self._pending_messages),
            instructions=instructions,
            continuation_ref=continuation_ref,
            metadata={
                "run_id": self._fleet_spec.fleet_run_id,
                "workflow_id": self._target_spec.target_task_id,
            },
        )
        local_input_tokens = self._manager.count_text(
            _serialize_compaction_request(compaction_request)
        )
        input_tokens = max(
            local_input_tokens,
            latest_input + latest_output + pending_tokens,
        )
        self._require_compaction_capacity(input_tokens)
        reservation = await self._coordinator.reserve_model_call(
            self._fleet_spec.fleet_budget,
            self._fleet_state.usage,
            self._target_spec.budget,
            self._target_state.usage,
            input_tokens=input_tokens,
            requested_output_tokens=self._compaction_budget_output_tokens(),
            target_state=self._target_state,
            target_spec=self._target_spec,
            trace_context=self._request_trace_context(
                compaction_request,
                local_input_tokens,
                cycle_turn=self._cycle_turn,
                call_kind="compact",
            ),
        )
        self._coordinator.record_compaction_started(
            self._target_spec.target_task_id,
            projected_context_tokens=projected_context,
            active_context_soft_limit_tokens=(
                self._limits.active_context_soft_limit_tokens
            ),
            model_context_window_tokens=self._profile.model_context_window_tokens,
            trace_payload={
                "cycle_id": self._cycle_id,
                "cycle_turn": self._cycle_turn,
                "trigger_threshold_tokens": trigger,
                "pending_message_tokens": pending_tokens,
                "latest_provider_input_tokens": latest_input,
                "latest_provider_output_tokens": latest_output,
                "local_compaction_request_tokens": local_input_tokens,
            },
        )
        result: LLMCompactionResult | None = None
        try:
            await self._coordinator.mark_model_invoked(reservation)
            result = await self._client.compact(compaction_request)
        except Exception as error:
            failed_usage = getattr(error, "usage", None)
            await self._coordinator.finish_model_call(
                reservation,
                self._target_state.usage,
                self._fleet_state.usage,
                failed_usage if isinstance(failed_usage, LLMUsage) else None,
                trace_payload=model_error_trace_payload(error),
                failed=True,
            )
            attempt_count = getattr(error, "attempt_count", 1)
            if isinstance(attempt_count, int) and attempt_count > 1:
                await self._coordinator.charge_additional_model_attempts(
                    self._target_state.usage,
                    self._fleet_state.usage,
                    attempt_count - 1,
                    target_state=self._target_state,
                    target_spec=self._target_spec,
                )
            raise
        assert result is not None
        await self._coordinator.finish_model_call(
            reservation,
            self._target_state.usage,
            self._fleet_state.usage,
            result.usage,
            trace_payload={
                "provider": result.context.provider,
                "model": self._profile.model,
                "retry_count": result.retry_count,
                "provider_attempt": result.retry_count + 1,
                "provider_usage": provider_usage_payload(result.usage),
            },
        )
        if result.retry_count:
            await self._coordinator.charge_additional_model_attempts(
                self._target_state.usage,
                self._fleet_state.usage,
                result.retry_count,
                target_state=self._target_state,
                target_spec=self._target_spec,
            )
        if result.context.provider != self._profile.provider:
            raise RuntimeError(
                "compacted context provider does not match worker provider"
            )
        self._compacted_context = result.context
        self._continuation_ref = None
        self._coordinator.record_compaction_completed(
            self._target_spec.target_task_id,
            projected_context_tokens=projected_context,
            active_context_soft_limit_tokens=(
                self._limits.active_context_soft_limit_tokens
            ),
            model_context_window_tokens=self._profile.model_context_window_tokens,
            trace_payload={
                "cycle_id": self._cycle_id,
                "cycle_turn": self._cycle_turn,
                "trigger_threshold_tokens": trigger,
                "pending_message_tokens": pending_tokens,
                "latest_provider_input_tokens": latest_input,
                "latest_provider_output_tokens": latest_output,
                "local_compaction_request_tokens": local_input_tokens,
            },
        )

    def _bound_pending_tool_results(
        self,
        results: list[LLMToolResult],
    ) -> list[LLMToolResult]:
        """Keep one pending tool batch small enough for provider compaction."""
        continuation_ref = self._continuation_ref
        latest_input = self._latest_usage.input_tokens
        latest_output = self._latest_usage.output_tokens
        if continuation_ref is None or latest_input is None or latest_output is None:
            return results

        instructions = self._exact_control_context(initial=False)
        base_request = LLMCompactionRequest(
            operation=LLMOperation.MEMORY_AGENT_WORKER,
            profile=self._profile.profile_id,
            instructions=instructions,
            continuation_ref=continuation_ref,
            metadata={
                "run_id": self._fleet_spec.fleet_run_id,
                "workflow_id": self._target_spec.target_task_id,
            },
        )
        fixed_tokens = self._manager.count_text(
            _serialize_compaction_request(base_request)
        )
        available_batch_tokens = (
            self._profile.model_context_window_tokens
            - max(fixed_tokens, latest_input + latest_output)
            - COMPACTION_INGRESS_SAFETY_TOKENS
        )
        if available_batch_tokens < 1:
            raise _ContextCapacityStop(
                "active trajectory leaves no provider capacity for compaction"
            )

        bounded = list(results)
        while True:
            pending_tokens = self._manager.count_text(
                _serialize_messages([result.as_message() for result in bounded])
            )
            if pending_tokens <= available_batch_tokens:
                return bounded
            largest_index, largest = max(
                enumerate(bounded),
                key=lambda item: len(orjson.dumps(item[1].model_dump(mode="json"))),
            )
            serialized_size = len(orjson.dumps(largest.model_dump(mode="json")))
            reduced = _bound_tool_result(
                largest,
                maximum_bytes=max(256, serialized_size // 2),
            )
            if len(orjson.dumps(reduced.model_dump(mode="json"))) >= serialized_size:
                raise _ContextCapacityStop(
                    "tool-result protocol overhead exceeds compaction ingress capacity"
                )
            bounded[largest_index] = reduced

    def _maximum_output_tokens(self, input_tokens: int) -> int:
        maximum = self._profile.reserved_response_tokens
        if maximum < 1:
            raise WorkerCyclePreflightError(
                "worker profile must reserve positive Stage 4 response capacity"
            )
        provider_remaining = self._profile.model_context_window_tokens - input_tokens
        if provider_remaining < 1:
            raise _ContextCapacityStop(
                "normal worker request leaves no provider response capacity"
            )
        maximum = min(maximum, provider_remaining)
        target_remaining = _remaining_optional(
            self._target_spec.budget.max_output_tokens,
            self._target_state.usage.output_tokens,
        )
        fleet_remaining = _remaining_optional(
            self._fleet_spec.fleet_budget.max_output_tokens,
            self._fleet_state.usage.output_tokens,
        )
        if target_remaining is not None:
            maximum = min(maximum, target_remaining)
        if fleet_remaining is not None:
            maximum = min(maximum, fleet_remaining)
        if maximum < 1:
            scope = (
                _BudgetScope.TARGET
                if target_remaining is not None and target_remaining < 1
                else _BudgetScope.FLEET
            )
            raise _BudgetStop(scope)
        return maximum

    def _require_execution_headroom(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        if (
            self._target_state.usage.model_calls
            >= self._target_spec.budget.max_model_calls
        ):
            raise _BudgetStop(_BudgetScope.TARGET)
        if (
            self._fleet_state.usage.model_calls
            >= self._fleet_spec.fleet_budget.max_model_calls
        ):
            raise _BudgetStop(_BudgetScope.FLEET)
        if self._target_spec.budget.max_input_tokens is not None and (
            budgeted_input_tokens(self._target_state.usage) + input_tokens
            > self._target_spec.budget.max_input_tokens
        ):
            raise _BudgetStop(_BudgetScope.TARGET)
        if self._fleet_spec.fleet_budget.max_input_tokens is not None and (
            budgeted_input_tokens(self._fleet_state.usage) + input_tokens
            > self._fleet_spec.fleet_budget.max_input_tokens
        ):
            raise _BudgetStop(_BudgetScope.FLEET)
        if output_tokens < 1:
            raise _BudgetStop(_BudgetScope.TARGET)

    def _require_compaction_capacity(self, input_tokens: int) -> None:
        """Require only input fit for the provider compaction endpoint."""
        if input_tokens > self._profile.model_context_window_tokens:
            raise _ContextCapacityStop(
                "compaction request exceeds the provider context capacity"
            )

    def _compaction_budget_output_tokens(self) -> int:
        """Reserve normal execution budget headroom without generation capacity."""
        target_remaining = _remaining_optional(
            self._target_spec.budget.max_output_tokens,
            self._target_state.usage.output_tokens,
        )
        fleet_remaining = _remaining_optional(
            self._fleet_spec.fleet_budget.max_output_tokens,
            self._fleet_state.usage.output_tokens,
        )
        maximum = self._profile.reserved_response_tokens
        if target_remaining is not None:
            maximum = min(maximum, target_remaining)
        if fleet_remaining is not None:
            maximum = min(maximum, fleet_remaining)
        if maximum < 1:
            scope = (
                _BudgetScope.TARGET
                if target_remaining is not None and target_remaining < 1
                else _BudgetScope.FLEET
            )
            raise _BudgetStop(scope)
        return maximum

    def _validate_invocation(self) -> None:
        if self._target_state.phase is not TargetPhase.HYDRATING:
            raise WorkerCycleInvocationError("worker cycle requires a HYDRATING target")
        if self._context.target_task_id != self._target_spec.target_task_id:
            raise WorkerCycleInvocationError(
                "WorkerContext belongs to a different target task"
            )
        if self._context.source != self._target_spec.source:
            raise WorkerCycleInvocationError(
                "WorkerContext source does not match the target source"
            )
        if self._target_state.target_task_id != self._target_spec.target_task_id:
            raise WorkerCycleInvocationError(
                "target spec/state identities do not match"
            )
        if (
            self._target_spec.fleet_run_id != self._fleet_spec.fleet_run_id
            or self._target_state.fleet_run_id != self._fleet_spec.fleet_run_id
            or self._fleet_state.fleet_run_id != self._fleet_spec.fleet_run_id
        ):
            raise WorkerCycleInvocationError("worker authorities span multiple fleets")
        if self._target_spec.source != self._fleet_spec.source:
            raise WorkerCycleInvocationError(
                "target source does not match fleet source"
            )
        if self._completion_state.target_task_id != self._target_spec.target_task_id:
            raise WorkerCycleInvocationError(
                "completion state belongs to a different target"
            )
        repair_context = self._context.mode is WorkerContextMode.REPAIR
        if repair_context != bool(self._target_state.open_finding_refs):
            raise WorkerCycleInvocationError(
                "WorkerContext mode does not match current repair findings"
            )
        if self._profile.profile_id != self._context.worker_profile_id:
            raise WorkerCyclePreflightError("worker profile does not match context")
        if self._context.worker_profile_id != self._target_spec.worker_profile_id:
            raise WorkerCyclePreflightError(
                "WorkerContext worker profile does not match the target task"
            )
        if (
            self._context.permission_profile_id
            != self._target_spec.permission_profile_id
        ):
            raise WorkerCyclePreflightError(
                "WorkerContext permission profile does not match the target task"
            )
        if self._manager.profile != self._profile:
            raise WorkerCyclePreflightError(
                "context-window manager does not match worker profile"
            )

    def _execution_overlay(self) -> str:
        overlay: dict[str, object] = {
            "supersedes_stale_worker_context_fields": True,
            "remaining_target_budget": _remaining_budget(
                self._target_spec.budget,
                self._target_state.usage,
            ),
        }
        completion = {
            item.obligation_id: (
                item.status,
                item.resolution_note,
                tuple(item.evidence_refs),
            )
            for item in self._completion_state.items
        }
        changed_completion = [
            item
            for item in self._completion_state.items
            if completion[item.obligation_id]
            != self._base_completion.get(item.obligation_id)
        ]
        if changed_completion:
            overlay["changed_completion_items"] = changed_completion
        artifacts = tuple(self._target_state.artifact_refs)
        if artifacts != self._base_artifacts:
            overlay["current_candidate_artifacts"] = artifacts
        if self._target_state.working_summary != self._base_summary:
            overlay["current_working_summary"] = self._target_state.working_summary
        question_refs = tuple(self._target_state.open_question_refs)
        if question_refs != self._base_questions:
            current_questions: list[OpenQuestion] = []
            for question_id in question_refs:
                question = self._questions.get(question_id)
                if (
                    question is None
                    or question.target_task_id != self._target_spec.target_task_id
                ):
                    raise RuntimeError("authoritative open question is missing")
                current_questions.append(question)
            overlay["current_open_questions"] = current_questions
        new_evidence: list[EvidenceReference] = []
        for evidence_id in self._target_state.evidence_refs:
            if evidence_id in self._base_evidence:
                continue
            reference = self._evidence.get(evidence_id)
            if reference is None:
                raise RuntimeError("authoritative evidence reference is missing")
            new_evidence.append(reference)
        if new_evidence:
            overlay["new_evidence"] = new_evidence
        serialized = orjson.dumps(
            overlay,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_INDENT_2,
            default=_json_default,
        ).decode()
        return (
            "Current execution-state overlay (authoritative corrections):\n"
            + serialized
        )

    @staticmethod
    def _is_valid_finalization(calls: list[LLMToolCall]) -> bool:
        return (
            len(calls) == 1
            and calls[0].name == FINALIZATION_TOOL_ID
            and not calls[0].has_malformed_arguments
            and not calls[0].arguments
        )

    @staticmethod
    def _is_valid_yield(calls: list[LLMToolCall]) -> bool:
        return (
            len(calls) == 1
            and calls[0].name == YIELD_CYCLE_TOOL_ID
            and not calls[0].has_malformed_arguments
            and not calls[0].arguments
        )

    def _outcome_for_budget_stop(
        self,
        scope: _BudgetScope,
    ) -> WorkerCycleOutcome:
        if scope is _BudgetScope.TARGET:
            self._target_state.phase = TargetPhase.EXHAUSTED
            return WorkerCycleOutcome.TARGET_BUDGET_EXHAUSTED
        return WorkerCycleOutcome.FLEET_BUDGET_STOP


def _require_cycle_capacity(
    budget: ExecutionBudget,
    usage: ExecutionUsage,
    repair: bool,
    scope: _BudgetScope,
) -> None:
    if usage.cycles >= budget.max_cycles:
        raise _BudgetStop(scope)
    if repair and usage.repair_cycles >= budget.max_repair_cycles:
        raise _BudgetStop(scope)


def _remaining_optional(limit: int | None, usage: int) -> int | None:
    return None if limit is None else max(0, limit - usage)


def _remaining_budget(
    budget: ExecutionBudget,
    usage: ExecutionUsage,
) -> dict[str, int | None]:
    return {
        "cycles": max(0, budget.max_cycles - usage.cycles),
        "repair_cycles": max(0, budget.max_repair_cycles - usage.repair_cycles),
        "model_calls": max(0, budget.max_model_calls - usage.model_calls),
        "tool_calls": max(0, budget.max_tool_calls - usage.tool_calls),
        "input_tokens": _remaining_optional(
            budget.max_input_tokens,
            budgeted_input_tokens(usage),
        ),
        "output_tokens": _remaining_optional(
            budget.max_output_tokens,
            usage.output_tokens,
        ),
    }


def _apply_usage_delta(
    target_usage: ExecutionUsage,
    fleet_usage: ExecutionUsage,
    **delta: int,
) -> None:
    for field_name, amount in delta.items():
        if amount < 0:
            raise ValueError("usage deltas cannot be negative")
        setattr(target_usage, field_name, getattr(target_usage, field_name) + amount)
        setattr(fleet_usage, field_name, getattr(fleet_usage, field_name) + amount)


def _usage_delta(before: ExecutionUsage, after: ExecutionUsage) -> dict[str, int]:
    """Return all execution counters changed by one worker cycle."""
    fields = (
        "cycles",
        "model_calls",
        "tool_calls",
        "repair_cycles",
        "input_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "output_tokens",
    )
    return {field: getattr(after, field) - getattr(before, field) for field in fields}


def _completion_changes(
    before: Mapping[str, tuple[object, ...]],
    after: TargetCompletionState,
) -> list[dict[str, object]]:
    """Summarize every obligation status transition, including opportunistic ones."""
    changes: list[dict[str, object]] = []
    for item in after.items:
        previous = before.get(item.obligation_id)
        previous_status = previous[0] if previous is not None else None
        if previous_status == item.status:
            continue
        changes.append(
            {
                "obligation_id": item.obligation_id,
                "from_status": (
                    previous_status.value
                    if isinstance(previous_status, StrEnum)
                    else previous_status
                ),
                "to_status": item.status.value,
            }
        )
    return changes


def _control_protocol_error(
    call: LLMToolCall,
    calls: list[LLMToolCall],
) -> LLMToolResult:
    control_name = call.name
    reason = (
        f"{control_name} must have no arguments"
        if call.arguments
        else f"{control_name} must be the sole call in its response"
    )
    if {item.name for item in calls} >= _CONTROL_TOOL_IDS:
        reason = "yield_cycle and request_finalization cannot be requested together"
    return LLMToolResult(
        call_id=call.id,
        name=call.name,
        error=LLMToolError(code="protocol_error", message=reason),
    )


def _malformed_arguments_result(call: LLMToolCall) -> LLMToolResult:
    """Return a correlated correction request without dispatching the tool."""
    return LLMToolResult(
        call_id=call.id,
        name=call.name,
        error=LLMToolError(
            code="malformed_arguments",
            message=(
                f"Invalid arguments for {call.name}: retry this call with a valid "
                "JSON object matching the tool schema."
            ),
        ),
    )


def _bound_tool_result(
    result: LLMToolResult,
    *,
    maximum_bytes: int,
) -> LLMToolResult:
    serialized = orjson.dumps(result.model_dump(mode="json"))
    if len(serialized) <= maximum_bytes:
        return result
    if result.error is not None:
        return _truncate_tool_error(result, maximum_bytes)

    prefix = serialized.decode("utf-8", errors="ignore")
    low = 0
    high = len(prefix)
    best: LLMToolResult | None = None
    while low <= high:
        length = (low + high) // 2
        candidate = result.model_copy(
            update={
                "output": {
                    "truncated": True,
                    "original_bytes": len(serialized),
                    "serialized_prefix": prefix[:length],
                    "instruction": "Retrieve a narrower range or smaller result set.",
                }
            }
        )
        if len(orjson.dumps(candidate.model_dump(mode="json"))) <= maximum_bytes:
            best = candidate
            low = length + 1
        else:
            high = length - 1
    if best is not None:
        return best
    return result.model_copy(
        update={
            "output": (
                "Result truncated. Retrieve a narrower range or smaller result set."
            )
        }
    )


def _truncate_tool_error(
    result: LLMToolResult,
    maximum_bytes: int,
) -> LLMToolResult:
    """Reduce an error body without changing its tool-result protocol shape."""
    assert result.error is not None
    message = result.error.message
    low = 0
    high = len(message)
    best: LLMToolResult | None = None
    while low <= high:
        length = (low + high) // 2
        candidate = result.model_copy(
            update={
                "error": result.error.model_copy(update={"message": message[:length]})
            }
        )
        if len(orjson.dumps(candidate.model_dump(mode="json"))) <= maximum_bytes:
            best = candidate
            low = length + 1
        else:
            high = length - 1
    return best or result


def _placeholder_batch(batch: _ToolBatch) -> _ToolBatch:
    results = [
        result.model_copy(
            update={
                "output": (
                    f"Previous {call.name} result body was removed from active "
                    "context; retrieve it again if needed."
                ),
                "error": None,
            }
        )
        for call, result in zip(batch.calls, batch.results, strict=True)
    ]
    return _ToolBatch(calls=batch.calls, results=results, placeholder=True)


def _serialize_request(request: LLMRequest) -> str:
    return orjson.dumps(
        request.model_dump(mode="json"),
        option=orjson.OPT_SORT_KEYS,
    ).decode()


def _serialize_canonical_ingress(request: LLMRequest) -> str:
    """Serialize only the request material owned by Bridger's canonical context."""
    canonical_request = request.model_copy(
        update={
            "messages": [],
            "continuation_ref": None,
            "compacted_context": None,
        }
    )
    return _serialize_request(canonical_request)


def _serialize_compaction_request(request: LLMCompactionRequest) -> str:
    return orjson.dumps(
        request.model_dump(mode="json"),
        option=orjson.OPT_SORT_KEYS,
    ).decode()


def _serialize_messages(messages: list[LLMMessage]) -> str:
    return orjson.dumps(
        [message.model_dump(mode="json") for message in messages],
        option=orjson.OPT_SORT_KEYS,
    ).decode()


def _instruction_breakpoints(sections: tuple[str, ...]) -> tuple[int, ...]:
    offsets: list[int] = []
    current = 0
    for section in sections:
        current += len(section)
        offsets.append(current)
    return tuple(offsets)


def _worker_prompt_cache_key(
    context: WorkerContext,
    target_spec: TargetTaskSpec,
    tools: list[LLMToolDefinition],
) -> str:
    identity = {
        "schema_version": "bridger-memory-worker-prompt-cache-v1",
        "worker_profile_id": context.worker_profile_id,
        "target_id": target_spec.target_id,
        "target_contract_version": target_spec.target_contract_version,
        "source": context.source,
        "permission_profile_id": context.permission_profile_id,
        "tools": tools,
    }
    serialized = orjson.dumps(
        identity,
        option=orjson.OPT_SORT_KEYS,
        default=_json_default,
    )
    return hashlib.sha256(serialized).hexdigest()


def _json_default(value: object) -> object:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    raise TypeError(f"cannot serialize {type(value).__name__}")


__all__ = [
    "FleetExecutionCoordinator",
    "WorkerCycleOutcome",
    "WorkerInterruption",
    "WorkerRunner",
    "WorkerRuntimeLimits",
]
