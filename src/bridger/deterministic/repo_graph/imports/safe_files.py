from collections.abc import Iterable

from bridger.models.file_index import FileIndexArtifact, validate_repository_path


class SafeFileIndex:
    """Read-only path boundary backed exclusively by file-index.files."""

    def __init__(self, file_index: FileIndexArtifact) -> None:
        self._safe_paths = frozenset(file.path for file in file_index.files)

    @property
    def safe_paths(self) -> frozenset[str]:
        return self._safe_paths

    def contains(self, path: str) -> bool:
        validated_path = validate_repository_path(path)
        return validated_path in self._safe_paths

    def existing_candidates(self, paths: Iterable[str]) -> tuple[str, ...]:
        """Return existing candidates in stable repository-path order."""
        validated_paths = {validate_repository_path(path) for path in paths}
        return tuple(sorted(validated_paths & self._safe_paths))
