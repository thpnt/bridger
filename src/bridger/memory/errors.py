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


class PersistenceRecoveryError(MemoryHarnessError):
    """Stage 5 could not safely persist or recover authoritative state."""


class FinalizationRequestError(MemoryHarnessError):
    """Stage 6 could not create or resolve a coherent candidate submission."""


class TargetReviewError(MemoryHarnessError):
    """Stage 8 could not compile, execute, or persist a coherent review."""


class TargetReviewInvocationError(TargetReviewError):
    """Stage 8 was invoked outside its exact validated-candidate boundary."""


class TargetReviewBudgetError(TargetReviewError):
    """A target or fleet execution budget prevents the reviewer call."""

    def __init__(self, scope: str) -> None:
        super().__init__(f"{scope} budget prevents target review")
        self.scope = scope


class TargetAcceptanceError(MemoryHarnessError):
    """Stage 10 could not establish or persist coherent local acceptance."""


class FleetValidationError(MemoryHarnessError):
    """Stage 11 was invoked outside its fleet-validation admission boundary."""


class FleetReviewError(MemoryHarnessError):
    """Stage 12 could not compile, execute, or persist a coherent review."""


class FleetReviewInvocationError(FleetReviewError):
    """Stage 12 was invoked outside its exact Stage 11 PASS boundary."""


class FleetReviewBudgetError(FleetReviewError):
    """The fleet execution budget prevents a reconciliation call."""

    def __init__(self, scope: str) -> None:
        super().__init__(f"{scope} budget prevents fleet review")
        self.scope = scope


class FleetAcceptanceError(MemoryHarnessError):
    """Stage 13 could not establish coherent final fleet acceptance."""


__all__ = [
    "ContextWindowConfigurationError",
    "FleetInitializationError",
    "FleetSchedulingError",
    "FleetValidationError",
    "FleetAcceptanceError",
    "FleetReviewBudgetError",
    "FleetReviewError",
    "FleetReviewInvocationError",
    "FinalizationRequestError",
    "InvalidTargetArtifacts",
    "MemoryHarnessError",
    "MemoryRunBindingError",
    "PersistenceRecoveryError",
    "TargetActivationError",
    "TargetAcceptanceError",
    "TargetReviewBudgetError",
    "TargetReviewError",
    "TargetReviewInvocationError",
    "WorkerContextHydrationError",
    "WorkerContextInvocationError",
    "WorkerCycleInvocationError",
    "WorkerCyclePreflightError",
]
