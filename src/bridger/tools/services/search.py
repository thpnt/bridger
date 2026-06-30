from pathlib import Path

from bridger.tools.errors import BridgerToolError
from bridger.tools.models import GrepFilters
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.file_index import FileIndexService


class SearchService:
    def __init__(
        self, repo_root: Path, files: FileIndexService, budgets: BudgetService
    ) -> None:
        self.repo_root = repo_root
        self.files = files
        self.budgets = budgets

    def grep(self, query: str, filters: GrepFilters) -> dict[str, object]:
        if not query:
            raise BridgerToolError("invalid_argument", "Grep query must not be empty")
        prefix = self.files.paths.validate_prefix(filters.path_prefix)
        candidates = [
            item
            for item in self.files.artifact.files
            if (
                prefix is None
                or item.path == prefix
                or item.path.startswith(f"{prefix}/")
            )
            and (filters.extension is None or item.extension == filters.extension)
        ]
        results: list[dict[str, object]] = []
        total = 0
        limit = self.budgets.grep_limit(filters.limit)
        for item in candidates:
            path = item.path
            try:
                lines = (
                    self.files.paths.resolve_for_read(path)
                    .read_text(encoding=item.detected_encoding)
                    .splitlines()
                )
            except (BridgerToolError, LookupError, OSError, UnicodeError):
                continue
            for line_number, line in enumerate(lines, start=1):
                if query.casefold() not in line.casefold():
                    continue
                total += 1
                if len(results) < limit:
                    results.append(
                        {
                            "path": path,
                            "line_number": line_number,
                            "match": line.strip(),
                        }
                    )
        return {
            "source_artifact": "file-index.json",
            "results": results,
            "total_matches": total,
            "limit_applied": limit,
            "truncated": total > limit,
        }
