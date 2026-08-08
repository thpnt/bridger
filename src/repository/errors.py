"""Explicit failures raised by Layer 1 repository operations."""


class RepositoryError(RuntimeError):
    """A Git repository source or controlled-read operation failed."""


class SourceReadDeniedError(RepositoryError):
    """A FileDisposition does not permit the requested source read."""
