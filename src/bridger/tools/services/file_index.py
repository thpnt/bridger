from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath

from bridger.models.file_index import FileIndexArtifact, IndexedFile
from bridger.tools.errors import BridgerToolError
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.cursors import CursorService
from bridger.tools.services.file_roles import classify_file_roles
from bridger.tools.services.path_safety import PathSafetyService


class FileIndexService:
    def __init__(
        self,
        artifact: FileIndexArtifact,
        paths: PathSafetyService,
        budgets: BudgetService,
        cursors: CursorService | None = None,
    ) -> None:
        self.artifact = artifact
        self.paths = paths
        self.budgets = budgets
        self.cursors = cursors or CursorService("file-index")
        self._files = {item.path: item for item in artifact.files}

    def get_file(self, path: str) -> IndexedFile:
        return self._files[self.paths.validate_file(path)]

    def list_files(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        extension: str | None = None,
        role: str | None = None,
        recursive: bool = False,
        max_depth: int = 1,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, object]:
        if limit > 500 or limit < 1:
            raise BridgerToolError(
                "result_limit_exceeded", "limit must be between 1 and 500"
            )
        if max_depth < 0 or max_depth > 8:
            raise BridgerToolError(
                "invalid_arguments", "max_depth must be between 0 and 8"
            )
        if role is not None and role not in {
            "manifest",
            "documentation",
            "instruction",
            "configuration",
            "test",
            "ci",
            "source",
        }:
            raise BridgerToolError("invalid_arguments", f"Unknown file role: {role}")
        normalized = self.paths.validate_prefix(prefix)
        extension_value = self._normalise_extension(extension)
        filters = {
            "prefix": normalized,
            "pattern": pattern,
            "extension": extension_value,
            "role": role,
            "recursive": recursive,
            "max_depth": max_depth,
        }
        entries = self._entries(normalized, recursive, max_depth)
        matches = [
            entry
            for entry in entries
            if (pattern is None or fnmatch(entry["path"], pattern))
            and (extension_value is None or entry.get("extension") == extension_value)
            and (role is None or role in entry.get("roles", []))
        ]
        matches.sort(key=lambda entry: str(entry["path"]))
        start = self._cursor_index(cursor, "list_files", filters, matches)
        page = matches[start : start + limit]
        has_more = start + len(page) < len(matches)
        return self._page(
            "list_files", filters, matches, page, start, has_more, "files"
        )

    def validate_paths(self, paths: list[str]) -> dict[str, object]:
        if len(paths) > 500:
            raise BridgerToolError(
                "result_limit_exceeded", "At most 500 paths are allowed"
            )
        results: list[dict[str, object]] = []
        for path in paths:
            try:
                normalized = self.paths.normalize(path)
            except BridgerToolError:
                results.append(self._path_result(path, "outside_repository"))
                continue
            file = self._files.get(normalized)
            if file is not None:
                status = (
                    "binary"
                    if file.is_binary
                    else (
                        "metadata_only"
                        if file.read_policy.value == "metadata_only"
                        else "valid_file"
                    )
                )
                results.append(self._path_result(normalized, status, file))
                continue
            if normalized in self.paths.skipped_paths:
                reason = self.paths.skipped_paths[normalized]
                status = "sensitive" if reason == "sensitive_file" else "excluded"
                results.append(self._path_result(normalized, status, reason=reason))
                continue
            if self.paths.is_prefix(normalized):
                results.append(self._path_result(normalized, "valid_directory_prefix"))
                continue
            results.append(self._path_result(normalized, "missing"))
        return self._common({"results": results}, len(results), len(results))

    def _entries(
        self, prefix: str | None, recursive: bool, max_depth: int
    ) -> list[dict[str, object]]:
        entries: dict[str, dict[str, object]] = {}
        base = prefix.split("/") if prefix else []
        for item in self.artifact.files:
            if prefix and not (
                item.path == prefix or item.path.startswith(f"{prefix}/")
            ):
                continue
            relative = item.path.split("/")[len(base) :]
            if not relative:
                entries[item.path] = self._file_item(item)
                continue
            visible_depth = (
                len(relative) if recursive else min(len(relative), max_depth)
            )
            if recursive:
                visible_depth = min(visible_depth, max_depth) if max_depth else 0
            if not recursive and len(relative) > max_depth:
                visible_depth = max_depth
            if visible_depth == 0:
                continue
            for depth in range(1, visible_depth + 1):
                candidate = "/".join([*base, *relative[:depth]])
                is_file = depth == len(relative)
                if is_file:
                    entries[candidate] = self._file_item(item)
                else:
                    entries.setdefault(candidate, self._directory_item(candidate))
        return list(entries.values())

    def _file_item(self, item: IndexedFile) -> dict[str, object]:
        return {
            "path": item.path,
            "kind": "file",
            "size_bytes": item.size_bytes,
            "line_count": item.line_count,
            "language": self._language(item.path),
            "content_kind": item.content_type.value,
            "roles": classify_file_roles(item.path),
            "read_policy": item.read_policy.value,
            "git_tracked": True,
            "extension": item.extension,
        }

    @staticmethod
    def _directory_item(path: str) -> dict[str, object]:
        return {
            "path": path,
            "kind": "directory_prefix",
            "roles": [],
            "git_tracked": True,
        }

    def _cursor_index(
        self,
        cursor: str | None,
        tool: str,
        filters: dict[str, object],
        items: list[dict[str, object]],
    ) -> int:
        if cursor is None:
            return 0
        key = self.cursors.decode(cursor, tool, filters)
        if len(key) != 1 or not isinstance(key[0], str):
            raise BridgerToolError("invalid_cursor", "Cursor ordering key is invalid")
        for index, item in enumerate(items):
            if item["path"] == key[0]:
                return index + 1
        raise BridgerToolError("invalid_cursor", "Cursor does not identify a result")

    def _page(
        self,
        tool: str,
        filters: dict[str, object],
        all_items: list[dict[str, object]],
        page: list[dict[str, object]],
        start: int,
        has_more: bool,
        key: str,
    ) -> dict[str, object]:
        next_cursor = (
            self.cursors.encode(tool, filters, [page[-1]["path"]])
            if has_more and page
            else None
        )
        return self._common(
            {
                key: page,
                "has_more": has_more,
                "next_cursor": next_cursor,
                "truncated": has_more,
                "omitted_count": len(all_items) - start - len(page),
                "omitted_reasons": ["result_limit"] if has_more else [],
            },
            len(all_items),
            len(page),
        )

    @staticmethod
    def _common(
        output: dict[str, object], total: int, returned: int
    ) -> dict[str, object]:
        return {
            "status": "completed",
            "source_artifact": "file-index.json",
            "total_available": total,
            "returned_count": returned,
            "has_more": output.get("has_more", False),
            "next_cursor": output.get("next_cursor"),
            "truncated": output.get("truncated", False),
            "omitted_count": output.get("omitted_count", 0),
            "omitted_reasons": output.get("omitted_reasons", []),
            "warnings": [],
            **output,
        }

    @staticmethod
    def _normalise_extension(extension: str | None) -> str | None:
        if extension is None or extension == "":
            return None
        return extension if extension.startswith(".") else f".{extension}"

    @staticmethod
    def _language(path: str) -> str | None:
        return {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".php": "php",
        }.get(PurePosixPath(path).suffix)

    def _path_result(
        self,
        path: str,
        status: str,
        file: IndexedFile | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "path": path,
            "status": status,
            "exists_in_inventory": file is not None,
            "git_tracked": file is not None,
        }
        if file is not None:
            result.update(
                {
                    "content_kind": file.content_type.value,
                    "read_policy": file.read_policy.value,
                }
            )
        if reason is not None:
            result["reason"] = reason
        return result
