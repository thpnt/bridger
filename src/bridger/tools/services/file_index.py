from bridger.models.file_index import FileIndexArtifact, IndexedFile
from bridger.tools.errors import BridgerToolError
from bridger.tools.models import FileFilters
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.path_safety import PathSafetyService


class FileIndexService:
    def __init__(
        self,
        artifact: FileIndexArtifact,
        paths: PathSafetyService,
        budgets: BudgetService,
    ) -> None:
        self.artifact = artifact
        self.paths = paths
        self.budgets = budgets
        self._files = {item.path: item for item in artifact.files}

    def get_file(self, path: str) -> IndexedFile:
        return self._files[self.paths.validate_file(path)]

    def list_files(self, filters: FileFilters) -> dict[str, object]:
        prefix = self.paths.validate_prefix(filters.path_prefix)
        matches = [
            item
            for item in self.artifact.files
            if (
                prefix is None
                or item.path == prefix
                or item.path.startswith(f"{prefix}/")
            )
            and (filters.extension is None or item.extension == filters.extension)
        ]
        matches.sort(key=lambda item: item.path)
        limit = self.budgets.file_limit(filters.limit)
        return self._limited_files(matches, limit)

    def search_paths(self, query: str, limit: int | None = None) -> dict[str, object]:
        if not query.strip():
            raise BridgerToolError("invalid_argument", "Search query must not be empty")
        lowered = query.casefold()
        matches = [
            item for item in self.artifact.files if lowered in item.path.casefold()
        ]
        matches.sort(key=lambda item: item.path)
        return self._limited_files(matches, self.budgets.file_limit(limit))

    def validate_paths(self, paths: list[str]) -> dict[str, object]:
        results: list[dict[str, object]] = []
        for path in paths:
            try:
                normalized = self.paths.validate_file(path)
            except BridgerToolError as error:
                results.append(
                    {
                        "path": path,
                        "valid": False,
                        "error": error.payload.error,
                        "message": error.payload.message,
                    }
                )
            else:
                results.append({"path": normalized, "valid": True})
        return {"source_artifact": "file-index.json", "results": results}

    def list_tree(
        self, path_prefix: str | None, depth: int, limit: int | None
    ) -> dict[str, object]:
        prefix = self.paths.validate_prefix(path_prefix)
        entries: dict[str, str] = {}
        prefix_parts = prefix.split("/") if prefix else []
        for path in self._files:
            parts = path.split("/")
            if prefix and not (path == prefix or path.startswith(f"{prefix}/")):
                continue
            relative = parts[len(prefix_parts) :]
            if not relative:
                entries[path] = "file"
                continue
            visible = relative[:depth]
            for index in range(1, len(visible) + 1):
                entry_parts = prefix_parts + visible[:index]
                entry = "/".join(entry_parts)
                is_file = index == len(relative) and path == entry
                entries[entry] = "file" if is_file else "directory"
        ordered = [{"path": path, "kind": entries[path]} for path in sorted(entries)]
        applied = self.budgets.file_limit(limit)
        return {
            "source_artifact": "file-index.json",
            "path_prefix": prefix,
            "entries": ordered[:applied],
            "total_matches": len(ordered),
            "limit_applied": applied,
            "truncated": len(ordered) > applied,
        }

    def _limited_files(
        self, matches: list[IndexedFile], limit: int
    ) -> dict[str, object]:
        return {
            "source_artifact": "file-index.json",
            "files": [item.model_dump(mode="json") for item in matches[:limit]],
            "total_matches": len(matches),
            "limit_applied": limit,
            "truncated": len(matches) > limit,
        }
