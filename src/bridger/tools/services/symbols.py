from bridger.models.symbol_index import SymbolIndexArtifact, SymbolRecord
from bridger.tools.errors import BridgerToolError
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.path_safety import PathSafetyService


class SymbolService:
    def __init__(
        self,
        artifact: SymbolIndexArtifact,
        paths: PathSafetyService,
        budgets: BudgetService,
    ) -> None:
        self.artifact = artifact
        self.paths = paths
        self.budgets = budgets
        self._symbols = {item.id: item for item in artifact.symbols}

    def search(self, query: str, limit: int | None = None) -> dict[str, object]:
        if not query.strip():
            raise BridgerToolError("invalid_argument", "Symbol query must not be empty")
        lowered = query.casefold()
        matches = [
            item
            for item in self.artifact.symbols
            if lowered in item.name.casefold() or lowered in item.declaration.casefold()
        ]
        matches.sort(key=lambda item: (item.path, item.line_start, item.id))
        return self._limited(matches, limit)

    def list_for_path(self, path: str, limit: int | None = None) -> dict[str, object]:
        normalized = self.paths.validate_file(path)
        matches = [item for item in self.artifact.symbols if item.path == normalized]
        matches.sort(key=lambda item: (item.line_start, item.id))
        return {"path": normalized, **self._limited(matches, limit)}

    def get(self, symbol_id: str) -> SymbolRecord:
        symbol = self._symbols.get(symbol_id)
        if symbol is None:
            raise BridgerToolError(
                "symbol_not_found", f"Symbol ID was not found: {symbol_id}"
            )
        self.paths.validate_file(symbol.path)
        return symbol

    def get_result(self, symbol_id: str) -> dict[str, object]:
        return {
            "source_artifact": "symbol-index.json",
            "symbol": self.get(symbol_id).model_dump(mode="json"),
        }

    def _limited(
        self, matches: list[SymbolRecord], requested: int | None
    ) -> dict[str, object]:
        limit = self.budgets.symbol_limit(requested)
        return {
            "source_artifact": "symbol-index.json",
            "symbols": [item.model_dump(mode="json") for item in matches[:limit]],
            "total_matches": len(matches),
            "limit_applied": limit,
            "truncated": len(matches) > limit,
        }
