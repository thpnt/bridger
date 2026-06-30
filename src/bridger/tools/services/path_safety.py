from pathlib import Path, PurePosixPath

from bridger.models.file_index import FileIndexArtifact
from bridger.tools.errors import BridgerToolError


class PathSafetyService:
    def __init__(
        self, file_index: FileIndexArtifact, repo_root: Path | None = None
    ) -> None:
        self.repo_root = repo_root.resolve() if repo_root is not None else None
        self._safe_paths = {item.path for item in file_index.files}
        self._skipped_paths = {
            item.path: item.skip_reason.value for item in file_index.skipped_files
        }

    @property
    def safe_paths(self) -> frozenset[str]:
        return frozenset(self._safe_paths)

    def normalize(self, path: str) -> str:
        if not path:
            raise BridgerToolError("invalid_path", "Path must not be empty")
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or "\\" in path:
            raise BridgerToolError(
                "invalid_path", "Path must be repository-relative and stay in the repo"
            )
        normalized = parsed.as_posix()
        if normalized in {"", "."}:
            raise BridgerToolError("invalid_path", "A file path is required")
        return normalized

    def validate_file(self, path: str) -> str:
        normalized = self.normalize(path)
        if normalized in self._skipped_paths:
            raise BridgerToolError(
                "path_skipped",
                f"Path is skipped by the file index: {normalized}",
                {"path": normalized, "skip_reason": self._skipped_paths[normalized]},
            )
        if normalized not in self._safe_paths:
            raise BridgerToolError(
                "path_not_indexed", f"Path is not in the safe file index: {normalized}"
            )
        return normalized

    def validate_prefix(self, prefix: str | None) -> str | None:
        if prefix is None or prefix == "":
            return None
        normalized = self.normalize(prefix).rstrip("/")
        if normalized in self._skipped_paths:
            raise BridgerToolError(
                "path_skipped", f"Path prefix is skipped: {normalized}"
            )
        has_match = any(
            path == normalized or path.startswith(f"{normalized}/")
            for path in self._safe_paths
        )
        if not has_match:
            raise BridgerToolError(
                "path_not_indexed",
                f"Path prefix has no files in the safe index: {normalized}",
            )
        return normalized

    def resolve_for_read(self, path: str) -> Path:
        normalized = self.validate_file(path)
        if self.repo_root is None:
            raise BridgerToolError(
                "invalid_path", "Repository root is required for safe file reading"
            )
        candidate = (self.repo_root / normalized).resolve()
        if not candidate.is_relative_to(self.repo_root):
            raise BridgerToolError(
                "invalid_path", f"Indexed path resolves outside the repo: {normalized}"
            )
        return candidate
