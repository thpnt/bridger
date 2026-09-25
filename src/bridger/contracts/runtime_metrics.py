"""Persisted, payload-free timing report for one init invocation."""

from pydantic import BaseModel, ConfigDict, Field


class TimedOperation(BaseModel):
    name: str
    started_at: str
    ended_at: str
    duration_ms: float
    status: str
    target_task_id: str | None = None
    cycle_id: str | None = None
    cycle_number: int | None = None
    mode: str | None = None
    repair: bool | None = None
    outcome: str | None = None


class ModelCall(BaseModel):
    operation: str
    role: str
    target_task_id: str | None = None
    cycle_id: str | None = None
    provider: str
    model: str
    reasoning_effort: str | None = None
    started_at: str
    duration_ms: float
    status: str
    attempt: int
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None


class ToolCall(BaseModel):
    target_task_id: str
    cycle_id: str | None = None
    tool: str
    call_id: str
    started_at: str
    duration_ms: float
    status: str
    result_bytes: int | None = None
    truncated: bool | None = None


class CycleMetrics(BaseModel):
    cycle_number: int
    cycle_id: str | None = None
    duration_ms: float
    outcome: str
    mode: str | None = None
    repair: bool
    context_hydration_ms: float
    model_wait_ms: float
    tool_wait_ms: float
    retry_backoff_ms: float
    other_harness_ms: float


class TargetMetrics(BaseModel):
    target_task_id: str
    target_id: str
    first_execution_started_at: str | None = None
    accepted_at: str | None = None
    elapsed_ms: float | None = None
    active_step_ms: float = 0
    cycles: list[CycleMetrics] = Field(default_factory=list)
    repair_cycles: int = 0
    hydration_ms: float = 0
    worker_cycle_ms: float = 0
    model_wait_ms: float = 0
    retry_backoff_ms: float = 0
    tool_wait_ms: float = 0
    validation_attempts: int = 0
    validation_time_ms: float = 0
    review_attempts: int = 0
    review_time_ms: float = 0
    time_to_first_finalization_ms: float | None = None
    time_to_acceptance_ms: float | None = None
    repair_penalty_ms: float | None = None


class BatchStep(BaseModel):
    target_task_id: str
    duration_ms: float
    outcome: str
    barrier_wait_ms: float


class BatchMetrics(BaseModel):
    batch_id: str
    started_at: str
    duration_ms: float
    target_steps: list[BatchStep]
    slowest_target: str | None = None
    straggler_extension_ms: float = 0


class RuntimeMetricsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    init_run_id: str
    fleet_run_id: str | None = None
    repository_id: str | None = None
    repository_revision: str | None = None
    mode: str
    fresh: bool
    reused: bool
    resumed: bool
    model: str | None = None
    reasoning_effort: str
    model_profile: str
    started_at: str
    finished_at: str
    status: str
    failed_stage: str | None = None
    total_duration_ms: float
    deterministic_total_ms: float
    model_driven_total_ms: float
    stages: list[TimedOperation]
    targets: list[TargetMetrics]
    model_calls: list[ModelCall]
    model_provider_wait_ms: float
    retry_backoff_ms: float
    total_model_wait_ms: float
    model_wall_ms: float = 0
    retry_backoff_wall_ms: float = 0
    model_by_role: dict[str, dict[str, float]]
    tool_calls: list[ToolCall]
    total_tool_wait_ms: float
    tool_wall_ms: float = 0
    tool_by_name: dict[str, dict[str, float]]
    batches: list[BatchMetrics]
    configured_concurrency: int | None = None
    fleet_wall_time_ms: float = 0
    target_execution_wall_ms: float = 0
    total_target_work_ms: float = 0
    average_active_targets: float = 0
    effective_parallel_speedup: float = 0
    concurrency_utilization: float = 0
    total_barrier_wait_ms: float = 0
    fleet_validation_ms: float = 0
    fleet_reconciliation_ms: float = 0
    checkpoint_ms: float = 0
    token_report_persistence_ms: float = 0
    brain_publication_ms: float = 0
    brain_index_ms: float = 0
    validation_and_review_ms: float = 0
    validation_review_wall_ms: float = 0
    critical_path_ms: float = 0
    critical_path_steps: list[str] = Field(default_factory=list)
    critical_path_target_ids: list[str] = Field(default_factory=list)
    other_harness_ms: float = 0
