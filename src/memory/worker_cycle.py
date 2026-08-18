"""Stage 4 bounded worker model/tool execution loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

import orjson
from pydantic import JsonValue

from llm.client import LLMClient
from llm.models import (
    LLMMessage,
    LLMOperation,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolError,
    LLMToolResult,
    LLMUsage,
)
from memory.context_window import ContextWindowManager
from memory.errors import WorkerCycleInvocationError, WorkerCyclePreflightError
from memory.hydration import serialize_worker_context
from memory.worker_tools import FINALIZATION_TOOL_ID, WorkerToolRuntime
from models.hydration import WorkerContext, WorkerContextMode, WorkerProfile
from models.memory import (
    ExecutionBudget,
    ExecutionUsage,
    FleetRunState,
    MemoryFleetSpec,
    TargetCompletionState,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from models.worker_cycle import EvidenceReference, OpenQuestion

DEFAULT_TOOL_CONTEXT_SOFT_TOKENS = 16_000
DEFAULT_TOOL_RESULT_MAX_BYTES = 32 * 1024
PROTECTED_TOOL_BATCHES = 3


class WorkerCycleOutcome(StrEnum):
    """Small non-persisted Stage 4 handoff result."""

    FINALIZATION_REQUESTED = "finalization-requested"
    TARGET_BUDGET_EXHAUSTED = "target-budget-exhausted"
    FLEET_BUDGET_STOP = "fleet-budget-stop"
    EXECUTION_INTERRUPTED = "execution-interrupted"


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

    def __post_init__(self) -> None:
        if self.tool_context_soft_tokens < 1 or self.tool_result_max_bytes < 1:
            raise ValueError("worker runtime limits must be positive")


@dataclass(slots=True)
class _ModelReservation:
    input_tokens: int
    output_tokens: int
    active: bool = True


@dataclass(slots=True)
class _ToolReservation:
    remaining: int
    active: bool = True


class FleetExecutionCoordinator:
    """Concurrency-safe in-flight coordination for one fleet's hard budgets."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._reserved_input_tokens = 0
        self._reserved_output_tokens = 0
        self._reserved_tool_calls = 0

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
    ) -> _ModelReservation:
        """Preflight the first action before atomically entering WORKING."""
        target_usage = target_state.usage
        if target_usage.model_calls >= target_budget.max_model_calls:
            raise _BudgetStop(_BudgetScope.TARGET)
        if target_budget.max_input_tokens is not None and (
            target_usage.input_tokens + input_tokens > target_budget.max_input_tokens
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
                fleet_usage.input_tokens + self._reserved_input_tokens + input_tokens
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

            target_state.phase = TargetPhase.WORKING
            _apply_usage_delta(target_usage, fleet_usage, cycles=1, model_calls=1)
            if repair:
                _apply_usage_delta(target_usage, fleet_usage, repair_cycles=1)
            self._reserved_input_tokens += input_tokens
            self._reserved_output_tokens += requested_output_tokens
            return _ModelReservation(input_tokens, requested_output_tokens)

    async def reserve_model_call(
        self,
        fleet_budget: ExecutionBudget,
        fleet_usage: ExecutionUsage,
        target_budget: ExecutionBudget,
        target_usage: ExecutionUsage,
        *,
        input_tokens: int,
        requested_output_tokens: int,
    ) -> _ModelReservation:
        """Reserve exact input and maximum output, then charge the call attempt."""
        if target_usage.model_calls >= target_budget.max_model_calls:
            raise _BudgetStop(_BudgetScope.TARGET)
        if target_budget.max_input_tokens is not None and (
            target_usage.input_tokens + input_tokens > target_budget.max_input_tokens
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
                fleet_usage.input_tokens + self._reserved_input_tokens + input_tokens
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
            _apply_usage_delta(target_usage, fleet_usage, model_calls=1)
            self._reserved_input_tokens += input_tokens
            self._reserved_output_tokens += requested_output_tokens
            return _ModelReservation(input_tokens, requested_output_tokens)

    async def finish_model_call(
        self,
        reservation: _ModelReservation,
        target_usage: ExecutionUsage,
        fleet_usage: ExecutionUsage,
        usage: LLMUsage | None,
    ) -> None:
        """Charge reported tokens and release the unused in-flight allowance."""
        async with self._lock:
            if not reservation.active:
                return
            reservation.active = False
            self._reserved_input_tokens -= reservation.input_tokens
            self._reserved_output_tokens -= reservation.output_tokens
            if usage is not None:
                _apply_usage_delta(
                    target_usage,
                    fleet_usage,
                    input_tokens=usage.input_tokens or 0,
                    output_tokens=usage.output_tokens or 0,
                )

    async def charge_additional_model_attempts(
        self,
        target_usage: ExecutionUsage,
        fleet_usage: ExecutionUsage,
        attempts: int,
    ) -> None:
        """Charge provider retries already performed inside an existing client."""
        if attempts < 0:
            raise ValueError("additional provider attempts cannot be negative")
        async with self._lock:
            _apply_usage_delta(
                target_usage,
                fleet_usage,
                model_calls=attempts,
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
    ) -> None:
        """Charge one attempted operational dispatch from a reserved batch."""
        async with self._lock:
            if not reservation.active or reservation.remaining < 1:
                raise RuntimeError("tool dispatch does not have a live reservation")
            reservation.remaining -= 1
            self._reserved_tool_calls -= 1
            _apply_usage_delta(target_usage, fleet_usage, tool_calls=1)

    async def release_tool_batch(self, reservation: _ToolReservation) -> None:
        """Release any operational calls not attempted after an interruption."""
        async with self._lock:
            if not reservation.active:
                return
            reservation.active = False
            self._reserved_tool_calls -= reservation.remaining
            reservation.remaining = 0


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
        self._limits = limits or WorkerRuntimeLimits()
        self._canonical_base = serialize_worker_context(context)
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

    async def run(self) -> WorkerCycleOutcome:
        """Preflight, charge, and execute one multi-turn hydrated worker cycle."""
        try:
            request, input_tokens, output_tokens = self._preflight()
        except _BudgetStop as stop:
            return self._outcome_for_budget_stop(stop.scope)
        repair = self._context.mode is WorkerContextMode.REPAIR
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
            try:
                response = await self._client.generate(request)
            except Exception as error:
                failed_usage = getattr(error, "usage", None)
                await self._coordinator.finish_model_call(
                    reservation,
                    self._target_state.usage,
                    self._fleet_state.usage,
                    failed_usage if isinstance(failed_usage, LLMUsage) else None,
                )
                attempt_count = getattr(error, "attempt_count", 1)
                if isinstance(attempt_count, int) and attempt_count > 1:
                    await self._coordinator.charge_additional_model_attempts(
                        self._target_state.usage,
                        self._fleet_state.usage,
                        attempt_count - 1,
                    )
                return WorkerCycleOutcome.EXECUTION_INTERRUPTED
            await self._coordinator.finish_model_call(
                reservation,
                self._target_state.usage,
                self._fleet_state.usage,
                response.usage,
            )
            if response.retry_count:
                await self._coordinator.charge_additional_model_attempts(
                    self._target_state.usage,
                    self._fleet_state.usage,
                    response.retry_count,
                )

            calls = response.tool_calls
            if not calls:
                return WorkerCycleOutcome.EXECUTION_INTERRUPTED
            if self._is_valid_finalization(calls):
                return WorkerCycleOutcome.FINALIZATION_REQUESTED

            operational = [call for call in calls if call.name != FINALIZATION_TOOL_ID]
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
            try:
                for call in calls:
                    if call.name == FINALIZATION_TOOL_ID:
                        results.append(_finalization_protocol_error(call))
                        continue
                    if tool_reservation is None:
                        raise RuntimeError("operational call lacks batch reservation")
                    await self._coordinator.begin_tool_dispatch(
                        tool_reservation,
                        self._target_state.usage,
                        self._fleet_state.usage,
                    )
                    result = await self._tools.execute_operational(call)
                    results.append(
                        _bound_tool_result(
                            result,
                            maximum_bytes=self._limits.tool_result_max_bytes,
                        )
                    )
            except Exception:
                if tool_reservation is not None:
                    await self._coordinator.release_tool_batch(tool_reservation)
                return WorkerCycleOutcome.EXECUTION_INTERRUPTED
            if tool_reservation is not None:
                await self._coordinator.release_tool_batch(tool_reservation)
            self._working_set.add(_ToolBatch(calls=list(calls), results=results))

            try:
                request, input_tokens, output_tokens = self._next_request()
            except (_BudgetStop, _ContextCapacityStop) as error:
                if isinstance(error, _BudgetStop):
                    return self._outcome_for_budget_stop(error.scope)
                return WorkerCycleOutcome.EXECUTION_INTERRUPTED
            except Exception:
                return WorkerCycleOutcome.EXECUTION_INTERRUPTED
            try:
                model_reservation = await self._coordinator.reserve_model_call(
                    self._fleet_spec.fleet_budget,
                    self._fleet_state.usage,
                    self._target_spec.budget,
                    self._target_state.usage,
                    input_tokens=input_tokens,
                    requested_output_tokens=output_tokens,
                )
            except _BudgetStop as stop:
                return self._outcome_for_budget_stop(stop.scope)

        return WorkerCycleOutcome.EXECUTION_INTERRUPTED

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
        self._require_model_headroom(input_tokens, output_tokens)
        if input_tokens > self._profile.initial_provider_input_hard_cap_tokens:
            raise WorkerCyclePreflightError(
                "complete initial provider request exceeds the Stage 3 hard cap"
            )
        return request, input_tokens, output_tokens

    def _next_request(self) -> tuple[LLMRequest, int, int]:
        request, input_tokens, output_tokens = self._build_request(initial=False)
        self._require_model_headroom(input_tokens, output_tokens)
        return request, input_tokens, output_tokens

    def _build_request(self, *, initial: bool) -> tuple[LLMRequest, int, int]:
        while True:
            messages = [LLMMessage.system(self._canonical_base)]
            if not initial:
                messages.append(LLMMessage.user(self._execution_overlay()))
            messages.extend(self._working_set.messages())
            request = LLMRequest(
                operation=LLMOperation.MEMORY_AGENT_WORKER,
                profile=self._profile.profile_id,
                messages=messages,
                tools=self._tools.definitions,
                tool_choice="required",
                max_output_tokens=max(1, self._profile.reserved_response_tokens),
                metadata={
                    "run_id": self._fleet_spec.fleet_run_id,
                    "workflow_id": self._target_spec.target_task_id,
                },
            )
            serialized = _serialize_request(request)
            input_tokens = self._manager.count_text(serialized)
            output_tokens = self._maximum_output_tokens(input_tokens)
            diagnostics = self._manager.inspect_request(
                serialized,
                reserved_response_tokens=output_tokens,
            )
            if diagnostics.within_context_limit:
                return (
                    request.model_copy(update={"max_output_tokens": output_tokens}),
                    diagnostics.current_request_input_tokens,
                    output_tokens,
                )
            if initial or not self._working_set.evict_one_for_context_pressure():
                raise _ContextCapacityStop("minimum valid worker request cannot fit")

    def _maximum_output_tokens(self, input_tokens: int) -> int:
        maximum = self._profile.reserved_response_tokens
        if maximum < 1:
            raise WorkerCyclePreflightError(
                "worker profile must reserve positive Stage 4 response capacity"
            )
        maximum = min(
            maximum,
            self._profile.model_context_window_tokens - input_tokens,
        )
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

    def _require_model_headroom(
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
            self._target_state.usage.input_tokens + input_tokens
            > self._target_spec.budget.max_input_tokens
        ):
            raise _BudgetStop(_BudgetScope.TARGET)
        if self._fleet_spec.fleet_budget.max_input_tokens is not None and (
            self._fleet_state.usage.input_tokens + input_tokens
            > self._fleet_spec.fleet_budget.max_input_tokens
        ):
            raise _BudgetStop(_BudgetScope.FLEET)
        if output_tokens < 1:
            raise _BudgetStop(_BudgetScope.TARGET)

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
            usage.input_tokens,
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


def _finalization_protocol_error(call: LLMToolCall) -> LLMToolResult:
    reason = (
        "request_finalization must have no arguments"
        if call.arguments
        else "request_finalization must be the sole call in its response"
    )
    return LLMToolResult(
        call_id=call.id,
        name=call.name,
        error=LLMToolError(code="protocol_error", message=reason),
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
        maximum_message_chars = max(1, maximum_bytes // 2)
        return result.model_copy(
            update={
                "error": result.error.model_copy(
                    update={"message": result.error.message[:maximum_message_chars]}
                )
            }
        )
    prefix = serialized[:maximum_bytes].decode("utf-8", errors="ignore")
    output: JsonValue = {
        "truncated": True,
        "original_bytes": len(serialized),
        "serialized_prefix": prefix,
        "instruction": "Retrieve a narrower range or smaller result set.",
    }
    return result.model_copy(update={"output": output})


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


def _serialize_messages(messages: list[LLMMessage]) -> str:
    return orjson.dumps(
        [message.model_dump(mode="json") for message in messages],
        option=orjson.OPT_SORT_KEYS,
    ).decode()


def _json_default(value: object) -> object:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    raise TypeError(f"cannot serialize {type(value).__name__}")


__all__ = [
    "FleetExecutionCoordinator",
    "WorkerCycleOutcome",
    "WorkerRunner",
    "WorkerRuntimeLimits",
]
