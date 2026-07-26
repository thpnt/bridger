from __future__ import annotations

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

    def read_ranges(self, path: str, ranges: list[dict[str, int]]) -> dict[str, object]:
        if not ranges or len(ranges) > 10:
            raise BridgerToolError(
                "range_limit_exceeded", "Provide between 1 and 10 inclusive line ranges"
            )
        metadata = self.files.get_file(path)
        normalized: list[tuple[int, int]] = []
        requested_total = 0
        for value in ranges:
            start, end = value.get("line_start"), value.get("line_end")
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or start < 1
                or end < start
                or end > metadata.line_count
            ):
                raise BridgerToolError(
                    "invalid_range",
                    "Ranges are inclusive, 1-based, and must fall within the file",
                    {"path": path, "file_total_lines": metadata.line_count},
                )
            if end - start + 1 > 300:
                raise BridgerToolError(
                    "range_limit_exceeded", "A single range may not exceed 300 lines"
                )
            requested_total += end - start + 1
            normalized.append((start, end))
        if requested_total > 800:
            raise BridgerToolError(
                "range_limit_exceeded",
                "Combined requested ranges may not exceed 800 lines",
                {"requested_total_lines": requested_total, "maximum_total_lines": 800},
            )
        merged = self._merge(normalized)
        lines = self._lines(path)
        content_ranges = [
            {
                "line_start": start,
                "line_end": end,
                "content": "\n".join(lines[start - 1 : end]),
            }
            for start, end in merged
        ]
        return self._result(path, metadata.line_count, content_ranges)

    def read_around(
        self, path: str, line: int, before: int = 20, after: int = 20
    ) -> dict[str, object]:
        metadata = self.files.get_file(path)
        if line < 1 or line > metadata.line_count:
            raise BridgerToolError(
                "invalid_range", "line must identify a line in the file"
            )
        if before < 0 or before > 100 or after < 0 or after > 100:
            raise BridgerToolError(
                "range_limit_exceeded", "before and after must be between 0 and 100"
            )
        start, end = max(1, line - before), min(metadata.line_count, line + after)
        if end - start + 1 > 250:
            raise BridgerToolError(
                "range_limit_exceeded", "The returned range may not exceed 250 lines"
            )
        lines = self._lines(path)
        return {
            **self._result(
                path,
                metadata.line_count,
                [
                    {
                        "line_start": start,
                        "line_end": end,
                        "content": "\n".join(lines[start - 1 : end]),
                    }
                ],
            ),
            "requested_anchor": line,
            "returned_range": {"line_start": start, "line_end": end},
            "clipped_at_start": start == 1 and line - before < 1,
            "clipped_at_end": end == metadata.line_count
            and line + after > metadata.line_count,
        }

    def read_symbol(
        self,
        path: str,
        declaration_start: int,
        declaration_end: int,
        context_lines: int,
        cursor: int | None = None,
    ) -> dict[str, object]:
        metadata = self.files.get_file(path)
        if context_lines < 0 or context_lines > 50:
            raise BridgerToolError(
                "invalid_arguments", "context_lines must be between 0 and 50"
            )
        start = max(1, declaration_start - context_lines)
        end = min(metadata.line_count, declaration_end + context_lines)
        page_start = cursor or start
        if page_start < start or page_start > end:
            raise BridgerToolError(
                "invalid_cursor", "Cursor is outside the symbol range"
            )
        page_end = min(end, page_start + 399)
        lines = self._lines(path)
        return {
            "returned_source_range": {"line_start": page_start, "line_end": page_end},
            "content": "\n".join(lines[page_start - 1 : page_end]),
            "has_more": page_end < end,
            "next_line": page_end + 1 if page_end < end else None,
            "truncated": page_end < end,
            "omitted_count": end - page_end,
            "omitted_reasons": ["symbol_page_limit"] if page_end < end else [],
            "warnings": [],
        }

    def _lines(self, path: str) -> list[str]:
        metadata = self.files.get_file(path)
        try:
            return (
                self.paths.resolve_for_read(path)
                .read_text(encoding=metadata.detected_encoding)
                .splitlines()
            )
        except BridgerToolError:
            raise
        except (LookupError, OSError, UnicodeError) as error:
            raise BridgerToolError(
                "content_restricted", f"Could not read indexed file: {path}"
            ) from error

    @staticmethod
    def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        result: list[tuple[int, int]] = []
        for start, end in sorted(ranges):
            if result and start <= result[-1][1] + 1:
                result[-1] = (result[-1][0], max(result[-1][1], end))
            else:
                result.append((start, end))
        return result

    @staticmethod
    def _result(
        path: str, total_lines: int, ranges: list[dict[str, object]]
    ) -> dict[str, object]:
        return {
            "status": "completed",
            "path": path,
            "file_total_lines": total_lines,
            "ranges": ranges,
            "total_available": len(ranges),
            "returned_count": len(ranges),
            "has_more": False,
            "next_cursor": None,
            "truncated": False,
            "omitted_count": 0,
            "omitted_reasons": [],
            "warnings": [],
        }
