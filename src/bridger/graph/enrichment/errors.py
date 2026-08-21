"""Narrow Layer 5 validation and lifecycle errors."""


class InvalidGraphEnrichment(RuntimeError):
    """Raised when an enrichment overlay violates its locked contract."""


__all__ = ["InvalidGraphEnrichment"]
