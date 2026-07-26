from pathlib import Path, PurePosixPath

from bridger.models.file_index import FileIndexArtifact, ReadPolicy
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
        self._read_policies = {
            item.path: (item.read_policy, item.read_policy_reason)
            for item in file_index.files
        }

    @property
    def safe_paths(self) -> frozenset[str]:
        return frozenset(self._safe_paths)

    @property
    def skipped_paths(self) -> dict[str, str]:
        return dict(self._skipped_paths)

    def is_prefix(self, path: str) -> bool:
        return any(item.startswith(f"{path}/") for item in self._safe_paths)

    def normalize(self, path: str) -> str:
        if not path:
            raise BridgerToolError("invalid_arguments", "Path must not be empty")
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or "\\" in path:
            raise BridgerToolError(
                "path_outside_repository",
                "Path must be repository-relative and stay in the repo",
            )
        normalized = parsed.as_posix()
        if normalized in {"", "."}:
            raise BridgerToolError("invalid_arguments", "A file path is required")
        return normalized

    def validate_file(self, path: str) -> str:
        normalized = self.normalize(path)
        if normalized in self._skipped_paths:
            raise BridgerToolError(
                "path_excluded",
                f"Path is skipped by the file index: {normalized}",
                {"path": normalized, "skip_reason": self._skipped_paths[normalized]},
            )
        if normalized not in self._safe_paths:
            raise BridgerToolError(
                "path_not_found", f"Path is not in the Git file inventory: {normalized}"
            )
        return normalized

    def validate_prefix(self, prefix: str | None) -> str | None:
        if prefix is None or prefix == "":
            return None
        normalized = self.normalize(prefix).rstrip("/")
        if normalized in self._skipped_paths:
            raise BridgerToolError(
                "path_excluded", f"Path prefix is excluded: {normalized}"
            )
        has_match = any(
            path == normalized or path.startswith(f"{normalized}/")
            for path in self._safe_paths
        )
        if not has_match:
            raise BridgerToolError(
                "path_not_found",
                f"Path prefix has no files in the Git inventory: {normalized}",
            )
        return normalized

    def resolve_for_read(self, path: str) -> Path:
        normalized = self.validate_file(path)
        read_policy, reason = self._read_policies[normalized]
        if read_policy is not ReadPolicy.READABLE:
            reason_text = reason.value if reason is not None else read_policy.value
            raise BridgerToolError(
                "content_restricted",
                f"Path is metadata-only in the file index: {normalized}",
                {
                    "path": normalized,
                    "read_policy": read_policy.value,
                    "reason": reason_text,
                },
            )
        if self.repo_root is None:
            raise BridgerToolError(
                "artifact_unavailable",
                "Repository root is required for safe file reading",
            )
        candidate = (self.repo_root / normalized).resolve()
        if not candidate.is_relative_to(self.repo_root):
            raise BridgerToolError(
                "path_outside_repository",
                f"Indexed path resolves outside the repo: {normalized}",
            )
        return candidate
