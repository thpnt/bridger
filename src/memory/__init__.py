"""Bridger memory-agent harness contracts and Stage 0-4 interfaces."""

from memory.context_window import ContextWindowManager
from memory.errors import (
    ContextWindowConfigurationError,
    FleetInitializationError,
    FleetSchedulingError,
    InvalidTargetArtifacts,
    MemoryHarnessError,
    MemoryRunBindingError,
    TargetActivationError,
    WorkerContextHydrationError,
    WorkerContextInvocationError,
    WorkerCycleInvocationError,
    WorkerCyclePreflightError,
)
from memory.hydration import (
    CandidateArtifactRecord,
    EvidenceRecord,
    FindingRecord,
    HydrationStateReader,
    OpenQuestionRecord,
    WorkerContextDebugSnapshot,
    WorkerContextDebugWriter,
    serialize_worker_context,
)
from memory.runtime import (
    ActivationRule,
    bind_memory_run,
    compile_worker_context,
    initialize_fleet,
    resolve_target_activation,
    run_worker_cycle,
    schedule_runnable_targets,
)
from memory.targets import load_target_artifacts
from memory.worker_cycle import (
    FleetExecutionCoordinator,
    WorkerCycleOutcome,
    WorkerRunner,
    WorkerRuntimeLimits,
)
from memory.worker_tools import (
    CompletionStateUpdater,
    EvidenceRecorder,
    ProgressUpdater,
    TargetWorkspace,
    WorkerToolRuntime,
)

__all__ = [
    "ActivationRule",
    "CandidateArtifactRecord",
    "ContextWindowConfigurationError",
    "ContextWindowManager",
    "EvidenceRecord",
    "FindingRecord",
    "FleetInitializationError",
    "FleetSchedulingError",
    "FleetExecutionCoordinator",
    "HydrationStateReader",
    "InvalidTargetArtifacts",
    "MemoryHarnessError",
    "MemoryRunBindingError",
    "OpenQuestionRecord",
    "TargetActivationError",
    "WorkerContextDebugSnapshot",
    "WorkerContextDebugWriter",
    "WorkerContextHydrationError",
    "WorkerContextInvocationError",
    "WorkerCycleInvocationError",
    "WorkerCycleOutcome",
    "WorkerCyclePreflightError",
    "WorkerRunner",
    "WorkerRuntimeLimits",
    "WorkerToolRuntime",
    "TargetWorkspace",
    "EvidenceRecorder",
    "CompletionStateUpdater",
    "ProgressUpdater",
    "bind_memory_run",
    "compile_worker_context",
    "initialize_fleet",
    "load_target_artifacts",
    "resolve_target_activation",
    "run_worker_cycle",
    "schedule_runnable_targets",
    "serialize_worker_context",
]
