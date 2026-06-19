from pathlib import Path

from bridger.tools.errors import BridgerToolError
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.file_index import FileIndexService
from bridger.tools.services.path_safety import PathSafetyService


class FileReadService:
    def __init__(
        self,
        repo_root: Path,
        paths: PathSafetyService,
        files: FileIndexService,
        budgets: BudgetService,
    ) -> None:
        self.repo_root = repo_root
        self.paths = paths
        self.files = files
        self.budgets = budgets

    def read_excerpt(
        self, path: str, start_line: int | None = None, end_line: int | None = None
    ) -> dict[str, object]:
        normalized = self.paths.validate_file(path)
        metadata = self.files.get_file(normalized)
        start = start_line or 1
        requested_end = end_line or metadata.line_count
        if start < 1 or requested_end < start:
            raise BridgerToolError(
                "invalid_argument",
                "Line range must be 1-based with end_line >= start_line",
            )
        if start > metadata.line_count:
            raise BridgerToolError(
                "invalid_argument",
                f"start_line exceeds file line count ({metadata.line_count})",
            )
        maximum_end = start + self.budgets.values.max_file_excerpt_lines - 1
        actual_end = min(requested_end, maximum_end, metadata.line_count)
        try:
            lines = (
                self.paths.resolve_for_read(normalized)
                .read_text(encoding=metadata.detected_encoding)
                .splitlines()
            )
        except (LookupError, OSError, UnicodeError) as error:
            raise BridgerToolError(
                "file_read_error", f"Could not read indexed file: {normalized}"
            ) from error
        content = "\n".join(lines[start - 1 : actual_end])
        return {
            "source_artifact": "file-index.json",
            "path": normalized,
            "line_start": start,
            "line_end": actual_end,
            "content": content,
            "requested_end_line": requested_end,
            "limit_applied": self.budgets.values.max_file_excerpt_lines,
            "truncated": actual_end < min(requested_end, metadata.line_count),
        }
