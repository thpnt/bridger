"""Narrow Layer 4 lifecycle errors."""


class FullRebuildRequired(RuntimeError):
    """Raised when an incremental snapshot cannot safely be produced."""


class InvalidGraphSnapshot(RuntimeError):
    """Raised when a staged or persisted graph snapshot fails validation."""
