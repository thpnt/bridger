from collections.abc import Iterable, Mapping

from bridger.models.symbol_index import (
    SymbolExtractionStatus,
    SymbolIndexArtifact,
    SymbolKind,
    SymbolRecord,
)
from bridger.tools.errors import BridgerToolError
from bridger.tools.services.budgets import BudgetService
from bridger.tools.services.cursors import CursorService
from bridger.tools.services.path_safety import PathSafetyService


class SymbolService:
    def __init__(
        self,
        artifact: SymbolIndexArtifact,
        paths: PathSafetyService,
        budgets: BudgetService,
        cursors: CursorService | None = None,
    ) -> None:
        self.artifact = artifact
        self.paths = paths
        self.budgets = budgets
        self.cursors = cursors or CursorService("symbol-index")
        self._symbols = {item.id: item for item in artifact.symbols}

    def search(
        self,
        query: str,
        limit: int | None = None,
        cursor: str | None = None,
        *,
        match_mode: str | None = None,
        path: str | None = None,
        path_prefix: str | None = None,
        language: str | None = None,
        kind: str | SymbolKind | None = None,
        parent_id: str | None = None,
        exported: bool | None = None,
        body_available: bool | None = None,
        extraction_status: str | SymbolExtractionStatus | None = None,
    ) -> dict[str, object]:
        if not query.strip():
            raise BridgerToolError("invalid_argument", "Symbol query must not be empty")
        if match_mode not in {
            None,
            "qualified_exact",
            "exact",
            "prefix",
            "contains",
            "fuzzy",
        }:
            raise BridgerToolError(
                "invalid_argument", f"Unsupported symbol match mode: {match_mode}"
            )
        query_folded = query.casefold()
        matches: list[tuple[int, SymbolRecord]] = []
        for symbol in self._filtered(
            path=path,
            path_prefix=path_prefix,
            language=language,
            kind=kind,
            parent_id=parent_id,
            exported=exported,
            body_available=body_available,
            extraction_status=extraction_status,
        ):
            rank = self._match_rank(symbol, query_folded, match_mode)
            if rank is not None:
                matches.append((rank, symbol))
        matches.sort(key=lambda item: (item[0], *self._canonical_key(item[1])))
        scope = {
            "query": query_folded,
            "path": path,
            "path_prefix": path_prefix,
            "kinds": kind,
            "language": language,
            "match_mode": match_mode,
            "parent_id": parent_id,
            "exported": exported,
            "body_available": body_available,
            "extraction_status": extraction_status,
        }
        return self._paginate("search_symbols", matches, limit, cursor, scope)

    def list_for_path(
        self,
        path: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        *,
        path_prefix: str | None = None,
        language: str | None = None,
        kind: str | SymbolKind | None = None,
        parent_id: str | None = None,
        exported: bool | None = None,
        body_available: bool | None = None,
        extraction_status: str | SymbolExtractionStatus | None = None,
    ) -> dict[str, object]:
        matches = self._filtered(
            path=path,
            path_prefix=path_prefix,
            language=language,
            kind=kind,
            parent_id=parent_id,
            exported=exported,
            body_available=body_available,
            extraction_status=extraction_status,
        )
        matches.sort(key=self._canonical_key)
        scope = {
            "path": path,
            "path_prefix": path_prefix,
            "language": language,
            "kind": str(kind) if kind is not None else None,
            "parent_id": parent_id,
            "exported": exported,
            "body_available": body_available,
            "extraction_status": str(extraction_status)
            if extraction_status is not None
            else None,
        }
        result = self._paginate(
            "list_symbols", [(0, symbol) for symbol in matches], limit, cursor, scope
        )
        if path is not None:
            result["path"] = self.paths.normalize(path)
        return result

    def list_symbols(
        self,
        path: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        *,
        path_prefix: str | None = None,
        language: str | None = None,
        kind: str | SymbolKind | None = None,
        parent_id: str | None = None,
        exported: bool | None = None,
        body_available: bool | None = None,
        extraction_status: str | SymbolExtractionStatus | None = None,
    ) -> dict[str, object]:
        return self.list_for_path(
            path,
            limit,
            cursor,
            path_prefix=path_prefix,
            language=language,
            kind=kind,
            parent_id=parent_id,
            exported=exported,
            body_available=body_available,
            extraction_status=extraction_status,
        )

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

    def _filtered(
        self,
        *,
        path: str | None,
        path_prefix: str | None,
        language: str | None,
        kind: str | SymbolKind | None,
        parent_id: str | None,
        exported: bool | None,
        body_available: bool | None,
        extraction_status: str | SymbolExtractionStatus | None,
    ) -> list[SymbolRecord]:
        normalized_path = self.paths.validate_file(path) if path is not None else None
        normalized_prefix = self.paths.validate_prefix(path_prefix)
        kind_value = kind.value if isinstance(kind, SymbolKind) else kind
        status_value = (
            extraction_status.value
            if isinstance(extraction_status, SymbolExtractionStatus)
            else extraction_status
        )
        allowed_kinds = {item.value for item in SymbolKind}
        if kind_value is not None and kind_value not in allowed_kinds:
            raise BridgerToolError(
                "invalid_argument", f"Unknown symbol kind: {kind_value}"
            )
        allowed_statuses = {item.value for item in SymbolExtractionStatus}
        if status_value is not None and status_value not in allowed_statuses:
            raise BridgerToolError(
                "invalid_argument", f"Unknown symbol extraction status: {status_value}"
            )
        return [
            symbol
            for symbol in self.artifact.symbols
            if (normalized_path is None or symbol.path == normalized_path)
            and (
                normalized_prefix is None
                or symbol.path == normalized_prefix
                or symbol.path.startswith(f"{normalized_prefix}/")
            )
            and (language is None or symbol.language == language)
            and (kind_value is None or symbol.kind.value == kind_value)
            and (parent_id is None or symbol.parent_id == parent_id)
            and (exported is None or symbol.exported is exported)
            and (body_available is None or symbol.body_available is body_available)
            and (status_value is None or symbol.extraction_status.value == status_value)
        ]

    @staticmethod
    def _match_rank(symbol: SymbolRecord, query: str, mode: str | None) -> int | None:
        qualified = symbol.qualified_name.casefold()
        name = symbol.name.casefold()
        declaration = symbol.declaration_preview.casefold()
        qualified_exact = qualified == query
        exact = name == query
        prefix = name.startswith(query) or qualified.startswith(query)
        contains = query in name or query in qualified or query in declaration
        fuzzy = SymbolService._is_subsequence(
            query, name
        ) or SymbolService._is_subsequence(query, qualified)
        ranks = {
            "qualified_exact": qualified_exact,
            "exact": exact,
            "prefix": prefix,
            "contains": contains,
            "fuzzy": fuzzy,
        }
        if mode is not None:
            return 0 if ranks[mode] else None
        for rank, key in enumerate(
            ("qualified_exact", "exact", "prefix", "contains", "fuzzy")
        ):
            if ranks[key]:
                return rank
        return None

    @staticmethod
    def _is_subsequence(query: str, value: str) -> bool:
        iterator = iter(value)
        return all(character in iterator for character in query)

    @staticmethod
    def _canonical_key(symbol: SymbolRecord) -> tuple[object, ...]:
        source_range = symbol.declaration_range
        if source_range.start_byte is not None:
            position: tuple[object, ...] = (0, source_range.start_byte)
        else:
            position = (1, source_range.start_line, source_range.start_column)
        return (
            symbol.path,
            *position,
            symbol.kind.value,
            symbol.qualified_name,
            symbol.id,
        )

    def _paginate(
        self,
        tool_name: str,
        matches: Iterable[tuple[int, SymbolRecord]],
        requested: int | None,
        cursor: str | None,
        scope: Mapping[str, object],
    ) -> dict[str, object]:
        ordered = list(matches)
        limit = self.budgets.symbol_limit(requested)
        start_index = 0
        if cursor is not None:
            last_key = self.cursors.decode(cursor, tool_name, scope)
            for index, (rank, symbol) in enumerate(ordered):
                if list((rank, *self._canonical_key(symbol))) == last_key:
                    start_index = index + 1
                    break
            else:
                raise BridgerToolError(
                    "invalid_cursor", "Cursor does not identify a result"
                )
        page = ordered[start_index : start_index + limit]
        has_more = start_index + len(page) < len(ordered)
        next_cursor = None
        if has_more and page:
            rank, symbol = page[-1]
            next_cursor = self.cursors.encode(
                tool_name, scope, [rank, *self._canonical_key(symbol)]
            )
        return {
            "source_artifact": "symbol-index.json",
            "symbols": [symbol.model_dump(mode="json") for _, symbol in page],
            "total_available": len(ordered),
            "returned_count": len(page),
            "total_matches": len(ordered),
            "returned_matches": len(page),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "omitted_count": len(ordered) - start_index - len(page),
            "omitted_reasons": ["result_limit"] if has_more else [],
            "warnings": [],
            "truncated": has_more,
        }
