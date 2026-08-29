"""Explicit failures raised by Layer 1 repository operations."""

from bridger.contracts.files import FileIndexPath


class RepositoryError(RuntimeError):
    """A Git repository source or controlled-read operation failed."""


class FileIndexPathMismatchError(RepositoryError):
    """An exact path is absent from the pinned FileIndex."""

    def __init__(
        self,
        requested_path: str,
        closest_valid_paths: tuple[FileIndexPath, ...],
    ) -> None:
        super().__init__("Repository path is absent from the pinned FileIndex.")
        self.requested_path = requested_path
        self.closest_valid_paths = closest_valid_paths


class SourceReadDeniedError(RepositoryError):
    """A FileDisposition does not permit the requested source read."""
