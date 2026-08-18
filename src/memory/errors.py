"""Explicit deterministic memory-harness failures."""


class MemoryHarnessError(RuntimeError):
    """Base failure for deterministic memory-harness setup."""


class InvalidTargetArtifacts(MemoryHarnessError):
    """A static target catalog bundle violates its locked contract."""


class TargetActivationError(MemoryHarnessError):
    """Deterministic target activation could not be resolved."""


class MemoryRunBindingError(MemoryHarnessError):
    """Stage 0 could not produce and persist a valid fleet specification."""


class FleetInitializationError(MemoryHarnessError):
    """Stage 1 could not atomically expose an initialized fleet."""


class FleetSchedulingError(MemoryHarnessError):
    """Stage 2 received invalid or inconsistent authoritative state."""


class WorkerContextInvocationError(MemoryHarnessError):
    """Stage 3 was invoked for a task that cannot legally enter hydration."""


class WorkerContextHydrationError(MemoryHarnessError):
    """Stage 3 encountered invalid configuration or authoritative state."""


class ContextWindowConfigurationError(WorkerContextHydrationError):
    """The V0 tokenizer or model context-window configuration is invalid."""


class WorkerCycleInvocationError(MemoryHarnessError):
    """Stage 4 was invoked outside its locked hydration boundary."""


class WorkerCyclePreflightError(MemoryHarnessError):
    """Stage 4 could not safely begin actual worker execution."""


__all__ = [
    "ContextWindowConfigurationError",
    "FleetInitializationError",
    "FleetSchedulingError",
    "InvalidTargetArtifacts",
    "MemoryHarnessError",
    "MemoryRunBindingError",
    "TargetActivationError",
    "WorkerContextHydrationError",
    "WorkerContextInvocationError",
    "WorkerCycleInvocationError",
    "WorkerCyclePreflightError",
]
