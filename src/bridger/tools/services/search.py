from __future__ import annotations

import re

from bridger.tools.errors import BridgerToolError
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.cursors import CursorService
from bridger.tools.services.file_index import FileIndexService


class SearchService:
    def __init__(
        self,
        repo_root: object,
        files: FileIndexService,
        budgets: BudgetService,
        cursors: CursorService,
    ) -> None:
        self.files, self.budgets, self.cursors = files, budgets, cursors

    def search_with_context(
        self,
        query: str,
        *,
        match_mode: str = "literal",
        case_sensitive: bool = False,
        path_prefix: str | None = None,
        file_pattern: str | None = None,
        before: int = 3,
        after: int = 3,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, object]:
        if not query:
            raise BridgerToolError("invalid_arguments", "query must not be empty")
        if match_mode not in {"literal", "regex"}:
            raise BridgerToolError(
                "invalid_arguments", "match_mode must be literal or regex"
            )
        if (
            limit < 1
            or limit > 100
            or before < 0
            or before > 20
            or after < 0
            or after > 20
        ):
            raise BridgerToolError(
                "result_limit_exceeded", "Requested context exceeds the tool limits"
            )
        try:
            expression = re.compile(
                query if match_mode == "regex" else re.escape(query),
                0 if case_sensitive else re.IGNORECASE,
            )
        except re.error as error:
            raise BridgerToolError(
                "invalid_regex", "Regex query is invalid", {"reason": str(error)}
            ) from None
        prefix = self.files.paths.validate_prefix(path_prefix)
        all_matches: list[dict[str, object]] = []
        skipped: dict[str, int] = {"binary": 0, "restricted": 0}
        for item in sorted(self.files.artifact.files, key=lambda value: value.path):
            if prefix and not (
                item.path == prefix or item.path.startswith(f"{prefix}/")
            ):
                continue
            if file_pattern and not __import__("fnmatch").fnmatch.fnmatch(
                item.path, file_pattern
            ):
                continue
            if item.is_binary:
                skipped["binary"] += 1
                continue
            if item.read_policy.value != "readable":
                skipped["restricted"] += 1
                continue
            try:
                lines = (
                    self.files.paths.resolve_for_read(item.path)
                    .read_text(encoding=item.detected_encoding)
                    .splitlines()
                )
            except (BridgerToolError, LookupError, OSError, UnicodeError):
                skipped["restricted"] += 1
                continue
            for number, text in enumerate(lines, 1):
                match = expression.search(text)
                if match:
                    all_matches.append(
                        {
                            "path": item.path,
                            "match_line": number,
                            "match_column": match.start() + 1,
                            "matched_text": match.group(0),
                            "_lines": lines,
                        }
                    )
        filters = {
            "query": query,
            "match_mode": match_mode,
            "case_sensitive": case_sensitive,
            "path_prefix": prefix,
            "file_pattern": file_pattern,
            "before": before,
            "after": after,
        }
        start = 0
        if cursor:
            key = self.cursors.decode(cursor, "search_with_context", filters)
            for index, value in enumerate(all_matches):
                if [value["path"], value["match_line"], value["match_column"]] == key:
                    start = index + 1
                    break
            else:
                raise BridgerToolError(
                    "invalid_cursor", "Cursor does not identify a result"
                )
        page = all_matches[start : start + limit]
        result: list[dict[str, object]] = []
        returned_lines = 0
        for item in page:
            lines = item.pop("_lines")
            line = int(item["match_line"])
            range_start, range_end = (
                max(1, line - before),
                min(len(lines), line + after),
            )
            count = range_end - range_start + 1
            if returned_lines + count > 600:
                break
            returned_lines += count
            result.append(
                {
                    **item,
                    "context_range": {"line_start": range_start, "line_end": range_end},
                    "content": "\n".join(lines[range_start - 1 : range_end]),
                }
            )
        has_more = start + len(result) < len(all_matches)
        next_cursor = (
            self.cursors.encode(
                "search_with_context",
                filters,
                [
                    result[-1]["path"],
                    result[-1]["match_line"],
                    result[-1]["match_column"],
                ],
            )
            if has_more and result
            else None
        )
        return {
            "status": "completed",
            "results": result,
            "total_available": len(all_matches),
            "returned_count": len(result),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "truncated": has_more,
            "omitted_count": len(all_matches) - start - len(result),
            "omitted_reasons": ["result_limit"] if has_more else [],
            "warnings": [
                f"skipped_binary_files={skipped['binary']}",
                f"skipped_restricted_files={skipped['restricted']}",
            ],
        }
