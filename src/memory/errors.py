"""Explicit Stage 0-2 memory-harness failures."""


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


__all__ = [
    "FleetInitializationError",
    "FleetSchedulingError",
    "InvalidTargetArtifacts",
    "MemoryHarnessError",
    "MemoryRunBindingError",
    "TargetActivationError",
]
